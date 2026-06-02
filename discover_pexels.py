"""Recherche Pexels + téléchargement + stockage pour les propositions Discover."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from discover_media_storage import store_discover_image

load_dotenv()

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
_PEXELS_HEADERS_BASE = {"User-Agent": "TerraCogitia/1.0"}
_KEYWORD_MIN_LEN = 2
_KEYWORD_MAX_PER_SECTION = 5
_IMAGES_MAX_PER_SECTION = 5


def normalize_keyword(raw: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", (raw or "").strip())
    if len(t) < _KEYWORD_MIN_LEN:
        return None
    if len(t) > 80:
        t = t[:80].strip()
    return t


def normalize_keywords_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    items: List[str] = []
    if isinstance(raw, str):
        items = re.split(r"[,;\n]+", raw)
    elif isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                items.append(x)
            elif isinstance(x, dict):
                for k in ("mot", "mot_cle", "keyword", "label", "texte", "text"):
                    v = x.get(k)
                    if isinstance(v, str) and v.strip():
                        items.append(v)
                        break
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        kw = normalize_keyword(item)
        if not kw:
            continue
        key = kw.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(kw)
        if len(out) >= _KEYWORD_MAX_PER_SECTION:
            break
    return out


async def _pexels_search_first_photo(
    client: httpx.AsyncClient, keyword: str, api_key: str
) -> Optional[Dict[str, Any]]:
    resp = await client.get(
        PEXELS_SEARCH_URL,
        params={"query": keyword, "per_page": 1, "orientation": "landscape"},
        headers={**_PEXELS_HEADERS_BASE, "Authorization": api_key},
    )
    if resp.status_code == 401:
        raise ValueError("Clé PEXELS_API_KEY invalide ou refusée par Pexels.")
    if resp.status_code >= 400:
        return None
    data = resp.json()
    photos = data.get("photos")
    if not isinstance(photos, list) or not photos:
        return None
    photo = photos[0]
    return photo if isinstance(photo, dict) else None


def _pick_download_url(photo: Dict[str, Any]) -> Optional[str]:
    src = photo.get("src")
    if isinstance(src, dict):
        for key in ("large", "medium", "landscape", "original"):
            u = src.get(key)
            if isinstance(u, str) and u.startswith("https://"):
                return u
    return None


async def build_image_link_for_keyword(
    client: httpx.AsyncClient, keyword: str, api_key: str
) -> Optional[Dict[str, str]]:
    photo = await _pexels_search_first_photo(client, keyword, api_key)
    if not photo:
        return None
    download_url = _pick_download_url(photo)
    if not download_url:
        return None

    img_resp = await client.get(download_url)
    if img_resp.status_code >= 400 or not img_resp.content:
        return None

    content_type = (img_resp.headers.get("content-type") or "image/jpeg").split(";")[0]
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"

    stored_url = await store_discover_image(img_resp.content, extension=ext, content_type=content_type)
    if not stored_url:
        return None

    pexels_page = photo.get("url")
    photographer = photo.get("photographer")
    label = keyword
    if isinstance(photographer, str) and photographer.strip():
        label = f"{keyword} — {photographer.strip()}"

    link: Dict[str, str] = {
        "label": label,
        "url": stored_url,
        "mot_cle": keyword,
    }
    if isinstance(pexels_page, str) and pexels_page.startswith("https://"):
        link["pexelsUrl"] = pexels_page
    return link


async def fetch_pexels_image_links_for_keywords(keywords: List[str]) -> List[Dict[str, str]]:
    """Une image stockée par mot-clé (max 5), via l’API Pexels."""
    api_key = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not api_key:
        return []

    normalized = normalize_keywords_list(keywords)
    if not normalized:
        return []

    links: List[Dict[str, str]] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for kw in normalized[:_IMAGES_MAX_PER_SECTION]:
            try:
                link = await build_image_link_for_keyword(client, kw, api_key)
            except ValueError:
                raise
            except httpx.HTTPError:
                continue
            if link:
                links.append(link)
    return links
