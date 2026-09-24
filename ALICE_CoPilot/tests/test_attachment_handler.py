import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from attachment_handler import is_text_attachment, extract_attachments_text, MAX_FILE_SIZE_BYTES


def test_is_text_attachment():
    assert is_text_attachment("report.md") is True
    assert is_text_attachment("REPORT.MARKDOWN") is True
    assert is_text_attachment("data.json") is True
    assert is_text_attachment("script.py") is True
    assert is_text_attachment("image.png") is False
    assert is_text_attachment("archive.zip") is False


def test_extract_attachments_text_success():
    async def run():
        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.filename = "report.md"
        mock_attachment.size = 100
        mock_attachment.read = AsyncMock(return_value="# 改修レポート\n\nAIアライメント機能の改善".encode("utf-8"))

        text, filenames = await extract_attachments_text([mock_attachment])
        assert filenames == ["report.md"]
        assert "【添付ファイル: report.md】" in text
        assert "# 改修レポート" in text

    asyncio.run(run())


def test_extract_attachments_text_oversized():
    async def run():
        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.filename = "large_report.md"
        mock_attachment.size = MAX_FILE_SIZE_BYTES + 1
        mock_attachment.read = AsyncMock()

        text, filenames = await extract_attachments_text([mock_attachment])
        assert filenames == []
        assert "サイズが2MBを超えているためスキップ" in text
        mock_attachment.read.assert_not_called()

    asyncio.run(run())


def test_extract_attachments_text_unsupported():
    async def run():
        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.filename = "photo.png"
        mock_attachment.size = 500

        text, filenames = await extract_attachments_text([mock_attachment])
        assert filenames == []
        assert text == ""

    asyncio.run(run())

