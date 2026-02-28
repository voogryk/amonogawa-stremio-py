"""
Stremio response builders.
Pure mapping functions — no I/O, no API calls.
Transforms Amonogawa API data into Stremio addon protocol format.
"""

BASE_URL = "https://amanogawa.space"
ID_PREFIX = "amngw:"


def build_manifest() -> dict:
    return {
        "id": "com.amonogawa.stremio",
        "version": "0.1.0",
        "name": "Amonogawa UA",
        "description": "Українське аніме від Амоногава",
        "logo": f"{BASE_URL}/media/images/posters/2025/posters_mini/133.jpg",
        "types": ["series", "movie"],
        "catalogs": [
            {
                "type": "series",
                "id": "amonogawa-series",
                "name": "Amonogawa — Серіали",
                "extra": [{"name": "search"}, {"name": "skip"}],
            },
            {
                "type": "movie",
                "id": "amonogawa-movies",
                "name": "Amonogawa — Фільми",
                "extra": [{"name": "search"}, {"name": "skip"}],
            },
        ],
        "resources": ["catalog", "meta", "stream"],
        "idPrefixes": [ID_PREFIX],
    }


def to_catalog_meta(title: dict) -> dict:
    """Map an Amonogawa catalog item to a Stremio catalog meta object."""
    title_type = "movie" if title.get("is_movie") else "series"
    year = title.get("year", "")
    episodes = title.get("episodes_total", "")
    schedule = title.get("schedule", "")

    # Build short description from available fields
    parts = []
    if year:
        parts.append(str(year))
    if episodes and title_type == "series":
        parts.append(f"{episodes} еп.")
    if schedule:
        parts.append(schedule)
    description = " • ".join(parts)

    poster = title.get("poster_thumb") or title.get("poster_mini", "")
    if poster and not poster.startswith("http"):
        poster = BASE_URL + poster

    # Build display name with season/part/year to disambiguate
    name = title.get("name", title.get("en_jp_name", "Unknown"))
    season = title.get("season", 0)
    part = title.get("part", 0)

    suffix_parts = []
    if season and season > 1:
        suffix_parts.append(f"Сезон {season}")
    if part and part > 0:
        suffix_parts.append(f"Ч.{part}")
    if not suffix_parts and year:
        # No season/part info — use year to disambiguate same-name titles
        suffix_parts.append(str(year))

    if suffix_parts:
        name = f"{name} ({', '.join(suffix_parts)})"

    return {
        "id": f"{ID_PREFIX}{title['id']}",
        "type": title_type,
        "name": name,
        "poster": poster,
        "description": description,
        "year": year if year else None,
    }


def to_meta(title: dict, episodes: list[dict]) -> dict:
    """Map Amonogawa title + episodes to a full Stremio meta object."""
    title_id = title["id"]
    title_type = "movie" if title.get("is_movie") else "series"
    season = title.get("season", 1)

    # Full poster
    poster = title.get("poster", "")
    if poster and not poster.startswith("http"):
        poster = BASE_URL + poster

    # Background from first screenshot
    background = None
    screens = title.get("screens_f", [])
    if screens and len(screens) > 0:
        background = screens[0][0]  # full-size screenshot
        if background and not background.startswith("http"):
            background = BASE_URL + background

    # Genres
    genres = [g[1] for g in title.get("genres_f", []) if len(g) > 1]

    # Director
    director = title.get("director")
    directors = [director] if director else []

    # Videos (episodes)
    videos = []
    for ep in episodes:
        ep_number = ep.get("number", 0)
        ep_name = ep.get("name", "")

        # Build episode title
        if ep.get("is_ova"):
            video_title = f"OVA — {ep_name}" if ep_name else "OVA"
        elif ep.get("is_extra"):
            video_title = f"Екстра — {ep_name}" if ep_name else "Екстра"
        else:
            video_title = f"Серія {ep_number} — {ep_name}" if ep_name else f"Серія {ep_number}"

        # Thumbnail
        thumb = ep.get("screen", "")
        if thumb and not thumb.startswith("http"):
            thumb = BASE_URL + thumb

        video = {
            "id": f"{ID_PREFIX}{title_id}:{ep_number}",
            "title": video_title,
            "season": season,
            "episode": ep_number,
        }
        if thumb:
            video["thumbnail"] = thumb
        if ep.get("post_date"):
            video["released"] = ep["post_date"]

        videos.append(video)

    # Build display name with season/part disambiguation (same as catalog)
    name = title.get("name", title.get("en_jp_name", "Unknown"))
    part = title.get("part", 0)
    year = title.get("year")

    suffix_parts = []
    if season and season > 1:
        suffix_parts.append(f"Сезон {season}")
    if part and part > 0:
        suffix_parts.append(f"Ч.{part}")
    if not suffix_parts and year:
        suffix_parts.append(str(year))

    if suffix_parts:
        name = f"{name} ({', '.join(suffix_parts)})"

    # releaseInfo — shown as subtitle in Stremio UI
    release_parts = []
    if year:
        release_parts.append(str(year))
    if season and season > 0:
        release_parts.append(f"Сезон {season}")
    if part and part > 0:
        release_parts.append(f"Ч.{part}")
    release_info = " • ".join(release_parts) if release_parts else None

    meta = {
        "id": f"{ID_PREFIX}{title_id}",
        "type": title_type,
        "name": name,
        "description": title.get("descrition", ""),  # their typo
        "year": year,
        "poster": poster,
        "genres": genres,
        "runtime": title.get("duration", ""),
    }

    if release_info:
        meta["releaseInfo"] = release_info
    if background:
        meta["background"] = background
    if directors:
        meta["director"] = directors
    if videos and title_type == "series":
        meta["videos"] = videos

    return meta


def to_streams(
    title: dict,
    episode_num: int | None = None,
    episode_bot_id: int | None = None,
    base_url: str = "",
) -> list[dict]:
    """Build stream list for a title (and optionally specific episode)."""
    streams = []

    # Telegram stream (primary — actual playback)
    if episode_bot_id and base_url:
        streams.append(
            {
                "url": f"{base_url}/tg/stream/{episode_bot_id}",
                "title": "🇺🇦 Amonogawa (Telegram)",
                "behaviorHints": {"notWebReady": True},
            }
        )

    # Toloka torrents (fallback)
    torrent_url = title.get("torrent_url")
    torrent_4k_url = title.get("torrent_4k_url")

    if torrent_url:
        streams.append(
            {
                "externalUrl": torrent_url,
                "title": "🇺🇦 Toloka torrent (весь сезон)",
            }
        )

    if torrent_4k_url:
        streams.append(
            {
                "externalUrl": torrent_4k_url,
                "title": "🇺🇦 Toloka torrent 4K (весь сезон)",
            }
        )

    return streams
