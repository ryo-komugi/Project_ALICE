"""
Backwards-compatibility wrapper for attachment_handler.
Implementation moved to interfaces.discord.attachments.
"""
from interfaces.discord.attachments import (
    SUPPORTED_TEXT_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    is_text_attachment,
    extract_attachments_text,
)

__all__ = [
    "SUPPORTED_TEXT_EXTENSIONS",
    "MAX_FILE_SIZE_BYTES",
    "is_text_attachment",
    "extract_attachments_text",
]
