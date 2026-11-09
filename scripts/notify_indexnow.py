#!/usr/bin/env python3
"""Notify IndexNow after deployment; the public key file proves site ownership."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

BASE = "https://prismawelt.github.io"


def changed_urls(sitemap_urls):
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD^", "HEAD"],
        check=True, capture_output=True, text=True
    )
    paths = result.stdout.splitlines()
    shared = ("_layouts/", "_includes/", "_plugins/", "_data/")
    if any(path.startswith(shared) or path in ("_config.yml", "sitemap.xml", "robots.txt")
           or re.fullmatch(r"[0-9a-f]{32}\.txt", path) for path in paths):
        return sitemap_urls
    urls = set()
    for name in paths:
        path = Path(name)
        if path.suffix == ".pdf":
            urls.add(BASE + "/" + name)
        elif name.startswith(("ko/", "en/", "ja/")) and path.suffix in (".md", ".html"):
            if path.is_file():
                match = re.search(r"^permalink:\s*(/\S+)", path.read_text(), re.MULTILINE)
                route = match.group(1) if match else "/" + str(path.with_suffix("")) + "/"
                if route.endswith("/index/"):
                    route = route[:-6]
                urls.add(BASE + route)
    return sorted(urls.intersection(sitemap_urls))


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
    with urlopen(BASE + "/sitemap.xml", timeout=30) as response:
        sitemap = ET.fromstring(response.read())
    urls = sorted({node.text for node in sitemap.findall(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc")})
    assert all(urlsplit(url).scheme == "https" and urlsplit(url).netloc == "prismawelt.github.io"
               for url in urls)
    selected = urls if args.all else changed_urls(urls)
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
