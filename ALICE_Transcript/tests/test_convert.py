from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import config
from core.utils import convert_to_wav


def test_convert_to_wav_with_preprocessing(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_PREPROCESSING_ENABLED", True)
    monkeypatch.setattr(config, "AUDIO_FILTER_HIGHPASS", 80)
    monkeypatch.setattr(config, "AUDIO_FILTER_LOWPASS", 7500)
    monkeypatch.setattr(config, "AUDIO_FILTER_DENOISE_NF", -25)
    monkeypatch.setattr(config, "AUDIO_LOUDNORM_I", -16.0)
    monkeypatch.setattr(config, "AUDIO_LOUDNORM_TP", -1.5)
    monkeypatch.setattr(config, "AUDIO_LOUDNORM_LRA", 11.0)

    with patch("subprocess.run") as mock_run:
        res = convert_to_wav("/path/to/input.m4a", "/path/to/output.wav")
        assert res == "/path/to/output.wav"
        assert mock_run.called

        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        af_val = cmd[af_idx + 1]

        assert "highpass=f=80" in af_val
        assert "lowpass=f=7500" in af_val
        assert "afftdn=nf=-25" in af_val
        assert "loudnorm=I=-16.0:TP=-1.5:LRA=11.0" in af_val
        assert "-ar" in cmd and "16000" in cmd
        assert "-ac" in cmd and "1" in cmd


def test_convert_to_wav_disabled_preprocessing(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_PREPROCESSING_ENABLED", False)
    monkeypatch.setattr(config, "AUDIO_NORMALIZE", True)

    with patch("subprocess.run") as mock_run:
        res = convert_to_wav("/path/to/input.mp3", "/path/to/output.wav")
        assert res == "/path/to/output.wav"
        assert mock_run.called

        cmd = mock_run.call_args[0][0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        assert cmd[af_idx + 1] == "highpass=f=80"
