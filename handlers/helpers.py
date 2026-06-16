"""
handlers/helpers.py
Shared utilities: permission checks, user info extraction.
"""

from __future__ import annotations

import logging

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message

from config import Config
from db import mongo

logger = logging.getLogger(__name__)

# In-memory sudo cache (populated on startup, updated by /addsudo /delsudo)
_sudo_cache: set[int] = set(Config.SUDO_USERS)
_sudo_cache.add(Config.OWNER_ID)


def add_sudo_cache(user_id: int) -> None:
    _sudo_cache.add(user_id)


def remove_sudo_cache(user_id: int) -> None:
    _sudo_cache.discard(user_id)


def is_sudo(user_id: int) -> bool:
    return user_id in _sudo_cache


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user is a chat admin."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


async def is_authorised(client: Client, chat_id: int, user_id: int) -> bool:
    """Returns True if user is owner, sudo, chat admin, or auth user."""
    if is_sudo(user_id):
        return True
    if await is_admin(client, chat_id, user_id):
        return True
    auth_users = await mongo.get_auth_users(chat_id)
    return user_id in auth_users


def get_mention(msg: Message) -> str:
    """Return @username or first name for a user."""
    u = msg.from_user
    if not u:
        return "Unknown"
    if u.username:
        return f"@{u.username}"
    return u.first_name or str(u.id)


async def resolve_target_user(client: Client, msg: Message) -> int | None:
    """
    Get target user_id from:
      1. Replied-to message
      2. Command argument (user ID or @username)
    Returns None if can't resolve.
    """
    # From reply
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id

    # From argument
    parts = msg.text.split(None, 1)
    if len(parts) < 2:
        return None

    arg = parts[1].strip()
    if arg.lstrip("-").isdigit():
        return int(arg)

    # Username lookup
    try:
        user = await client.get_users(arg.lstrip("@"))
        return user.id
    except Exception:
        return None
