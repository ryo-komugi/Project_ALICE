# ALICE_Transcript

## Current Version

|  Item  |  Value  |
|--------|---------|
| Version | v1.0.0 |
| Status | Stable |
| Python | 3.10 |
| Platform | Ubuntu 26.04 LTS |
| License | Private |

## 1. Overview

ALICE_Transcript is an offline speech transcription engine for Project ALICE.

It converts meeting audio into speaker-attributed transcripts using Whisper and Pyannote.

Main Features

- Offline processing
- Speaker diarization
- Word-level speaker alignment
- Text normalization
- Automatic queue processing
- Multi-format audio support

ALICE_Transcript is designed to run continuously as a systemd service on Ubuntu Server.

## 2. Features

- Whisper transcription
- Pyannote speaker diarization
- Word-level speaker alignment
- Automatic WAV conversion
- Text Normalizer
- Queue based processing
- Folder monitoring
- JSON / TXT export
- Logging
- Automatic log archive
- MP3 / M4A / WAV support

## 3. System Architecture

The overall architecture and design documents are available in:

docs/architecture/

/data
├── staging/      Incoming audio files
├── audio_in/     Converted WAV files
├── audio_work/   Files currently being processed
├── audio_out/    Processing results
└── logs/         Runtime logs

## 5. Installation

### Requirements

- Ubuntu 26.04 LTS
- Python 3.10
- FFmpeg
- CUDA (optional)
- HuggingFace Token
- Whisper Model

### Create virtual environment

(Create your virtual environment.)

### Install dependencies

pip install -r requirements.txt

## 6. Configuration

Main configuration file:

config.py

## 7. Usage

Start the service
sudo systemctl start alice-transcript

Stop the service
sudo systemctl stop alice-transcript

Restart the service
sudo systemctl restart alice-transcript

Check service status
sudo systemctl status alice-transcript

Place audio files into:
The service automatically detects and processes new files.

## 8. Processing Pipeline

Audio
   │
   ▼
Convert WAV
   │
   ▼
Pyannote
   │
   ▼
Whisper
   │
   ▼
Alignment
   │
   ▼
Text Normalizer
   │
   ▼
Exporter

## 9. Output

basename_timestamp/
├── transcript.txt
├── transcript.json
└── meeting.wav

## 10. Project Structure

core/
engines/
docs/
main.py
config.py

## 11. Roadmap

### v1.0

- Stable Release

### v1.1

- Google Drive API
- Input Adapter
- Unit Tests

## 12. License

Private Project