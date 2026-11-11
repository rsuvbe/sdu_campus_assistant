"""
Campus events from SDU Life (life.sdu.edu.kz), the university's own student
platform, copied into the project's events table.

US19 and US20 want the events in the project's own database, searched there,
so SDU Life is not asked on every page view: its events are copied into
campus_events (UserStore.sync_events) at most every FRESH seconds, and the
events page, the search and the map read them from there like the ones an
administrator added.

Where they come from: SDU Life's public home page (/en) carries every event of
the last weeks and the coming ones in its Next.js payload, as
{"id", "title", "date", "hasTime", "organizer", "location", "description",
"category", ...}. Its /api/ is closed to robots (robots.txt) and each event's
own page asks for a sign-in, so only the public page is read. SDU Life gives no
end time; an event is taken to last DEFAULT_LENGTH, and one without a time the
whole day.
"""
import html
import json
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from .auth import AuthError, clean_event
from .engine import CAMPUS_TZ

SOURCE = "sdulife"
HOME_URL = "https://life.sdu.edu.kz/en"
EVENT_URL = "https://life.sdu.edu.kz/en/events/{id}"
FRESH = 30 * 60               # seconds between two copies
RETRY = 5 * 60                # after a failure
TIMEOUT = 6                   # seconds; the events page waits for this at most
MAX_BYTES = 4 * 1024 * 1024
DEFAULT_LENGTH = timedelta(hours=2)
NO_PLACE = "Place not announced"
USER_AGENT = "SDU-Campus-Assistant/1.0 (campus wayfinding; reads the public events on life.sdu.edu.kz)"

PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
EVENT_START_RE = re.compile(r'\{\s*"id"\s*:\s*\d{1,9}\s*,\s*"title"\s*:')
URL_RE = re.compile(r"https?://|forms\.gle|www\.", re.I)
DATE_OR_TIME_RE = re.compile(r"^[\d\s.:/–—-]+$")     # "12.11", "18:00", "12.11 – 18:00"
# SDU Life keeps its posters in one bucket; a picture anywhere else is not fetched
POSTER_RE = re.compile(r"^https://s3\.twcstorage\.ru/240b4d6f-sdu-life/[A-Za-z0-9/_.-]{1,200}\.(?:webp|png|jpe?g)$")
POSTER_MAX_BYTES = 6 * 1024 * 1024


class SourceError(Exception):
    pass


def fetch_home(url: str = HOME_URL) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html",
                                                   "Accept-Language": "en"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as res:   # noqa: S310 (a fixed https URL)
        body = res.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise SourceError("the page is larger than expected")
    return body


