"""
core/stream.py
Streaming engine — reads local file via ffmpeg → PyTgCalls → Telegram VC.
Handles pre-download trigger, song-end callback, cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import os

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import AudioPiped, HighQualityAudio
from pytgcalls.types.stream import StreamAudioEnded

from config import Config
from core import cleanup, nowplaying
from core import queue as Q
from db import mongo

logger = logging.getLogger(__name__)


class StreamManager:
    def __init__(self, assistant: Client, bot: Client):
        self.assistant = assistant
        self.bot = bot
        self.calls = PyTgCalls(assistant)
        self._duration_tasks: dict[int, asyncio.Task] = {}

        # Register stream-ended callback
        @self.calls.on_stream_end()
        async def _on_end(_, update):
            if isinstance(update, StreamAudioEnded):
                await self._handle_song_end(update.chat_id)

    async def start(self) -> None:
        await self.calls.start()
        logger.info("[stream] PyTgCalls started")

    # ── Public API ────────────────────────────────────────────────────────────

    async def play(self, chat_id: int, track: dict) -> bool:
        """
        Start streaming `track` in the voice chat of `chat_id`.
        `track` must have a valid `file_path`.
        Returns True on success.
        """
        file_path = track.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.error("[stream] file not found: %s", file_path)
            return False

        state = Q.get_state(chat_id)
        state["current_file"] = file_path
        state["status"] = "playing"

        try:
            await self.calls.join_group_call(
                chat_id,
                AudioPiped(
                    file_path,
                    audio_parameters=HighQualityAudio(),
                ),
            )
            logger.info("[stream] started playing '%s' in %d", track["title"], chat_id)
        except Exception as exc:
            logger.error("[stream] join_group_call failed for %d: %s", chat_id, exc)
            state["status"] = "idle"
            return False

        # Schedule prefetch when nearing end
        duration = track.get("duration", 0)
        self._schedule_prefetch(chat_id, duration)

        # Send Now Playing
        await nowplaying.delete_now_playing(self.bot, chat_id)
        await nowplaying.send_now_playing(self.bot, chat_id, track)

        # Persist queue to DB
        await Q.save_to_db(chat_id)
        return True

    async def pause(self, chat_id: int) -> bool:
        try:
            await self.calls.pause_stream(chat_id)
            Q.get_state(chat_id)["status"] = "paused"
            return True
        except (NotInCallError, NoActiveGroupCall):
            return False
        except Exception as exc:
            logger.warning("[stream] pause error %d: %s", chat_id, exc)
            return False

    async def resume(self, chat_id: int) -> bool:
        try:
            await self.calls.resume_stream(chat_id)
            Q.get_state(chat_id)["status"] = "playing"
            return True
        except (NotInCallError, NoActiveGroupCall):
            return False
        except Exception as exc:
            logger.warning("[stream] resume error %d: %s", chat_id, exc)
            return False

    async def skip(self, chat_id: int) -> bool:
        """Skip current track and play next."""
        await self._cleanup_current(chat_id)
        return await self._play_next(chat_id)

    async def stop(self, chat_id: int, leave: bool = True) -> None:
        """Stop stream, optionally leave VC, full cleanup."""
        self._cancel_prefetch_timer(chat_id)
        await Q.wait_for_prefetch(chat_id)

        state = Q.get_state(chat_id)
        cleanup.full_cleanup_chat(state)

        try:
            if leave:
                await self.calls.leave_group_call(chat_id)
        except (NotInCallError, NoActiveGroupCall):
            pass
        except Exception as exc:
            logger.warning("[stream] leave VC error %d: %s", chat_id, exc)

        await nowplaying.delete_now_playing(self.bot, chat_id)
        Q.clear_queue(chat_id)
        Q.reset_state(chat_id)
        await mongo.clear_queue_backup(chat_id)
        logger.info("[stream] stopped and cleaned up chat %d", chat_id)

    def get_status(self, chat_id: int) -> str:
        return Q.get_state(chat_id).get("status", "idle")

    def active_chats(self) -> list:
        return [cid for cid, s in Q._chats.items() if s.get("status") != "idle"]

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _handle_song_end(self, chat_id: int) -> None:
        """Called by PyTgCalls when a track finishes naturally."""
        logger.info("[stream] song ended in chat %d", chat_id)
        self._cancel_prefetch_timer(chat_id)
        await self._cleanup_current(chat_id)
        await self._play_next(chat_id)

    async def _cleanup_current(self, chat_id: int) -> None:
        """Delete current file and free RAM."""
        self._cancel_prefetch_timer(chat_id)
        state = Q.get_state(chat_id)
        cleanup.cleanup_after_song(state.get("current_file"))
        state["current_file"] = None
        Q.pop_current(chat_id)

    async def _play_next(self, chat_id: int) -> bool:
        """Play the next track in queue. Returns True if started."""
        await Q.wait_for_prefetch(chat_id)

        next_track = Q.get_current(chat_id)
        if not next_track:
            # Queue empty
            await nowplaying.delete_now_playing(self.bot, chat_id)
            Q.get_state(chat_id)["status"] = "idle"
            try:
                await self.calls.leave_group_call(chat_id)
            except Exception:
                pass
            await mongo.clear_queue_backup(chat_id)
            logger.info("[stream] queue empty in chat %d — leaving VC", chat_id)
            return False

        state = Q.get_state(chat_id)

        # Use pre-downloaded file if available
        if state.get("prefetched_file") and os.path.exists(state["prefetched_file"]):
            next_track["file_path"] = state["prefetched_file"]
            state["prefetched_file"] = None
            logger.info("[stream] using pre-downloaded file for next track")
        else:
            # Pre-download wasn't ready — download now
            from core.downloader import download_audio
            logger.info("[stream] pre-download not ready, downloading now...")
            result = await download_audio(
                next_track["query"], chat_id, next_track["requested_by"]
            )
            if not result:
                logger.error("[stream] download failed for next track, skipping")
                Q.pop_current(chat_id)
                return await self._play_next(chat_id)
            next_track.update(result)

        return await self.play(chat_id, next_track)

    def _schedule_prefetch(self, chat_id: int, duration: int) -> None:
        """Schedule background prefetch PREFETCH_AT_SECONDS before end."""
        self._cancel_prefetch_timer(chat_id)

        delay = duration - Config.PREFETCH_AT_SECONDS
        if delay < 5:
            delay = 5  # minimum 5 second delay

        async def _trigger():
            await asyncio.sleep(delay)
            await Q.trigger_prefetch(chat_id)

        task = asyncio.create_task(_trigger())
        self._duration_tasks[chat_id] = task

    def _cancel_prefetch_timer(self, chat_id: int) -> None:
        task = self._duration_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
