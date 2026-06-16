"""
web/server.py
Minimal Flask web server.
Required by Render Free Tier (must bind an HTTP port).
UptimeRobot pings /health every 5 min to prevent sleep.
"""

import logging

from flask import Flask, jsonify

from config import Config

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "Anthropie Music Bot"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


def run_web_server() -> None:
    """Run Flask in blocking mode — call from a background thread."""
    logger.info("[web] starting health server on port %d", Config.PORT)
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=False,
        use_reloader=False,   # must be False when running in a thread
    )
