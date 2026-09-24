import unittest
import sys
from pathlib import Path

# Add ALICE_Transcript to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
TRANSCRIPT_DIR = SCRIPT_DIR.parent
if str(TRANSCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSCRIPT_DIR))

from engines.alignment_engine import AlignmentEngine


class TestAlignmentEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AlignmentEngine()

    def test_extract_words(self):
        class DummyWord:
            def __init__(self, start, end, word):
                self.start = start
                self.end = end
                self.word = word

        class DummySeg:
            def __init__(self, words):
                self.words = words

        seg = DummySeg([
            DummyWord(0.0, 0.5, " こんにちは "),
            DummyWord(None, 0.8, "無効"),
            DummyWord(0.8, 1.2, "世界"),
            DummyWord(1.2, 1.5, "   ")
        ])

        words = self.engine.extract_words([seg])
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0], {"start": 0.0, "end": 0.5, "text": "こんにちは"})
        self.assertEqual(words[1], {"start": 0.8, "end": 1.2, "text": "世界"})

    def test_assign_speakers_direct_and_proximity(self):
        words = [
            {"start": 1.0, "end": 2.0, "text": "重なりあり"},
            {"start": 2.1, "end": 2.2, "text": "0.1秒手前の近傍"},
            {"start": 10.0, "end": 10.5, "text": "離れすぎ"},
            {"start": 3.0, "end": 3.0, "text": "ゼロ秒単語"}
        ]

        pyannote_segments = [
            {"start": 0.5, "end": 2.0, "speaker": "SPEAKER_00"},
            {"start": 2.2, "end": 4.0, "speaker": "SPEAKER_01"}
        ]

        assigned = self.engine.assign_speakers(words, pyannote_segments, tolerance_margin=0.35)

        # 1. 重なりあり -> SPEAKER_00
        self.assertEqual(assigned[0]["speaker"], "SPEAKER_00")
        # 2. 0.1秒手前（2.1-2.2は2.2直前） -> tolerance_margin(0.35)以内でSPEAKER_01に近接吸着
        self.assertEqual(assigned[1]["speaker"], "SPEAKER_01")
        # 3. 10.0-10.5はどのセグメントからも6秒以上離れている -> UNKNOWN
        self.assertEqual(assigned[2]["speaker"], "UNKNOWN")
        # 4. ゼロ秒単語 (3.0s) -> SPEAKER_01(2.2-4.0)の内包
        self.assertEqual(assigned[3]["speaker"], "SPEAKER_01")

    def test_interpolate_unknown_sandwich(self):
        assigned = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "私は"},
            {"start": 2.1, "end": 2.4, "speaker": "UNKNOWN", "text": "昨日"},
            {"start": 2.5, "end": 3.0, "speaker": "SPEAKER_00", "text": "学校へ行った"}
        ]

        interpolated = self.engine.interpolate_unknown(assigned, max_gap=1.5)
        self.assertEqual(interpolated[1]["speaker"], "SPEAKER_00")

    def test_interpolate_unknown_edges(self):
        assigned = [
            {"start": 0.8, "end": 1.0, "speaker": "UNKNOWN", "text": "えーと"},
            {"start": 1.1, "end": 2.0, "speaker": "SPEAKER_01", "text": "会議を始めます"},
            {"start": 2.1, "end": 2.3, "speaker": "UNKNOWN", "text": "ね"}
        ]

        interpolated = self.engine.interpolate_unknown(assigned)
        self.assertEqual(interpolated[0]["speaker"], "SPEAKER_01")
        self.assertEqual(interpolated[2]["speaker"], "SPEAKER_01")

    def test_interpolate_short_flip_deglitch(self):
        # SPEAKER_00の間に0.15秒の極小SPEAKER_01が誤検出で挟まるケース
        assigned = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "今日は"},
            {"start": 2.05, "end": 2.18, "speaker": "SPEAKER_01", "text": "で"},
            {"start": 2.22, "end": 3.5, "speaker": "SPEAKER_00", "text": "会議を進めます"}
        ]

        interpolated = self.engine.interpolate_unknown(assigned)
        self.assertEqual(interpolated[1]["speaker"], "SPEAKER_00")

    def test_interpolate_micro_flip_smoothing(self):
        # 0.5秒の複数トークンがPyannote誤認で別話者になったケース
        assigned = [
            {"start": 1.0, "end": 2.5, "speaker": "SPEAKER_02", "text": "この"},
            {"start": 2.55, "end": 2.8, "speaker": "SPEAKER_00", "text": "書いて"},
            {"start": 2.8, "end": 3.0, "speaker": "SPEAKER_00", "text": "くれた"},
            {"start": 3.05, "end": 4.5, "speaker": "SPEAKER_02", "text": "理由は何ですか?"}
        ]

        interpolated = self.engine.interpolate_unknown(assigned)
        # SPEAKER_00の区間 (0.45s) が SPEAKER_02 に平滑化されること
        self.assertEqual(interpolated[1]["speaker"], "SPEAKER_02")
        self.assertEqual(interpolated[2]["speaker"], "SPEAKER_02")

    def test_build_utterances_multi_speaker_dialogue(self):
        assigned = [
            {"start": 1.0, "end": 1.8, "speaker": "SPEAKER_00", "text": "合ってる?"},
            {"start": 2.0, "end": 2.4, "speaker": "SPEAKER_01", "text": "はい。"},
            {"start": 2.8, "end": 4.0, "speaker": "SPEAKER_00", "text": "じゃあ確定させます。"}
        ]

        utterances = self.engine.build_utterances(assigned)

        self.assertEqual(len(utterances), 3)
        self.assertEqual(utterances[0]["speaker"], "SPEAKER_00")
        self.assertEqual(utterances[0]["text"], "合ってる?")
        self.assertEqual(utterances[1]["speaker"], "SPEAKER_01")
        self.assertEqual(utterances[1]["text"], "はい。")
        self.assertEqual(utterances[2]["speaker"], "SPEAKER_00")
        self.assertEqual(utterances[2]["text"], "じゃあ確定させます。")

    def test_build_utterances_pause_and_punctuation_split(self):
        assigned = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "第一問です。"},
            # 0.5s pause after terminal punct "。" -> should split
            {"start": 2.5, "end": 3.5, "speaker": "SPEAKER_00", "text": "第二問です。"},
            # 1.2s pause (>= PAUSE_THRESHOLD 1.0s) -> should split
            {"start": 4.7, "end": 5.5, "speaker": "SPEAKER_00", "text": "第三問です"}
        ]

        utterances = self.engine.build_utterances(assigned, pause_threshold=1.0)
        self.assertEqual(len(utterances), 3)

    def test_build_utterances_grammatical_boundary_protection(self):
        # 文末記号なしで語尾が別話者に切断されたケースの救済
        assigned = [
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "これ何を言"},
            {"start": 2.1, "end": 2.4, "speaker": "SPEAKER_01", "text": "ってるの?"},
        ]
        utterances = self.engine.build_utterances(assigned)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["text"], "これ何を言ってるの?")

    def test_build_utterances_english_and_japanese_spacing(self):
        assigned = [
            {"start": 1.0, "end": 1.5, "speaker": "SPEAKER_00", "text": "Project"},
            {"start": 1.5, "end": 2.0, "speaker": "SPEAKER_00", "text": "ALICE"},
            {"start": 2.0, "end": 2.5, "speaker": "SPEAKER_00", "text": "の"},
            {"start": 2.5, "end": 3.0, "speaker": "SPEAKER_00", "text": "開発"}
        ]

        utterances = self.engine.build_utterances(assigned)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["text"], "Project ALICEの開発")


if __name__ == "__main__":
    unittest.main()
