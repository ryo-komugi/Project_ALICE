import gc
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
        audio_files = []
        for ext in config.SUPPORTED_AUDIO_EXTENSIONS:
            audio_files.extend(input_dir.glob(f"*{ext}"))
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

        job.status = JobStatus.RUNNING
        job.t0 = time.time()
        self.logger.info(f"[TranscriptPipeline] Starting Pipeline for {input_audio.name} (model={self.model_name})")

        try:
            # 1. pyannote (話者分離)
            job.t_py_start = time.time()
            self.logger.info(f"[{job.basename}] pyannote開始")
            job.wav_audio = convert_to_wav(job.input_audio, job.wav_audio)
            self.pyannote.run(job)
            job.t_py_end = time.time()

            # 2. Whisper (音声認識)
            job.t_wh_start = time.time()
            self.logger.info(f"[{job.basename}] Whisper開始")
            self.whisper.run(job)
            job.t_wh_end = time.time()

            # 3. Alignment (話者とテキストの照合)
            job.t_aln_start = time.time()
            self.logger.info(f"[{job.basename}] アライメント開始")
            self.alignment.run(job)
            job.t_aln_end = time.time()

            # 4. Normalization (テキスト正規化)
            job.t_norm_start = time.time()
            self.logger.info(f"[{job.basename}] Normalization開始")
            self.normalizer.run(job)
            job.t_norm_end = time.time()

            # 5. Export (成果物書き出し)
            self.logger.info(f"[{job.basename}] 成果物出力中")
            job.status = JobStatus.COMPLETED
            job.calc_times()
            summary = self.exporter.run(job, self.model_name)
            self.logger.info(
                f"[{job.basename}] Exported to: {job.transcript_json}, {job.output_txt}, {job.metadata_json}"
            )

            self.logger.info(f"[TranscriptPipeline] Pipeline COMPLETED for {job.basename}")
            return job

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.calc_times()
            self.logger.error(f"[TranscriptPipeline] Pipeline FAILED: {e}")
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
