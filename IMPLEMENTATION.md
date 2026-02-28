# Amonogawa Stremio Addon — MVP Implementation Plan

## Goal

Build a Stremio addon that serves Ukrainian-dubbed anime catalog from amanogawa.space. MVP = catalog browsing + metadata + torrent links. No Telegram streaming yet.

## Tech Stack

- **Python 3.12** + **FastAPI** + **uvicorn**
- **httpx** (async HTTP client for Amonogawa API)
- No database — all data proxied from Amonogawa API in real-time
- Venv already exists at `.venv/`

## Project Structure

```
/home/nosjr/endgame/amonogawa/
├── IMPLEMENTATION.md    ← this file
├── scraper.py           ← existing research scraper (can ignore)
├── .venv/               ← Python venv
├── main.py              ← FastAPI app entry point
├── amonogawa_client.py  ← async client for amanogawa.space API
└── stremio.py           ← Stremio response builders (data mapping)
```

## Amonogawa API (already discovered, no auth needed)

Base URL: `https://amanogawa.space`

| Endpoint | Returns |
|----------|---------|
| `GET /api/titles?page=N` | Paginated catalog (10 per page, 17 pages) |
| `GET /api/title/{id}` | Title detail (NB: singular!) |
| `GET /api/episodes/{id}?page=N` | Episode list (paginated) |
| `GET /api/titles/current` | Currently airing |
| `GET /api/filters` | Genres + years |

### Title object (from `/api/title/133`):
```json
{
  "id": 133,
  "name": "Дандадан",
  "en_jp_name": "Dandadan",
  "descrition": "...",
  "year": 2024,
  "duration": "~ 23 хв.",
  "company": "Science SARU",
  "director": "Ямашіро Фууґа",
  "episodes_total": "12",
  "season": 1,
  "part": 0,
  "torrent_url": "https://toloka.to/t682007",
  "torrent_4k_url": null,
  "is_movie": false,
  "poster": "/media/images/posters/2025/133.jpg",
  "poster_thumb": "/media/images/posters/2025/posters_thumbs/133.jpg",
  "genres_f": [[11, "бойовик"], [1, "комедія"]],
  "voices_f": [[9, "Alisand"], [1, "Bodya500icq"], ...],
  "group_f": [{"id": 156, "name": "Дандадан", "season": 1, ...}]
}
```

### Episode object (from `/api/episodes/133`):
```json
{
  "pages": 3,
  "data": [
    {
      "id": 1489,
      "name": "Ось, як має зароджуватись кохання",
      "number": 1,
      "bot_id": 1444,
      "title_id": 133,
      "is_ova": false,
      "is_extra": false,
      "screen": "/media/images/episodes/2024/episode_133_1.jpg"
    }
  ],
  "bot_url": "https://t.me/amanogawa_ua_bot"
}
```

### Catalog item (from `/api/titles?page=1`):
```json
{
  "id": 133,
  "name": "Дандадан",
  "en_jp_name": "Dandadan",
  "is_current": false,
  "is_movie": false,
  "episodes_total": "12",
  "year": 2024,
  "season": 1,
  "views": 34736,
  "poster_thumb": "/media/images/posters/2025/posters_thumbs/133.jpg",
  "poster_mini": "/media/images/posters/2025/posters_mini/133.jpg",
  "schedule": "Проєкт завершено!"
}
```

## Stremio Addon Protocol — what to implement

Stremio addon is a simple HTTP server. Stremio app calls our endpoints and expects JSON responses.

### Endpoint 1: `GET /manifest.json`

```json
{
  "id": "com.amonogawa.stremio",
  "version": "0.1.0",
  "name": "Amonogawa UA",
  "description": "Українське аніме від Амоногава",
  "logo": "https://amanogawa.space/media/images/posters/2025/posters_mini/133.jpg",
  "types": ["series", "movie"],
  "catalogs": [
    {
      "type": "series",
      "id": "amonogawa-series",
      "name": "Amonogawa — Серіали",
      "extra": [
        {"name": "skip"}
      ]
    },
    {
      "type": "movie",
      "id": "amonogawa-movies",
      "name": "Amonogawa — Фільми",
      "extra": [
        {"name": "skip"}
      ]
    }
  ],
  "resources": ["catalog", "meta", "stream"],
  "idPrefixes": ["amngw:"]
}
```

Notes:
- `idPrefixes` tells Stremio to only ask us about IDs starting with `amngw:`
- Two catalogs: series (is_movie=false) and movies (is_movie=true)
- `skip` extra enables pagination

### Endpoint 2: `GET /catalog/{type}/{id}.json` and `GET /catalog/{type}/{id}/skip={N}.json`

Maps to Amonogawa: `GET /api/titles?page=N` (where page = skip/10 + 1)

Filter by `is_movie` based on `{type}` (series vs movie).

Response:
```json
{
  "metas": [
    {
      "id": "amngw:133",
      "type": "series",
      "name": "Дандадан",
      "poster": "https://amanogawa.space/media/images/posters/2025/posters_thumbs/133.jpg",
      "description": "2024 • 12 епізодів • Проєкт завершено!",
      "year": 2024
    }
  ]
}
```

Mapping:
- `id` → `"amngw:" + str(amonogawa_id)`
- `type` → `"movie"` if `is_movie` else `"series"`
- `name` → `name` (Ukrainian title)
- `poster` → `"https://amanogawa.space" + poster_thumb`
- Catalog items don't have full description — use schedule + year + episodes_total

### Endpoint 3: `GET /meta/{type}/{id}.json`

Parse `{id}` → strip `amngw:` prefix → get numeric ID.

