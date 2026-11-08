"""
News from SDU University's own site, sdu.edu.kz, read from its English RSS feed.

The university publishes no events in a form a program can read (its events
page is empty, and the "upcoming events" on its home page are pictures), but
its news is a WordPress feed. The events page shows the latest items under its
own heading, as news with the date it was published: a news date is not the
date of an event, and nothing here pretends it is. Events with a time and a
room are added by an administrator (see app/main.py, /api/events).

The feed is fetched at most every FRESH seconds per server instance and kept in
memory; when the site can't be reached the last copy is served, marked stale.
Only links and pictures on sdu.edu.kz are kept, so the page never points
anywhere else on the feed's say-so.
"""
import html
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from .engine import CAMPUS_TZ

FEED_URL = "https://sdu.edu.kz/en/feed/"
NEWS_PAGE = "https://sdu.edu.kz/en/"
SITE = re.compile(r"^https://(?:www\.)?sdu\.edu\.kz/[^\s\"'<>]*$")
FRESH = 30 * 60              # seconds a fetched feed is used before asking again
RETRY = 5 * 60               # after a failure, seconds before trying again
TIMEOUT = 6                  # seconds; the page waits for this at most
MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 10
EXCERPT = 220
USER_AGENT = "SDU-Campus-Assistant/1.0 (campus wayfinding; reads the public news feed)"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


class FeedError(Exception):
    pass


def fetch_feed(url: str = FEED_URL) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/rss+xml, text/xml"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as res:   # noqa: S310 (a fixed https URL)
        body = res.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise FeedError("the feed is larger than expected")
    return body


def _text(fragment: str) -> str:
    """HTML to one line of plain text."""
    no_tags = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", fragment or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _excerpt(description: str, title: str) -> str:
    text = _text(description)
    # WordPress's excerpt begins by repeating the title
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" :–—-")
    text = re.sub(r"\s*(?:\[(?:…|&hellip;|\.\.\.)\]|The post .*$)", "", text).strip()
    if len(text) > EXCERPT:
        text = text[:EXCERPT].rsplit(" ", 1)[0].rstrip(",;:—– ") + "…"
    return text


def _picture(content: str) -> str | None:
    for src in re.findall(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']", content or "", flags=re.I):
        src = html.unescape(src)
        if SITE.match(src) and "/wp-content/uploads/" in src:
            return src
    return None


def parse_feed(body: bytes) -> list[dict]:
    """The items of an RSS 2.0 feed as the page shows them, newest first. A
    document declaring entities or a doctype is refused rather than parsed, so a
    feed can't expand itself into something enormous."""
    head = body[:4096].decode("utf-8", "replace")
    if re.search(r"<!(DOCTYPE|ENTITY)", head, re.I) or b"<!ENTITY" in body:
        raise FeedError("the feed declares entities")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise FeedError(f"the feed isn't valid XML ({err})") from None
    channel = root.find("channel")
    if channel is None:
        raise FeedError("the feed has no channel")
    items = []
    for item in channel.findall("item"):
        title = _text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if not title or not SITE.match(link):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(CAMPUS_TZ)
        except (TypeError, ValueError):
            continue
        items.append({"title": title, "link": link,
                      "published": published.strftime("%Y-%m-%d %H:%M"),
                      "date": f"{published.day} {published:%B %Y}",
                      "excerpt": _excerpt(item.findtext("description") or "", title),
                      "image": _picture(item.findtext(CONTENT) or "")})
    items.sort(key=lambda i: i["published"], reverse=True)
    return items[:MAX_ITEMS]


class NewsFeed:
    """The feed, kept in memory and asked again when it has gone stale."""

    def __init__(self, fetch=fetch_feed, clock=time.monotonic) -> None:
        self._fetch, self._clock = fetch, clock
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._fetched_at: datetime | None = None
        self._next_try = 0.0
        self._ok = False

    def latest(self) -> dict:
        now = self._clock()
        if now >= self._next_try and self._lock.acquire(blocking=False):
            try:
                self._items = parse_feed(self._fetch())
                self._fetched_at = datetime.now(CAMPUS_TZ)
                self._ok = True
                self._next_try = now + FRESH
            except Exception:              # noqa: BLE001 — any failure: keep what we had
                self._ok = False
                self._next_try = now + RETRY
            finally:
                self._lock.release()
        return {"items": self._items, "source": NEWS_PAGE,
                "fetched_at": self._fetched_at.strftime("%Y-%m-%d %H:%M") if self._fetched_at else None,
                "stale": not self._ok}
