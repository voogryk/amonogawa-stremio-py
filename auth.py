"""One-time Pyrogram auth. Run interactively: python auth.py"""
import os
from dotenv import load_dotenv
from pyrogram import Client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = Client(
    name="amonogawa",
    api_id=int(os.getenv("TG_API_ID", "0")),
    api_hash=os.getenv("TG_API_HASH", ""),
    workdir=os.path.dirname(__file__) or ".",
)

with app:
    me = app.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username})")
    print("Session file created. You can now run the server.")
