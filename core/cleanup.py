"""
core/cleanup.py
Handles all file deletion and RAM cleanup.
"""

from __future__ import annotations

import asyncio
import gc
import glob
import logging
import os
import time

import psutil

from config import Config

logger = logging.getLogger(__name__)


def delete_file(file_path: str | None) -> None:
    """Delete a single audio file safely."""
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("[cleanup] deleted file: %s", file_path)
    except Exception as exc:
        logger.warning("[cleanup] could not delete %s: %s", file_path, exc)


def free_ram() -> None:
    """Run Python garbage collector and log current RAM."""
    collected = gc.collect()
    mem = psutil.virtual_memory()
    logger.info(
        "[cleanup] gc collected %d objects | RAM: %.1f MB used / %.1f MB total (%.1f%%)",
        collected,
        mem.used / (1024 * 1024),
        mem.total / (1024 * 1024),
        mem.percent,
    )


def cleanup_after_song(file_path: str | None) -> None:
    """Called immediately after a song finishes. Delete file + free RAM."""
    delete_file(file_path)
    free_ram()


async def cleanup_orphans() -> None:
    """
    Scan /tmp for leftover am_*.* files older than ORPHAN_MAX_AGE seconds.
    Called periodically every CLEANUP_INTERVAL seconds.
    """
    pattern = os.path.join(Config.TMP_DIR, "am_*.*")
    now = time.time()
    deleted = 0

    try:
        for fpath in glob.glob(pattern):
            try:
                age = now - os.path.getmtime(fpath)
                if age > Config.ORPHAN_MAX_AGE:
                    os.remove(fpath)
                    deleted += 1
                    logger.info("[cleanup] orphan deleted: %s (age %.0fs)", fpath, age)
            except Exception as exc:
                logger.warning("[cleanup] could not delete orphan %s: %s", fpath, exc)
    except Exception as exc:
        logger.error("[cleanup] orphan scan error: %s", exc)

    if deleted:
        free_ram()
    logger.info("[cleanup] orphan scan done — deleted %d file(s)", deleted)


async def periodic_cleanup_task() -> None:
    """Background task. Runs orphan scan every CLEANUP_INTERVAL seconds."""
    logger.info(
        "[cleanup] periodic task started — interval %ds", Config.CLEANUP_INTERVAL
    )
    while True:
        await asyncio.sleep(Config.CLEANUP_INTERVAL)
        await cleanup_orphans()


def full_cleanup_chat(chat_state: dict) -> None:
    """
    Full cleanup for a chat on /stop or /end.
    Deletes current file + prefetched file, frees RAM.
    """
    delete_file(chat_state.get("current_file"))
    delete_file(chat_state.get("prefetched_file"))
    free_ram()
