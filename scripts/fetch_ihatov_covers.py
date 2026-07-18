#!/usr/bin/env python3
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import math
import random
import re
import time
import os
import unicodedata
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import colorsys


DEFAULT_MUSIC_JSON = "assets/data/ihatov/music.json"
DEFAULT_SPRITE_JSON = "assets/data/ihatov/sprite.json"
DEFAULT_SPRITE_IMAGE = "assets/files/ihatov/music/sprite.webp"
DEFAULT_CACHE_DIR = ".cache/ihatov_music"
DEFAULT_LASTFM_ENV = ".cache/ihatov_music/lastfm.env"
DEFAULT_OVERRIDES = "scripts/ihatov_cover_overrides.json"
COUNTRIES = ("KR", "JP", "US", "GB", "FR", "DE", "CA", "AU", "TW", "HK", "SG")
USER_AGENT = "prismawelt.github.io ihatov cover builder (https://prismawelt.github.io)"
MIN_MATCH_SCORE = 14
DEFAULT_SOURCES = "lastfm,itunes,deezer,musicbrainz,discogs"
WIKIPEDIA_LANGS = ("en", "ko", "ja", "fr", "de")


class TemporaryLookupError(Exception):
    pass


def read_env_file(path):
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def norm(value):
    value = (value or "").lower()
    value = value.translate(str.maketrans({
        "ı": "i",
        "ł": "l",
        "đ": "d",
        "ð": "d",
        "þ": "th",
        "ø": "o",
        "œ": "oe",
        "æ": "ae",
        "ß": "ss",
    }))
    value = re.sub(r"\(\d+\)", " ", value)
    value = value.replace("&", " and ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def has_non_latin(value):
    return any(ord(char) > 127 for char in value or "")


def add_limited(target, values, limit=12):
    for value in values:
        value = (value or "").strip()
        if value and value not in target:
            target.append(value)
        if len(target) >= limit:
            break
    return target


def visible_variants(value):
    value = (value or "").strip()
    variants = []
    add_limited(variants, [value])
    outside = strip_annotations(value)
    if outside and outside != value:
        add_limited(variants, [outside])
    add_limited(variants, re.findall(r"\[([^\]]+)\]", value))
    add_limited(variants, re.findall(r"[\(（]([^\)）]+)[\)）]", value))
    return variants


def visible_search_variants(value):
    variants = []
    for variant in visible_variants(value):
        add_limited(variants, [variant])
        if re.search(r"[A-Za-z]\d|\d[A-Za-z]", variant):
            add_limited(variants, [re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", variant)])
        if re.search(r"[A-Za-z]\s+\d|\d\s+[A-Za-z]", variant):
            add_limited(variants, [re.sub(r"(?<=[A-Za-z])\s+(?=\d)|(?<=\d)\s+(?=[A-Za-z])", "", variant)])
        if norm(variant) == "various artists":
            add_limited(variants, ["Various"])
    return variants


def strip_annotations(value):
    value = re.sub(r"\[[^\]]+\]", " ", value or "")
    value = re.sub(r"[\(（][^\)）]+[\)）]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def bracket_variants(value):
    value = value or ""
    variants = {norm(value)}
    outside = strip_annotations(value)
    if outside:
        variants.add(norm(outside))
    for bracketed in re.findall(r"\[([^\]]+)\]", value):
        variants.add(norm(bracketed))
    for bracketed in re.findall(r"[\(（]([^\)）]+)[\)）]", value):
        variants.add(norm(bracketed))
    expanded = set()
    for variant in variants:
        if not variant:
            continue
        expanded.add(variant)
        if re.search(r"[a-z]\d|\d[a-z]", variant):
            expanded.add(re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", variant))
        if re.search(r"[a-z]\s+\d|\d\s+[a-z]", variant):
            expanded.add(re.sub(r"(?<=[a-z])\s+(?=\d)|(?<=\d)\s+(?=[a-z])", "", variant))
        if has_non_latin(variant):
            expanded.add(variant.replace(" ", ""))
    return {variant for variant in expanded if variant}


def artist_variants(*values):
    variants = set()
    for value in values:
        variants.update(bracket_variants(value))
        for pattern in (r"\s+featuring\s+", r"\s+feat\.?\s+", r"\s+with\s+"):
            lead = re.split(pattern, value or "", maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if lead and lead != value:
                variants.update(bracket_variants(lead))
        normalized = norm(value)
        if normalized.startswith("the "):
            variants.add(normalized[4:])
        elif normalized:
            variants.add(f"the {normalized}")
        for part in re.split(r"\s*/\s*|\s+&\s+|\s+and\s+|,\s*", value or "", flags=re.IGNORECASE):
            if part.strip():
                variants.update(bracket_variants(part))
    if variants.intersection({"various", "various artists"}):
        variants.update({"various", "various artists"})
    return variants


GENERIC_TITLE_PARTS = {
    "album",
    "best",
    "complete works",
    "disc",
    "images",
    "part",
    "piano music",
    "piano works",
    "selected works",
    "volume",
    "works",
}


def safe_title_part(value):
    normalized = norm(strip_annotations(value) or value)
    if not normalized:
        return False
    if normalized in GENERIC_TITLE_PARTS:
        return False
    if re.fullmatch(r"(cd|disc|part|vol|volume)\s+\d+", normalized):
        return False
    if re.fullmatch(r"[ivxlcdm]+|\d+", normalized):
        return False
    compact = normalized.replace(" ", "")
    if has_non_latin(value):
        return len(compact) >= 3
    return len(compact) >= 4


def title_split_parts(value):
    for part in re.split(r"\s*/\s*|\s*;\s*", value or ""):
        part = part.strip()
        if part and safe_title_part(part):
            yield part


def title_variants(value):
    variants = set(bracket_variants(value))
    for part in title_split_parts(value):
        variants.update(bracket_variants(part))
    return {variant for variant in variants if variant}


def variant_in_text(variants, text):
    normalized = norm(text)
    compact = normalized.replace(" ", "")
    for variant in variants:
        if not variant:
            continue
        candidate = variant.replace(" ", "") if has_non_latin(variant) else variant
        if len(candidate) < (2 if has_non_latin(candidate) else 4):
            continue
        if variant in normalized or candidate in compact:
            return True
    return False


def text_confirms_item(item, text):
    title_match = variant_in_text(title_variants(item.get("title")), text)
    artist_match = variant_in_text(artist_variants(item.get("artist"), item.get("artist_latin")), text)
    if title_match and artist_match:
        return True

    year = str(item.get("year") or "")
    lowered = text.lower()
    album_context = any(word in lowered for word in ("album", "음반", "앨범", "アルバム"))
    if title_match and has_non_latin(item.get("title")) and album_context and (not year or year in text):
        return True
    return False


def wikipedia_langs_for_item(item):
    text = f"{item.get('artist', '')} {item.get('artist_latin', '')} {item.get('title', '')}"
    langs = ["en"]
    if re.search(r"[가-힣]", text):
        langs.append("ko")
    if re.search(r"[ぁ-ゟ゠-ヿ一-龯]", text):
        langs.append("ja")
    if re.search(r"[àâäçéèêëîïôöùûüÿœæ]", text.lower()):
        langs.append("fr")
    return [lang for lang in WIKIPEDIA_LANGS if lang in langs]


def artist_query_values(item, limit=12):
    values = []
    for artist in (item.get("artist_latin", ""), item.get("artist", "")):
        add_limited(values, visible_search_variants(artist), limit=limit)
        for pattern in (r"\s+featuring\s+", r"\s+feat\.?\s+", r"\s+with\s+"):
            lead = re.split(pattern, artist or "", maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if lead and lead != artist:
                add_limited(values, visible_search_variants(lead), limit=limit)
        for part in re.split(r"\s*/\s*|\s+&\s+|\s+and\s+|,\s*", artist or "", flags=re.IGNORECASE):
            add_limited(values, visible_search_variants(part), limit=limit)
    return values[:limit]


def title_query_values(item, limit=10):
    title = item.get("title", "")
    values = []
    add_limited(values, visible_search_variants(title), limit=limit)
    for part in title_split_parts(title):
        add_limited(values, visible_search_variants(part), limit=limit)
    return values[:limit]


def album_query_pairs(item, limit=24):
    pairs = []
    for artist in artist_query_values(item):
        for title in title_query_values(item):
            pair = (artist, title)
            if all(pair) and pair not in pairs:
                pairs.append(pair)
            if len(pairs) >= limit:
                return pairs
    return pairs


def focused_album_query_pairs(item, artist_limit=5, title_limit=6):
    artists = artist_query_values(item, limit=artist_limit)
    titles = title_query_values(item, limit=title_limit)
    pairs = []
    for artist in artists[:3]:
        for title in titles[:3]:
            pair = (artist, title)
            if all(pair) and pair not in pairs:
                pairs.append(pair)
    for artist in artists[3:]:
        if titles:
            pair = (artist, titles[0])
            if all(pair) and pair not in pairs:
                pairs.append(pair)
    for title in titles[3:]:
        if artists:
            pair = (artists[0], title)
            if all(pair) and pair not in pairs:
                pairs.append(pair)
    return pairs


def same_year(item_year, result_date):
    if not item_year or not result_date:
        return True
    match = re.search(r"\d{4}", str(result_date))
    return not match or match.group(0) == str(item_year)


def cover_url_from_itunes(url):
    return re.sub(r"/\d+x\d+bb\.", "/600x600bb.", url)


def itunes_get(session, params, request_delay=0.25):
    attempts = 0
    while True:
        response = session.get(
            "https://itunes.apple.com/search",
            params=params,
            timeout=12,
        )
        if response.status_code != 429:
            return response
        attempts += 1
        if attempts >= 3:
            raise TemporaryLookupError("itunes rate limit")
        time.sleep(max(60.0, request_delay))


def split_discogs_title(value):
    parts = re.split(r"\s+-\s+", value or "", maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", value or ""


def title_values_match(item_titles, result_titles):
    if item_titles.intersection(result_titles):
        return True
    for item_title in item_titles:
        for result_title in result_titles:
            shorter = item_title if len(item_title) <= len(result_title) else result_title
            if shorter in GENERIC_TITLE_PARTS:
                continue
            if len(shorter.replace(" ", "")) < 12 or len(shorter.split()) < 2:
                continue
            if item_title in result_title or result_title in item_title:
                return True
            item_tokens = set(item_title.split())
            result_tokens = set(result_title.split())
            if len(item_tokens) >= 5 and len(result_tokens) >= 5:
                shared = len(item_tokens.intersection(result_tokens))
                if shared >= max(5, math.ceil(min(len(item_tokens), len(result_tokens)) * 0.8)):
                    return True
    return False


def artist_credit_names(artist_credit):
    names = []
    for credit in artist_credit or []:
        name = credit.get("name") or (credit.get("artist") or {}).get("name")
        if name:
            names.append(name)
    return " / ".join(names)


def score_result(item, result):
    item_titles = title_variants(item.get("title"))
    result_titles = title_variants(result.get("collectionName"))
    item_artists = artist_variants(item.get("artist"), item.get("artist_latin"))
    result_artists = artist_variants(result.get("artistName"))
    if not title_values_match(item_titles, result_titles):
        return 0
    if not item_artists.intersection(result_artists):
        return 0
    if not same_year(item.get("year"), result.get("releaseDate")):
        return 0
    return MIN_MATCH_SCORE + (2 if result.get("releaseDate") else 0)


def score_result_relaxed_year(item, result):
    item_titles = title_variants(item.get("title"))
    result_titles = title_variants(result.get("collectionName"))
    item_artists = artist_variants(item.get("artist"), item.get("artist_latin"))
    result_artists = artist_variants(result.get("artistName"))
    if title_values_match(item_titles, result_titles) and item_artists.intersection(result_artists):
        return MIN_MATCH_SCORE
    return 0


def title_is_specific(item):
    title = item.get("title", "")
    normalized = norm(strip_annotations(title) or title)
    generic = {
        "bounce",
        "complete piano music",
        "court music",
        "curley",
        "essential mix",
        "jazz music",
        "piano works",
        "string quartets",
        "the complete piano music",
        "works for orchestra",
    }
    if normalized in generic:
        return False
    tokens = normalized.split()
    if has_non_latin(title):
        return len(normalized) >= 8
    return len(normalized) >= 18 and len(tokens) >= 3


def score_result_catalog_title_year(item, result):
    if not item.get("year") or not same_year(item.get("year"), result.get("releaseDate")):
        return 0
    if not title_is_specific(item):
        return 0
    item_titles = title_variants(item.get("title"))
    result_titles = title_variants(result.get("collectionName"))
    if title_values_match(item_titles, result_titles):
        return MIN_MATCH_SCORE
    return 0


def valid_artwork_url(url):
    if not url:
        return False
    lowered = url.lower()
    if "2a96cbd8b46e442fc41c2b86b821562f" in lowered:
        return False
    if ".svg" in lowered or "audio_a" in lowered:
        return False
    return lowered.startswith(("http://", "https://"))


def wikipedia_coverish_url(url):
    if not valid_artwork_url(url):
        return False
    lowered = url.lower()
    return any(token in lowered for token in ("cover", "album", "album_art", "jacket", "front"))


def wikipedia_file_looks_cover(file_title, page_title):
    lowered = file_title.lower()
    if any(skip in lowered for skip in ("audio", "icon", "logo", "symbol", "star", "edit", "commons")):
        return False
    if any(prefer in lowered for prefer in ("cover", "album", "art", "jacket", "front")):
        return True
    file_norm = norm(re.sub(r"^file:", "", re.sub(r"\.[a-z0-9]+$", "", file_title, flags=re.IGNORECASE), flags=re.IGNORECASE))
    page_norm = norm(page_title)
    return bool(page_norm and len(page_norm) >= 5 and file_norm == page_norm)


def coverartarchive_front(session, kind, candidate_id):
    if not candidate_id:
        return ""
    cover = f"https://coverartarchive.org/{kind}/{candidate_id}/front-500"
    head = session.get(cover, timeout=10, allow_redirects=False)
    if head.status_code in (200, 307, 308):
        return cover
    return ""


def cache_match_is_suspect(item, cached, cache_dir):
    if cached.get("status") != "ok":
        return False
    cover_path = cache_dir / cached.get("path", "")
    if not cover_path.exists():
        return True
    if cached.get("source") in ("manual", "override"):
        return False
    converted = {
        "collectionName": cached.get("matched_title", ""),
        "artistName": cached.get("matched_artist", ""),
        "releaseDate": item.get("release_date", "") or item.get("year", ""),
    }
    return max(
        score_result(item, converted),
        score_result_relaxed_year(item, converted),
        score_result_catalog_title_year(item, converted),
    ) < MIN_MATCH_SCORE


def image_from_payload(payload):
    images = payload.get("images") or []
    primary = next((image for image in images if image.get("type") == "primary"), None)
    image = primary or (images[0] if images else {})
    return image.get("uri") or image.get("resource_url") or image.get("uri150") or ""


def discogs_result_too_loose(item, result_title):
    item_title = norm(strip_annotations(item.get("title")) or item.get("title"))
    result_full = norm(result_title)
    result_outside = norm(strip_annotations(result_title))
    if not item_title or result_full == item_title:
        return False
    if result_outside == item_title and re.search(r"[\(\[]", result_title or ""):
        compact = item_title.replace(" ", "")
        return len(compact) < 12 or len(item_title.split()) <= 1
    return False


def release_group_primary_type(release):
    group = release.get("release-group") or {}
    return group.get("primary-type") or group.get("type") or ""


def discogs_headers(token):
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    return headers


def discogs_get(session, url, token="", request_delay=0.25, **kwargs):
    attempts = 0
    while True:
        response = session.get(url, headers=discogs_headers(token), timeout=10, **kwargs)
        if response.status_code != 429:
            return response
        attempts += 1
        if attempts >= 3:
            raise TemporaryLookupError("discogs rate limit")
        retry_after = response.headers.get("Retry-After")
        try:
            wait = float(retry_after) if retry_after else 65.0
        except ValueError:
            wait = 65.0
        time.sleep(max(wait, request_delay))


def discogs_search(item, session, token="", request_delay=0.25):
    best = None
    best_score = -1
    seen_requests = set()
    seen_results = set()
    for pair_index, (artist, title) in enumerate(focused_album_query_pairs(item)[:4]):
        for discogs_type in ("master", "release"):
            search_params = [
                {
                    "q": f"{artist} {title}",
                    "type": discogs_type,
                    "per_page": 50,
                },
            ]
            if pair_index == 0:
                search_params.insert(
                    0,
                    {
                        "release_title": title,
                        "artist": artist,
                        "type": discogs_type,
                        "per_page": 50,
                    },
                )
            for params in search_params:
                request_key = tuple(sorted(params.items()))
                if request_key in seen_requests:
                    continue
                seen_requests.add(request_key)
                response = discogs_get(
                    session,
                    "https://api.discogs.com/database/search",
                    params=params,
                    token=token,
                    request_delay=request_delay,
                )
                if response.status_code == 429:
                    raise TemporaryLookupError("discogs rate limit")
                if response.status_code >= 500:
                    raise TemporaryLookupError(f"discogs {response.status_code}")
                if response.status_code != 200:
                    continue

                for result in response.json().get("results", []):
                    result_key = result.get("resource_url") or result.get("master_url") or result.get("id")
                    if result_key and result_key in seen_results:
                        continue
                    if result_key:
                        seen_results.add(result_key)
                    result_artist, result_title = split_discogs_title(result.get("title", ""))
                    if discogs_result_too_loose(item, result_title):
                        continue
                    converted = {
                        "collectionName": result_title,
                        "artistName": result_artist,
                        "releaseDate": str(result.get("year") or ""),
                    }
                    result_score = score_result_relaxed_year(item, converted)
                    if result_score < MIN_MATCH_SCORE:
                        result_score = score_result_catalog_title_year(item, converted)
                    if result_score < MIN_MATCH_SCORE or result_score <= best_score:
                        continue

                    artwork = result.get("cover_image") or result.get("thumb") or ""
                    resource_url = result.get("master_url") or result.get("resource_url")
                    if not artwork and resource_url:
                        detail = discogs_get(session, resource_url, token=token, request_delay=request_delay)
                        if detail.status_code == 429:
                            raise TemporaryLookupError("discogs rate limit")
                        if detail.status_code >= 500:
                            raise TemporaryLookupError(f"discogs {detail.status_code}")
                        if detail.status_code == 200:
                            artwork = image_from_payload(detail.json())

                    if valid_artwork_url(artwork):
                        best = {
                            "source": "discogs",
                            "url": artwork,
                            "artist": result_artist,
                            "title": result_title,
                            "score": result_score,
                        }
                        best_score = result_score
            if best and best_score >= 14:
                break
            time.sleep(request_delay)
        if best and best_score >= 14:
            break

    return best


def deezer_search(item, session):
    queries = []
    for artist, title in album_query_pairs(item, limit=20):
        query = f"{artist} {title}".strip()
        if query and query not in queries:
            queries.append(query)
    add_limited(queries, title_query_values(item, limit=6), limit=26)

    best = None
    best_score = -1
    for query in queries:
        response = session.get(
            "https://api.deezer.com/search/album",
            params={"q": query, "limit": 8},
            timeout=12,
        )
        if response.status_code == 429:
            raise TemporaryLookupError("deezer rate limit")
        if response.status_code >= 500:
            raise TemporaryLookupError(f"deezer {response.status_code}")
        if response.status_code != 200:
            continue
        for result in response.json().get("data", []):
            artwork = result.get("cover_big") or result.get("cover_xl") or result.get("cover_medium")
            if not valid_artwork_url(artwork):
                continue
            converted = {
                "collectionName": result.get("title", ""),
                "artistName": (result.get("artist") or {}).get("name", ""),
                "releaseDate": result.get("release_date", ""),
            }
            result_score = score_result(item, converted)
            if result_score > best_score:
                best = {
                    "source": "deezer",
                    "url": artwork,
                    "artist": converted["artistName"],
                    "title": converted["collectionName"],
                    "score": result_score,
                }
                best_score = result_score
        if best and best_score >= 14:
            break

    return best if best and best_score >= MIN_MATCH_SCORE else None


def itunes_search(item, session, request_delay=0.25, countries=COUNTRIES):
    queries = []
    for artist, title in album_query_pairs(item, limit=6):
        query = f"{artist} {title}".strip()
        if query and query not in queries:
            queries.append(query)
    add_limited(queries, title_query_values(item, limit=4), limit=10)

    best = None
    best_score = -1
    for query in queries:
        for country in countries:
            response = itunes_get(
                session,
                {"term": query, "media": "music", "entity": "album", "limit": 8, "country": country},
                request_delay=request_delay,
            )
            if response.status_code == 429:
                raise TemporaryLookupError("itunes rate limit")
            if response.status_code >= 500:
                raise TemporaryLookupError(f"itunes {response.status_code}")
            if response.status_code != 200:
                continue
            for result in response.json().get("results", []):
                artwork = result.get("artworkUrl100")
                if not valid_artwork_url(artwork):
                    continue
                result_score = score_result(item, result)
                if result_score > best_score:
                    best = {
                        "source": "itunes",
                        "country": country,
                        "url": cover_url_from_itunes(artwork),
                        "artist": result.get("artistName", ""),
                        "title": result.get("collectionName", ""),
                        "score": result_score,
                    }
                    best_score = result_score
            time.sleep(request_delay)
        if best and best_score >= 14:
            break

    return best if best and best_score >= MIN_MATCH_SCORE else None


def lastfm_search(item, session, api_key):
    if not api_key:
        return None

    best = None
    best_score = -1
    for artist, title in album_query_pairs(item, limit=20):
        if not artist or not title:
            continue
        response = session.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "album.getinfo",
                "artist": artist,
                "album": title,
                "api_key": api_key,
                "autocorrect": 1,
                "format": "json",
            },
            timeout=15,
        )
        if response.status_code == 429:
            raise TemporaryLookupError("lastfm rate limit")
        if response.status_code >= 500:
            raise TemporaryLookupError(f"lastfm {response.status_code}")
        if response.status_code != 200:
            continue
        album = response.json().get("album") or {}
        converted = {
            "collectionName": album.get("name", ""),
            "artistName": album.get("artist", ""),
            "releaseDate": "",
        }
        result_score = score_result(item, converted)
        if result_score < MIN_MATCH_SCORE or result_score <= best_score:
            continue
        images = album.get("image") or []
        artwork = ""
        for image in reversed(images):
            if image.get("#text"):
                artwork = image["#text"]
                break
        source = "lastfm"
        if not valid_artwork_url(artwork) and album.get("mbid"):
            artwork = (
                coverartarchive_front(session, "release-group", album.get("mbid"))
                or coverartarchive_front(session, "release", album.get("mbid"))
            )
            source = "coverartarchive-lastfm"
        if valid_artwork_url(artwork):
            best = {
                "source": source,
                "url": artwork,
                "artist": converted["artistName"],
                "title": converted["collectionName"],
                "score": result_score,
            }
            best_score = result_score
        if best and best_score >= 14:
            break

    return best or lastfm_album_search(item, session, api_key)


def lastfm_album_search(item, session, api_key):
    queries = []
    for artist, title in album_query_pairs(item, limit=20):
        for query in (f"{artist} {title}".strip(), title):
            if query and query not in queries:
                queries.append(query)

    best = None
    best_score = -1
    for query in queries[:18]:
        response = session.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "album.search",
                "album": query,
                "api_key": api_key,
                "format": "json",
                "limit": 10,
            },
            timeout=15,
        )
        if response.status_code == 429:
            raise TemporaryLookupError("lastfm rate limit")
        if response.status_code >= 500:
            raise TemporaryLookupError(f"lastfm {response.status_code}")
        if response.status_code != 200:
            continue

        matches = ((response.json().get("results") or {}).get("albummatches") or {}).get("album") or []
        if isinstance(matches, dict):
            matches = [matches]
        for album in matches:
            converted = {
                "collectionName": album.get("name", ""),
                "artistName": album.get("artist", ""),
                "releaseDate": "",
            }
            result_score = score_result(item, converted)
            if result_score < MIN_MATCH_SCORE or result_score <= best_score:
                continue
            artwork = ""
            for image in reversed(album.get("image") or []):
                if image.get("#text"):
                    artwork = image["#text"]
                    break
            if valid_artwork_url(artwork):
                best = {
                    "source": "lastfm-search",
                    "url": artwork,
                    "artist": converted["artistName"],
                    "title": converted["collectionName"],
                    "score": result_score,
                }
                best_score = result_score
        if best:
            break

    return best


def wikipedia_search(item, session):
    queries = []
    for title in title_query_values(item, limit=4):
        for query in (f'"{title}"', title):
            if query and query not in queries:
                queries.append(query)
    for artist, title in album_query_pairs(item, limit=4):
        for query in (f'"{title}" "{artist}"', f"{title} {artist}"):
            if query and query not in queries:
                queries.append(query)

    for lang in wikipedia_langs_for_item(item):
        for query in queries[:6]:
            response = session.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": 5,
                    "prop": "pageimages|extracts|images",
                    "exintro": 1,
                    "explaintext": 1,
                    "imlimit": 20,
                    "pithumbsize": 600,
                    "format": "json",
                    "formatversion": 2,
                    "redirects": 1,
                },
                timeout=15,
            )
            if response.status_code == 429:
                raise TemporaryLookupError("wikipedia rate limit")
            if response.status_code >= 500:
                raise TemporaryLookupError(f"wikipedia {response.status_code}")
            if response.status_code != 200:
                continue

            pages = (response.json().get("query") or {}).get("pages") or []
            for page in pages:
                image = (page.get("thumbnail") or {}).get("source", "")
                page_text = f"{page.get('title', '')}\n{page.get('extract', '')}"
                if not text_confirms_item(item, page_text):
                    continue
                image = image or wikipedia_file_image(session, lang, page)
                if not wikipedia_coverish_url(image):
                    continue
                return {
                    "source": f"wikipedia-{lang}",
                    "url": image,
                    "artist": item.get("artist_latin") or item.get("artist", ""),
                    "title": item.get("title", ""),
                    "score": MIN_MATCH_SCORE,
                }
            time.sleep(0.2)
    return None


def wikipedia_file_image(session, lang, page):
    image_titles = []
    for image in page.get("images") or []:
        title = image.get("title", "")
        lowered = title.lower()
        if not title.startswith("File:"):
            continue
        if not wikipedia_file_looks_cover(title, page.get("title", "")):
            continue
        if any(prefer in lowered for prefer in ("cover", "album", "front")):
            image_titles.insert(0, title)
        else:
            image_titles.append(title)

    for title in image_titles[:8]:
        response = session.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": 600,
                "format": "json",
                "formatversion": 2,
            },
            timeout=15,
        )
        if response.status_code != 200:
            continue
        pages = (response.json().get("query") or {}).get("pages") or []
        for image_page in pages:
            imageinfo = image_page.get("imageinfo") or []
            if not imageinfo:
                continue
            url = imageinfo[0].get("thumburl") or imageinfo[0].get("url") or ""
            if wikipedia_coverish_url(url) or wikipedia_file_looks_cover(title, page.get("title", "")):
                return url
        time.sleep(0.2)
    return ""


