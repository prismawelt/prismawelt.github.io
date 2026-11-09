#!/usr/bin/env python3
"""Check generated metadata, translation links, feeds and comment mapping."""
import datetime
import json
from html.parser import HTMLParser
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

BASE = "https://prismawelt.github.io"
LANGUAGES = ("ko", "en", "ja")


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.meta, self.links, self.comments, self.schemas = {}, [], [], []
        self.http_equiv = {}
        self.lang, self.in_schema, self.schema = None, False, ""
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang = attrs.get("lang")
        if tag == "meta":
            self.meta[attrs.get("name", attrs.get("property"))] = attrs.get("content")
        if tag == "meta" and "http-equiv" in attrs:
            self.http_equiv[attrs["http-equiv"]] = attrs.get("content")
        if tag == "link":
            self.links.append(attrs)
        if "data-comments" in attrs:
            self.comments.append(attrs)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_schema, self.schema = True, ""

    def handle_data(self, text):
        if self.in_schema:
            self.schema += text

    def handle_endtag(self, tag):
        if tag == "script" and self.in_schema:
            self.schemas.append(json.loads(self.schema))
            self.in_schema = False

    def canonical(self):
        links = [link["href"] for link in self.links if link.get("rel") == "canonical"]
        assert len(links) == 1
        return links[0]

    def alternates(self):
        return {link["hreflang"]: link["href"] for link in self.links if "hreflang" in link}


def check(site):
    def local(url):
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "prismawelt.github.io", url
        path = site / unquote(parts.path).lstrip("/")
        return path / "index.html" if path.is_dir() else path

    pages = {}
    articles = {lang: [] for lang in LANGUAGES}
    for lang in LANGUAGES:
        for path in (site / lang).rglob("*.html"):
            page = Page(path)
            assert page.lang == lang, path
            canonical = page.canonical()
            assert local(canonical) == path, (path, canonical)
            assert page.meta.get("description"), path
            assert page.meta.get("og:url") == canonical, path
            assert "noindex" not in page.meta.get("robots", ""), path
            assert "max-image-preview:large" in page.meta.get("robots", ""), path
            assert len(page.schemas) == 1, path
            graph = page.schemas[0]["@graph"]
            entries = [entry for entry in graph if entry["@type"] in ("Article", "BlogPosting")]
            for entry in entries:
                assert entry["url"] == canonical and entry["inLanguage"] == lang
                datetime.date.fromisoformat(entry["datePublished"])
                modified = datetime.datetime.fromisoformat(entry["dateModified"])
                assert modified.tzinfo is not None
                assert len(page.comments) == 1, path
                comments = page.comments[0]
                assert comments["data-term"] == urlsplit(page.alternates()["ko"]).path
                assert comments["data-language"] == lang
                assert comments["data-repo"] == "prismawelt/prismawelt.github.io"
                assert comments["data-category-id"].startswith("DIC_")
                if lang != "ko":
                    assert entry["translationOfWork"]["url"] == page.alternates()["ko"]
                for image in entry.get("image", []):
                    assert local(image).is_file(), image
                articles[lang].append(canonical)
            if not entries:
                assert not page.comments, path
            pages[canonical] = page

    for url, page in pages.items():
        alts = page.alternates()
        assert set(alts) == {*LANGUAGES, "x-default"}, url
        assert alts["x-default"] == alts["ko"], url
        for lang in LANGUAGES:
            assert alts[lang] in pages, (url, lang)
            assert pages[alts[lang]].alternates() == alts, url

    root = Page(site / "index.html")
    assert root.canonical() == BASE + "/ko/"
    assert root.http_equiv.get("refresh") == "0; url=/ko/"

    sitemap = ET.parse(site / "sitemap.xml")
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
    assert len(locations) == len(set(locations))
    assert set(pages).issubset(locations)
    for url in locations:
        assert local(url).is_file(), url
    for modified in sitemap.findall("s:url/s:lastmod", namespace):
        datetime.datetime.fromisoformat(modified.text)

    atom = {"a": "http://www.w3.org/2005/Atom"}
    for lang in LANGUAGES:
        feed = ET.parse(site / lang / "feed.xml")
        entries = feed.findall("a:entry", atom)
        assert {entry.find("a:id", atom).text for entry in entries} == set(articles[lang])
        for entry in entries:
            assert entry.find("a:content", atom).text
            datetime.datetime.fromisoformat(entry.find("a:updated", atom).text)
    index = (site / "llms.txt").read_text()
    for urls in articles.values():
        for url in urls:
            assert url in index, url
    robots = (site / "robots.txt").read_text()
    assert "Allow: /" in robots and BASE + "/sitemap.xml" in robots
    for excluded in ("scripts", "tests", "Gemfile", "Gemfile.lock"):
        assert not (site / excluded).exists(), excluded
    print(f"PASS: {len(pages)} pages, {sum(map(len, articles.values()))} articles, "
          f"{len(locations)} sitemap URLs, 3 feeds, AI index, shared comment mappings")


if __name__ == "__main__":
    check(Path(sys.argv[1] if len(sys.argv) > 1 else "_site").resolve())
