"""
Telegram streaming bridge.
Uses Pyrogram to request video from @amanogawa_ua_bot and stream it via HTTP.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import AsyncGenerator

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.types import Message

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

log = logging.getLogger("tg-stream")

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_DIR = os.path.dirname(__file__)
BOT_USERNAME = "amanogawa_ua_bot"

CHUNK_SIZE = 1024 * 1024  # 1 MiB — Pyrogram's internal chunk size

# Cache: bot_id -> (Message, file_size, timestamp)
_msg_cache: dict[int, tuple[Message, int, float]] = {}
CACHE_TTL = 3600  # 1 hour

# Pyrogram client — initialized once at startup
_client: Client | None = None


async def get_client() -> Client:
    """Get or create the Pyrogram client."""
    global _client
    if _client is None:
        _client = Client(
            name="amonogawa",
            api_id=API_ID,
            api_hash=API_HASH,
            workdir=SESSION_DIR,
        )
    if not _client.is_connected:
        await _client.start()
        log.info("Pyrogram client connected")
    return _client


async def stop_client():
    """Stop the Pyrogram client gracefully."""
    global _client
    if _client and _client.is_connected:
        await _client.stop()


async def get_video_message(episode_bot_id: int) -> tuple[Message, int] | None:
    """
    Request a video from @amanogawa_ua_bot for a specific episode.
    Sends /start sep_{bot_id} and waits for the bot's video response.
    Returns (Message, file_size) or None if failed.
    """
    # Check cache
    cached = _msg_cache.get(episode_bot_id)
    if cached and time.time() - cached[2] < CACHE_TTL:
        log.info(f"Cache hit for bot_id {episode_bot_id}")
        return cached[0], cached[1]

    client = await get_client()

    try:
        # Record time BEFORE sending — only accept responses after this
        # Pyrogram msg.date is naive UTC, so we use utcnow() for comparison
        before_send = datetime.utcnow()

        # Send /start command with deep link parameter
        deep_link = f"/start sep_{episode_bot_id}"
        log.info(f"Sending to @{BOT_USERNAME}: {deep_link}")
        await client.send_message(BOT_USERNAME, deep_link)

        # Wait for bot response
        video_msg = await _wait_for_video(client, after=before_send, timeout=30)

        if video_msg is None:
            log.warning(f"No video received for bot_id {episode_bot_id}")
            return None

        # Extract file info
        video = video_msg.video or video_msg.document
        if video is None:
            log.warning(f"Message has no video/document for bot_id {episode_bot_id}")
            return None

        file_size = video.file_size or 0

        # Cache the full message object
        _msg_cache[episode_bot_id] = (video_msg, file_size, time.time())
        log.info(
            f"Got video for bot_id {episode_bot_id}: "
            f"size={file_size} ({file_size / 1024 / 1024:.1f} MB), "
            f"file_id={video.file_id[:20]}..."
        )
        return video_msg, file_size

    except Exception as e:
        log.error(f"Failed to get video for bot_id {episode_bot_id}: {e}", exc_info=True)
        return None


async def _wait_for_video(
    client: Client, after: datetime, timeout: int = 30
) -> Message | None:
    """Wait for a video message from the bot sent AFTER the given timestamp."""
    start = time.time()

    while time.time() - start < timeout:
        await asyncio.sleep(1.5)

        try:
            async for msg in client.get_chat_history(BOT_USERNAME, limit=5):
                # Skip our own messages
                if msg.outgoing:
                    continue
                # Only accept messages after our command was sent
                if msg.date and msg.date < after:
                    break  # older messages — stop looking
                if msg.video or msg.document:
                    log.info(f"Found video message: msg_id={msg.id}, date={msg.date}")
                    return msg
        except Exception as e:
            log.warning(f"Error polling chat history: {e}")

    return None


async def stream_video(
    message: Message, byte_offset: int = 0
) -> AsyncGenerator[bytes, None]:
    """
    Stream a video file from Telegram in chunks.

    byte_offset: byte position to start from (for HTTP Range requests).
    Pyrogram's stream_media uses chunk-based offset (1 MiB chunks),
    so we convert and handle partial first chunk.
    """
    client = await get_client()

    # Convert byte offset to chunk offset
    chunk_offset = byte_offset // CHUNK_SIZE
    skip_bytes = byte_offset % CHUNK_SIZE  # bytes to skip in first chunk

    log.info(
        f"Streaming: byte_offset={byte_offset}, chunk_offset={chunk_offset}, "
        f"skip_bytes_in_first_chunk={skip_bytes}"
    )

    bytes_sent = 0
    first_chunk = True

    try:
        async for chunk in client.stream_media(message, offset=chunk_offset):
            if first_chunk and skip_bytes > 0:
                chunk = chunk[skip_bytes:]
                first_chunk = False
            first_chunk = False

            bytes_sent += len(chunk)
            yield chunk
    except Exception as e:
        log.error(f"Stream error after {bytes_sent} bytes: {e}", exc_info=True)
    finally:
        log.info(f"Stream done: {bytes_sent} bytes sent ({bytes_sent / 1024 / 1024:.1f} MB)")
