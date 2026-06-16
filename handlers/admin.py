"""handlers/admin.py — /pause /resume /skip /end /stop /reload"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMembersFilter
from pyrogram.types import Message

from core.stream import StreamManager
from handlers.helpers import is_authorised

logger = logging.getLogger(__name__)

# In-memory admin cache per chat: { chat_id: set(user_ids) }
_admin_cache: dict[int, set] = {}


async def _refresh_admins(client: Client, chat_id: int) -> set:
    admins = set()
    async for member in client.get_chat_members(
        chat_id, filter=ChatMembersFilter.ADMINISTRATORS
    ):
        admins.add(member.user.id)
    _admin_cache[chat_id] = admins
    return admins


def register(app: Client, stream: StreamManager) -> None:

    @app.on_message(filters.command("pause") & filters.group)
    async def pause_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        if stream.get_status(msg.chat.id) != "playing":
            return await msg.reply_text("❌ Nothing is playing right now.", quote=True)

        ok = await stream.pause(msg.chat.id)
        if ok:
            await msg.reply_text("⏸ Stream paused.", quote=True)
        else:
            await msg.reply_text("❌ Could not pause. Is there an active Voice Chat?", quote=True)

    @app.on_message(filters.command("resume") & filters.group)
    async def resume_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        if stream.get_status(msg.chat.id) != "paused":
            return await msg.reply_text("❌ Stream is not paused.", quote=True)

        ok = await stream.resume(msg.chat.id)
        if ok:
            await msg.reply_text("▶️ Stream resumed.", quote=True)
        else:
            await msg.reply_text("❌ Could not resume.", quote=True)

    @app.on_message(filters.command("skip") & filters.group)
    async def skip_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        if stream.get_status(msg.chat.id) == "idle":
            return await msg.reply_text("❌ Nothing is playing right now.", quote=True)

        await msg.reply_text("⏭ Skipping...", quote=True)
        await stream.skip(msg.chat.id)

    @app.on_message(filters.command("end") & filters.group)
    async def end_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        await stream.stop(msg.chat.id, leave=False)
        await msg.reply_text("⏹ Stream ended and queue cleared.", quote=True)

    @app.on_message(filters.command("stop") & filters.group)
    async def stop_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        await stream.stop(msg.chat.id, leave=True)
        await msg.reply_text("🛑 Stopped and left Voice Chat.", quote=True)

    @app.on_message(filters.command("reload") & filters.group)
    async def reload_cmd(client: Client, msg: Message):
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        await _refresh_admins(client, msg.chat.id)
        await msg.reply_text("🔄 Admin cache refreshed.", quote=True)
