from pyannote.audio import Pipeline
import json
import sys
import torch
import soundfile as sf
import numpy as np

if len(sys.argv) < 3:
    print("Usage: python run_pyannote.py <input_wav> <output_json>", file=sys.stderr)
    sys.exit(1)

audio_path = sys.argv[1]
transcript_json = sys.argv[2]

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1"
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
pipeline.to(device)

waveform, sr = sf.read(audio_path)

# stereo → mono
if waveform.ndim > 1:
    waveform = waveform.mean(axis=1)

waveform = waveform.astype("float32")

file = {
    "waveform": torch.tensor(waveform).float().unsqueeze(0),
    "sample_rate": 16000   # ←16kHz固定推奨
}

diarization = pipeline(file)

segments = []
for turn, _, speaker in diarization.speaker_diarization.itertracks(yield_label=True):
    segments.append({
        "start": float(turn.start),
        "end": float(turn.end),
        "speaker": speaker
    })

with open(transcript_json, "w", encoding="utf-8") as f:
    json.dump(segments, f, ensure_ascii=False, indent=2)

# VRAM解放
if torch.cuda.is_available():
    torch.cuda.empty_cache()
