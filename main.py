"""
main.py — Anthropie Music Bot entry point
"""

import asyncio
import logging
import threading

from pyrogram import Client

from config import Config
from core.cleanup import periodic_cleanup_task
from core.stream import StreamManager
from db import mongo
from handlers import helpers
from web.server import run_web_server

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


async def main() -> None:
    import uvloop
    uvloop.install()

    logger.info("=" * 50)
    logger.info("  Anthropie Music Bot — Starting")
    logger.info("=" * 50)

    await mongo.connect()

    db_sudos = await mongo.get_sudos()
    for uid in db_sudos:
        helpers.add_sudo_cache(uid)
    logger.info("Loaded %d sudo user(s) from DB.", len(db_sudos))

    stream = StreamManager(assistant, bot)
    register_all_handlers(stream)

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Health server started on port %d", Config.PORT)

    await bot.start()
    await assistant.start()
    bot_me = await bot.get_me()
    asst_me = await assistant.get_me()
    logger.info("Bot started     : @%s (id=%d)", bot_me.username, bot_me.id)
    logger.info("Assistant started: @%s (id=%d)", asst_me.username, asst_me.id)

    await stream.start()

    asyncio.create_task(periodic_cleanup_task())
    asyncio.create_task(db_keepalive_task())
    logger.info("Background tasks started.")

    logger.info("=" * 50)
    logger.info("  Bot is running. Press Ctrl+C to stop.")
    logger.info("=" * 50)

    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down — bye!")
