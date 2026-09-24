"""
ALICE_Minute Configuration Module
"""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MinuteConfig:
    # Ollama settings
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model_name: str = os.getenv("ALICE_MINUTE_MODEL", "gemma4:12b")
    fallback_model: str = os.getenv("ALICE_MINUTE_FALLBACK_MODEL", "gemma4:e4b")

    # Dynamic Context Sizing
    num_ctx: int = int(os.getenv("ALICE_MINUTE_NUM_CTX", "32768"))
    max_num_ctx: int = int(os.getenv("ALICE_MINUTE_MAX_NUM_CTX", "65536"))
    ctx_threshold_standard: int = 28000
    ctx_threshold_extended: int = 44000

    # Thinking & Predict Limits
    stage1_think: bool = os.getenv("ALICE_MINUTE_STAGE1_THINK", "false").lower() == "true"
    stage2_think: bool = os.getenv("ALICE_MINUTE_STAGE2_THINK", "false").lower() == "true"
    stage1_num_predict: int = int(os.getenv("ALICE_MINUTE_STAGE1_NUM_PREDICT", "8192"))
    stage2_num_predict: int = int(os.getenv("ALICE_MINUTE_STAGE2_NUM_PREDICT", "8192"))

    # Temperature & Timeouts
    stage1_temperature: float = float(os.getenv("ALICE_MINUTE_STAGE1_TEMP", "0.1"))
    stage2_temperature: float = float(os.getenv("ALICE_MINUTE_STAGE2_TEMP", "0.2"))
    timeout_seconds: int = int(os.getenv("ALICE_MINUTE_TIMEOUT", "900"))

    # VRAM lifecycle
    keep_alive: str = os.getenv("ALICE_MINUTE_KEEP_ALIVE", "5m")
    final_keep_alive: int = 0

    # Default template
    default_template: str = os.getenv("ALICE_MINUTE_DEFAULT_TEMPLATE", "standard")

    # Project directories
    module_root: Path = Path(__file__).resolve().parent
    prompts_dir: Path = module_root / "prompts"
    templates_dir: Path = module_root / "prompts" / "templates"


# Singleton instance
config = MinuteConfig()