def musicbrainz_search(item, session):
    year = item.get("year", "")
    for artist, title in album_query_pairs(item, limit=20):
        query_variants = []
        terms = [f'release:"{title}"', f'artist:"{artist}"']
        if year:
            terms.append(f"date:{year}")
        query_variants.append(" AND ".join(terms))
        query_variants.append(f'release:"{title}" AND artist:"{artist}"')
        if year and title_is_specific(item):
            query_variants.append(f'release:"{title}" AND date:{year}')
        for query in query_variants:
            response = session.get(
                "https://musicbrainz.org/ws/2/release-group/",
                params={"query": query.replace("release:", "releasegroup:"), "fmt": "json", "limit": 8},
                timeout=15,
            )
            if response.status_code == 429:
                raise TemporaryLookupError("musicbrainz rate limit")
            if response.status_code >= 500:
                raise TemporaryLookupError(f"musicbrainz {response.status_code}")
            if response.status_code == 200:
                release_groups = response.json().get("release-groups", [])
                for release_group in release_groups:
                    converted = {
                        "collectionName": release_group.get("title", title),
                        "artistName": artist_credit_names(release_group.get("artist-credit")) or artist,
                        "releaseDate": release_group.get("first-release-date", ""),
                    }
                    result_score = score_result_relaxed_year(item, converted)
                    if result_score < MIN_MATCH_SCORE:
                        result_score = score_result_catalog_title_year(item, converted)
                    if result_score < MIN_MATCH_SCORE:
                        continue
                    cover = coverartarchive_front(session, "release-group", release_group.get("id"))
                    if cover:
                        return {
                            "source": "coverartarchive",
                            "url": cover,
                            "artist": converted["artistName"],
                            "title": converted["collectionName"],
                            "score": result_score,
                        }
                    time.sleep(0.2)
            time.sleep(1.1)

            response = session.get(
                "https://musicbrainz.org/ws/2/release/",
                params={"query": query, "fmt": "json", "limit": 8},
                timeout=15,
            )
            if response.status_code == 429:
                raise TemporaryLookupError("musicbrainz rate limit")
            if response.status_code >= 500:
                raise TemporaryLookupError(f"musicbrainz {response.status_code}")
            if response.status_code != 200:
                continue
            releases = response.json().get("releases", [])
            for release in releases:
                converted = {
                    "collectionName": release.get("title", title),
                    "artistName": artist_credit_names(release.get("artist-credit")) or artist,
                    "releaseDate": release.get("date", ""),
                }
                result_score = score_result_relaxed_year(item, converted)
                if result_score < MIN_MATCH_SCORE:
                    result_score = score_result_catalog_title_year(item, converted)
                if result_score < MIN_MATCH_SCORE:
                    continue
                mbid = release.get("id")
                release_group_id = (release.get("release-group") or {}).get("id")
                for kind, candidate_id in (("release-group", release_group_id), ("release", mbid)):
                    cover = coverartarchive_front(session, kind, candidate_id)
                    if cover:
                        return {
                            "source": "coverartarchive",
                            "url": cover,
                            "artist": converted["artistName"],
                            "title": converted["collectionName"],
                            "score": result_score,
                        }
                    time.sleep(0.2)
            time.sleep(1.1)
    return None


