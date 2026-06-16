import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def _int_list(key: str) -> list:
    raw = os.getenv(key, "")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


class Config:
    # Telegram
    BOT_TOKEN: str = _require("BOT_TOKEN")
    API_ID: int = int(_require("API_ID"))
    API_HASH: str = _require("API_HASH")
    SESSION_STRING: str = _require("SESSION_STRING")

    # Owner / Sudo
    OWNER_ID: int = int(_require("OWNER_ID"))
    SUDO_USERS: list = _int_list("SUDO_USERS")

    # MongoDB
    MONGO_URI: str = _require("MONGO_URI")
    DB_NAME: str = os.getenv("DB_NAME", "anthropie_music")

    # Web server — Render sets PORT automatically
    PORT: int = int(os.getenv("PORT", "8080"))

    # Queue
    QUEUE_LIMIT: int = 10

    # Download
    TMP_DIR: str = "/tmp"
    MAX_DOWNLOAD_TIMEOUT: int = 60       # seconds before yt-dlp killed
    PREFETCH_AT_SECONDS: int = 30        # pre-download next song when X secs left
    ORPHAN_MAX_AGE: int = 900            # 15 min — delete leftover files
    CLEANUP_INTERVAL: int = 600          # run orphan scan every 10 min

    # ffmpeg
    FFMPEG_THREADS: str = "1"
    AUDIO_BITRATE: str = "48000"
    AUDIO_CHANNELS: str = "2"

    # yt-dlp audio format preference
    YTDLP_FORMAT: str = (
        "bestaudio[ext=opus]/bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio"
    )
