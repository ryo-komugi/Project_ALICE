"""
Adaptive Audio Preprocessor module for ALICE_Transcript.
Probes acoustic characteristics (RMS, speech energy, stereo correlation)
and dynamically builds optimal FFmpeg filter chains to rescue quiet speakers
and eliminate comb-filtering without manual intervention.
Supports manual override via config or API.
"""
import subprocess
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any


@dataclass
class AcousticProfile:
    channels: int
    duration_sec: float
    overall_rms_db: float
    active_speech_rms_db: float
    peak_db: float
    channel_rms: List[float]
    stereo_correlation: Optional[float]
    applied_m: float
    applied_channel_mode: str  # "mono", "ch1", "ch2", "mix"
    is_adaptive: bool
    filter_chain: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def probe_acoustics(audio_path: Path | str, sample_sec: float = 90.0) -> Dict[str, Any]:
    """
    Fast acoustic analysis of incoming audio.
    Analyzes channels, peak/RMS volume, active speech energy, and stereo correlation
    within 0.1 ~ 0.3 seconds.
    """
    path_str = str(audio_path)

    # 1. ffprobe for channels and duration
    cmd_info = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels,duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path_str
    ]
    try:
        info_out = subprocess.check_output(cmd_info, text=True).strip().split()
        channels = int(info_out[0]) if len(info_out) >= 1 else 1
        duration = float(info_out[1]) if len(info_out) >= 2 and info_out[1] != "N/A" else 0.0
    except Exception:
        channels = 1
        duration = 0.0

    # 2. Extract representative PCM segment (skip first few seconds if long)
    ss = 5.0 if duration > 30.0 else 0.0
    cmd_pcm = [
        "ffmpeg", "-v", "error",
        "-ss", str(ss),
        "-i", path_str,
        "-t", str(sample_sec),
        "-f", "s16le",
        "-ar", "16000",
        "-"
    ]
    try:
        p = subprocess.Popen(cmd_pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw, _ = p.communicate()
    except Exception:
        raw = b""

    if len(raw) == 0:
        return {
            "channels": channels,
            "duration_sec": duration,
            "overall_rms_db": -24.0,
            "active_speech_rms_db": -24.0,
            "peak_db": 0.0,
            "channel_rms": [-24.0],
            "stereo_correlation": None,
            "suggested_channel": "mono",
        }

    audio = np.frombuffer(raw, dtype=np.int16)
    channel_rms = []
    correlation = None
    suggested_channel = "mono"

    if channels == 2 and len(audio) % 2 == 0:
        audio2d = audio.reshape(-1, 2)
        ch1 = audio2d[:, 0].astype(np.float32) / 32768.0
        ch2 = audio2d[:, 1].astype(np.float32) / 32768.0

        rms1 = float(20 * np.log10(max(np.sqrt(np.mean(ch1**2)), 1e-9)))
        rms2 = float(20 * np.log10(max(np.sqrt(np.mean(ch2**2)), 1e-9)))
        channel_rms = [rms1, rms2]

        overall_rms = float(20 * np.log10(max(np.sqrt(np.mean(audio.astype(np.float32)**2 / (32768.0**2))), 1e-9)))
        peak = float(20 * np.log10(max(np.max(np.abs(audio2d).astype(np.float32) / 32768.0), 1e-9)))

        # Stereo Correlation
        if np.std(ch1) > 1e-5 and np.std(ch2) > 1e-5:
            corr = np.corrcoef(ch1, ch2)[0, 1]
            correlation = float(corr)
        else:
            correlation = 1.0

        # Channel selection: avoid comb-filtering
        rms_diff = abs(rms1 - rms2)
        if rms_diff >= 3.0:
            suggested_channel = "ch1" if rms1 > rms2 else "ch2"
            eval_audio = ch1 if rms1 > rms2 else ch2
        elif correlation is not None and correlation < 0.75:
            suggested_channel = "ch1" if rms1 >= rms2 else "ch2"
            eval_audio = ch1 if rms1 >= rms2 else ch2
        else:
            suggested_channel = "mix"
            eval_audio = (ch1 + ch2) * 0.5
    else:
        ch = audio.astype(np.float32) / 32768.0
        overall_rms = float(20 * np.log10(max(np.sqrt(np.mean(ch**2)), 1e-9)))
        peak = float(20 * np.log10(max(np.max(np.abs(ch)), 1e-9)) if len(ch) > 0 else 0.0)
        channel_rms = [overall_rms]
        eval_audio = ch
        suggested_channel = "mono"

    # 3. Active speech energy analysis (speech activity gating)
    frame_len = 1600  # 100ms at 16kHz
    n_frames = len(eval_audio) // frame_len
    if n_frames > 0:
        frames = eval_audio[:n_frames * frame_len].reshape(n_frames, frame_len)
        frame_rms_db = 20 * np.log10(np.maximum(np.sqrt(np.mean(frames**2, axis=1)), 1e-9))
        voiced_frames = frame_rms_db[frame_rms_db > -55.0]
        if len(voiced_frames) > 5:
            active_speech_rms = float(np.percentile(voiced_frames, 50))
        else:
            active_speech_rms = float(overall_rms)
    else:
        active_speech_rms = float(overall_rms)

    return {
        "channels": channels,
        "duration_sec": duration,
        "overall_rms_db": overall_rms,
        "active_speech_rms_db": active_speech_rms,
        "peak_db": peak,
        "channel_rms": channel_rms,
        "stereo_correlation": correlation,
        "suggested_channel": suggested_channel,
    }


def calculate_adaptive_dynaudnorm_m(
    speech_rms_db: float,
    target_rms: float = -22.0,
    m_min: float = 3.0,
    m_max: float = 20.0
) -> float:
    """
    Computes smooth, continuously variable dynaudnorm maximum gain (m)
    based on the speech energy deficit below target RMS level.
    """
    deficit_db = max(0.0, target_rms - speech_rms_db)
    # Exponential gain scaling matching human hearing & Whisper ideal operating point
    calc_m = m_min * (10.0 ** (deficit_db / 25.0))
    return round(float(np.clip(calc_m, m_min, m_max)), 2)


def build_audio_filter_chain(
    audio_path: Path | str,
    manual_m: Optional[float] = None,
    manual_channel: Optional[str] = None,
    adaptive_enabled: bool = True,
    target_rms: float = -22.0,
    highpass_hz: int = 100,
    lowpass_hz: int = 7600,
) -> tuple[List[str], AcousticProfile]:
    """
    Builds the complete FFmpeg audio filter list and returns the acoustic profile.
    Supports both fully adaptive continuous scaling and manual override.
    """
    raw_stats = probe_acoustics(audio_path)

    # 1. Determine channel mode
    if manual_channel and manual_channel != "auto":
        channel_mode = manual_channel
    else:
        channel_mode = raw_stats["suggested_channel"]

    # 2. Determine dynaudnorm m value
    if manual_m is not None and manual_m > 0:
        applied_m = round(float(manual_m), 2)
        is_adaptive = False
    elif adaptive_enabled:
        applied_m = calculate_adaptive_dynaudnorm_m(
            raw_stats["active_speech_rms_db"],
            target_rms=target_rms
        )
        is_adaptive = True
    else:
        applied_m = 4.0
        is_adaptive = False

    # 3. Assemble FFmpeg filter list
    filters = []

    # Stereo channel routing
    if raw_stats["channels"] >= 2:
        if channel_mode == "ch1":
            filters.append("pan=mono|c0=c0")
        elif channel_mode == "ch2":
            filters.append("pan=mono|c0=c1")
        # "mix" or "mono": handled by downstream -ac 1 or pan

    # Frequency bandpass
    if highpass_hz:
        filters.append(f"highpass=f={highpass_hz}")
    if lowpass_hz:
        filters.append(f"lowpass=f={lowpass_hz}")

    # Dynamic audio normalizer with adaptive m
    filters.append(f"dynaudnorm=f=500:g=31:p=0.95:m={applied_m}")

    filter_str = ",".join(filters)

    deficit = max(0.0, target_rms - raw_stats["active_speech_rms_db"])
    desc = (
        f"[Acoustic] Ch={raw_stats['channels']} ({channel_mode}), "
        f"SpeechRMS={raw_stats['active_speech_rms_db']:.1f}dBFS (Deficit=+{deficit:.1f}dB), "
        f"dynaudnorm m={applied_m} ({'Adaptive' if is_adaptive else 'Manual'})"
    )
    if raw_stats["stereo_correlation"] is not None:
        desc += f", Corr={raw_stats['stereo_correlation']:.3f}"

    profile = AcousticProfile(
        channels=raw_stats["channels"],
        duration_sec=raw_stats["duration_sec"],
        overall_rms_db=raw_stats["overall_rms_db"],
        active_speech_rms_db=raw_stats["active_speech_rms_db"],
        peak_db=raw_stats["peak_db"],
        channel_rms=raw_stats["channel_rms"],
        stereo_correlation=raw_stats["stereo_correlation"],
        applied_m=applied_m,
        applied_channel_mode=channel_mode,
        is_adaptive=is_adaptive,
        filter_chain=filter_str,
        description=desc
    )

    return filters, profile