def download_cover(
    item,
    cache_dir,
    cache,
    use_musicbrainz=False,
    use_discogs=False,
    discogs_token="",
    lastfm_api_key="",
    sources=None,
    refresh_missing=False,
    refresh_suspect=False,
    skip_deezer=False,
    skip_itunes=False,
    request_delay=0.25,
    itunes_countries=COUNTRIES,
):
    item_id = item["id"]
    cached = cache.get(item_id)
    if cached:
        cover_path = cache_dir / cached.get("path", "")
        if cached.get("status") == "ok" and cover_path.exists():
            if not refresh_suspect or not cache_match_is_suspect(item, cached, cache_dir):
                return item_id, cached
        if cached.get("status") == "missing" and not refresh_missing:
            return item_id, cached

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    match = None
    error = ""
    try:
        if sources is None:
            sources = []
            if use_discogs:
                sources.append("discogs")
            if use_musicbrainz:
                sources.append("musicbrainz")
            if not skip_deezer:
                sources.append("deezer")
            if not skip_itunes:
                sources.append("itunes")
            if lastfm_api_key:
                sources.append("lastfm")
        for source in sources:
            if source == "lastfm" and lastfm_api_key:
                match = lastfm_search(item, session, lastfm_api_key)
            elif source == "itunes" and not skip_itunes:
                match = itunes_search(item, session, request_delay=request_delay, countries=itunes_countries)
            elif source == "deezer" and not skip_deezer:
                match = deezer_search(item, session)
            elif source == "musicbrainz":
                time.sleep(1.1)
                match = musicbrainz_search(item, session)
            elif source == "discogs":
                match = discogs_search(item, session, token=discogs_token, request_delay=request_delay)
            elif source == "wikipedia":
                match = wikipedia_search(item, session)
            if match:
                break
        if not match:
            return item_id, {"status": "missing", "updated_at": utc_now()}

        response = session.get(match["url"], timeout=20, allow_redirects=True)
        response.raise_for_status()
        extension = ".jpg"
        content_type = response.headers.get("Content-Type", "")
        if "png" in content_type:
            extension = ".png"
        rel_path = f"covers/{item_id}{extension}"
        cover_path = cache_dir / rel_path
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cover_path.write_bytes(response.content)
        return item_id, {
            "status": "ok",
            "path": rel_path,
            "source": match["source"],
            "matched_artist": match.get("artist", ""),
            "matched_title": match.get("title", ""),
            "matched_score": match.get("score", 0),
            "url": match["url"],
            "updated_at": utc_now(),
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    status = "retry" if "TemporaryLookupError" in error or "rate limit" in error else "missing"
    return item_id, {"status": status, "error": error, "updated_at": utc_now()}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def override_local_path(location):
    windows_path = re.match(r"^([A-Za-z]):[\\/](.*)$", location)
    if windows_path:
        drive = windows_path.group(1).lower()
        suffix = windows_path.group(2).replace("\\", "/")
        return Path("/mnt") / drive / suffix
    return Path(location) if not location.startswith(("http://", "https://")) else None


def download_override(item, location, cache_dir):
    local_path = override_local_path(location)
    if local_path is not None:
        content = local_path.read_bytes()
    else:
        response = requests.get(
            location,
            timeout=30,
            allow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        response.raise_for_status()
        content = response.content
    with Image.open(io.BytesIO(content)) as image:
        image_format = (image.format or "").upper()
        image.verify()
    extension = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
    }.get(image_format, ".img")
    rel_path = f"covers/{item['id']}{extension}"
    cover_path = cache_dir / rel_path
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(content)
    return {
        "status": "ok",
        "path": rel_path,
        "source": "override",
        "matched_artist": item.get("artist", ""),
        "matched_title": item.get("title", ""),
        "matched_score": MIN_MATCH_SCORE,
        "url": location,
        "updated_at": utc_now(),
    }


def apply_cover_overrides(items, cache_dir, cache, overrides_path, workers=2):
    if not overrides_path.exists():
        return
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    items_by_id = {item["id"]: item for item in items}
    pending = []
    for item_id, location in overrides.items():
        item = items_by_id.get(item_id)
        if not item:
            print(f"override ignored; unknown id: {item_id}", flush=True)
            continue
        cached = cache.get(item_id, {})
        cover_path = cache_dir / cached.get("path", "")
        if (
            cached.get("status") == "ok"
            and cached.get("source") == "override"
            and cached.get("url") == location
            and cover_path.exists()
        ):
            continue
        pending.append((item, location))

    if not pending:
        return
    print(f"downloading {len(pending)} cover overrides", flush=True)
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(download_override, item, location, cache_dir): item
            for item, location in pending
        }
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                cache[item["id"]] = future.result()
            except Exception as exc:
                print(
                    f"override failed: {item['artist']} - {item['title']}: {type(exc).__name__}: {exc}",
                    flush=True,
                )
            completed += 1
            if completed % 5 == 0 or completed == len(pending):
                (cache_dir / "cover-cache.json").write_text(
                    json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"{completed}/{len(pending)} overrides processed", flush=True)


