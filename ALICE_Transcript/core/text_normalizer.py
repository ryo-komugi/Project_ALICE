import re
from core.utils import overlap_length


class TextNormalizer:
    """発話テキストの意味を変更しない範囲で正規化・スタッター除去・クレンジングを行うクラス"""

    # 4文字〜25文字の同一フレーズ連続重複（Whisperの反復幻覚）を検知する正規表現
    PHRASE_REPEAT_PATTERN = re.compile(r"(.{4,25}?)\1+")

    # 3回以上連続する同一文字（「あああああ」「、、、、」等）を2回に短縮する正規表現
    CHAR_REPEAT_PATTERN = re.compile(r"(.)\1{2,}")

    # 無音区間でWhisperが出力しやすい典型的な単独ハルシネーション
    HALLUCINATION_STANDALONE_PATTERN = re.compile(
        r"^(?:BGM|ＢＧＭ|音楽|拍手|字幕|ご視聴ありがとうございました[。！!]?|チャンネル登録.*)$",
        re.IGNORECASE,
    )

    # 代表的なフィラー重複パターン
    FILLER_REPEAT_PATTERNS = [
        (re.compile(r"(あの[、\s]?){2,}"), "あの、"),
        (re.compile(r"(その[、\s]?){2,}"), "その、"),
        (re.compile(r"(えーと[、\s]?){2,}"), "えーと、"),
        (re.compile(r"(ええと[、\s]?){2,}"), "ええと、"),
        (re.compile(r"(まあ[、\s]?){2,}"), "まあ、"),
    ]

    def remove_duplicate_phrase(self, text: str) -> str:
        """フレーズ単位の反復や過剰な文字重複を安全に除去する。
        ※「ここまで」「いろいろ」「それぞれ」「だんだん」「少々」等の自然な日本語畳語は保護する。
        """
        if not text:
            return ""

        # 1. 代表的なフィラー重複の整理
        for pat, repl in self.FILLER_REPEAT_PATTERNS:
            text = pat.sub(repl, text)

        # 2. 4文字以上のフレーズ即時反復除去（Whisperハルシネーション対策）
        text = self.PHRASE_REPEAT_PATTERN.sub(r"\1", text)

        # 3. 3文字以上の同一文字連続を2文字へ制限
        text = self.CHAR_REPEAT_PATTERN.sub(r"\1\1", text)

        return text

    # 互換性エイリアス
    def remove_duplicate_phraze(self, text: str) -> str:
        return self.remove_duplicate_phrase(text)

    def remove_duplicate_prefix(self, text: str) -> str:
        return self.remove_duplicate_phrase(text)

    def normalize_overlap(self, results: list) -> list:
        for r in results:
            r["text"] = self.remove_duplicate_phrase(r.get("text", ""))
        return results

    def normalize_segment_overlap(self, results: list, min_overlap: int = 4) -> list:
        """隣接セグメント間の重複フレーズを除去する。
        偶然の一致（1〜3文字）による語尾切断を防ぐため、4文字以上の重複のみ対象とする。
        """
        if len(results) < 2:
            return results

        for i in range(len(results) - 1):
            current = results[i]
            nxt = results[i + 1]
            ov = overlap_length(current["text"], nxt["text"])
            if ov >= min_overlap:
                current["text"] = current["text"][:-ov]

        return results

    def normalize_whitespace(self, results: list) -> list:
        for r in results:
            text = r.get("text", "")
            text = re.sub(r"[\t\r\n]+", " ", text)
            text = text.replace("\u3000", " ")
            text = re.sub(r" +", " ", text)
            r["text"] = text.strip()
        return results

    def normalize_symbols(self, results: list) -> list:
        for r in results:
            text = r.get("text", "")
            text = text.replace("～", "〜")
            text = re.sub(r"\s+([,.!?])", r"\1", text)
            text = re.sub(r"([。、！？!?]){2,}", r"\1", text)
            r["text"] = text.strip()
        return results

    def normalize_segment_deduplication(self, results: list) -> list:
        """同一話者による隣接セグメント間の単語スタッター（連呼）やフレーズの完全重複を統合する。"""
        if len(results) < 2:
            return results

        merged = []
        for r in results:
            text = r.get("text", "").strip()
            if not text:
                continue
            if not merged:
                merged.append(r)
                continue

            prev = merged[-1]
            prev_text = prev.get("text", "").strip()
            same_speaker = prev.get("speaker") == r.get("speaker")

            # 同一話者での完全一致単語連呼（例: 「本当に」「本当に」）
            if same_speaker and text == prev_text:
                prev["end"] = r.get("end", prev.get("end"))
                continue

            # 同一話者での6文字以上のフレーズ完全重複（例: 「気になるところがあるんだけれども」）
            if same_speaker and len(text) >= 6 and text in prev_text:
                prev["end"] = r.get("end", prev.get("end"))
                continue

            merged.append(r)

        return merged

    def normalize(self, results: list) -> list:
        results = self.normalize_overlap(results)
        results = self.normalize_segment_overlap(results)
        results = self.normalize_segment_deduplication(results)
        results = self.normalize_whitespace(results)
        results = self.normalize_symbols(results)
        # 空発話および無音ハルシネーション単独セグメントの除外
        filtered = []
        for r in results:
            txt = r.get("text", "").strip()
            if not txt:
                continue
            if self.HALLUCINATION_STANDALONE_PATTERN.match(txt):
                continue
            filtered.append(r)
        return filtered

    def run(self, job):
        job.results = self.normalize(job.results)
