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
            with open(transcript_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse transcript.json: {e}")

        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("transcript.json is empty or not a valid list")

        return data

    @staticmethod
    def format_time(seconds: float) -> str:
        """秒数を [MM:SS] 形式（累積分:秒）に変換する"""
        total_sec = max(0, int(seconds))
        minutes, secs = divmod(total_sec, 60)
        return f"{minutes:02d}:{secs:02d}"

    @classmethod
    def format_transcript_for_prompt(cls, segments: List[Dict[str, Any]]) -> str:
        """Transcript セグメントをプロンプト入力用のテキストに変換する"""
        lines = []
        for s in segments:
            speaker = s.get("speaker", "UNKNOWN")
            text = s.get("text", "").strip()
            if not text:
                continue
            start = s.get("start", 0.0)
            lines.append(f"[{cls.format_time(start)}] {speaker}: {text}")
        return "\n".join(lines)

    @staticmethod
    def summarize_speakers(segments: List[Dict[str, Any]]) -> str:
        """Transcript 内の全話者ラベルと発話回数・発話秒数を集計し、話者漏れを防ぐ補助情報を生成する"""
        stats: Dict[str, Dict[str, float]] = {}
        for s in segments:
            text = s.get("text", "").strip()
            if not text:
                continue
            sp = s.get("speaker", "UNKNOWN")
            dur = max(0.0, float(s.get("end", 0.0)) - float(s.get("start", 0.0)))
            if sp not in stats:
                stats[sp] = {"count": 0, "duration": 0.0}
            stats[sp]["count"] += 1
            stats[sp]["duration"] += dur

        if not stats:
            return ""
        lines = []
        for sp in sorted(stats.keys()):
            cnt = int(stats[sp]["count"])
            dur = stats[sp]["duration"]
            lines.append(f"- {sp}: 発話 {cnt}回（計 {dur:.1f}秒）")
        return "\n".join(lines)

    @classmethod
    def load_analysis_json(cls, workspace_path: Path) -> Dict[str, Any]:
        analysis_path = cls.get_summary_dir(workspace_path) / "analysis.json"
        if not analysis_path.exists():
            raise FileNotFoundError(f"analysis.json not found: {analysis_path}")
        with open(analysis_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    @classmethod
    def save_analysis_json(cls, workspace_path: Path, data: Dict[str, Any]) -> Path:
        target_path = cls.get_summary_dir(workspace_path) / "analysis.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return target_path

    @staticmethod
    def calculate_dynamic_num_ctx(formatted_text: str, base_margin: int = 6144) -> int:
        """入力テキスト量から必要な Ollama num_ctx を安全側に自動算出する"""
        # 日本語 1 文字 ≒ 1.5 トークン換算 + システム/指示プロンプトおよび出力トークン余裕
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
        with open(draft_path, "r", encoding="utf-8-sig") as f:
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
        """指定されたパスの .md ファイルを優先して読み込み、無ければ .txt をフォールバック読み込みする（UTF-8 BOM除去対応）"""
        md_path = base_path_no_ext.with_suffix(".md")
        if md_path.exists():
            with open(md_path, "r", encoding="utf-8-sig") as f:
                return f.read()

        txt_path = base_path_no_ext.with_suffix(".txt")
        if txt_path.exists():
            with open(txt_path, "r", encoding="utf-8-sig") as f:
                return f.read()

        # そのままのパスで存在する場合
        if base_path_no_ext.exists():
            with open(base_path_no_ext, "r", encoding="utf-8-sig") as f:
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
    def clean_markdown_output(md_text: str) -> str:
        """LLM出力のMarkdownから不要なコードブロック囲みや会話的前置き、未置換の '### N. ' 等を整形する"""
        text = md_text.strip()

        # コードブロックで囲まれている場合は剥がす
        if text.startswith("```markdown") and text.endswith("```"):
            text = text[len("```markdown") : -3].strip()
        elif text.startswith("```md") and text.endswith("```"):
            text = text[len("```md") : -3].strip()
        elif text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()

        # 冒頭の会話的な前置き（「承知いたしました」「以下に〜を作成します」等）を除去
        lines = text.splitlines()
        while lines:
            first = lines[0].strip()
            if not first or first == "---":
                lines.pop(0)
                continue
            if re.match(r"^(承知|かしこまり|了解|はい、|以下に|提供された|ご提示|分析データに基づき)", first):
                lines.pop(0)
                continue
            break
        text = "\n".join(lines).strip()

        # 未置換の「### N. 」または「## N. 」を連番に置換
        counter = 0
        out_lines = []
        for line in text.splitlines():
            m = re.match(r"^(#{1,4}\s*)N\.\s+(.*)$", line)
            if m:
                counter += 1
                out_lines.append(f"{m.group(1)}{counter}. {m.group(2)}")
            else:
                m_num = re.match(r"^#{1,4}\s*(\d+)\.\s+", line)
                if m_num:
                    counter = int(m_num.group(1))
                out_lines.append(line)
        return "\n".join(out_lines).strip()

    @staticmethod
    def markdown_to_plain_text(md_text: str) -> str:
        """Markdown 記号を適度に整形し、人間がプレーンテキストとして読みやすい文章に変換する"""
        text = md_text

        # コードブロックの ``` を除去
        text = re.sub(r"```[a-zA-Z]*\n?", "", text)

        # 水平線 --- や *** を除去
        text = re.sub(r"^\s*([-*_]){3,}\s*$", "", text, flags=re.MULTILINE)

        # 見出し # -> ■、## -> ◆、### -> ▸、#### -> ・
        text = re.sub(r"^#\s+(.*?)$", r"■ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^##\s+(.*?)$", r"◆ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^###\s+(.*?)$", r"▸ \1", text, flags=re.MULTILINE)
        text = re.sub(r"^#{4,}\s+(.*?)$", r"・ \1", text, flags=re.MULTILINE)

        # チェックボックス - [ ] / - [x] を変換
        text = re.sub(r"^(\s*)[-*•]\s+\[[ xX]\]\s+", r"\1・", text, flags=re.MULTILINE)

        # 箇条書きの -, *, •, o をインデント保持で ・ に統一（※インライン *...* 除去より先に実行）
        text = re.sub(r"^(\s*)[-*•o]\s+", r"\1・", text, flags=re.MULTILINE)

        # 太字 **text** または インライン斜体 *text* -> text（同一行内のみ）
        text = re.sub(r"\*\*([^\n*]+?)\*\*", r"\1", text)
        text = re.sub(r"(?<!\*)\*([^\n*]+?)\*(?!\*)", r"\1", text)

        # 連続空行を整理
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
