# ===========================
# Centralized System Paths
# ===========================
DATA_DIR = "/data"
RUNTIME_DIR = f"{DATA_DIR}/runtime"

# ===========================
# Whisper
# ===========================
# 高精度・語彙認識・自然な句読点付与を最優先し、large-v3 を標準採用
# 超高速処理を最優先する場合は CLI 引数 --model またはここで "deepdml/faster-whisper-large-v3-turbo-ct2" を指定可能
MODEL_NAME = "large-v3"
"""
Whisperモデル一覧:
tiny, base, small, medium, large, large-v2, large-v3, deepdml/faster-whisper-large-v3-turbo-ct2
"""

# ===========================
# pyannote
# ===========================
import os
from pathlib import Path
TRANSCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(TRANSCRIPT_DIR.parent)))
PYANNOTE_PYTHON = str(PROJECT_ROOT / "myenv" / "pyannote_env" / "bin" / "python")

# ===========================
# Supported audio fileType
# ===========================
SUPPORTED_AUDIO_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".wav",
)

# ===========================
# Debug
# ===========================
DEBUG_EXPORT = False

# ===========================
# Alignment Engine Parameters
# ===========================
# PyannoteとWhisperの微小なタイムラグを吸収する近傍探索マージン (秒)
TOLERANCE_MARGIN = 0.35

# 同一話者内で発話を分割するポーズ（無音）閾値 (秒)
PAUSE_THRESHOLD = 1.0

# 1発話の最大継続時間（長大発話の防止） (秒)
MAX_UTTERANCE_DURATION = 25.0

# UNKNOWN補間を行う最大時間ギャップ (秒)
INTERPOLATE_MAX_GAP = 1.5

# 同一話者に挟まれた微小な異話者フリップ（Pyannoteのオーバーラップ誤認等）を平滑化する閾値 (秒)
MICRO_FLIP_MAX_DURATION = 0.8

# 同一話者の近接発話を自然に1つに結合する最大ギャップ (秒)
MERGE_SAME_SPEAKER_GAP = 1.2

# ===========================
# Audio Preprocessing
# ===========================
# 音声変換時の音響前処理パイプライン設定 (FFmpegネイティブ)
# 目的: 空調・反響ノイズ低減とEBU R128ラウドネス均一化により、Pyannoteの過剰クラスタリング（ゴースト話者）を抑制
AUDIO_NORMALIZE = True
AUDIO_PREPROCESSING_ENABLED = True
AUDIO_FILTER_HIGHPASS = 80       # 空調・机振動・低周波ノイズ除去 (Hz)
AUDIO_FILTER_LOWPASS = 7500      # 超高域ヒスノイズ・高周波歪み除去 (Hz)
AUDIO_FILTER_DENOISE_NF = -25    # FFTスペクトルノイズ低減フロア (dB)
AUDIO_LOUDNORM_I = -16.0         # 統合ラウドネス目標値 (LUFS, EBU R128標準)
AUDIO_LOUDNORM_TP = -1.5         # トゥルーピーク上限 (dBTP)
AUDIO_LOUDNORM_LRA = 11.0        # ラウドネスレンジ目標 (LU)

# ===========================
# Whisper Parameters
# ===========================
# Silero VAD による非音声区間フィルタリング
WHISPER_VAD_FILTER = True

# Silero VAD による頭切れ・語尾切れを防ぐためのパディング (ミリ秒)
WHISPER_VAD_SPEECH_PAD_MS = 300

# ノイズ環境での反復幻覚ループ抑止
WHISPER_CONDITION_ON_PREV = False

# 日本語句読点生成と汎用的な会話トーンを促す初期プロンプト
WHISPER_INITIAL_PROMPT = "こんにちは。本日の会議・面談・インタビューを始めます。議題の進捗確認、連絡事項、質疑応答などについて話し合います。よろしくお願いします。"

# ビームサーチ幅
WHISPER_BEAM_SIZE = 5

# 反復ペナルティ
WHISPER_REPETITION_PENALTY = 1.0
