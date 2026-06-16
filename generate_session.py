"""
generate_session.py
Run this ONCE locally to generate the SESSION_STRING for your assistant account.
Copy the printed string into your .env or Render environment variables.

Usage:
    python generate_session.py
"""

from pyrogram import Client

API_ID = int(input("Enter API_ID: ").strip())
API_HASH = input("Enter API_HASH: ").strip()

with Client(
    "session_gen",
    api_id=API_ID,
    api_hash=API_HASH,
) as app:
    session_string = app.export_session_string()
    print("\n" + "=" * 60)
    print("YOUR SESSION_STRING (copy this into .env or Render):")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    print("Delete the session_gen.session file after copying.\n")
