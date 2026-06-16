"""
db/mongo.py
All MongoDB operations. Uses motor (async).
Collections:
  sudo_users    — global sudo list
  auth_users    — per-chat authorised users  { chat_id, users: [int] }
  served_chats  — every chat that used the bot
  served_users  — every user that used the bot
  queue_backup  — crash-recovery queue snapshot per chat
"""

from __future__ import annotations

import logging
from typing import List

from motor.motor_asyncio import AsyncIOMotorClient

from config import Config

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db = None


async def connect() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(
        Config.MONGO_URI,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=8000,
    )
    await _client.admin.command("ping")
    _db = _client[Config.DB_NAME]
    logger.info("MongoDB connected to database: %s", Config.DB_NAME)


async def ping() -> bool:
    """Keep-alive ping. Returns True on success."""
    try:
        await _client.admin.command("ping")
        return True
    except Exception as exc:
        logger.warning("MongoDB ping failed: %s", exc)
        return False


def _col(name: str):
    return _db[name]


# ── Sudo ──────────────────────────────────────────────────────────────────────

async def add_sudo(user_id: int) -> None:
    await _col("sudo_users").update_one(
        {"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True
    )


async def remove_sudo(user_id: int) -> None:
    await _col("sudo_users").delete_one({"_id": user_id})


async def get_sudos() -> List[int]:
    return [doc["_id"] async for doc in _col("sudo_users").find({}, {"_id": 1})]


# ── Auth users ────────────────────────────────────────────────────────────────

async def auth_user(chat_id: int, user_id: int) -> None:
    await _col("auth_users").update_one(
        {"chat_id": chat_id},
        {"$addToSet": {"users": user_id}},
        upsert=True,
    )


async def unauth_user(chat_id: int, user_id: int) -> None:
    await _col("auth_users").update_one(
        {"chat_id": chat_id},
        {"$pull": {"users": user_id}},
    )


async def get_auth_users(chat_id: int) -> List[int]:
    doc = await _col("auth_users").find_one({"chat_id": chat_id})
    return doc.get("users", []) if doc else []


# ── Served chats / users ──────────────────────────────────────────────────────

async def add_served_chat(chat_id: int) -> None:
    await _col("served_chats").update_one(
        {"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True
    )


async def add_served_user(user_id: int) -> None:
    await _col("served_users").update_one(
        {"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True
    )


async def get_served_chats() -> List[int]:
    return [doc["_id"] async for doc in _col("served_chats").find({}, {"_id": 1})]


async def get_served_users() -> List[int]:
    return [doc["_id"] async for doc in _col("served_users").find({}, {"_id": 1})]


# ── Queue backup ──────────────────────────────────────────────────────────────

async def save_queue(chat_id: int, queue: list) -> None:
    # Strip file paths before saving — paths are invalid after restart
    safe = []
    for t in queue:
        entry = {k: v for k, v in t.items() if k != "file_path"}
        safe.append(entry)
    await _col("queue_backup").update_one(
        {"_id": chat_id}, {"$set": {"queue": safe}}, upsert=True
    )


async def load_queue(chat_id: int) -> list:
    doc = await _col("queue_backup").find_one({"_id": chat_id})
    return doc.get("queue", []) if doc else []


async def clear_queue_backup(chat_id: int) -> None:
    await _col("queue_backup").delete_one({"_id": chat_id})
