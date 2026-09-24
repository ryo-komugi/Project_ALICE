import os
from dataclasses import dataclass


@dataclass
class SummaryConfig:
    # Ollama settings
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    default_model: str = os.getenv("SUMMARY_DEFAULT_MODEL", "gemma4:12b")
    fallback_model: str = os.getenv("SUMMARY_FALLBACK_MODEL", "qwen3:14b")

    # Context and generation settings
    num_ctx: int = int(os.getenv("SUMMARY_NUM_CTX", "32768"))
    max_num_ctx: int = int(os.getenv("SUMMARY_MAX_NUM_CTX", "65536"))
    temperature_stage1: float = float(os.getenv("SUMMARY_TEMP_STAGE1", "0.1"))
    temperature_stage2: float = float(os.getenv("SUMMARY_TEMP_STAGE2", "0.3"))
    temperature_stage3: float = float(os.getenv("SUMMARY_TEMP_STAGE3", "0.1"))
    timeout_sec: int = int(os.getenv("SUMMARY_TIMEOUT_SEC", "900"))
    keep_alive: str = os.getenv("SUMMARY_KEEP_ALIVE", "5m")  # Keep model in VRAM during pipeline
    final_keep_alive: int = 0  # Unload from VRAM after final stage completed

    # Dynamic Context Sizing Thresholds
    ctx_threshold_standard: int = 28000   # <= 28k tokens -> 32768
    ctx_threshold_extended: int = 44000   # <= 44k tokens -> 49152, else -> 65536

    # Generation length limits & repetition penalty
    num_predict_stage1: int = int(os.getenv("SUMMARY_NUM_PREDICT_STAGE1", "4096"))
    num_predict_stage2: int = int(os.getenv("SUMMARY_NUM_PREDICT_STAGE2", "4096"))
    num_predict_stage3: int = int(os.getenv("SUMMARY_NUM_PREDICT_STAGE3", "6144"))
    repeat_penalty: float = float(os.getenv("SUMMARY_REPEAT_PENALTY", "1.1"))

    # Resilience: Retries and Fallbacks
    max_retries: int = int(os.getenv("SUMMARY_MAX_RETRIES", "3"))
    retry_delay: float = float(os.getenv("SUMMARY_RETRY_DELAY", "2.0"))
    backoff_factor: float = float(os.getenv("SUMMARY_BACKOFF_FACTOR", "2.0"))
    enable_fallback: bool = os.getenv("SUMMARY_ENABLE_FALLBACK", "true").lower() in ("true", "1", "yes")


DEFAULT_CONFIG = SummaryConfig()

