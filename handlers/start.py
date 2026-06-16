"""handlers/start.py — /start command"""

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from db import mongo


def register(app: Client) -> None:

    @app.on_message(filters.command("start"))
    async def start_cmd(client: Client, msg: Message):
        await mongo.add_served_user(msg.from_user.id)

        if msg.chat.type == ChatType.PRIVATE:
            await msg.reply_text(
                "👋 **Hi! I'm Anthropie Music.**\n\n"
                "🎵 I stream audio into Telegram Voice Chats — "
                "smooth, lag-free, glitch-free.\n\n"
                "**How to use me:**\n"
                "1. Add me to your group\n"
                "2. Start a Voice Chat in the group\n"
                "3. Use `/play song name` to start streaming\n\n"
                "**Main commands:**\n"
                "`/play` — Play a song\n"
                "`/skip` — Skip current song\n"
                "`/pause` — Pause\n"
                "`/resume` — Resume\n"
                "`/queue` — Show queue\n"
                "`/stop` — Stop and leave VC\n\n"
                "Add me to a group and let's play some music! 🎶",
                quote=True,
            )
        else:
            await mongo.add_served_chat(msg.chat.id)
            await msg.reply_text("Hey, let's play songs here! 🎵", quote=True)