Fetch from Amonogawa:
1. `GET /api/title/{id}` — title detail
2. `GET /api/episodes/{id}?page=1` through `?page=N` — ALL episodes (loop through pages)

Response:
```json
{
  "meta": {
    "id": "amngw:133",
    "type": "series",
    "name": "Дандадан",
    "description": "Старшокласниця Момо Аясе побилась об заклад...",
    "year": 2024,
    "poster": "https://amanogawa.space/media/images/posters/2025/133.jpg",
    "background": "https://amanogawa.space/media/images/titles_screens/2024/title_screen_1WV2eFO.jpg",
    "genres": ["бойовик", "комедія", "надприродне"],
    "director": ["Ямашіро Фууґа"],
    "runtime": "~ 23 хв.",
    "videos": [
      {
        "id": "amngw:133:1",
        "title": "Серія 1 — Ось, як має зароджуватись кохання",
        "season": 1,
        "episode": 1,
        "thumbnail": "https://amanogawa.space/media/images/episodes/2024/episode_133_1.jpg",
        "released": "2024-10-04T00:43:36Z"
      },
      {
        "id": "amngw:133:2",
        "title": "Серія 2 — Це ж космічний прибулець, бляха!",
        "season": 1,
        "episode": 2
      }
    ]
  }
}
```

Mapping:
- `description` → title's `descrition` field (yes, their typo)
- `poster` → full-size poster (not thumb)
- `background` → first screenshot from `screens_f[0][0]`
- `genres` → extract names from `genres_f` array
- `videos` → built from episodes. Each video:
  - `id` → `"amngw:{title_id}:{episode_number}"`
  - `title` → `"Серія {number} — {name}"` (or `"OVA — {name}"` if is_ova)
  - `season` → title's `season` field (use `part` if > 0 as second digit?)
  - `episode` → episode's `number`
  - `thumbnail` → `"https://amanogawa.space" + episode.screen`
  - `released` → episode's `post_date`

For movies (`is_movie=true`), skip `videos` array — Stremio treats movies as single-stream items.

### Endpoint 4: `GET /stream/{type}/{id}.json`

Parse `{id}`:
- For series: `"amngw:133:1"` → title_id=133, episode=1
- For movies: `"amngw:133"` → title_id=133

MVP stream: return `externalUrl` pointing to Toloka torrent page. This opens the browser — not ideal but works for MVP.

```json
{
  "streams": [
    {
      "externalUrl": "https://toloka.to/t682007",
      "title": "Toloka torrent (весь сезон)"
    }
  ]
}
```

Note: `torrent_url` is per-title (whole season), not per-episode. So all episodes of the same title return the same torrent link.

**Future improvement**: scrape Toloka for magnet link → use `infoHash` + `fileIdx` for per-episode torrent streaming natively in Stremio.

## Implementation Steps (in order)

### Step 1: Setup
```bash
cd /home/nosjr/endgame/amonogawa
source .venv/bin/activate
pip install fastapi uvicorn httpx
```

### Step 2: `amonogawa_client.py`
Async client class wrapping all Amonogawa API calls:
- `get_catalog(page: int) -> dict` — `/api/titles?page=N`
- `get_title(id: int) -> dict` — `/api/title/{id}`
- `get_episodes(id: int) -> list[dict]` — all pages of `/api/episodes/{id}`, returns flat list
- `get_filters() -> dict` — `/api/filters`
- Use httpx.AsyncClient with base_url, timeouts, and simple error handling
- Cache responses in-memory with TTL (e.g., 5 min for catalog, 15 min for title detail)

### Step 3: `stremio.py`
Pure mapping functions (no I/O):
- `to_catalog_meta(title: dict) -> dict` — map Amonogawa title to Stremio catalog item
- `to_meta(title: dict, episodes: list[dict]) -> dict` — map to full Stremio meta object
- `to_stream(title: dict, episode_num: int | None) -> dict` — build stream response
- `build_manifest() -> dict` — return static manifest

### Step 4: `main.py`
FastAPI app with these routes:
- `GET /manifest.json` → return manifest
- `GET /catalog/{type}/{catalog_id}.json` → catalog without skip
- `GET /catalog/{type}/{catalog_id}/skip={skip}.json` → catalog with pagination
- `GET /meta/{type}/{id}.json` → title + episodes
- `GET /stream/{type}/{id}.json` → torrent link
- CORS middleware (Stremio needs it): allow all origins

### Step 5: Run & Test
```bash
cd /home/nosjr/endgame/amonogawa
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 7000
```

Test in browser:
- `http://localhost:7000/manifest.json`
- `http://localhost:7000/catalog/series/amonogawa-series.json`
- `http://localhost:7000/meta/series/amngw:133.json`
- `http://localhost:7000/stream/series/amngw:133:1.json`

Install in Stremio: open `stremio://localhost:7000/manifest.json` or add URL manually in Stremio settings.

## Edge Cases to Handle

- Amonogawa API might be slow → set 10s timeout, return empty on failure
- Some titles may not have `torrent_url` → return empty streams array
- Episode pagination: fetch ALL pages, not just first
- `is_movie` titles: no episodes list, stream ID format is `amngw:{id}` (no episode number)
- Poster/image paths are relative → always prepend `https://amanogawa.space`
- CORS headers are mandatory — Stremio web and desktop apps need them

## What MVP Does NOT Include (future work)

- Search (need to check if Amonogawa API has search endpoint)
- Genre/year filtering
- Magnet link extraction from Toloka (requires Toloka scraping)
- Telegram bot streaming
- Caching persistence (just in-memory for now)
- Franchise grouping
- OVA/Extra episodes handling (include them but no special treatment)
