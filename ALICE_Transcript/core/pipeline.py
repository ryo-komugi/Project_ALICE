import gc
import json
import os
import time
from pathlib import Path
import config
from engines.whisper_engine import WhisperEngine
from engines.pyannote_engine import PyannoteEngine
from engines.alignment_engine import AlignmentEngine
from core.exporter import Exporter
from core.logger import Logger
from core.text_normalizer import TextNormalizer
from core.job import Job, JobStatus
from core.utils import convert_to_wav


class TranscriptPipeline:
    """Workspace を入力とし、文字起こし・話者分離・アライメント・成果物出力を一元統括するパイプライン"""

    def __init__(
        self,
        model_name: str | None = None,
        device: str = "cuda",
        language: str = "ja",
        logger: Logger | None = None,
        whisper: WhisperEngine | None = None,
        pyannote: PyannoteEngine | None = None,
        alignment: AlignmentEngine | None = None,
        normalizer: TextNormalizer | None = None,
        exporter: Exporter | None = None,
    ):
        self.model_name = model_name or getattr(config, "MODEL_NAME", "deepdml/faster-whisper-large-v3-turbo-ct2")
        self.device = device
        self.language = language
        self.logger = logger or Logger()
        self.whisper = whisper or WhisperEngine(self.model_name, device=self.device)
        self.pyannote = pyannote or PyannoteEngine()
        self.alignment = alignment or AlignmentEngine()
        self.normalizer = normalizer or TextNormalizer()
        self.exporter = exporter or Exporter()

    def discover_input_audio(self, input_dir: Path) -> Path:
        valid_extensions = {ext.lower() for ext in config.SUPPORTED_AUDIO_EXTENSIONS}
        audio_files = [
            p for p in input_dir.iterdir()
            if p.is_file() and p.suffix.lower() in valid_extensions
        ]
        if not audio_files:
            raise FileNotFoundError(f"No supported audio file found in {input_dir}")
        return sorted(audio_files, key=lambda p: p.stat().st_mtime)[0]

    def run(self, workspace_dir: Path) -> Job:
        workspace = workspace_dir.resolve()
        input_dir = workspace / "input"
        transcript_dir = workspace / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)

        input_audio = self.discover_input_audio(input_dir)
        basename = input_audio.stem
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        job = Job(input_audio=input_audio)
        job.basename = basename
        job.timestamp = timestamp

        # Workspace/transcript 配下の入出力成果物パス定義
        job.wav_audio = transcript_dir / "audio.wav"
        job.segments_json = transcript_dir / "segments.json"
        job.metadata_json = transcript_dir / "metadata.json"
        job.transcript_json = transcript_dir / "transcript.json"
        job.output_txt = transcript_dir / "transcript.txt"

        progress_path = transcript_dir / "progress.json"
        live_transcript_path = transcript_dir / "live_transcript.txt"
        progress_percent = 0

        def write_progress(stage: str, percent: int) -> None:
            nonlocal progress_percent
            progress_percent = max(progress_percent, min(100, max(0, int(percent))))
            temporary_path = progress_path.with_suffix(".json.tmp")
            try:
                temporary_path.write_text(
                    json.dumps({"stage": stage, "percent": progress_percent}, ensure_ascii=False),
                    encoding="utf-8",
                )
                os.replace(temporary_path, progress_path)
            except OSError as exc:
                self.logger.warning(f"[TranscriptPipeline] Could not write progress: {exc}")

        job.status = JobStatus.RUNNING
        job.t0 = time.time()
        self.logger.info(f"[TranscriptPipeline] Starting Pipeline for {input_audio.name} (model={self.model_name})")

        try:
            # 1. pyannote (話者分離)
            write_progress("音声の準備・話者解析中", 3)
            job.t_py_start = time.time()
            self.logger.info(f"[{job.basename}] pyannote開始")
            job.wav_audio = convert_to_wav(job.input_audio, job.wav_audio)
            self.pyannote.run(job)
            job.t_py_end = time.time()

            # 2. Whisper (音声認識)
            write_progress("Whisperで文字起こし中", 20)
            job.t_wh_start = time.time()
            self.logger.info(f"[{job.basename}] Whisper開始")
            setter = getattr(self.whisper, "set_progress_callback", None)
            if callable(setter):
                try:
                    live_file = live_transcript_path.open("w", encoding="utf-8")
                except OSError as exc:
                    self.logger.warning(f"[TranscriptPipeline] Could not open live transcript: {exc}")
                    self.whisper.run(job)
                else:

                    def on_segment(segment, info):
                        try:
                            text = str(getattr(segment, "text", "")).strip()
                            if text:
                                live_file.write(text + "\n")
                                live_file.flush()
                            duration = float(
                                getattr(info, "duration_after_vad", None)
                                or getattr(info, "duration", 0)
                                or 0
                            )
                            end = float(getattr(segment, "end", 0) or 0)
                            estimate = 20 + int(60 * min(1.0, end / duration)) if duration > 0 else 20
                            write_progress("Whisperで文字起こし中", estimate)
                        except Exception as exc:
                            self.logger.warning(f"[TranscriptPipeline] Could not write live transcript: {exc}")

                    setter(on_segment)
                    try:
                        self.whisper.run(job)
                    finally:
                        setter(None)
                        live_file.close()
            else:
                self.whisper.run(job)
            job.t_wh_end = time.time()

            # 3. Alignment (話者とテキストの照合)
            write_progress("話者と文字起こしを照合中", 84)
            job.t_aln_start = time.time()
            self.logger.info(f"[{job.basename}] アライメント開始")
            self.alignment.run(job)
            job.t_aln_end = time.time()

            # 4. Normalization (テキスト正規化)
            write_progress("文字起こしを整えています", 91)
            job.t_norm_start = time.time()
            self.logger.info(f"[{job.basename}] Normalization開始")
            self.normalizer.run(job)
            job.t_norm_end = time.time()

            # 5. Export (成果物書き出し)
            write_progress("結果を保存しています", 97)
            self.logger.info(f"[{job.basename}] 成果物出力中")
            job.status = JobStatus.COMPLETED
            job.calc_times()
            summary = self.exporter.run(job, self.model_name)
            self.logger.info(
                f"[{job.basename}] Exported to: {job.transcript_json}, {job.output_txt}, {job.metadata_json}"
            )

            self.logger.info(f"[TranscriptPipeline] Pipeline COMPLETED for {job.basename}")
            write_progress("完了", 100)
            return job

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.calc_times()
            self.logger.error(f"[TranscriptPipeline] Pipeline FAILED: {e}")
            write_progress("処理に失敗しました", progress_percent)
            self.exporter.export_failure_metadata(job, self.model_name, str(e))
            raise

        finally:
            job.cleanup()
            self._free_memory()

    def _free_memory(self):
        """GPU VRAM およびインメモリキャッシュの明示的解放"""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()
