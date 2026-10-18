import logging
from typing import Callable
from faster_whisper import WhisperModel
import config

logger = logging.getLogger(__name__)


class WhisperEngine:
    def __init__(self, model_name=None, device="cuda", compute_type="float16"):
        self.model_name = model_name or getattr(config, "MODEL_NAME", "large-v3")
        self.device = device
        self.compute_type = compute_type
        self.progress_callback: Callable | None = None
        try:
            self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        except Exception as exc:
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
        no_speech_threshold=None,
        log_prob_threshold=None,
        hallucination_silence_threshold=None,
        hotwords=None,
        temperature=None,
    ):
        if vad_filter is None:
            vad_filter = getattr(config, "WHISPER_VAD_FILTER", False)

        if vad_parameters is None and vad_filter:
            speech_pad_ms = getattr(config, "WHISPER_VAD_SPEECH_PAD_MS", 350)
            min_silence_ms = getattr(config, "WHISPER_VAD_MIN_SILENCE_MS", 600)
            threshold = getattr(config, "WHISPER_VAD_THRESHOLD", 0.30)
            vad_parameters = dict(
                threshold=threshold,
                min_silence_duration_ms=min_silence_ms,
                speech_pad_ms=speech_pad_ms,
            )

        if condition_on_previous_text is None:
            condition_on_previous_text = getattr(config, "WHISPER_CONDITION_ON_PREV", False)

        if initial_prompt is None:
            initial_prompt = getattr(
                config,
                "WHISPER_INITIAL_PROMPT",
                "こんにちは。本日の会議・面談・インタビューを始めます。議題の進捗確認、連絡事項、質疑応答などについて話し合います。よろしくお願いします。"
            )

        if beam_size is None:
            beam_size = getattr(config, "WHISPER_BEAM_SIZE", 5)

        if repetition_penalty is None:
            repetition_penalty = getattr(config, "WHISPER_REPETITION_PENALTY", 1.05)

        if no_speech_threshold is None:
            no_speech_threshold = getattr(config, "WHISPER_NO_SPEECH_THRESHOLD", 0.85)

        if log_prob_threshold is None:
            log_prob_threshold = getattr(config, "WHISPER_LOG_PROB_THRESHOLD", -1.0)

        if hallucination_silence_threshold is None:
            hallucination_silence_threshold = getattr(config, "WHISPER_HALLUCINATION_SILENCE_THRESHOLD", None)

        if hotwords is None:
            hotwords = getattr(config, "WHISPER_HOTWORDS", None)

        if temperature is None:
            temperature = getattr(config, "WHISPER_TEMPERATURES", (0.0, 0.2, 0.4))

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
            no_speech_threshold=no_speech_threshold,
            log_prob_threshold=log_prob_threshold,
            hallucination_silence_threshold=hallucination_silence_threshold,
            hotwords=hotwords,
            temperature=temperature,
        )
        collected = []
        for segment in segments:
            collected.append(segment)
            if self.progress_callback:
                self.progress_callback(segment, info)
        return collected, info

    def set_progress_callback(self, callback: Callable | None) -> None:
        """Set an optional callback invoked as Whisper yields each segment."""
        self.progress_callback = callback

    def run(self, job):
        job.whisper_segments, job.whisper_info = self.transcribe(job.wav_audio)
