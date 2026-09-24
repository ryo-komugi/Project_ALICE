import unittest
import sys
from pathlib import Path

# Add ALICE_Transcript to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
TRANSCRIPT_DIR = SCRIPT_DIR.parent
if str(TRANSCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSCRIPT_DIR))

from core.text_normalizer import TextNormalizer


class TestTextNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = TextNormalizer()

    def test_protect_japanese_reduplication(self):
        """「ここまで」「いろいろ」「それぞれ」「だんだん」「少々」等の自然な日本語が削られないことを確認"""
        words_to_protect = [
            "ここまでOKかな?",
            "いろいろ思うところがある",
            "それぞれ確認をお願いします",
            "だんだん良くなってきました",
            "少々お待ちください",
            "ここに行きます",
            "人々が集まる",
            "時々見かけます",
            "ますます元気です",
            "どんどん進めてください",
            "たまたま会いました",
            "もともとそうでした"
        ]

        for w in words_to_protect:
            res = self.normalizer.remove_duplicate_phrase(w)
            self.assertEqual(res, w, f"Expected '{w}' to be preserved, but got '{res}'")

    def test_remove_whisper_hallucination_repeats(self):
        """Whisperの4文字以上のフレーズ連続重複およびフィラー重複が除去されることを確認"""
        # フレーズ重複
        text1 = "本日の会議を始めます。本日の会議を始めます。"
        self.assertEqual(self.normalizer.remove_duplicate_phrase(text1), "本日の会議を始めます。")

        # フィラー重複
        text2 = "あの、あの、ちょっと質問です"
        self.assertEqual(self.normalizer.remove_duplicate_phrase(text2), "あの、ちょっと質問です")

        text3 = "えーと、えーと、次の項目です"
        self.assertEqual(self.normalizer.remove_duplicate_phrase(text3), "えーと、次の項目です")

    def test_safe_segment_overlap(self):
        """1〜3文字の偶然の一致（「た」「す」等）で語尾が削られず、4文字以上の実質的重複のみ削られることを確認"""
        # 1文字一致: 「〜まして」「てきとう...」 -> 削られないこと
        results1 = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "ちゃんと話をしまして"},
            {"start": 2.1, "end": 3.0, "speaker": "SPEAKER_01", "text": "てきとうな返事は困ります"}
        ]
        norm1 = self.normalizer.normalize_segment_overlap(results1)
        self.assertEqual(norm1[0]["text"], "ちゃんと話をしまして")

        # 5文字重複: 「会議を始めます」が前行末尾と次行先頭で重複
        results2 = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "それでは会議を始めます"},
            {"start": 2.1, "end": 3.0, "speaker": "SPEAKER_00", "text": "会議を始めます本日のアジェンダです"}
        ]
        norm2 = self.normalizer.normalize_segment_overlap(results2)
        self.assertEqual(norm2[0]["text"], "それでは")

    def test_filter_empty_utterances(self):
        results = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "有効な発話"},
            {"start": 2.1, "end": 2.5, "speaker": "SPEAKER_00", "text": "   "},
            {"start": 2.6, "end": 3.0, "speaker": "SPEAKER_00", "text": "！！"},  # 記号のみ
        ]

        normalized = self.normalizer.normalize(results)
        self.assertGreaterEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["text"], "有効な発話")
        self.assertTrue(all(r["text"].strip() for r in normalized))


if __name__ == "__main__":
    unittest.main()

