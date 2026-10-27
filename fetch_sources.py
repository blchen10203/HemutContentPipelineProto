"""Snapshot Hemut source pages into knowledge/sources/<name>_<YYYY-MM-DD>.txt.

HTML pages also keep the untouched response as <name>_<date>.html; the .txt is its visible text,
extracted the same way every run so dated snapshots diff cleanly. Claims cite these files.

Run: python fetch_sources.py [name ...]   (no names: every URL below)
"""
import datetime
import sys
from html.parser import HTMLParser
from pathlib import Path

import httpx

URLS = {
    "llms-full": "https://hemut.com/llms-full.txt",
    "pricing": "https://hemut.com/pricing",
    "roi-case-studies": "https://hemut.com/roi-case-studies",
    "iftach-carriers": "https://www.iftach.org/Carriers/",  # IFTA quarterly due dates
    "nhc-climo": "https://www.nhc.noaa.gov/climo/",  # official Atlantic hurricane season dates
}
OUT = Path(__file__).parent / "knowledge" / "sources"
SKIP = {"script", "style", "noscript", "template", "svg"}
BLOCK = {
    "title", "p", "div", "section", "article", "header", "footer", "nav", "main", "aside",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "tr", "td", "th", "h1", "h2", "h3", "h4",
    "h5", "h6", "br", "hr", "blockquote", "pre", "figure", "figcaption", "button",
}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    # Inline tags join without a break, so per-letter <span> animations read as words.
    p = _Text()
    p.feed(html)
    p.close()
    lines = (" ".join(line.split()) for line in "".join(p.parts).splitlines())
    return "\n".join(line for line in lines if line) + "\n"


def main(names: list[str] | None = None):
    if unknown := set(names or []) - URLS.keys():
        raise SystemExit(f"Unknown source names {sorted(unknown)}; known: {sorted(URLS)}")
    urls = {n: URLS[n] for n in names} if names else URLS
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    # Claims cite these files, so a dated snapshot is never silently replaced.
    if existing := sorted(p.name for n in urls for p in OUT.glob(f"{n}_{today}.*")):
        raise SystemExit(f"Snapshots for {today} already exist, delete them to refetch: {existing}")
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for name, url in urls.items():
            r = client.get(url)
            r.raise_for_status()
            if "html" in r.headers.get("content-type", ""):
                (OUT / f"{name}_{today}.html").write_bytes(r.content)
                (OUT / f"{name}_{today}.txt").write_text(html_to_text(r.text), encoding="utf-8", newline="\n")
            else:
                (OUT / f"{name}_{today}.txt").write_bytes(r.content)
            print(f"{name}: {url} -> {name}_{today}.txt")


if __name__ == "__main__":
    main(sys.argv[1:])
