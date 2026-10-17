"""
Workspace I/O utility for ALICE_Minute.
Handles reading transcript.json, summary analysis.json, templates, and writing minutes artifacts.
"""
from datetime import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import config
from core.models import MinuteAnalysisResult

logger = logging.getLogger(__name__)


class WorkspaceIO:
    @staticmethod
    def get_transcript_path(workspace_dir: Path | str) -> Path:
        return Path(workspace_dir) / "transcript" / "transcript.json"

    @staticmethod
    def get_summary_analysis_path(workspace_dir: Path | str) -> Path:
        return Path(workspace_dir) / "summary" / "analysis.json"

    @staticmethod
    def get_minutes_dir(workspace_dir: Path | str) -> Path:
        minutes_dir = Path(workspace_dir) / "minutes"
        minutes_dir.mkdir(parents=True, exist_ok=True)
        return minutes_dir

    @staticmethod
    def load_transcript(workspace_dir: Path | str) -> List[Dict[str, Any]]:
        path = WorkspaceIO.get_transcript_path(workspace_dir)
        if not path.exists():
            raise FileNotFoundError(f"Transcript file not found: {path}")

        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        if isinstance(data, dict) and "segments" in data:
            return data["segments"]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Unexpected transcript format in {path}")

    @staticmethod
    def load_summary_analysis(workspace_dir: Path | str) -> Optional[Dict[str, Any]]:
        """ALICE_Summary が生成した中間構造化データ (summary/analysis.json) を読み込む（存在する場合）"""
        path = WorkspaceIO.get_summary_analysis_path(workspace_dir)
        if not path.exists():
            logger.info(f"[WorkspaceIO] No summary/analysis.json found at {path}. Will fallback to transcript-only analysis.")
            return None

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            logger.info(f"[WorkspaceIO] Loaded summary analysis from {path}")
            return data
        except Exception as e:
            logger.warning(f"[WorkspaceIO] Failed to load summary analysis from {path}: {e}")
            return None

    @staticmethod
    def format_time(seconds: float) -> str:
        """秒数を [MM:SS] 形式（累積分:秒、ALICE_Summary と完全統一）に変換する"""
        total_sec = max(0, int(seconds))
        minutes, secs = divmod(total_sec, 60)
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def normalize_timestamp_str(ts: Optional[str]) -> str:
        """'01:10:01' のような HH:MM:SS 表記があれば累積 '70:01' (MM:SS) に統一する"""
        if not ts:
            return ""
        s = str(ts).strip()
        m = re.match(r"^(\d+):(\d{2}):(\d{2})$", s)
        if m:
            total_min = int(m.group(1)) * 60 + int(m.group(2))
            return f"{total_min:02d}:{m.group(3)}"
        return s

    @classmethod
    def format_transcript_for_prompt(cls, segments: List[Dict[str, Any]]) -> str:
        """セグメント一覧をLLM入力用の時系列発言フォーマットに変換（累積 MM:SS に統一）"""
        lines = []
        for seg in segments:
            start_sec = seg.get("start", 0.0)
            speaker = seg.get("speaker", "UNKNOWN")
            text = seg.get("text", "").strip()
            if not text:
                continue

            time_str = cls.format_time(start_sec)
            lines.append(f"[{time_str}] {speaker}: {text}")

        return "\n".join(lines)

    @staticmethod
    def summarize_speakers(segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Transcript 内の全話者ラベルと発話回数・発話秒数・最初の発話例を集計する"""
        stats: Dict[str, Dict[str, Any]] = {}
        for s in segments:
            text = s.get("text", "").strip()
            if not text:
                continue
            sp = s.get("speaker", "UNKNOWN")
            dur = max(0.0, float(s.get("end", 0.0)) - float(s.get("start", 0.0)))
            if sp not in stats:
                stats[sp] = {"count": 0, "duration": 0.0, "sample": text[:40]}
            stats[sp]["count"] += 1
            stats[sp]["duration"] += dur
        return stats

    @staticmethod
    def load_template(template_name: str) -> str:
        """指定されたテンプレート名のMarkdownファイルを読み込む"""
        templates_dir = config.templates_dir
        tpl_path = templates_dir / f"{template_name}.md"
        if not tpl_path.exists():
            # フォールバック: standard.md
            fallback_path = templates_dir / "standard.md"
            if fallback_path.exists():
                logger.warning(
                    f"[WorkspaceIO] Template '{template_name}' not found at {tpl_path}. "
                    f"Falling back to 'standard.md'."
                )
                tpl_path = fallback_path
            else:
                raise FileNotFoundError(f"Template not found: {tpl_path}")

        with open(tpl_path, "r", encoding="utf-8-sig") as f:
            return f.read().strip()

    @staticmethod
    def save_stage1_analysis(workspace_dir: Path | str, analysis: MinuteAnalysisResult) -> Path:
        minutes_dir = WorkspaceIO.get_minutes_dir(workspace_dir)
        out_path = minutes_dir / "analysis.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(
                analysis.model_dump_json(indent=2)
                if hasattr(analysis, "model_dump_json")
                else json.dumps(analysis.dict(), ensure_ascii=False, indent=2)
            )
        return out_path

    @staticmethod
    def load_stage1_analysis(workspace_dir: Path | str) -> MinuteAnalysisResult:
        minutes_dir = WorkspaceIO.get_minutes_dir(workspace_dir)
        in_path = minutes_dir / "analysis.json"
        if not in_path.exists():
            raise FileNotFoundError(f"Analysis file not found: {in_path}")

        with open(in_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        return (
            MinuteAnalysisResult.model_validate(data)
            if hasattr(MinuteAnalysisResult, "model_validate")
            else MinuteAnalysisResult.parse_obj(data)
        )

    @staticmethod
    def markdown_to_plain_text(md_text: str) -> str:
        """Markdown記法をスマホ・LINE上で読みやすいプレーンテキスト記号に変換"""
        text = md_text

        # 見出し
        text = re.sub(r"^# (.+)$", r"■ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^## (.+)$", r"◆ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^### (.+)$", r"【\1】", text, flags=re.MULTILINE)
        text = re.sub(r"^#### (.+)$", r"● \1", text, flags=re.MULTILINE)

        # 水平線
        text = re.sub(r"^---+", r"────────────────────", text, flags=re.MULTILINE)

        # チェックボックスとリスト記号（インデント保持、インライン装飾除去より先に実行）
        text = re.sub(r"^(\s*)- \[ \] (.+)$", r"\1□ \2", text, flags=re.MULTILINE)
        text = re.sub(r"^(\s*)- \[[xX]\] (.+)$", r"\1■ \2", text, flags=re.MULTILINE)
        text = re.sub(r"^(\s*)[-*•] (.+)$", r"\1・\2", text, flags=re.MULTILINE)

        # 太字・装飾
        text = re.sub(r"\*\*([^\n*]+?)\*\*", r"\1", text)
        text = re.sub(r"__([^\n_]+?)__", r"\1", text)
        text = re.sub(r"`([^\n`]+?)`", r"\1", text)

        # 余分な改行の連続を整理
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def save_stage2_artifacts(
        workspace_dir: Path | str,
        markdown_text: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Path]:
        minutes_dir = WorkspaceIO.get_minutes_dir(workspace_dir)

        # 1. minutes.md
        md_path = minutes_dir / "minutes.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_text.strip() + "\n")

        # 2. minutes.txt
        txt_path = minutes_dir / "minutes.txt"
        plain_text = WorkspaceIO.markdown_to_plain_text(markdown_text)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(plain_text + "\n")

        # 3. metadata.json
        meta_path = minutes_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return {
            "minutes_md": md_path,
            "minutes_txt": txt_path,
            "metadata_json": meta_path,
        }

    @staticmethod
    def save_failure_metadata(
        workspace_dir: Path | str,
        error_message: str,
        target_model: str = "",
        template_name: str = "standard",
    ) -> Path:
        """パイプライン異常終了時に metadata.json に失敗情報を記録"""
        minutes_dir = WorkspaceIO.get_minutes_dir(workspace_dir)
        meta_path = minutes_dir / "metadata.json"
        failure_data = {
            "module": "ALICE_Minute",
            "version": "0.2.0",
            "status": "FAILED",
            "model": target_model,
            "template": template_name,
            "created_at": datetime.now().isoformat(),
            "is_complete": False,
            "error": error_message,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(failure_data, f, ensure_ascii=False, indent=2)
        return meta_path
