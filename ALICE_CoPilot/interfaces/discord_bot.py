"""
Backwards-compatibility wrapper for discord_bot.py.
Implementation moved to interfaces.discord.bot.
"""
from interfaces.discord.bot import (
    handle_discord_ready,
    handle_discord_message,
    create_discord_client,
    run_discord_bot,
)

__all__ = [
    "handle_discord_ready",
    "handle_discord_message",
    "create_discord_client",
    "run_discord_bot",
]
