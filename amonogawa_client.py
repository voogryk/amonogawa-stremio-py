"""
Async client for amanogawa.space API.
Wraps all endpoints, handles pagination, basic in-memory caching.
"""

import time
from typing import Any

import httpx

BASE_URL = "https://amanogawa.space"
TIMEOUT = 10.0

# Simple TTL cache: {key: (data, expires_at)}
_cache: dict[str, tuple[Any, float]] = {}

CACHE_TTL_CATALOG = 300  # 5 min
CACHE_TTL_TITLE = 900  # 15 min
CACHE_TTL_EPISODES = 900  # 15 min


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    data, expires_at = entry
    if time.time() > expires_at:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: Any, ttl: float) -> None:
    _cache[key] = (data, time.time() + ttl)


async def get_catalog(page: int = 1) -> dict:
    """Fetch paginated catalog. Returns {"pages": N, "data": [...]}."""
    cache_key = f"catalog:{page}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/api/titles", params={"page": page})
        resp.raise_for_status()
        data = resp.json()

    _cache_set(cache_key, data, CACHE_TTL_CATALOG)
    return data


async def get_all_titles() -> list[dict]:
    """Fetch ALL titles from catalog (all pages). Cached for 5 min."""
    cache_key = "all_titles"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    all_titles: list[dict] = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/api/titles", params={"page": 1})
        resp.raise_for_status()
        first_page = resp.json()

        total_pages = first_page.get("pages", 1)
        all_titles.extend(first_page.get("data", []))

        for page in range(2, total_pages + 1):
            resp = await client.get("/api/titles", params={"page": page})
            resp.raise_for_status()
            all_titles.extend(resp.json().get("data", []))

    _cache_set(cache_key, all_titles, CACHE_TTL_CATALOG)
    return all_titles


async def get_title(title_id: int) -> dict:
    """Fetch single title detail. NB: endpoint is /api/title/ (singular)."""
    cache_key = f"title:{title_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get(f"/api/title/{title_id}")
        resp.raise_for_status()
        data = resp.json()

    _cache_set(cache_key, data, CACHE_TTL_TITLE)
    return data


async def get_episodes(title_id: int) -> list[dict]:
    """Fetch ALL episodes for a title (all pages). Returns flat list."""
    cache_key = f"episodes:{title_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    all_episodes: list[dict] = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # First page to get total pages count
        resp = await client.get(f"/api/episodes/{title_id}", params={"page": 1})
        resp.raise_for_status()
        first_page = resp.json()

        total_pages = first_page.get("pages", 1)
        all_episodes.extend(first_page.get("data", []))

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            resp = await client.get(
                f"/api/episodes/{title_id}", params={"page": page}
            )
            resp.raise_for_status()
            page_data = resp.json()
            all_episodes.extend(page_data.get("data", []))

    # Sort by episode number
    all_episodes.sort(key=lambda ep: ep.get("number", 0))

    _cache_set(cache_key, all_episodes, CACHE_TTL_EPISODES)
    return all_episodes


async def get_filters() -> dict:
    """Fetch available genres and years for filtering."""
    cache_key = "filters"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/api/filters")
        resp.raise_for_status()
        data = resp.json()

    _cache_set(cache_key, data, CACHE_TTL_CATALOG)
    return data
