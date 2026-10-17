import subprocess
import os

# ===========================
# 時間フォーマット
# ===========================
def format_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02}:{m:02}:{s:02}"

# ===========================
# overlap計算
# ===========================
def overlap(a_start, a_end, b_start, b_end):
    return max(
        0,
        min(a_end, b_end) - max(a_start, b_start)
    )

# ===========================
# 音声変換 (mp3/m4a → wav) & 音響前処理
# ===========================
def convert_to_wav(input_path, output_path):
    import config
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    if getattr(config, "AUDIO_PREPROCESSING_ENABLED", False):
        filters = []
        # 1. 帯域フィルタ (低周波・超高域ノイズカット)
        hp = getattr(config, "AUDIO_FILTER_HIGHPASS", 100)
        lp = getattr(config, "AUDIO_FILTER_LOWPASS", 7600)
        if hp:
            filters.append(f"highpass=f={hp}")
        if lp:
            filters.append(f"lowpass=f={lp}")

        # 2. FFTスペクトルノイズ抑制 (明示設定時のみ)
        nf = getattr(config, "AUDIO_FILTER_DENOISE_NF", None)
        if nf is not None:
            filters.append(f"afftdn=nf={nf}")

        # 3. 音量正規化 (loudnorm明示設定時はloudnorm、デフォルトは小声救済に優れたdynaudnorm)
        norm_i = getattr(config, "AUDIO_LOUDNORM_I", None)
        dynaudnorm = getattr(config, "AUDIO_DYNAUDNORM", "f=250:g=15:p=0.90:m=6.0:s=12.0")
        if norm_i is not None:
            norm_tp = getattr(config, "AUDIO_LOUDNORM_TP", -1.5)
            norm_lra = getattr(config, "AUDIO_LOUDNORM_LRA", 11.0)
            filters.append(f"loudnorm=I={norm_i}:TP={norm_tp}:LRA={norm_lra}")
        elif dynaudnorm:
            filters.append(f"dynaudnorm={dynaudnorm}")

        if filters:
            cmd.extend(["-af", ",".join(filters)])
    elif getattr(config, "AUDIO_NORMALIZE", True):
        cmd.extend(["-af", "highpass=f=80"])

    cmd.extend(["-ar", "16000", "-ac", "1", str(output_path)])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

# ===========================
# オーバーラップ長
# ===========================
def overlap_length(text1, text2):
    # text1末尾とtext2先頭の最大一致長を返す
    max_overlap = 0
    max_len = min(len(text1), len(text2))
    for i in range(1, max_len + 1):
        if text1[-i:] == text2[:i]:
            max_overlap = i
    return max_overlap
