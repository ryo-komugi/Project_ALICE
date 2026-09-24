import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class JobStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Job:
    """文字起こしパイプライン実行コンテキスト"""

    # ===========================
    # INPUT
    # ===========================
    input_audio: Path

    # ===========================
    # BASIC
    # ===========================
    basename: str = ""
    timestamp: str = ""
    status: JobStatus = JobStatus.CREATED
    error_message: str | None = None

    # ===========================
    # WORKSPACE ARTIFACTS
    # ===========================
    # Runtime Artifacts (一時ファイル: cleanupで削除)
    wav_audio: Path | None = None
    segments_json: Path | None = None

    # Pipeline Output Artifacts (成果物)
    transcript_json: Path | None = None
    output_txt: Path | None = None
    metadata_json: Path | None = None

    # ===========================
    # MEMORY
    # ===========================
    whisper_segments = None
    whisper_info = None
    pyannote_segments = None
    assigned_words = None
    results = None

    # ===========================
    # TIMING
    # ===========================
    t0: float = 0.0
    t_py_start: float = 0.0
    t_py_end: float = 0.0
    t_wh_start: float = 0.0
    t_wh_end: float = 0.0
    t_aln_start: float = 0.0
    t_aln_end: float = 0.0
    t_norm_start: float = 0.0
    t_norm_end: float = 0.0
    py_time: float = 0.0
    wh_time: float = 0.0
    aln_time: float = 0.0
    norm_time: float = 0.0
    total_time: float = 0.0

    def cleanup(self):
        """Pipeline実行中に生成したRuntime Artifact（中間ファイル）を削除する"""
        runtime_artifacts = [self.wav_audio, self.segments_json]
        for file in runtime_artifacts:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except OSError:
                    pass

    def calc_times(self):
        self.total_time = time.time() - self.t0
        self.py_time = max(0.0, self.t_py_end - self.t_py_start)
        self.wh_time = max(0.0, self.t_wh_end - self.t_wh_start)
        self.aln_time = max(0.0, self.t_aln_end - self.t_aln_start)
        self.norm_time = max(0.0, self.t_norm_end - self.t_norm_start)


# Backward compatibility alias
TranscriptJob = Job
