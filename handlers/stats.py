"""handlers/stats.py — /stats /ping /active"""

from __future__ import annotations

import time
from datetime import timedelta

import psutil
from pyrogram import Client, filters
from pyrogram.types import Message

from core.stream import StreamManager

_start_time = time.time()


def register(app: Client, stream: StreamManager) -> None:

    @app.on_message(filters.command("stats"))
    async def stats_cmd(client: Client, msg: Message):
        from db import mongo

        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        uptime = timedelta(seconds=int(time.time() - _start_time))

        served_chats = await mongo.get_served_chats()
        served_users = await mongo.get_served_users()

        disk = psutil.disk_usage("/tmp")

        text = (
            "📊 **Anthropie Music — Stats**\n\n"
            f"🖥 **CPU:** `{cpu:.1f}%`\n"
            f"💾 **RAM:** `{mem.used // (1024*1024)} MB` used / "
            f"`{mem.total // (1024*1024)} MB` total (`{mem.percent:.1f}%`)\n"
            f"💿 **Disk (/tmp):** `{disk.used // (1024*1024)} MB` used / "
            f"`{disk.total // (1024*1024)} MB` total\n"
            f"⏱ **Uptime:** `{uptime}`\n"
            f"📡 **Active Streams:** `{len(stream.active_chats())}`\n"
            f"💬 **Served Chats:** `{len(served_chats)}`\n"
            f"👤 **Served Users:** `{len(served_users)}`"
        )
        await msg.reply_text(text, quote=True)

    @app.on_message(filters.command("ping"))
    async def ping_cmd(client: Client, msg: Message):
        t1 = time.time()
        sent = await msg.reply_text("🏓 Pong!", quote=True)
        diff = (time.time() - t1) * 1000
        await sent.edit_text(f"🏓 **Pong!** `{diff:.1f} ms`")

    @app.on_message(filters.command("active"))
    async def active_cmd(client: Client, msg: Message):
        active = stream.active_chats()
        if not active:
            return await msg.reply_text("📡 No active streams right now.", quote=True)
        await msg.reply_text(
            f"📡 **Active Streams:** `{len(active)}` chat(s)", quote=True
        )
