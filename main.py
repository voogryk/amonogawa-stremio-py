"""
Amonogawa Stremio Addon — FastAPI server.
Serves Ukrainian-dubbed anime catalog from amanogawa.space via Stremio protocol.
Streams video from Telegram via Pyrogram proxy.

Run: uvicorn main:app --host 0.0.0.0 --port 7000
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import amonogawa_client as api
import stremio
import telegram_stream as tg

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amonogawa-addon")

BASE_URL = os.getenv("BASE_URL", "http://localhost:7000")

app = FastAPI(title="Amonogawa Stremio Addon")

# Stremio requires CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ITEMS_PER_PAGE = 10  # Amonogawa returns 10 per page


@app.get("/manifest.json")
async def manifest():
    return stremio.build_manifest()


@app.get("/catalog/{type}/{catalog_id}.json")
async def catalog(type: str, catalog_id: str):
    return await _get_catalog(type, catalog_id, skip=0)


@app.get("/catalog/{type}/{catalog_id}/skip={skip}.json")
async def catalog_with_skip(type: str, catalog_id: str, skip: int):
    return await _get_catalog(type, catalog_id, skip=skip)


@app.get("/catalog/{type}/{catalog_id}/search={query}.json")
async def catalog_search(type: str, catalog_id: str, query: str):
    """Search across all titles. Loads full catalog and filters by name."""
    is_movie = type == "movie"
    query_lower = query.lower()

    try:
        all_titles = await api.get_all_titles()
    except Exception as e:
        log.error(f"Failed to fetch all titles for search: {e}")
        return {"metas": []}

    # Filter by type + name match (Ukrainian name OR en/jp name)
    filtered = []
    for t in all_titles:
        if t.get("is_movie", False) != is_movie:
            continue
        name = (t.get("name") or "").lower()
        en_jp = (t.get("en_jp_name") or "").lower()
        if query_lower in name or query_lower in en_jp:
            filtered.append(t)

    metas = [stremio.to_catalog_meta(t) for t in filtered]
    return {"metas": metas}


async def _get_catalog(type: str, catalog_id: str, skip: int) -> dict:
    """Shared catalog logic. Fetches from Amonogawa and filters by type."""
    page = (skip // ITEMS_PER_PAGE) + 1
    is_movie = type == "movie"

    try:
        data = await api.get_catalog(page)
    except Exception as e:
        log.error(f"Failed to fetch catalog page {page}: {e}")
        return {"metas": []}

    titles = data.get("data", [])

    # Filter by series/movie
    filtered = [t for t in titles if t.get("is_movie", False) == is_movie]

    metas = [stremio.to_catalog_meta(t) for t in filtered]
    return {"metas": metas}


@app.get("/meta/{type}/{id}.json")
async def meta(type: str, id: str):
    # Parse ID: "amngw:133" → 133
    title_id = _parse_title_id(id)
    if title_id is None:
        return {"meta": None}

    try:
        title = await api.get_title(title_id)
    except Exception as e:
        log.error(f"Failed to fetch title {title_id}: {e}")
        return {"meta": None}

    # Fetch episodes for series
    episodes = []
    if not title.get("is_movie", False):
        try:
            episodes = await api.get_episodes(title_id)
        except Exception as e:
            log.error(f"Failed to fetch episodes for {title_id}: {e}")

    meta_obj = stremio.to_meta(title, episodes)
    return {"meta": meta_obj}


@app.get("/stream/{type}/{id}.json")
async def stream(type: str, id: str):
    # Parse ID: "amngw:133:1" → title_id=133, episode=1
    # or "amngw:133" → title_id=133, episode=None
    title_id, episode_num = _parse_stream_id(id)
    if title_id is None:
        return {"streams": []}

    try:
        title = await api.get_title(title_id)
    except Exception as e:
        log.error(f"Failed to fetch title {title_id} for stream: {e}")
        return {"streams": []}

    # Find the episode's bot_id for Telegram streaming
    episode_bot_id = None
    if episode_num is not None:
        try:
            episodes = await api.get_episodes(title_id)
            for ep in episodes:
                if ep.get("number") == episode_num:
                    episode_bot_id = ep.get("bot_id")
                    break
        except Exception as e:
            log.error(f"Failed to fetch episodes for stream: {e}")

    streams = stremio.to_streams(title, episode_num, episode_bot_id, BASE_URL)
    return {"streams": streams}


@app.get("/tg/stream/{episode_bot_id}")
async def tg_stream(episode_bot_id: int, request: Request):
    """Proxy-stream a video from Telegram to HTTP."""
    result = await tg.get_video_message(episode_bot_id)
    if result is None:
        return {"error": "Video not found"}

    message, file_size = result

    # Handle Range requests for seeking
    range_header = request.headers.get("range")
    byte_offset = 0
    if range_header and range_header.startswith("bytes="):
        byte_offset = int(range_header.split("=")[1].split("-")[0])

    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
    }
    if file_size and byte_offset:
        headers["Content-Range"] = f"bytes {byte_offset}-{file_size - 1}/{file_size}"
        headers["Content-Length"] = str(file_size - byte_offset)
        status_code = 206
    elif file_size:
        headers["Content-Length"] = str(file_size)
        status_code = 200
    else:
        status_code = 200

    return StreamingResponse(
        tg.stream_video(message, byte_offset=byte_offset),
        status_code=status_code,
        headers=headers,
        media_type="video/mp4",
    )


@app.on_event("shutdown")
async def shutdown():
    await tg.stop_client()


def _parse_title_id(stremio_id: str) -> int | None:
    """Parse 'amngw:133' → 133."""
    if not stremio_id.startswith(stremio.ID_PREFIX):
        return None
    try:
        return int(stremio_id[len(stremio.ID_PREFIX):])
    except ValueError:
        return None


def _parse_stream_id(stremio_id: str) -> tuple[int | None, int | None]:
    """Parse 'amngw:133:1' → (133, 1) or 'amngw:133' → (133, None)."""
    if not stremio_id.startswith(stremio.ID_PREFIX):
        return None, None
    rest = stremio_id[len(stremio.ID_PREFIX):]
    parts = rest.split(":")
    try:
        title_id = int(parts[0])
        episode_num = int(parts[1]) if len(parts) > 1 else None
        return title_id, episode_num
    except (ValueError, IndexError):
        return None, None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7000)
