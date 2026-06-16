"""
core/nowplaying.py
Send and auto-delete "Now Playing" messages.
Text only — no thumbnails, no links (copyright compliance).
"""

from __future__ import annotations

import logging

from pyrogram import Client
from pyrogram.errors import MessageDeleteForbidden, MessageNotModified

from core import queue as Q

logger = logging.getLogger(__name__)


async def send_now_playing(bot: Client, chat_id: int, track: dict) -> None:
    """Send Now Playing message and store its ID for later deletion."""
    text = (
        f"🎵 **Now Playing**\n"
        f"🎶 **{track['title']}**\n"
        f"⏱ Duration: `{track.get('duration_str', '??:??')}`\n"
        f"👤 Requested by: {track.get('requested_by', 'Unknown')}"
    )
    try:
        msg = await bot.send_message(chat_id, text)
        state = Q.get_state(chat_id)
        state["np_msg_id"] = msg.id
    except Exception as exc:
        logger.warning("[nowplaying] could not send message to %d: %s", chat_id, exc)


async def delete_now_playing(bot: Client, chat_id: int) -> None:
    """Delete the previous Now Playing message."""
    state = Q.get_state(chat_id)
    msg_id = state.get("np_msg_id")
    if not msg_id:
        return
    try:
        await bot.delete_messages(chat_id, msg_id)
        state["np_msg_id"] = None
    except (MessageDeleteForbidden, MessageNotModified):
        state["np_msg_id"] = None
    except Exception as exc:
        logger.warning("[nowplaying] could not delete message %d: %s", msg_id, exc)
        state["np_msg_id"] = None
