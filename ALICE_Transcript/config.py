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
PYANNOTE_MAX_SPEAKERS = 8

# ===========================
# Supported audio fileType
# ===========================
SUPPORTED_AUDIO_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".flac",
    ".ogg",
)

# ===========================
# Debug
# ===========================
DEBUG_EXPORT = False

# ===========================
# Alignment Engine Parameters
# ===========================
TOLERANCE_MARGIN = 0.35
PAUSE_THRESHOLD = 1.0
MAX_UTTERANCE_DURATION = 25.0
INTERPOLATE_MAX_GAP = 1.5
MICRO_FLIP_MAX_DURATION = 0.8
MERGE_SAME_SPEAKER_GAP = 1.2

# ===========================
# Audio Preprocessing & Adaptive Gain (可変・適応型音響前処理)
# ===========================
AUDIO_NORMALIZE = True
AUDIO_PREPROCESSING_ENABLED = True
AUDIO_FILTER_HIGHPASS = 100      # 空調・机振動・低周波ノイズ除去 (Hz)
AUDIO_FILTER_LOWPASS = 7600      # 超高域ヒスノイズ除去・子音帯域保持 (Hz)
AUDIO_FILTER_DENOISE_NF = None   # FFTスペクトル減算はデフォルト無効

# アダプティブ連続可変ゲイン設定
AUDIO_ADAPTIVE_PREPROCESSING = True  # 音声ごとの音量・ステレオ相関に応じた完全自動可変
AUDIO_ADAPTIVE_TARGET_RMS = -22.0    # Whisperの最適動作目標会話音量 (dBFS)
AUDIO_DYNAUDNORM_M_MIN = 3.0         # 通常大音量時の下限m値（過剰増幅防止）
AUDIO_DYNAUDNORM_M_MAX = 20.0        # 極小音量ささやき声時の上限m値（限界救済）

# 手動上書き用設定 (None の場合は自動判定)
AUDIO_MANUAL_DYNAUDNORM_M = None     # 数値指定時は自動計算を上書きして固定
AUDIO_MANUAL_CHANNEL_MODE = None     # "auto", "mono", "ch1", "ch2", "mix" で手動指定可能

AUDIO_LOUDNORM_I = None          # 明示指定時のみEBU R128 loudnormを使用
AUDIO_LOUDNORM_TP = -1.5         # トゥルーピーク上限 (dBTP)
AUDIO_LOUDNORM_LRA = 11.0        # ラウドネスレンジ目標 (LU)

# ===========================
# Whisper Parameters
# ===========================
WHISPER_VAD_FILTER = False
WHISPER_VAD_THRESHOLD = 0.30
WHISPER_VAD_MIN_SILENCE_MS = 600
WHISPER_VAD_SPEECH_PAD_MS = 350
WHISPER_CONDITION_ON_PREV = False
WHISPER_NO_SPEECH_THRESHOLD = 0.85
WHISPER_LOG_PROB_THRESHOLD = -1.0
WHISPER_HALLUCINATION_SILENCE_THRESHOLD = None
WHISPER_TEMPERATURES = (0.0, 0.2, 0.4)
WHISPER_INITIAL_PROMPT = None
WHISPER_HOTWORDS = None
WHISPER_BEAM_SIZE = 5
WHISPER_REPETITION_PENALTY = 1.08
