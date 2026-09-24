import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from core.pipeline import TranscriptPipeline
from core.job import Job, JobStatus


def test_discover_input_audio(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    audio1 = input_dir / "test1.m4a"
    audio1.write_text("dummy")

    pipeline = TranscriptPipeline.__new__(TranscriptPipeline)
    found = pipeline.discover_input_audio(input_dir)
    assert found == audio1


def test_discover_input_audio_not_found(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    pipeline = TranscriptPipeline.__new__(TranscriptPipeline)
    with pytest.raises(FileNotFoundError):
        pipeline.discover_input_audio(input_dir)


def test_pipeline_run_success(tmp_path):
    workspace = tmp_path / "test_ws"
    input_dir = workspace / "input"
    input_dir.mkdir(parents=True)
    audio = input_dir / "sample.mp3"
    audio.write_text("dummy")

    mock_whisper = MagicMock()
    mock_pyannote = MagicMock()
    mock_alignment = MagicMock()
    mock_normalizer = MagicMock()
    mock_exporter = MagicMock()
    mock_logger = MagicMock()

    # Setup pipeline with mocks
    pipeline = TranscriptPipeline(
        model_name="mock-model",
        logger=mock_logger,
        whisper=mock_whisper,
        pyannote=mock_pyannote,
        alignment=mock_alignment,
        normalizer=mock_normalizer,
        exporter=mock_exporter,
    )

    with patch("core.pipeline.convert_to_wav") as mock_convert:
        mock_convert.return_value = workspace / "transcript" / "audio.wav"
        job = pipeline.run(workspace)

        assert job.status == JobStatus.COMPLETED
        assert job.basename == "sample"
        assert mock_convert.called
        assert mock_pyannote.run.called
        assert mock_whisper.run.called
        assert mock_alignment.run.called
        assert mock_normalizer.run.called
        assert mock_exporter.run.called


def test_pipeline_run_failure(tmp_path):
    workspace = tmp_path / "test_ws_fail"
    input_dir = workspace / "input"
    input_dir.mkdir(parents=True)
    audio = input_dir / "sample.wav"
    audio.write_text("dummy")

    mock_whisper = MagicMock()
    mock_pyannote = MagicMock()
    mock_pyannote.run.side_effect = RuntimeError("Pyannote OOM error")
    mock_alignment = MagicMock()
    mock_normalizer = MagicMock()
    mock_exporter = MagicMock()
    mock_logger = MagicMock()

    pipeline = TranscriptPipeline(
        model_name="mock-model",
        logger=mock_logger,
        whisper=mock_whisper,
        pyannote=mock_pyannote,
        alignment=mock_alignment,
        normalizer=mock_normalizer,
        exporter=mock_exporter,
    )

    with patch("core.pipeline.convert_to_wav") as mock_convert:
        mock_convert.return_value = workspace / "transcript" / "audio.wav"
        with pytest.raises(RuntimeError, match="Pyannote OOM error"):
            pipeline.run(workspace)

        assert mock_exporter.export_failure_metadata.called
        call_args = mock_exporter.export_failure_metadata.call_args[0]
        assert "Pyannote OOM error" in str(call_args[2])
