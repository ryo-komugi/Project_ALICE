import subprocess
import os
from pathlib import Path

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
# 音声変換 (mp3/m4a → wav) & アダプティブ音響前処理
# ===========================
def convert_to_wav(input_path, output_path, job=None, manual_m=None, manual_channel=None):
    """
    Converts audio to 16kHz mono WAV with adaptive acoustic preprocessing.
    Continuously tunes dynaudnorm gain (m) and routes stereo channels to avoid comb-filtering.
    """
    import config
    from core.audio_processor import build_audio_filter_chain

    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    profile = None

    if getattr(config, "AUDIO_PREPROCESSING_ENABLED", True):
        adaptive_enabled = getattr(config, "AUDIO_ADAPTIVE_PREPROCESSING", True)
        target_rms = getattr(config, "AUDIO_ADAPTIVE_TARGET_RMS", -22.0)
        hp = getattr(config, "AUDIO_FILTER_HIGHPASS", 100)
        lp = getattr(config, "AUDIO_FILTER_LOWPASS", 7600)

        # Job parameter or Config manual override
        m_override = manual_m
        if m_override is None and job is not None:
            m_override = getattr(job, "manual_m", None)
        if m_override is None:
            m_override = getattr(config, "AUDIO_MANUAL_DYNAUDNORM_M", None)

        ch_override = manual_channel
        if ch_override is None and job is not None:
            ch_override = getattr(job, "manual_channel", None)
        if ch_override is None:
            ch_override = getattr(config, "AUDIO_MANUAL_CHANNEL_MODE", None)

        filters, profile = build_audio_filter_chain(
            input_path,
            manual_m=m_override,
            manual_channel=ch_override,
            adaptive_enabled=adaptive_enabled,
            target_rms=target_rms,
            highpass_hz=hp,
            lowpass_hz=lp,
        )
        if filters:
            cmd.extend(["-af", ",".join(filters)])
    elif getattr(config, "AUDIO_NORMALIZE", True):
        cmd.extend(["-af", "highpass=f=80"])

    cmd.extend(["-ar", "16000", "-ac", "1", str(output_path)])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if job is not None and profile is not None:
        job.acoustic_profile = profile

    return output_path

# ===========================
# オーバーラップ長
# ===========================
def overlap_length(text1, text2):
    max_overlap = 0
    max_len = min(len(text1), len(text2))
    for i in range(1, max_len + 1):
        if text1[-i:] == text2[:i]:
            max_overlap = i
    return max_overlap
