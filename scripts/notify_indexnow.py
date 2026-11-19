#!/usr/bin/env python3
"""Notify IndexNow after deployment; the public key file proves site ownership."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

BASE = "https://prismawelt.github.io"


def page_urls(revision, path):
    """Read the published route and its archive at either end of a push."""
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], capture_output=True, text=True
    )
    header = re.match(r"\A---\r?\n(.*?)^---\s*$", result.stdout, re.MULTILINE | re.DOTALL)
    if not header or re.search(r"^(?:sitemap|published):\s*false\s*$", header[1], re.MULTILINE):
        return set()
    # Site permalinks are absolute paths. Index pages may use Jekyll's default.
    fallback = f"/{path.parent}/" if path.stem == "index" else f"/{path.with_suffix('.html')}"

    def route(key, default=None):
        field = re.search(rf"""^{key}:[ \t]*['"]?(/[^'"\s#]*)['"]?[ \t]*(?:\#.*)?$""",
                          header[1], re.MULTILINE)
        value = field[1] if field else default
        if value and value.startswith("/") and not value.startswith("//"):
            return BASE + value
        return None

    return {url for url in (route("permalink", fallback), route("parent_permalink")) if url}


def changed_urls(sitemap_urls, before=None):
    current = set(sitemap_urls)
    base = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{before or 'HEAD^'}^{{commit}}"],
        capture_output=True, text=True,
    )
    if base.returncode:
        print("Prior commit unavailable; using the published sitemap.", file=sys.stderr)
        return sorted(current)
    revision = base.stdout.strip()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision, "HEAD"], text=True
    ).split("\0")
    paths = [Path(name) for name in changed if name]
    shared = {"_config.yml", "sitemap.xml", "robots.txt"}
    if any(path.parts[0] in {"_layouts", "_includes", "_plugins", "_data"}
           or str(path) in shared or re.fullmatch(r"[0-9a-f]{32}\.txt", str(path)) for path in paths):
        selected = {url for url in current if url.endswith("/")}
    else:
        selected = set()

    for path in paths:
        if path.parts[0] in {"ko", "en", "ja"} and path.suffix in {".md", ".html"}:
            previous = page_urls(revision, path)
            updated = page_urls("HEAD", path)
            # Added pages may precede the CDN sitemap; removed routes only exist in Git.
            selected.update(previous | updated)
        elif path.parts[:2] == ("assets", "files") and path.suffix.lower() == ".pdf":
            url = BASE + "/" + str(path)
            if url in current or not path.is_file():
                selected.add(url)
    return sorted(selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Submit the entire sitemap once.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    keys = [path for path in Path(".").glob("*.txt")
            if re.fullmatch(r"[0-9a-f]{32}\.txt", path.name)]
    assert len(keys) == 1, "Expected one IndexNow verification file"
    key = keys[0].read_text().strip()
    assert keys[0].stem == key
    key_url = BASE + "/" + keys[0].name
    with urlopen(key_url, timeout=30) as response:
        assert response.read().decode().strip() == key, "Published key does not match"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    with urlopen(BASE + "/sitemap.xml?revision=" + commit, timeout=30) as response:
        sitemap = ET.fromstring(response.read())
    urls = sorted({node.text for node in sitemap.findall(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc")})
    assert all(urlsplit(url).scheme == "https" and urlsplit(url).netloc == "prismawelt.github.io"
               for url in urls)
    selected = urls if args.all else changed_urls(urls, os.getenv("INDEXNOW_BEFORE"))
    if not selected:
        print("No indexed content URLs changed; no IndexNow request sent.")
        return
    if args.dry_run:
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        return
    payload = {"host": "prismawelt.github.io", "key": key,
               "keyLocation": key_url, "urlList": selected}
    request = Request("https://api.indexnow.org/indexnow",
                      data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json; charset=utf-8"},
                      method="POST")
    with urlopen(request, timeout=30) as response:
        assert response.status in (200, 202), response.status
        print(f"IndexNow received {len(selected)} URLs (HTTP {response.status}). "
              "Submission does not guarantee indexing.")


if __name__ == "__main__":
    main()
