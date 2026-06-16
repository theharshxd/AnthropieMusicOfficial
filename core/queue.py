"""
core/queue.py
Per-chat queue management.
Handles add / remove / pre-download / state tracking.

Chat state structure:
{
    "tracks":          list[dict],   # full queue (max 10)
    "current_file":    str | None,   # file path of currently playing track
    "prefetched_file": str | None,   # file path of next track (pre-downloaded)
    "prefetch_task":   Task | None,  # asyncio task doing pre-download
    "np_msg_id":       int | None,   # Now Playing message ID to delete
    "status":          str,          # "playing" | "paused" | "idle"
}
"""

from __future__ import annotations

import asyncio
import logging

from config import Config
from db import mongo

logger = logging.getLogger(__name__)

# Global in-memory store: { chat_id: state_dict }
_chats: dict[int, dict] = {}


def _default_state() -> dict:
    return {
        "tracks": [],
        "current_file": None,
        "prefetched_file": None,
        "prefetch_task": None,
        "np_msg_id": None,
        "status": "idle",
    }


def get_state(chat_id: int) -> dict:
    if chat_id not in _chats:
        _chats[chat_id] = _default_state()
    return _chats[chat_id]


def reset_state(chat_id: int) -> None:
    _chats[chat_id] = _default_state()


# ── Queue operations ──────────────────────────────────────────────────────────

def queue_length(chat_id: int) -> int:
    return len(get_state(chat_id)["tracks"])


def is_full(chat_id: int) -> bool:
    return queue_length(chat_id) >= Config.QUEUE_LIMIT


def add_track(chat_id: int, track: dict) -> int:
    """Add track to end of queue. Returns new queue length."""
    state = get_state(chat_id)
    state["tracks"].append(track)
    return len(state["tracks"])


def get_current(chat_id: int) -> dict | None:
    state = get_state(chat_id)
    return state["tracks"][0] if state["tracks"] else None


def get_next(chat_id: int) -> dict | None:
    state = get_state(chat_id)
    return state["tracks"][1] if len(state["tracks"]) > 1 else None


def pop_current(chat_id: int) -> dict | None:
    """Remove and return the first track from queue."""
    state = get_state(chat_id)
    if state["tracks"]:
        return state["tracks"].pop(0)
    return None


def get_queue_list(chat_id: int) -> list:
    return get_state(chat_id)["tracks"].copy()


def clear_queue(chat_id: int) -> None:
    get_state(chat_id)["tracks"].clear()


# ── Prefetch ──────────────────────────────────────────────────────────────────

async def trigger_prefetch(chat_id: int) -> None:
    """
    Called when current song has PREFETCH_AT_SECONDS remaining.
    Downloads track[1] in background if not already done.
    """
    from core.downloader import download_audio  # local import avoids circular

    state = get_state(chat_id)
    next_track = get_next(chat_id)

    if not next_track:
        return  # nothing to prefetch

    if state["prefetched_file"] or state["prefetch_task"]:
        return  # already in progress or done

    async def _fetch():
        logger.info(
            "[queue] pre-downloading next track: %s", next_track.get("title", next_track["query"])
        )
        result = await download_audio(
            next_track["query"],
            chat_id,
            next_track["requested_by"],
        )
        if result:
            state["prefetched_file"] = result["file_path"]
            # Update the track dict with download info
            state["tracks"][1].update(result)
            logger.info("[queue] pre-download complete: %s", result["file_path"])
        else:
            logger.warning("[queue] pre-download failed for: %s", next_track["query"])
        state["prefetch_task"] = None

    task = asyncio.create_task(_fetch())
    state["prefetch_task"] = task


async def wait_for_prefetch(chat_id: int) -> None:
    """Wait for any ongoing prefetch task to finish."""
    state = get_state(chat_id)
    task = state.get("prefetch_task")
    if task and not task.done():
        await task


# ── Persistence ───────────────────────────────────────────────────────────────

async def save_to_db(chat_id: int) -> None:
    try:
        tracks = get_state(chat_id)["tracks"]
        await mongo.save_queue(chat_id, tracks)
    except Exception as exc:
        logger.warning("[queue] could not save queue to DB: %s", exc)