def _payload(page: str) -> str:
    """The Next.js flight data of a page: the strings it pushes, decoded and joined."""
    parts = []
    for chunk in PUSH_RE.findall(page):
        try:
            parts.append(json.loads(f'"{chunk}"'))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _one_line(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—– ") + "…"


def _description(text: str, limit: int = 1000) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in html.unescape(text or "").splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—– ") + "…"


def clean_place(location: str) -> str:
    """SDU Life's location field, as a place: organisers put registration links,
    dates and hours in it too ("12.11\\nMini Red Hall\\n18:00"), so only the
    lines that name a place are kept."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in html.unescape(location or "").splitlines()]
    kept = [line for line in lines if line and not URL_RE.search(line) and not DATE_OR_TIME_RE.match(line)
            and not re.match(r"^(тіркелу|registration|регистрация)\b", line, re.I)]
    return _one_line(", ".join(kept), 120) or NO_PLACE


def parse_events(body: bytes) -> list[dict]:
    """The events on SDU Life's home page, as fields of campus_events (see
    clean_event), each with its SDU Life id as `source_id`. An event that can't be
    read is left out; a page with none at all is an error, so a changed page
    never empties the list."""
    payload = _payload(body.decode("utf-8", "replace"))
    decoder = json.JSONDecoder()
    found: dict[int, dict] = {}
    for match in EVENT_START_RE.finditer(payload):
        try:
            item, _ = decoder.raw_decode(payload, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and {"date", "location", "description"} <= item.keys():
            found.setdefault(item["id"], item)
    events = []
    for source_id, item in found.items():
        try:
            starts = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
            if starts.tzinfo is None:
                starts = starts.replace(tzinfo=timezone.utc)
            starts = starts.astimezone(CAMPUS_TZ)
            if item.get("hasTime") is False:
                starts = starts.replace(hour=0, minute=0)
                ends = starts + timedelta(days=1)
            else:
                ends = starts + DEFAULT_LENGTH
            fields = clean_event(_one_line(str(item.get("title") or ""), 120),
                                 _description(str(item.get("description") or "")),
                                 clean_place(str(item.get("location") or "")),
                                 f"{starts:%Y-%m-%dT%H:%M}", f"{ends:%Y-%m-%dT%H:%M}",
                                 EVENT_URL.format(id=int(source_id)))
        except (AuthError, TypeError, ValueError, OverflowError):
            continue
        fields["source_id"] = str(int(source_id))
        fields["organizer"] = _one_line(str(item.get("organizer") or ""), 120) or None
        image = str(item.get("image") or "")
        fields["image"] = image if POSTER_RE.match(image) else None
        events.append(fields)
    if not events:
        raise SourceError("no events on the page")
    events.sort(key=lambda e: (e["starts_at"], e["title"]))
    return events


def fetch_poster(url: str) -> tuple[bytes, str]:
    """An event's poster from SDU Life's bucket, and its media type, for the
    administrator's browser to read (the bucket doesn't let a page read it)."""
    if not POSTER_RE.match(url or ""):
        raise SourceError("not a poster of SDU Life")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    with urllib.request.urlopen(request, timeout=10) as res:   # noqa: S310 (checked against POSTER_RE)
        kind = res.headers.get_content_type()
        body = res.read(POSTER_MAX_BYTES + 1)
    if not kind.startswith("image/") or len(body) > POSTER_MAX_BYTES:
        raise SourceError("the poster isn't a picture of a usual size")
    return body, kind


class SduLifeSync:
    """Copies SDU Life's events into the store when the last copy has gone stale.
    The time of the last copy is kept in the database, so every server instance
    goes by the same one; a failure is retried after RETRY, and the events
    already copied stay."""

    def __init__(self, store, room_of=lambda place: None, fetch=fetch_home,
                 clock=time.monotonic, now=lambda: datetime.now(CAMPUS_TZ)) -> None:
        self._store, self._room_of, self._fetch = store, room_of, fetch
        self._clock, self._now = clock, now
        self._lock = threading.Lock()
        self._next_try = 0.0
        self.ok: bool | None = None          # None: not tried on this instance
        self.error: str | None = None

    def refresh(self, force: bool = False) -> bool:
        """Copy the events if they are due (or `force`); True when a copy was made."""
        if not force and self._clock() < self._next_try:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if not force:
                last = self._store.last_sync(SOURCE)
                age = (self._now() - datetime.fromisoformat(last).replace(tzinfo=CAMPUS_TZ)).total_seconds() \
                    if last else None
                if age is not None and 0 <= age < FRESH:
                    self._next_try = self._clock() + (FRESH - age)
                    self.ok = True if self.ok is None else self.ok
                    return False
            try:
                events = parse_events(self._fetch())
                for event in events:
                    room = self._room_of(event["place"]) if event["place"] != NO_PLACE else None
                    event["room_number"] = room
                self._store.sync_events(SOURCE, events, self._now().strftime("%Y-%m-%d %H:%M:%S"))
            except Exception as err:         # noqa: BLE001 — any failure: keep what was copied
                self.ok, self.error = False, f"{type(err).__name__}: {err}"[:200]
                self._next_try = self._clock() + RETRY
                return False
            self.ok, self.error = True, None
            self._next_try = self._clock() + FRESH
            return True
        finally:
            self._lock.release()

    def status(self) -> dict:
        last = self._store.last_sync(SOURCE)
        return {"name": "SDU Life", "url": HOME_URL, "synced_at": last[:16] if last else None,
                "stale": self.ok is False}
