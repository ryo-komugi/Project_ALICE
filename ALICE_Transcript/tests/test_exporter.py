import json
from pathlib import Path
from core.exporter import Exporter
from core.job import Job, JobStatus


def test_exporter_success(tmp_path):
    exporter = Exporter()
    audio = tmp_path / "test.m4a"
    audio.write_text("dummy")

    job = Job(input_audio=audio)
    job.basename = "test"
    job.timestamp = "20260923_180000"
    job.status = JobStatus.COMPLETED
    job.output_txt = tmp_path / "transcript.txt"
    job.transcript_json = tmp_path / "transcript.json"
    job.metadata_json = tmp_path / "metadata.json"

    job.results = [
        {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_00", "text": "こんにちは。"},
        {"start": 2.8, "end": 5.0, "speaker": "SPEAKER_01", "text": "お疲れ様です。"},
    ]

    job.total_time = 10.5
    job.py_time = 3.2
    job.wh_time = 5.1
    job.aln_time = 1.0
    job.norm_time = 0.5

    summary = exporter.run(job, model_name="test-model")

    assert job.output_txt.exists()
    assert job.transcript_json.exists()
    assert job.metadata_json.exists()

    # Check json output
    with open(job.transcript_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 2
        assert data[0]["speaker"] == "SPEAKER_00"

    # Check txt output
    txt_content = job.output_txt.read_text(encoding="utf-8")
    assert "SPEAKER_00: こんにちは。" in txt_content
    assert "SPEAKER_01: お疲れ様です。" in txt_content
    assert "Whisper(test-model)" in txt_content

    # Check metadata output
    with open(job.metadata_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["status"] == "COMPLETED"
        assert meta["whisper_model"] == "test-model"
        assert meta["execution"]["total"] == 10.5
        assert meta["execution"]["normalization"] == 0.5


def test_exporter_failure_metadata(tmp_path):
    exporter = Exporter()
    audio = tmp_path / "test.m4a"
    audio.write_text("dummy")

    job = Job(input_audio=audio)
    job.basename = "test"
    job.timestamp = "20260923_180000"
    job.metadata_json = tmp_path / "metadata.json"
    job.total_time = 2.0
    job.py_time = 1.5

    exporter.export_failure_metadata(job, "test-model", "Fatal memory error")

    assert job.metadata_json.exists()
    with open(job.metadata_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["status"] == "FAILED"
        assert meta["error"] == "Fatal memory error"
        assert meta["whisper_model"] == "test-model"
