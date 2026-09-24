import json
import re
from pathlib import Path
from typing import List, Dict, Any


class WorkspaceIO:
    """Workspace の入出力および検証を担当するクラス"""

    @staticmethod
    def get_summary_dir(workspace_path: Path) -> Path:
        summary_dir = workspace_path / "summary"
        summary_dir.mkdir(parents=True, exist_ok=True)
        return summary_dir

    @staticmethod
    def load_transcript(workspace_path: Path) -> List[Dict[str, Any]]:
        transcript_path = workspace_path / "transcript" / "transcript.json"
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript JSON does not exist: {transcript_path}")

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse transcript.json: {e}")

        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("transcript.json is empty or not a valid list")

        return data

    @staticmethod
    def format_transcript_for_prompt(segments: List[Dict[str, Any]]) -> str:
        """Transcript セグメントをプロンプト入力用のテキストに変換する"""
        lines = []
        for s in segments:
            speaker = s.get("speaker", "UNKNOWN")
            text = s.get("text", "").strip()
            if not text:
                continue
            start = s.get("start", 0.0)
            end = s.get("end", 0.0)
            # 時間表示 [mm:ss]
            start_min, start_sec = divmod(int(start), 60)
            lines.append(f"[{start_min:02d}:{start_sec:02d}] {speaker}: {text}")
        return "\n".join(lines)

    @classmethod
    def load_analysis_json(cls, workspace_path: Path) -> Dict[str, Any]:
        analysis_path = cls.get_summary_dir(workspace_path) / "analysis.json"
        if not analysis_path.exists():
            raise FileNotFoundError(f"analysis.json not found: {analysis_path}")
        with open(analysis_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def save_analysis_json(cls, workspace_path: Path, data: Dict[str, Any]) -> Path:
        target_path = cls.get_summary_dir(workspace_path) / "analysis.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return target_path

    @staticmethod
    def calculate_dynamic_num_ctx(formatted_text: str, base_margin: int = 4096) -> int:
        """入力テキスト量から必要な Ollama num_ctx を安全側に自動算出する"""
        # 日本語 1 文字 ≒ 1.5 トークン換算 + システム/指示プロンプト余裕
        estimated_tokens = int(len(formatted_text) * 1.5) + base_margin
        if estimated_tokens <= 28000:
            return 32768   # ~60分程度（標準）
        elif estimated_tokens <= 44000:
            return 49152   # 60分〜100分程度
        else:
            return 65536   # 100分〜120分超（最大 64k）

    @classmethod
    def save_draft_summary(cls, workspace_path: Path, draft_md: str) -> Path:
        summary_dir = cls.get_summary_dir(workspace_path)
        draft_path = summary_dir / "draft_summary.md"
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft_md.strip() + "\n")
        return draft_path

    @classmethod
    def load_draft_summary(cls, workspace_path: Path) -> str:
        draft_path = cls.get_summary_dir(workspace_path) / "draft_summary.md"
        if not draft_path.exists():
            # draft_summary.md がない場合は summary.md があればそれを代替利用
            summary_md_path = cls.get_summary_dir(workspace_path) / "summary.md"
            if summary_md_path.exists():
                draft_path = summary_md_path
            else:
                raise FileNotFoundError(f"Neither draft_summary.md nor summary.md found in {workspace_path}")
        with open(draft_path, "r", encoding="utf-8") as f:
            return f.read()

    @classmethod
    def save_consistency_report(cls, workspace_path: Path, report_md: str) -> Path:
        summary_dir = cls.get_summary_dir(workspace_path)
        report_path = summary_dir / "consistency_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md.strip() + "\n")
        return report_path

    @classmethod
    def save_summary_documents(cls, workspace_path: Path, summary_md: str, summary_txt: str = "") -> tuple[Path, Path]:
        summary_dir = cls.get_summary_dir(workspace_path)
        md_path = summary_dir / "summary.md"
        txt_path = summary_dir / "summary.txt"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(summary_md.strip() + "\n")

        # txt が渡されなかった場合は Markdown から変換
        if not summary_txt:
            summary_txt = cls.markdown_to_plain_text(summary_md)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(summary_txt.strip() + "\n")

        return md_path, txt_path

    @classmethod
    def read_prompt_file(cls, base_path_no_ext: Path) -> str:
        """指定されたパスの .md ファイルを優先して読み込み、無ければ .txt をフォールバック読み込みする"""
        md_path = base_path_no_ext.with_suffix(".md")
        if md_path.exists():
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()

        txt_path = base_path_no_ext.with_suffix(".txt")
        if txt_path.exists():
            with open(txt_path, "r", encoding="utf-8") as f:
                return f.read()

        # そのままのパスで存在する場合
        if base_path_no_ext.exists():
            with open(base_path_no_ext, "r", encoding="utf-8") as f:
                return f.read()

        raise FileNotFoundError(f"Neither .md nor .txt prompt template found for: {base_path_no_ext}")

    @classmethod
    def save_commentary_documents(cls, workspace_path: Path, commentary_md: str, commentary_txt: str = "") -> tuple[Path, Path]:
        """解説・講評ドキュメント（commentary.md, commentary.txt）を保存する"""
        summary_dir = cls.get_summary_dir(workspace_path)
        md_path = summary_dir / "commentary.md"
        txt_path = summary_dir / "commentary.txt"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(commentary_md.strip() + "\n")

        if not commentary_txt:
            commentary_txt = cls.markdown_to_plain_text(commentary_md)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(commentary_txt.strip() + "\n")

        return md_path, txt_path

    @classmethod
    def save_metadata(cls, workspace_path: Path, metadata: Dict[str, Any]) -> Path:
        target_path = cls.get_summary_dir(workspace_path) / "metadata.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return target_path

    @staticmethod
    def markdown_to_plain_text(md_text: str) -> str:
        """Markdown 記号を適度に整形し、人間がプレーンテキストとして読みやすい文章に変換する"""
        text = md_text

        # 見出し # -> ■、## -> ◆、### -> ・
        text = re.sub(r"^#\s+(.*?)$", r"■ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^##\s+(.*?)$", r"◆ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^###\s+(.*?)$", r"・ \1", text, flags=re.MULTILINE)

        # 太字 **text** または *text* -> text
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)

        # 箇条書きの - を ・ またはインデントに統一
        text = re.sub(r"^-\s+", r"・", text, flags=re.MULTILINE)

        # コードブロックの ``` を除去
        text = re.sub(r"```[a-zA-Z]*\n?", "", text)

        # 連続空行を整理
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