def find_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/mnt/c/Windows/Fonts/malgunbd.ttf" if bold else "/mnt/c/Windows/Fonts/malgun.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def palette_for(item_id):
    digest = hashlib.sha256(item_id.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    sat = 0.16 + (digest[1] / 255.0) * 0.18
    val = 0.90 + (digest[2] / 255.0) * 0.08
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return tuple(int(channel * 255) for channel in (r, g, b))


def wrap_text(draw, text, font, max_width, max_lines):
    words = re.split(r"\s+", text.strip())
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) == max_lines:
        while draw.textbbox((0, 0), lines[-1], font=font)[2] > max_width and len(lines[-1]) > 1:
            lines[-1] = lines[-1][:-4] + "..."
    return lines


def make_text_tile(item, tile_size):
    bg = palette_for(item["id"])
    image = Image.new("RGB", (tile_size, tile_size), bg)
    draw = ImageDraw.Draw(image)
    title_font = find_font(max(9, tile_size // 9), bold=True)
    meta_font = find_font(max(7, tile_size // 12), bold=False)
    margin = max(7, tile_size // 12)
    max_width = tile_size - margin * 2
    title_lines = wrap_text(draw, item.get("title", ""), title_font, max_width, 4)
    artist_lines = wrap_text(draw, item.get("artist_latin") or item.get("artist", ""), meta_font, max_width, 2)
    line_h_title = title_font.size + 2
    line_h_meta = meta_font.size + 1
    total_h = len(title_lines) * line_h_title + len(artist_lines) * line_h_meta + 5
    y = max(margin, (tile_size - total_h) // 2)
    for line in title_lines:
        draw.text((margin, y), line, fill=(0, 0, 0), font=title_font)
        y += line_h_title
    y += 4
    for line in artist_lines:
        draw.text((margin, y), line, fill=(0, 0, 0), font=meta_font)
        y += line_h_meta
    return image


def crop_cover(path, tile_size):
    with Image.open(path) as image:
        return ImageOps.fit(image.convert("RGB"), (tile_size, tile_size), method=Image.Resampling.LANCZOS)


def average_hsv(image):
    small = image.resize((1, 1), Image.Resampling.BOX)
    r, g, b = [channel / 255.0 for channel in small.getpixel((0, 0))]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return [round(h * 360, 3), round(s * 100, 3), round(v * 100, 3)]


def write_archive_files(music_path, items, cache, cache_dir):
    if not music_path.exists():
        return
    payload = json.loads(music_path.read_text(encoding="utf-8"))
    for item in payload.get("items", []):
        cached = cache.get(item["id"], {})
        item["cover"] = cached.get("url", "") if cached.get("status") == "ok" else ""
        item["cover_cache"] = cached.get("path", "") if cached.get("status") == "ok" and (cache_dir / cached.get("path", "")).exists() else ""
        item["cover_status"] = cached.get("status", "missing")
    payload["generated_at"] = utc_now()
    music_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive_path = music_path.with_name("archive.json")
    archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_sprite(items, cache_dir, cache, sprite_image_path, sprite_json_path, tile_size):
    count = len(items)
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = math.ceil(count / cols)
    sprite = Image.new("RGB", (cols * tile_size, rows * tile_size), (255, 255, 255))
    hsv = {}
    missing = 0

    for slot, item in enumerate(items):
        item_id = item["id"]
        cached = cache.get(item_id, {})
        tile = None
        if cached.get("status") == "ok":
            cover_path = cache_dir / cached.get("path", "")
            if cover_path.exists():
                try:
                    tile = crop_cover(cover_path, tile_size)
                except Exception:
                    tile = None
        if tile is None:
            missing += 1
            tile = make_text_tile(item, tile_size)
        x = (slot % cols) * tile_size
        y = (slot // cols) * tile_size
        sprite.paste(tile, (x, y))
        hsv[item_id] = average_hsv(tile)

    sprite_image_path.parent.mkdir(parents=True, exist_ok=True)
    sprite.save(sprite_image_path, "WEBP", quality=82, method=6)
    sprite_payload = {
        "generated_at": utc_now(),
        "tile": tile_size,
        "cols": cols,
        "rows": rows,
        "count": count,
        "missing": missing,
        "ids": [item["id"] for item in items],
        "hsv": hsv,
    }
    sprite_json_path.parent.mkdir(parents=True, exist_ok=True)
    sprite_json_path.write_text(json.dumps(sprite_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Fetch cover art and build the IHATOV music sprite.")
    parser.add_argument("--music-json", default=DEFAULT_MUSIC_JSON)
    parser.add_argument("--sprite-json", default=DEFAULT_SPRITE_JSON)
    parser.add_argument("--sprite-image", default=DEFAULT_SPRITE_IMAGE)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--overrides", default=DEFAULT_OVERRIDES)
    parser.add_argument("--tile-size", type=int, default=96)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="Limit items for testing; 0 means all.")
    parser.add_argument("--only-id", action="append", default=[], help="Only process the given item id; can be repeated.")
    parser.add_argument("--pending-limit", type=int, default=0, help="Limit pending network fetches for chunked long runs.")
    parser.add_argument("--sources", default=DEFAULT_SOURCES, help="Comma-separated source order: lastfm,itunes,deezer,musicbrainz,discogs,wikipedia")
    parser.add_argument("--musicbrainz-fallback", action="store_true")
    parser.add_argument("--discogs", action="store_true", help="Use Discogs catalog search before store APIs.")
    parser.add_argument("--discogs-token", default=os.environ.get("DISCOGS_TOKEN", ""))
    parser.add_argument("--lastfm-env", default=DEFAULT_LASTFM_ENV)
    parser.add_argument("--lastfm-api-key", default=os.environ.get("LASTFM_API_KEY", ""))
    parser.add_argument("--skip-deezer", action="store_true")
    parser.add_argument("--skip-itunes", action="store_true")
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--itunes-countries", default=",".join(COUNTRIES), help="Comma-separated iTunes storefront country codes.")
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument("--refresh-missing", action="store_true")
    parser.add_argument("--refresh-suspect", action="store_true", help="Re-fetch cached covers whose stored match no longer passes validation.")
    parser.add_argument("--skip-network", action="store_true")
    args = parser.parse_args()
    if not args.lastfm_api_key:
        args.lastfm_api_key = read_env_file(args.lastfm_env).get("LASTFM_API_KEY", "")
    sources = [source.strip().lower() for source in args.sources.split(",") if source.strip()]
    valid_sources = {"lastfm", "itunes", "deezer", "musicbrainz", "discogs", "wikipedia"}
    unknown_sources = [source for source in sources if source not in valid_sources]
    if unknown_sources:
        raise SystemExit(f"unknown sources: {', '.join(unknown_sources)}")
    itunes_countries = tuple(country.strip().upper() for country in args.itunes_countries.split(",") if country.strip())

    music_path = Path(args.music_json)
    cache_dir = Path(args.cache_dir)
    cache_path = cache_dir / "cover-cache.json"
    items = json.loads(music_path.read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[: args.limit]
    fetch_items = items
    if args.only_id:
        wanted_ids = set(args.only_id)
        fetch_items = [item for item in items if item["id"] in wanted_ids]
    cache_dir.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache = {}

    if not args.skip_network:
        apply_cover_overrides(
            items,
            cache_dir,
            cache,
            Path(args.overrides),
            workers=args.workers,
        )

    if not args.skip_network:
        pending = [
            item for item in fetch_items
            if item["id"] not in cache
            or (cache[item["id"]].get("status") == "ok" and not (cache_dir / cache[item["id"]].get("path", "")).exists())
            or (args.refresh_suspect and cache_match_is_suspect(item, cache[item["id"]], cache_dir))
            or cache[item["id"]].get("status") == "retry"
            or (cache[item["id"]].get("status") == "missing" and args.refresh_missing)
        ]
        random.shuffle(pending)
        if args.pending_limit:
            pending = pending[: args.pending_limit]
        print(f"fetching {len(pending)} covers; cached {len(fetch_items) - len(pending)}", flush=True)
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(
                    download_cover,
                    item,
                    cache_dir,
                    cache,
                    args.musicbrainz_fallback,
                    args.discogs,
                    args.discogs_token,
                    args.lastfm_api_key,
                    sources,
                    args.refresh_missing,
                    args.refresh_suspect,
                    args.skip_deezer,
                    args.skip_itunes,
                    args.request_delay,
                    itunes_countries,
                )
                for item in pending
            ]
            for future in concurrent.futures.as_completed(futures):
                item_id, result = future.result()
                cache[item_id] = result
                completed += 1
                checkpoint_every = max(1, args.checkpoint_every)
                if completed % checkpoint_every == 0 or completed == len(pending):
                    ok = sum(1 for item in items if cache.get(item["id"], {}).get("status") == "ok")
                    retry = sum(1 for item in items if cache.get(item["id"], {}).get("status") == "retry")
                    print(f"{completed}/{len(pending)} fetched; {ok}/{len(items)} with covers; {retry} retry", flush=True)
                    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_archive_files(music_path, items, cache, cache_dir)
    build_sprite(
        items=items,
        cache_dir=cache_dir,
        cache=cache,
        sprite_image_path=Path(args.sprite_image),
        sprite_json_path=Path(args.sprite_json),
        tile_size=args.tile_size,
    )
    ok = sum(1 for item in items if cache.get(item["id"], {}).get("status") == "ok")
    print(f"sprite complete: {ok}/{len(items)} downloaded covers, {len(items) - ok} text tiles", flush=True)


if __name__ == "__main__":
    main()
