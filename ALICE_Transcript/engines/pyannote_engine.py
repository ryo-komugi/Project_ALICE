import subprocess
import json
import os
from pathlib import Path
from config import PYANNOTE_PYTHON

class PyannoteEngine:
    def __init__(self):
        pass

    def diarize(self, wav_audio, segments_json):
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = (
            "/usr/lib/wsl/lib:"
            + env.get("LD_LIBRARY_PATH", "")
        )

        script_path = Path(__file__).resolve().parent.parent / "scripts" / "run_pyannote.py"
        subprocess.run(
            [
                PYANNOTE_PYTHON,
                str(script_path),
                str(wav_audio),
                str(segments_json)
            ],
            env=env,
            check=True
        )

        with open(
            segments_json,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    def run(self, job):
        job.pyannote_segments = self.diarize(job.wav_audio, job.segments_json)