"""
main.py — Anthropie Music Bot entry point
Web server starts FIRST so Render health check passes immediately.
"""

import asyncio
import logging
import threading

import uvloop
from pyrogram import Client
from pyrogram.errors import FloodWait

from config import Config
from core.cleanup import periodic_cleanup_task
from core.stream import StreamManager
from db import mongo
from handlers import helpers
from web.server import run_web_server

# ── Install uvloop BEFORE event loop starts ───────────────────────────────────
uvloop.install()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AnthropieMusic")

# ── Clients ───────────────────────────────────────────────────────────────────
bot = Client(
    "anthropie_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

assistant = Client(
    "anthropie_assistant",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.SESSION_STRING,
)


def register_all_handlers(stream: StreamManager) -> None:
    from handlers import start, play, admin, auth, queue_cmd, stats, sudo

    start.register(bot)
    play.register(bot, stream)
    admin.register(bot, stream)
    auth.register(bot)
    queue_cmd.register(bot)
    stats.register(bot, stream)
    sudo.register(bot)
    logger.info("All handlers registered.")


async def db_keepalive_task() -> None:
    while True:
        await asyncio.sleep(240)
        ok = await mongo.ping()
        if not ok:
            logger.warning("[main] MongoDB ping failed — attempting reconnect...")
            try:
                await mongo.connect()
            except Exception as exc:
                logger.error("[main] MongoDB reconnect failed: %s", exc)


async def _start_client(client: Client, name: str) -> None:
    while True:
        try:
            await client.start()
            return
        except FloodWait as e:
            logger.warning("[main] %s FloodWait — waiting %ds", name, e.value)
            await asyncio.sleep(e.value + 5)
        except Exception as exc:
            logger.error("[main] %s failed to start: %s", name, exc)
            raise


async def main() -> None:
    logger.info("=" * 50)
    logger.info("  Anthropie Music Bot — Starting")
    logger.info("=" * 50)

    # 1. Start web/health server FIRST — Render's health check must pass fast
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Health server started on port %d", Config.PORT)

    # 2. MongoDB
    await mongo.connect()

    # 3. Load sudo cache
    db_sudos = await mongo.get_sudos()
    for uid in db_sudos:
        helpers.add_sudo_cache(uid)
    logger.info("Loaded %d sudo user(s) from DB.", len(db_sudos))

    # 4. Start bot clients
    await _start_client(bot, "Bot")
    await _start_client(assistant, "Assistant")

    bot_me = await bot.get_me()
    asst_me = await assistant.get_me()
    logger.info("Bot      : @%s (id=%d)", bot_me.username, bot_me.id)
    logger.info("Assistant: @%s (id=%d)", asst_me.username, asst_me.id)

    # 5. Build stream manager and register handlers
    stream = StreamManager(assistant, bot)
    register_all_handlers(stream)

    # 6. Start PyTgCalls
    await stream.start()

    # 7. Background tasks
    asyncio.create_task(periodic_cleanup_task())
    asyncio.create_task(db_keepalive_task())
    logger.info("Background tasks started.")

    logger.info("=" * 50)
    logger.info("  Bot is running.")
    logger.info("=" * 50)

    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Shutting down...")
        try:
            await bot.stop()
        except Exception:
            pass
        try:
            await assistant.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bye!")
