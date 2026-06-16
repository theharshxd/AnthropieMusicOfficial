"""handlers/auth.py — /auth /unauth /authlist"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from db import mongo
from handlers.helpers import is_authorised, resolve_target_user


def register(app: Client) -> None:

    @app.on_message(filters.command("auth") & filters.group)
    async def auth_cmd(client: Client, msg: Message):
        if not msg.from_user:
            return
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        target = await resolve_target_user(client, msg)
        if not target:
            return await msg.reply_text(
                "❌ Reply to a user or provide a user ID.\nExample: `/auth 123456789`",
                quote=True,
            )

        await mongo.auth_user(msg.chat.id, target)
        await msg.reply_text(f"✅ User `{target}` added to authorised list.", quote=True)

    @app.on_message(filters.command("unauth") & filters.group)
    async def unauth_cmd(client: Client, msg: Message):
        if not msg.from_user:
            return
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        target = await resolve_target_user(client, msg)
        if not target:
            return await msg.reply_text(
                "❌ Reply to a user or provide a user ID.", quote=True
            )

        await mongo.unauth_user(msg.chat.id, target)
        await msg.reply_text(f"✅ User `{target}` removed from authorised list.", quote=True)

    @app.on_message(filters.command("authlist") & filters.group)
    async def authlist_cmd(client: Client, msg: Message):
        if not msg.from_user:
            return
        if not await is_authorised(client, msg.chat.id, msg.from_user.id):
            return await msg.reply_text("❌ You don't have permission to do that.", quote=True)

        users = await mongo.get_auth_users(msg.chat.id)
        if not users:
            return await msg.reply_text("📋 No authorised users in this chat.", quote=True)

        lines = [f"`{uid}`" for uid in users]
        text = "📋 **Authorised Users:**\n" + "\n".join(lines)
        await msg.reply_text(text, quote=True)
        
