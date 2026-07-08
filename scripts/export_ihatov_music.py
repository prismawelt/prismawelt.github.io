#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
import json
import re
from pathlib import Path


DEFAULT_CSV = "/mnt/d/00_Inbox/2heon2-music-export.csv"
DEFAULT_OUT = "assets/data/ihatov/music.json"
DEFAULT_SINGLES = ".cache/singles"


def field(row, name):
    for key, value in row.items():
        if key and key.strip() == name:
            return html.unescape(value or "").strip()
    return ""


def joined(*parts):
    return " ".join(part for part in parts if part).strip()


def slugify(value):
    value = value.lower()
    value = re.sub(r"[^a-z0-9가-힣ぁ-ゟ゠-ヿ一-龯]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "item"


def norm_match(value):
    value = (value or "").lower()
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def match_variants(value):
    variants = {norm_match(value)}
    for bracketed in re.findall(r"\[([^\]]+)\]", value or ""):
        variants.add(norm_match(bracketed))
    return {variant for variant in variants if variant}


def parse_singles(path):
    singles_path = Path(path)
    if not singles_path.exists():
        return set()

    singles = set()
    for line in singles_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("\t"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        artist = parts[1].strip()
        title = parts[2].strip()
        try:
            float(parts[3].strip())
        except ValueError:
            continue
        for artist_key in match_variants(artist):
            for title_key in match_variants(title):
                singles.add((artist_key, title_key))
    return singles


def is_single(artist, artist_latin, title, singles):
    if not singles:
        return False
    artist_keys = match_variants(artist) | match_variants(artist_latin)
    title_keys = match_variants(title)
    return any((artist_key, title_key) in singles for artist_key in artist_keys for title_key in title_keys)


def read_rows(csv_path, singles=None):
    singles = singles or set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for index, row in enumerate(reader, start=1):
            rating = int(field(row, "Rating") or 0)
            if rating == 0:
                continue

            source_id = field(row, "RYM Album")
            first = field(row, "First Name")
            last = field(row, "Last Name")
            first_local = field(row, "First Name localized")
            last_local = field(row, "Last Name localized")
            artist = joined(first, last) or joined(first_local, last_local)
            artist_latin = joined(first_local, last_local) or artist
            title = field(row, "Title")
            if is_single(artist, artist_latin, title, singles):
                continue
            release_date = field(row, "Release_Date")
            year_match = re.search(r"\d{4}", release_date)
            year = year_match.group(0) if year_match else ""
            stable_key = source_id or f"{artist}-{title}-{release_date}-{index}"

            yield {
                "id": f"rym-{source_id}" if source_id else slugify(stable_key),
                "source_id": source_id,
                "cover": "",
                "artist": artist,
                "artist_latin": artist_latin,
                "title": title,
                "release_date": release_date,
                "year": year,
                "rating": rating,
                "ownership": field(row, "Ownership"),
                "purchase_date": field(row, "Purchase Date"),
                "media_type": field(row, "Media Type"),
                "sort_key": f"{artist_latin or artist} {year} {title}".strip(),
            }


def main():
    parser = argparse.ArgumentParser(description="Export rated RYM albums to IHATOV music JSON.")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to 2heon2-music-export.csv")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output JSON path")
    parser.add_argument("--archive-alias", default="assets/data/ihatov/archive.json", help="Optional friend-code-style archive alias")
    parser.add_argument("--exclude-singles", default=DEFAULT_SINGLES, help="Tab-separated singles list to exclude")
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser()
    out_path = Path(args.out)
    singles = parse_singles(args.exclude_singles) if args.exclude_singles else set()
    items = list(read_rows(csv_path, singles=singles))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": str(csv_path),
        "count": len(items),
        "items": items,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.archive_alias:
        alias_path = Path(args.archive_alias)
        alias_path.parent.mkdir(parents=True, exist_ok=True)
        alias_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items to {out_path}")


if __name__ == "__main__":
    main()
