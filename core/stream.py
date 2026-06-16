"""
core/stream.py — pytgcalls 2.2.1 verified API
  - leave_call()          (NOT leave_group_call)
  - MediaStream(path, audio_parameters=AudioQuality.HIGH)  (NOT audio_quality=)
  - on_update(fl.stream_end)  (on_stream_end() does NOT exist in 2.2.1)
  - pause(chat_id) / resume(chat_id) confirmed
"""
from __future__ import annotations

import asyncio
import logging
import os

from pyrogram import Client
from pytgcalls import PyTgCalls, filters as fl
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import AudioQuality, MediaStream

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

    async def start(self) -> None:
        @self.calls.on_update(fl.stream_end)
        async def _on_end(client, update):
            chat_id = getattr(update, "chat_id", None)
            if chat_id is not None:
                asyncio.create_task(self._handle_song_end(chat_id))

        await self.calls.start()
        logger.info("[stream] PyTgCalls 2.x started OK")

    # ── Public API ─────────────────────────────────────────────────────────────

    async def play(self, chat_id: int, track: dict) -> bool:
        file_path = track.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.error("[stream] file not found: %s", file_path)
            return False

        state = Q.get_state(chat_id)
        state["current_file"] = file_path
        state["status"] = "playing"

        try:
            # audio_parameters= (NOT audio_quality=) per 2.2.1 API
            await self.calls.play(
                chat_id,
                MediaStream(file_path, audio_parameters=AudioQuality.HIGH),
            )
            logger.info("[stream] playing '%s' in chat %d", track["title"], chat_id)
        except Exception as exc:
            logger.error("[stream] play() failed for %d: %s", chat_id, exc)
            state["status"] = "idle"
            return False

        self._schedule_prefetch(chat_id, track.get("duration", 0))
        await nowplaying.delete_now_playing(self.bot, chat_id)
        await nowplaying.send_now_playing(self.bot, chat_id, track)
        await Q.save_to_db(chat_id)
        return True

    async def pause(self, chat_id: int) -> bool:
        try:
            await self.calls.pause(chat_id)
            Q.get_state(chat_id)["status"] = "paused"
            return True
        except (NotInCallError, NoActiveGroupCall):
            return False
        except Exception as exc:
            logger.warning("[stream] pause error %d: %s", chat_id, exc)
            return False

    async def resume(self, chat_id: int) -> bool:
        try:
            await self.calls.resume(chat_id)
            Q.get_state(chat_id)["status"] = "playing"
            return True
        except (NotInCallError, NoActiveGroupCall):
            return False
        except Exception as exc:
            logger.warning("[stream] resume error %d: %s", chat_id, exc)
            return False

    async def skip(self, chat_id: int) -> bool:
        await self._cleanup_current(chat_id)
        return await self._play_next(chat_id)

    async def stop(self, chat_id: int, leave: bool = True) -> None:
        self._cancel_prefetch_timer(chat_id)
        await Q.wait_for_prefetch(chat_id)
        cleanup.full_cleanup_chat(Q.get_state(chat_id))
        if leave:
            try:
                await self.calls.leave_call(chat_id)   # leave_call() in 2.x
            except (NotInCallError, NoActiveGroupCall):
                pass
            except Exception as exc:
                logger.warning("[stream] leave_call error %d: %s", chat_id, exc)
        await nowplaying.delete_now_playing(self.bot, chat_id)
        Q.clear_queue(chat_id)
        Q.reset_state(chat_id)
        await mongo.clear_queue_backup(chat_id)
        logger.info("[stream] stopped chat %d", chat_id)

    def get_status(self, chat_id: int) -> str:
        return Q.get_state(chat_id).get("status", "idle")

    def active_chats(self) -> list:
        return [cid for cid, s in Q._chats.items() if s.get("status") != "idle"]

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _handle_song_end(self, chat_id: int) -> None:
        logger.info("[stream] song ended in chat %d", chat_id)
        self._cancel_prefetch_timer(chat_id)
        await self._cleanup_current(chat_id)
        await self._play_next(chat_id)

    async def _cleanup_current(self, chat_id: int) -> None:
        self._cancel_prefetch_timer(chat_id)
        state = Q.get_state(chat_id)
        cleanup.cleanup_after_song(state.get("current_file"))
        state["current_file"] = None
        Q.pop_current(chat_id)

    async def _play_next(self, chat_id: int) -> bool:
        await Q.wait_for_prefetch(chat_id)
        next_track = Q.get_current(chat_id)
        if not next_track:
            await nowplaying.delete_now_playing(self.bot, chat_id)
            Q.get_state(chat_id)["status"] = "idle"
            try:
                await self.calls.leave_call(chat_id)   # leave_call() in 2.x
            except Exception:
                pass
            await mongo.clear_queue_backup(chat_id)
            logger.info("[stream] queue empty in chat %d — leaving VC", chat_id)
            return False

        state = Q.get_state(chat_id)
        if state.get("prefetched_file") and os.path.exists(state["prefetched_file"]):
            next_track["file_path"] = state["prefetched_file"]
            state["prefetched_file"] = None
        else:
            from core.downloader import download_audio
            result = await download_audio(
                next_track["query"], chat_id, next_track["requested_by"]
            )
            if not result:
                Q.pop_current(chat_id)
                return await self._play_next(chat_id)
            next_track.update(result)

        return await self.play(chat_id, next_track)

    def _schedule_prefetch(self, chat_id: int, duration: int) -> None:
        self._cancel_prefetch_timer(chat_id)
        delay = max(duration - Config.PREFETCH_AT_SECONDS, 5)
        async def _trigger():
            await asyncio.sleep(delay)
            await Q.trigger_prefetch(chat_id)
        self._duration_tasks[chat_id] = asyncio.create_task(_trigger())

    def _cancel_prefetch_timer(self, chat_id: int) -> None:
        task = self._duration_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
