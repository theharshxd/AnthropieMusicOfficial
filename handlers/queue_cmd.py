"""handlers/queue_cmd.py — /queue command"""

from pyrogram import Client, filters
from pyrogram.types import Message

from core import queue as Q


def register(app: Client) -> None:

    @app.on_message(filters.command("queue") & filters.group)
    async def queue_cmd(client: Client, msg: Message):
        chat_id = msg.chat.id
        tracks = Q.get_queue_list(chat_id)

        if not tracks:
            return await msg.reply_text("📋 Queue is empty.", quote=True)

        lines = []
        for i, t in enumerate(tracks, 1):
            title = t.get("title", t.get("query", "Unknown"))
            dur = t.get("duration_str", "??:??")
            req = t.get("requested_by", "Unknown")
            marker = " ◀ **Now Playing**" if i == 1 else ""
            lines.append(f"{i}. **{title}** `[{dur}]` — {req}{marker}")

        text = f"📋 **Queue — {msg.chat.title}**\n\n" + "\n".join(lines)
        await msg.reply_text(text, quote=True)
        
