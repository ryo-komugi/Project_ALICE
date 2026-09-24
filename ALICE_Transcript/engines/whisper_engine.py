import logging
from faster_whisper import WhisperModel
import config

logger = logging.getLogger(__name__)


class WhisperEngine:
    def __init__(self, model_name=None, device="cuda", compute_type="float16"):
        self.model_name = model_name or getattr(config, "MODEL_NAME", "deepdml/faster-whisper-large-v3-turbo-ct2")
        self.device = device
        self.compute_type = compute_type
        try:
            self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        except Exception as exc:
            # 万が一turboモデルの取得に失敗した場合は従来のlarge-v3へフォールバック
            fallback_model = "large-v3"
            logger.warning(
                f"[WhisperEngine] Failed to load primary model '{self.model_name}' ({exc}). "
                f"Falling back to '{fallback_model}'..."
            )
            self.model_name = fallback_model
            self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)

    def transcribe(
        self,
        wav_audio,
        language="ja",
        word_timestamps=True,
        vad_filter=None,
        vad_parameters=None,
        condition_on_previous_text=None,
        initial_prompt=None,
        beam_size=None,
        repetition_penalty=None,
    ):
        if vad_filter is None:
            vad_filter = getattr(config, "WHISPER_VAD_FILTER", True)

        if vad_parameters is None and vad_filter:
            speech_pad_ms = getattr(config, "WHISPER_VAD_SPEECH_PAD_MS", 300)
            vad_parameters = dict(min_silence_duration_ms=500, speech_pad_ms=speech_pad_ms)

        if condition_on_previous_text is None:
            condition_on_previous_text = getattr(config, "WHISPER_CONDITION_ON_PREV", False)

        if initial_prompt is None:
            initial_prompt = getattr(
                config,
                "WHISPER_INITIAL_PROMPT",
                "本日の業務面談・会議を始めます。進捗報告、勤怠や離席、体調管理、業務改善などの課題について率直に話し合いましょう。"
            )

        if beam_size is None:
            beam_size = getattr(config, "WHISPER_BEAM_SIZE", 5)

        if repetition_penalty is None:
            repetition_penalty = getattr(config, "WHISPER_REPETITION_PENALTY", 1.0)

        segments, info = self.model.transcribe(
            str(wav_audio),
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters,
            condition_on_previous_text=condition_on_previous_text,
            initial_prompt=initial_prompt,
            beam_size=beam_size,
            repetition_penalty=repetition_penalty,
        )
        return list(segments), info

    def run(self, job):
        job.whisper_segments, job.whisper_info = self.transcribe(job.wav_audio)
