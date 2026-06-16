"""handlers/sudo.py — /addsudo /delsudo /sudolist /broadcast /restart /update"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from db import mongo
from handlers.helpers import (
    add_sudo_cache,
    is_sudo,
    remove_sudo_cache,
    resolve_target_user,
)

logger = logging.getLogger(__name__)


def _owner_or_sudo(user_id: int) -> bool:
    return user_id == Config.OWNER_ID or is_sudo(user_id)


def register(app: Client) -> None:

    @app.on_message(filters.command("addsudo"))
    async def addsudo_cmd(client: Client, msg: Message):
        if not _owner_or_sudo(msg.from_user.id):
            return await msg.reply_text("❌ Owner/sudo only.", quote=True)

        target = await resolve_target_user(client, msg)
        if not target:
            return await msg.reply_text("❌ Provide a user ID or reply to a user.", quote=True)

        await mongo.add_sudo(target)
        add_sudo_cache(target)
        await msg.reply_text(f"✅ `{target}` added as sudo user.", quote=True)

    @app.on_message(filters.command(["delsudo", "rmsudo"]))
    async def delsudo_cmd(client: Client, msg: Message):
        if msg.from_user.id != Config.OWNER_ID:
            return await msg.reply_text("❌ Owner only.", quote=True)

        target = await resolve_target_user(client, msg)
        if not target:
            return await msg.reply_text("❌ Provide a user ID or reply to a user.", quote=True)

        await mongo.remove_sudo(target)
        remove_sudo_cache(target)
        await msg.reply_text(f"✅ `{target}` removed from sudo.", quote=True)

    @app.on_message(filters.command("sudolist"))
    async def sudolist_cmd(client: Client, msg: Message):
        if not _owner_or_sudo(msg.from_user.id):
            return await msg.reply_text("❌ Owner/sudo only.", quote=True)

        db_sudos = await mongo.get_sudos()
        all_sudos = set(db_sudos) | set(Config.SUDO_USERS)

        if not all_sudos:
            return await msg.reply_text("📋 No sudo users configured.", quote=True)

        lines = [f"`{uid}`" for uid in sorted(all_sudos)]
        await msg.reply_text(
            f"👑 **Owner:** `{Config.OWNER_ID}`\n\n"
            f"🛡 **Sudo Users:**\n" + "\n".join(lines),
            quote=True,
        )

    @app.on_message(filters.command(["broadcast", "gcast"]))
    async def broadcast_cmd(client: Client, msg: Message):
        if not _owner_or_sudo(msg.from_user.id):
            return await msg.reply_text("❌ Owner/sudo only.", quote=True)

        if not msg.reply_to_message:
            return await msg.reply_text(
                "❌ Reply to a message to broadcast it.\n"
                "Flags: `-pin` `-pinloud` `-nobot`",
                quote=True,
            )

        flags = msg.text.lower() if msg.text else ""
        pin = "-pin" in flags or "-pinloud" in flags
        pin_loud = "-pinloud" in flags
        skip_bots = "-nobot" in flags

        chats = await mongo.get_served_chats()
        status = await msg.reply_text(
            f"📢 Broadcasting to `{len(chats)}` chats...", quote=True
        )

        success = 0
        failed = 0

        for chat_id in chats:
            try:
                # Skip bot check (can't tell if a chat is a bot group from ID alone)
                sent = await msg.reply_to_message.copy(chat_id)
                if pin:
                    try:
                        await sent.pin(disable_notification=not pin_loud)
                    except Exception:
                        pass
                success += 1
                await asyncio.sleep(0.2)   # rate limit
            except Exception as exc:
                logger.warning("[broadcast] failed to %d: %s", chat_id, exc)
                failed += 1

        await status.edit_text(
            f"📢 **Broadcast complete**\n"
            f"✅ Success: `{success}`\n"
            f"❌ Failed: `{failed}`"
        )

    @app.on_message(filters.command("restart"))
    async def restart_cmd(client: Client, msg: Message):
        if not _owner_or_sudo(msg.from_user.id):
            return await msg.reply_text("❌ Owner/sudo only.", quote=True)

        await msg.reply_text("🔄 Restarting...", quote=True)
        logger.info("[sudo] restart requested by %d", msg.from_user.id)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @app.on_message(filters.command("update"))
    async def update_cmd(client: Client, msg: Message):
        if not _owner_or_sudo(msg.from_user.id):
            return await msg.reply_text("❌ Owner/sudo only.", quote=True)

        status = await msg.reply_text("⬇️ Pulling latest code...", quote=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = (stdout + stderr).decode(errors="ignore").strip()
            await status.edit_text(f"```\n{output[:3000]}\n```\n\n🔄 Restarting...")
        except Exception as exc:
            await status.edit_text(f"❌ git pull failed: `{exc}`")
            return

        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
