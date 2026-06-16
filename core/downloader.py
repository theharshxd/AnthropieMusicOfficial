"""
core/downloader.py
Downloads audio from YouTube to /tmp using yt-dlp.
Returns a track dict or None on failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from config import Config

logger = logging.getLogger(__name__)


async def download_audio(
    query: str,
    chat_id: int,
    requested_by: str,
    retries: int = 1,
) -> dict | None:
    """
    Download audio for `query` into Config.TMP_DIR.
    Returns track dict or None if failed after retries.

    Track dict keys:
        title         str
        duration      int   (seconds)
        duration_str  str   (mm:ss)
        file_path     str   (absolute path to downloaded file)
        query         str   (original query — used for re-download on skip)
        requested_by  str
        chat_id       int
    """
    for attempt in range(retries + 1):
        result = await _do_download(query, chat_id, requested_by)
        if result is not None:
            return result
        if attempt < retries:
            logger.warning(
                "[downloader] attempt %d failed for '%s', retrying...", attempt + 1, query
            )
            await asyncio.sleep(2)

    logger.error("[downloader] all attempts failed for '%s'", query)
    return None


async def _do_download(query: str, chat_id: int, requested_by: str) -> dict | None:
    timestamp = int(time.time())
    out_template = os.path.join(
        Config.TMP_DIR, f"am_{chat_id}_{timestamp}.%(ext)s"
    )

    # Build yt-dlp command
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--no-part",                 # no .part temp files
        "--no-mtime",
        "--no-write-thumbnail",      # no thumbnail (copyright)
        "--no-write-info-json",
        "--no-write-description",
        "--no-write-annotations",
        "--format", Config.YTDLP_FORMAT,
        "--output", out_template,
        "--print", "%(title)s|||%(duration)s",   # print metadata before download
    ]

    # Treat as search query if not a URL
    if not query.startswith("http://") and not query.startswith("https://"):
        cmd.append(f"ytsearch1:{query}")
    else:
        cmd.append(query)

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=Config.MAX_DOWNLOAD_TIMEOUT,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=Config.MAX_DOWNLOAD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("[downloader] yt-dlp timed out for '%s'", query)
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as exc:
        logger.error("[downloader] yt-dlp error for '%s': %s", query, exc)
        return None

    if proc.returncode != 0:
        err = stderr.decode(errors="ignore").strip()
        logger.error("[downloader] yt-dlp exited %d: %s", proc.returncode, err)
        return None

    # Parse metadata line
    meta_line = stdout.decode(errors="ignore").strip().splitlines()
    title = "Unknown Title"
    duration = 0
    if meta_line:
        parts = meta_line[0].split("|||")
        title = parts[0].strip() if parts else "Unknown Title"
        try:
            duration = int(parts[1].strip()) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            duration = 0

    # Find downloaded file
    file_path = _find_downloaded_file(chat_id, timestamp)
    if not file_path:
        logger.error("[downloader] could not find downloaded file for '%s'", query)
        return None

    logger.info(
        "[downloader] downloaded '%s' → %s (%.1f MB)",
        title,
        file_path,
        os.path.getsize(file_path) / (1024 * 1024),
    )

    return {
        "title": title,
        "duration": duration,
        "duration_str": _fmt_duration(duration),
        "file_path": file_path,
        "query": query,
        "requested_by": requested_by,
        "chat_id": chat_id,
    }


def _find_downloaded_file(chat_id: int, timestamp: int) -> str | None:
    """Locate the file yt-dlp created (extension varies)."""
    prefix = f"am_{chat_id}_{timestamp}"
    try:
        for fname in os.listdir(Config.TMP_DIR):
            if fname.startswith(prefix):
                full = os.path.join(Config.TMP_DIR, fname)
                if os.path.isfile(full) and os.path.getsize(full) > 0:
                    return full
    except Exception as exc:
        logger.error("[downloader] file search error: %s", exc)
    return None


def _fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
