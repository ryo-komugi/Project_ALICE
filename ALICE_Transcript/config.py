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
# PyannoteとWhisperの微小なタイムラグを吸収する近傍探索マージン (秒)
TOLERANCE_MARGIN = 0.35

# 同一話者内で発話を分割するポーズ（無音）閾値 (秒)
PAUSE_THRESHOLD = 1.0

# 1つの発話セグメントの最大継続時間 (秒)
MAX_UTTERANCE_DURATION = 25.0

# 同一話者に挟まれたUNKNOWN単語を補間する最大ギャップ係数 (秒)
INTERPOLATE_MAX_GAP = 1.5

# 同一話者に挟まれた微小な異話者フリップ（Pyannoteのオーバーラップ誤認等）を平滑化する閾値 (秒)
MICRO_FLIP_MAX_DURATION = 0.8

# 同一話者の近接発話を自然に1つに結合する最大ギャップ (秒)
MERGE_SAME_SPEAKER_GAP = 1.2

# ===========================
# Audio Preprocessing
# ===========================
# 音声変換時の音響前処理パイプライン設定 (FFmpegネイティブ)
# 目的: 卓上マイク録音での小声話者（面談対象者等）の持ち上げと低域空調ノイズ除去
AUDIO_NORMALIZE = True
AUDIO_PREPROCESSING_ENABLED = True
AUDIO_FILTER_HIGHPASS = 100      # 空調・机振動・低周波ノイズ除去 (Hz)
AUDIO_FILTER_LOWPASS = 7600      # 超高域ヒスノイズ除去・子音帯域保持 (Hz)
AUDIO_FILTER_DENOISE_NF = None   # FFTスペクトル減算による子音劣化・nospeech誤判定を防ぐためデフォルト無効
AUDIO_DYNAUDNORM = "f=500:g=31:p=0.95:m=4.0"  # 声質・話者特徴量を壊さず小声を緩やかに持ち上げるダイナミックノーマライザ
AUDIO_LOUDNORM_I = None          # 明示指定時のみEBU R128 loudnormを使用
AUDIO_LOUDNORM_TP = -1.5         # トゥルーピーク上限 (dBTP)
AUDIO_LOUDNORM_LRA = 11.0        # ラウドネスレンジ目標 (LU)

# ===========================
# Whisper Parameters
# ===========================
# Silero VAD のチャンク強制結合(collect_chunks)による時間軸ジャンプ・単語分断・チャンク破棄を防ぐためデフォルトFalse
WHISPER_VAD_FILTER = False

# VAD有効時のパラメータ
WHISPER_VAD_THRESHOLD = 0.30
WHISPER_VAD_MIN_SILENCE_MS = 600
WHISPER_VAD_SPEECH_PAD_MS = 350

# ノイズ環境での反復幻覚ループ抑止
WHISPER_CONDITION_ON_PREV = False

# large-v3 の過敏な nospeech 判定による30秒チャンク丸ごとスキップを抑制
WHISPER_NO_SPEECH_THRESHOLD = 0.85
WHISPER_LOG_PROB_THRESHOLD = -1.0
# 日本語短トークン(<0.133s)に対する過剰な再シーク・後半切断を防ぐためNone
WHISPER_HALLUCINATION_SILENCE_THRESHOLD = None
# 無音区間での高Temperatureランダムサンプリング幻覚を防止
WHISPER_TEMPERATURES = (0.0, 0.2, 0.4)

# 日本語句読点生成と汎用的な会話トーンを促す初期プロンプト
WHISPER_INITIAL_PROMPT = "こんにちは。本日の会議・面談・インタビューを始めます。議題の進捗確認、連絡事項、質疑応答などについて話し合います。よろしくお願いします。"

# 社内・業務頻出語の認識精度を高めるホットワード (condition_on_previous_text=False時はエコー防止のためデフォルトNone)
WHISPER_HOTWORDS = None

# ビームサーチ幅
WHISPER_BEAM_SIZE = 5

# 反復ペナルティ
WHISPER_REPETITION_PENALTY = 1.05
