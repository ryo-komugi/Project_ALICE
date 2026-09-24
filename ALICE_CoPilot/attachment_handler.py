from typing import List, Tuple
import discord

SUPPORTED_TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".json", ".py", ".yaml", ".yml", ".log", ".csv"
}

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB


def is_text_attachment(filename: str) -> bool:
    """
    Check if the attachment filename has a supported text extension.
    """
    filename_lower = filename.lower()
    return any(filename_lower.endswith(ext) for ext in SUPPORTED_TEXT_EXTENSIONS)


async def extract_attachments_text(attachments: List[discord.Attachment]) -> Tuple[str, List[str]]:
    """
    Extract text contents from a list of Discord attachments.

    Returns:
        Tuple[str, List[str]]:
            - combined_text: Combined string of all extracted file contents with headers.
            - processed_filenames: List of successfully processed attachment filenames.
    """
    extracted_texts = []
    processed_filenames = []

    for attachment in attachments:
        if not is_text_attachment(attachment.filename):
            continue

        if attachment.size > MAX_FILE_SIZE_BYTES:
            extracted_texts.append(
                f"【添付ファイル: {attachment.filename} (サイズが2MBを超えているためスキップされました)】"
            )
            continue

        try:
            content_bytes = await attachment.read()
            text_content = content_bytes.decode("utf-8", errors="replace").strip()
            if text_content:
                extracted_texts.append(
                    f"【添付ファイル: {attachment.filename}】\n{text_content}"
                )
                processed_filenames.append(attachment.filename)
        except Exception as e:
            extracted_texts.append(
                f"【添付ファイル: {attachment.filename} (読み込みエラー: {e})】"
            )

    combined_text = "\n\n".join(extracted_texts)
    return combined_text, processed_filenames
