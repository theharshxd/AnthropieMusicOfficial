"""handlers/play.py — /play and /vplay commands"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from core import queue as Q
from core.downloader import download_audio
from core.stream import StreamManager
from db import mongo
from handlers.helpers import get_mention

logger = logging.getLogger(__name__)


def register(app: Client, stream: StreamManager) -> None:

    @app.on_message(filters.command(["play", "vplay"]) & filters.group)
    async def play_cmd(client: Client, msg: Message):
        chat_id = msg.chat.id
        user_id = msg.from_user.id if msg.from_user else None
        mention = get_mention(msg)

        if user_id:
            await mongo.add_served_user(user_id)
        await mongo.add_served_chat(chat_id)

        # ── Resolve query ─────────────────────────────────────────────────────
        query = None

        if msg.reply_to_message:
            rep = msg.reply_to_message
            if rep.audio:
                query = rep.audio.file_name or "audio file"
            elif rep.video:
                query = rep.video.file_name or "video file"
            elif rep.document:
                query = rep.document.file_name or "document"
            elif rep.text:
                query = rep.text.strip()

        if not query:
            parts = msg.text.split(None, 1)
            if len(parts) > 1:
                query = parts[1].strip()

        if not query:
            await msg.reply_text(
                "❌ Please provide a song name or URL.\n"
                "Example: `/play Shape of You`",
                quote=True,
            )
            return

        # ── Queue check ───────────────────────────────────────────────────────
        if Q.is_full(chat_id):
            await msg.reply_text(
                f"❌ Queue is full! Max {Config.QUEUE_LIMIT} songs per chat.\n"
                "Use `/skip` to move to the next song.",
                quote=True,
            )
            return

        status_msg = await msg.reply_text("🔍 Searching and downloading...", quote=True)

        # ── Download ──────────────────────────────────────────────────────────
        track = await download_audio(query, chat_id, mention)

        if not track:
            try:
                await status_msg.edit_text(
                    "❌ Could not find or download that song. Please try another query."
                )
            except Exception:
                pass
            return

        # ── Add to queue ──────────────────────────────────────────────────────
        position = Q.add_track(chat_id, track)
        current_status = stream.get_status(chat_id)

        if current_status == "idle":
            try:
                await status_msg.edit_text(f"▶️ Starting: **{track['title']}**")
            except Exception:
                pass
            success = await stream.play(chat_id, track)
            if not success:
                Q.pop_current(chat_id)
                try:
                    await status_msg.edit_text(
                        "❌ Could not join the Voice Chat.\n"
                        "Make sure a Voice Chat is active in this group."
                    )
                except Exception:
                    pass
        else:
            # Already playing — show queue position
            try:
                await status_msg.edit_text(
                    f"✅ **Added to Queue** #{position}\n"
                    f"🎵 {track['title']}\n"
                    f"⏱ {track.get('duration_str', '??:??')}\n"
                    f"👤 {mention}"
                )
            except Exception:
                pass

        await Q.save_to_db(chat_id)
        
