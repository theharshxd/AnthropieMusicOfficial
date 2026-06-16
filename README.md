# 🎵 Anthropie Music Bot

Telegram Voice Chat music bot — Python, Pyrogram, PyTgCalls.  
Downloads audio fully before streaming → smooth, stutter-free playback.  
Pre-downloads next song while current plays → zero gap between tracks.

---

## Tech Stack

| Component | Library |
|---|---|
| Language | Python 3.11+ |
| Telegram Bot | Pyrogram 2.0 |
| Voice Chat | PyTgCalls |
| Audio | yt-dlp + ffmpeg |
| Database | MongoDB Atlas (Motor async) |
| Web server | Flask (health endpoint) |
| Event loop | uvloop (faster than asyncio) |

---

## How It Plays (No Stutter)

```
/play song  →  download to /tmp  →  stream from disk  →  pre-download next
                                                              ↓
                                          song ends → delete file → gc.collect()
                                                              ↓
                                              next song plays instantly (pre-downloaded)
```

---

## Setup

### Step 1 — Get Telegram credentials
1. Go to https://my.telegram.org → create an app → copy `API_ID` and `API_HASH`
2. Create a bot at @BotFather → copy `BOT_TOKEN`

### Step 2 — Generate Session String (assistant account)
Run this **once on your local machine** with a second Telegram account:
```bash
pip install pyrogram tgcrypto
python generate_session.py
```
Copy the printed `SESSION_STRING`.

### Step 3 — MongoDB Atlas
1. Go to https://cloud.mongodb.com → create free M0 cluster
2. Database Access → create user with password
3. Network Access → Add IP → `0.0.0.0/0` (allow all — required for Render)
4. Connect → Drivers → copy connection string
5. Replace `<password>` in the string with your DB user password

### Step 4 — Deploy to Render
1. Push this repo to GitHub
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Set these environment variables in Render dashboard:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your bot token |
| `API_ID` | Your API ID |
| `API_HASH` | Your API hash |
| `SESSION_STRING` | Generated session string |
| `OWNER_ID` | Your Telegram user ID |
| `SUDO_USERS` | Optional: `123,456` |
| `MONGO_URI` | MongoDB Atlas URI |
| `PYTHONUNBUFFERED` | `1` |
| `PYTHONOPTIMIZE` | `1` |

5. Build command: `pip install -r requirements.txt`
6. Start command: `python main.py`
7. Deploy!

### Step 5 — UptimeRobot (prevent Render sleep)
1. Go to https://uptimerobot.com → Add Monitor
2. Type: HTTP(s)
3. URL: `https://your-render-url.onrender.com/health`
4. Interval: 5 minutes
5. Save

---

## Commands

### Everyone
| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/play [name/URL]` | Play audio in Voice Chat |
| `/vplay [name/URL]` | Play video audio in Voice Chat |
| `/queue` | Show current queue |
| `/ping` | Check bot response time |

### Admins / Auth Users
| Command | Description |
|---|---|
| `/pause` | Pause stream |
| `/resume` | Resume stream |
| `/skip` | Skip to next song |
| `/end` | Stop stream, clear queue |
| `/stop` | Stop stream, leave Voice Chat |
| `/reload` | Refresh admin cache |
| `/auth [ID/reply]` | Authorise a user |
| `/unauth [ID/reply]` | Remove authorisation |
| `/authlist` | List authorised users |

### Sudo / Owner
| Command | Description |
|---|---|
| `/addsudo` | Add sudo user |
| `/delsudo` | Remove sudo user |
| `/sudolist` | List sudo users |
| `/stats` | Bot stats (RAM, CPU, uptime) |
| `/active` | Count active streams |
| `/broadcast` | Broadcast to all chats |
| `/restart` | Restart bot |
| `/update` | git pull + restart |

---

## Notes
- Queue limit: 10 songs per chat
- Audio files are deleted immediately after each song ends
- /tmp is scanned every 10 minutes for orphan files
- RAM is freed with `gc.collect()` after every song
- No thumbnails or links are ever sent (copyright compliance)
