"""
Campus events copied from SDU Life (life.sdu.edu.kz) into the project's own
events table, where the events page searches them (US19, US20).

Nothing here goes to the network: SDU Life's page is a document written below,
shaped like its home page, whose Next.js payload carries the events.
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.auth import UserStore
from app.engine import CAMPUS_TZ
from app.main import app
from app.sdulife import (FRESH, NO_PLACE, RETRY, SOURCE, SduLifeSync, SourceError, clean_place, venue_of,
                         parse_events)

PASSWORD = "Campus#2026"
ADMIN = "240104101@sdu.edu.kz"

EVENTS = [
    {"id": 301, "title": "ZHAUAP BER!", "date": "2030-11-12T12:30:00Z", "hasTime": True,
     "organizer": "GAP", "location": "12.11\nMini Red Hall\n18:00",
     "description": "Интеллектуалдық ойын.\n\nBring a team of four.", "category": ["Games"],
     "attendees": 3, "image": "https://s3.twcstorage.ru/240b4d6f-sdu-life/igpalife/media/event_banners/1/q.webp",
     "blur": None},
    {"id": 302, "title": "Health Day", "date": "2030-11-13T04:00:00Z", "hasTime": True,
     "organizer": "RC SDU", "location": "", "description": "Free check-ups.", "category": [],
     "attendees": 0, "image": "https://elsewhere.example/poster.webp", "blur": None},
    {"id": 303, "title": "Research Poster Day", "date": "2030-11-14T00:00:00Z", "hasTime": False,
     "organizer": "", "location": "Registration: https://forms.gle/abc\nF202",
     "description": "Posters by every school.", "category": [], "attendees": 0, "image": None, "blur": None},
    # not an event: a club has an id and a title too
    {"id": 9, "title": "Puzzle club", "members": 40},
]


def page(events=EVENTS) -> bytes:
    """SDU Life's home page as the server sends it: the events inside strings
    pushed to self.__next_f, split across two pushes."""
    flight = '1:["$","div",null,{"events":' + json.dumps(events, ensure_ascii=False) + "}]"
    half = len(flight) // 2
    pushes = "".join(f"<script>self.__next_f.push([1,{json.dumps(part, ensure_ascii=False)}])</script>"
                     for part in (flight[:half], flight[half:]))
    return f"<!DOCTYPE html><html><body><div id=events></div>{pushes}</body></html>".encode()


# ------------------------------------------------------------ reading the page
def test_the_events_are_read_from_the_page_in_campus_time():
    events = parse_events(page())
    assert [e["source_id"] for e in events] == ["301", "302", "303"]
    quiz = events[0]
    # 12:30 UTC is 17:30 on campus; SDU Life gives no end, so two hours are taken
    assert quiz["starts_at"] == "2030-11-12 17:30" and quiz["ends_at"] == "2030-11-12 19:30"
    assert quiz["place"] == "Mini Red Hall" and quiz["organizer"] == "GAP"
    assert quiz["link"] == "https://life.sdu.edu.kz/en/events/301"
    assert quiz["description"] == "Интеллектуалдық ойын.\n\nBring a team of four."


def test_an_event_without_a_time_takes_the_whole_day():
    poster = parse_events(page())[2]
    assert (poster["starts_at"], poster["ends_at"]) == ("2030-11-14 00:00", "2030-11-15 00:00")


def test_links_dates_and_hours_are_not_taken_for_a_place():
    assert clean_place("Registration: https://forms.gle/abc\nF202") == "F202"
    assert clean_place("12.11\nMini Red Hall\n18:00") == "Mini Red Hall"
    assert clean_place("Капитандарға арналған Google форма: https://forms.gle/x\nТіркелу мерзімі: 11 қарашаға дейін") \
        == NO_PLACE
    assert clean_place("") == NO_PLACE


def test_long_fields_are_cut_to_what_an_event_may_hold():
    long = [{**EVENTS[1], "title": "T" * 300, "description": "word " * 400}]
    event = parse_events(page(long))[0]
    assert len(event["title"]) <= 120 and len(event["description"]) <= 1000
    assert event["description"].endswith("…")


def test_a_page_without_events_is_an_error_not_an_empty_list():
    with pytest.raises(SourceError):
        parse_events(b"<html><body>Maintenance</body></html>")
    with pytest.raises(SourceError):
        parse_events(page([{"id": 1, "title": "Broken", "date": "soon", "location": "", "description": ""}]))


# ------------------------------------------------------------- the copy kept
@pytest.fixture()
def store(tmp_path):
    return UserStore(tmp_path / "users.db")


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.at = datetime(2030, 11, 10, 12, 0, tzinfo=CAMPUS_TZ)

    def mono(self):
        return self.t

    def now(self):
        return self.at

    def wait(self, seconds):
        self.t += seconds
        self.at += timedelta(seconds=seconds)


def sync_of(store, pages, clock):
    calls = []

    def fetch():
        calls.append(1)
        body = pages[0]
        if isinstance(body, Exception):
            raise body
        return body

    rooms = {"F202": "F202"}
    return SduLifeSync(store, room_of=rooms.get, fetch=fetch, clock=clock.mono, now=clock.now), calls


def test_a_copy_lands_in_the_events_table_and_is_searched_there(store):
    clock = Clock()
    sync, _ = sync_of(store, [page()], clock)
    assert sync.refresh() is True
    rows = store.campus_events(after="2030-11-10 12:00")
    assert [r["title"] for r in rows] == ["ZHAUAP BER!", "Health Day", "Research Poster Day"]
    assert {r["source"] for r in rows} == {SOURCE}
    # a place that is a room of the plans is linked to it
    assert [r["room_number"] for r in rows] == [None, None, "F202"]
    assert rows[1]["place"] == NO_PLACE
    assert [r["title"] for r in store.campus_events(words=["ойын"])] == ["ZHAUAP BER!"]
    assert sync.status()["synced_at"] == "2030-11-10 12:00" and sync.status()["stale"] is False


def test_a_second_copy_updates_in_place_and_drops_an_upcoming_one_called_off(store):
    clock = Clock()
    pages = [page()]
    sync, _ = sync_of(store, pages, clock)
    sync.refresh()
    ids = {r["title"]: r["event_id"] for r in store.campus_events()}
    moved = [{**EVENTS[0], "title": "ZHAUAP BER! Final", "date": "2030-11-12T13:00:00Z"}, EVENTS[2]]
    pages[0] = page(moved)
    clock.wait(FRESH + 1)
    assert sync.refresh() is True
    rows = store.campus_events()
    assert [r["title"] for r in rows] == ["ZHAUAP BER! Final", "Research Poster Day"]
    assert rows[0]["event_id"] == ids["ZHAUAP BER!"] and rows[0]["starts_at"] == "2030-11-12 18:00"


def test_one_that_has_started_stays_when_the_page_no_longer_lists_it(store):
    clock = Clock()
    pages = [page()]
    sync, _ = sync_of(store, pages, clock)
    sync.refresh()
    clock.at = datetime(2030, 11, 12, 18, 0, tzinfo=CAMPUS_TZ)     # the quiz is on
    clock.wait(FRESH + 1)
    pages[0] = page(EVENTS[1:3])
    sync.refresh()
    assert "ZHAUAP BER!" in [r["title"] for r in store.campus_events()]


def test_the_page_is_asked_at_most_every_half_hour_by_any_instance(store):
    clock = Clock()
    first, calls_1 = sync_of(store, [page()], clock)
    first.refresh()
    clock.wait(60)
    # another server instance, started later, goes by the time kept in the database
    second, calls_2 = sync_of(store, [page()], clock)
    assert second.refresh() is False and first.refresh() is False
    assert (len(calls_1), len(calls_2)) == (1, 0)
    clock.wait(FRESH)
    assert second.refresh() is True and len(calls_2) == 1


def test_when_sdu_life_cant_be_reached_the_copy_stays_and_is_marked_stale(store):
    clock = Clock()
    pages = [page()]
    sync, calls = sync_of(store, pages, clock)
    sync.refresh()
    pages[0] = OSError("timed out")
    clock.wait(FRESH + 1)
    assert sync.refresh() is False
    assert len(store.campus_events()) == 3 and sync.status()["stale"] is True
    clock.wait(RETRY - 1)
    sync.refresh()
    assert len(calls) == 2              # not asked again before RETRY
    pages[0] = page()
    clock.wait(2)
    assert sync.refresh() is True and sync.status()["stale"] is False


def test_a_copied_event_cant_be_changed_or_deleted_in_the_store(store):
    sync, _ = sync_of(store, [page()], Clock())
    sync.refresh()
    row = store.campus_events()[0]
    assert store.event_source(row["event_id"]) == SOURCE
    assert store.delete_event(row["event_id"]) is False
    assert store.update_event(row["event_id"], {**row, "link": None}, None) is None


def test_an_old_users_database_gains_the_new_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE campus_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                 " description TEXT NOT NULL, place TEXT NOT NULL, room_number TEXT, starts_at TEXT NOT NULL,"
                 " ends_at TEXT NOT NULL, link TEXT, created_by INTEGER, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO campus_events (title, description, place, starts_at, ends_at, created_at)"
                 " VALUES ('Old', 'kept', 'F202', '2030-01-01 10:00', '2030-01-01 11:00', 'x')")
    conn.commit()
    conn.close()
    store = UserStore(path)
    assert store.campus_events()[0]["source"] is None
    sync, _ = sync_of(store, [page()], Clock())
    assert sync.refresh() is True and len(store.campus_events()) == 4


# -------------------------------------------------------------------- the API
def account(number: int) -> TestClient:
    c = TestClient(app)
    email = f"24010{number:04d}@sdu.edu.kz"
    res = c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Aidana Serikova"})
    if res.status_code != 200:
        res = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return c


@pytest.fixture()
def live(monkeypatch):
    """The app with SDU Life copying turned on, reading the page above."""
    clock = Clock()
    clock.at = datetime.now(CAMPUS_TZ)
    sync = SduLifeSync(main.users, room_of=main._room_of, fetch=lambda: page(), clock=clock.mono, now=clock.now)
    monkeypatch.setattr(main, "sdulife", sync)
    monkeypatch.setattr(main, "ADMINS", {ADMIN})
    main._events_changed()
    yield sync
    with main.users._connect() as conn:
        conn.execute("DELETE FROM campus_events WHERE source = ?", (SOURCE,))
    main._events_changed()


def test_the_events_page_copies_sdu_life_first_and_says_so(live):
    c = account(4102)
    data = c.get("/api/events").json()
    titles = [e["title"] for e in data["events"]]
    assert titles[:3] == ["ZHAUAP BER!", "Health Day", "Research Poster Day"]
    quiz = data["events"][0]
    assert quiz["source"] == SOURCE and quiz["organizer"] == "GAP" and quiz["editable"] is False
    assert quiz["date"] == "Tue 12 Nov" and quiz["time"] == "17:30–19:30"
    poster = data["events"][2]
    assert poster["room"] == "F202" and poster["where"]           # it lights up on the plan
    assert data["sources"][0]["name"] == "SDU Life" and data["sources"][0]["stale"] is False
    # US20: the search and the dates run on the same table
    assert [e["title"] for e in c.get("/api/events", params={"q": "ОЙЫН"}).json()["events"]] == ["ZHAUAP BER!"]
    week = c.get("/api/events", params={"from": "2030-11-13", "to": "2030-11-13"}).json()["events"]
    assert [e["title"] for e in week] == ["Health Day"]


def test_pressing_a_copied_event_finds_it_on_the_map(live):
    c = account(4102)
    c.get("/api/events")
    answer = c.get("/api/search", params={"q": "Research Poster Day"}).json()
    assert answer["occasion"]["title"] == "Research Poster Day" and "F202" in answer["summary"]


def test_a_copied_event_is_not_deleted_here(live):
    admin = account(4101)
    quiz = admin.get("/api/events").json()["events"][0]
    assert admin.delete(f"/api/events/{quiz['event_id']}").status_code == 409


# ------------------------------------------------- corrections from the poster
def test_a_correction_in_the_store_outlives_the_next_copy(store):
    clock = Clock()
    sync, _ = sync_of(store, [page()], clock)
    sync.refresh()
    quiz = store.campus_events()[0]
    fixed = store.correct_event(quiz["event_id"], "Red Hall", None, "2030-11-12 18:00", "2030-11-12 20:30")
    assert fixed["corrected"] == 1
    clock.wait(FRESH + 1)
    renamed = [{**EVENTS[0], "title": "ZHAUAP BER! Final"}, *EVENTS[1:]]
    sync._fetch = lambda: page(renamed)
    assert sync.refresh() is True
    row = next(r for r in store.campus_events() if r["event_id"] == quiz["event_id"])
    # SDU Life's title still comes through; the place and the times are the poster's
    assert (row["title"], row["place"], row["starts_at"], row["ends_at"]) == \
        ("ZHAUAP BER! Final", "Red Hall", "2030-11-12 18:00", "2030-11-12 20:30")
    assert store.uncorrect_event(quiz["event_id"]) is True
    sync.refresh(force=True)
    row = next(r for r in store.campus_events() if r["event_id"] == quiz["event_id"])
    assert (row["place"], row["starts_at"], row["corrected"]) == ("Mini Red Hall", "2030-11-12 17:30", 0)


def test_an_event_added_here_cant_be_corrected_as_a_copy(store):
    row = store.add_event({"title": "Club fair", "description": "", "place": "F202", "starts_at": "2030-11-20 15:00",
                           "ends_at": "2030-11-20 17:00", "link": None}, "F202", None)
    assert store.correct_event(row["event_id"], "Red Hall", None, "2030-11-20 15:00", "2030-11-20 16:00") is None
    assert store.uncorrect_event(row["event_id"]) is False


def test_an_administrator_corrects_place_and_time_but_not_the_title(live):
    admin = account(4101)
    quiz = admin.get("/api/events").json()["events"][0]
    form = {"title": "Renamed", "description": "Changed", "room": "F202", "place": "",
            "starts": "2030-11-12T18:00", "ends": "2030-11-12T20:00", "link": quiz["link"]}
    res = admin.put(f"/api/events/{quiz['event_id']}", json=form)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["title"] == "ZHAUAP BER!" and out["description"].startswith("Интеллектуалдық")
    assert out["room"] == "F202" and out["time"] == "18:00–20:00" and out["corrected"] is True
    # a copy made now keeps it, and the search finds it in its new room
    admin.post("/api/events/sync")
    again = next(e for e in admin.get("/api/events").json()["events"] if e["event_id"] == quiz["event_id"])
    assert again["room"] == "F202" and again["time"] == "18:00–20:00"
    assert "F202" in admin.get("/api/search", params={"q": "ZHAUAP BER!"}).json()["summary"]
    # undone, SDU Life's place and time are back at once
    assert admin.delete(f"/api/events/{quiz['event_id']}/correction").status_code == 200
    back = next(e for e in admin.get("/api/events").json()["events"] if e["event_id"] == quiz["event_id"])
    assert (back["place"], back["time"], back["corrected"]) == ("Mini Red Hall", "17:30–19:30", False)
    assert admin.delete(f"/api/events/{quiz['event_id']}/correction").status_code == 200   # nothing to undo is fine


def test_a_student_cant_correct_an_event(live):
    student = account(4102)
    quiz = student.get("/api/events").json()["events"][0]
    form = {"title": quiz["title"], "place": "Red Hall", "starts": "2030-11-12T18:00", "ends": "2030-11-12T20:00"}
    assert student.put(f"/api/events/{quiz['event_id']}", json=form).status_code == 403
    assert student.delete(f"/api/events/{quiz['event_id']}/correction").status_code == 403


def test_an_administrator_can_copy_now_and_a_student_cant(live):
    student = account(4102)
    assert student.post("/api/events/sync").status_code == 403
    admin = account(4101)
    res = admin.post("/api/events/sync")
    assert res.status_code == 200 and res.json()["synced_at"]


def test_with_copying_turned_off_the_events_page_has_no_source(monkeypatch):
    monkeypatch.setattr(main, "sdulife", None)
    data = account(4102).get("/api/events").json()
    assert data["sources"] == []


# ------------------------------------------------------------------ posters
POSTER = "https://s3.twcstorage.ru/240b4d6f-sdu-life/igpalife/media/event_banners/1/q.webp"


def test_only_a_poster_in_sdu_lifes_bucket_is_kept():
    quiz, health, poster_day = parse_events(page())
    assert quiz["image"] == POSTER
    assert health["image"] is None and poster_day["image"] is None


def test_an_administrator_gets_the_poster_through_the_site(live, monkeypatch):
    asked = []

    def fake(url):
        asked.append(url)
        return b"RIFF....WEBP", "image/webp"

    monkeypatch.setattr(main, "fetch_poster", fake)
    admin = account(4101)
    events = admin.get("/api/events").json()["events"]
    quiz, health = events[0], events[1]
    assert quiz["poster"] == f"/api/events/{quiz['event_id']}/poster" and health["poster"] is None
    res = admin.get(quiz["poster"])
    assert res.status_code == 200 and res.content == b"RIFF....WEBP"
    assert res.headers["content-type"] == "image/webp" and asked == [POSTER]
    assert admin.get(f"/api/events/{health['event_id']}/poster").status_code == 404
    # a student doesn't, and nothing is fetched for them
    assert account(4102).get(quiz["poster"]).status_code == 403 and len(asked) == 1


def test_a_poster_that_cant_be_fetched_is_a_502(live, monkeypatch):
    def broken(url):
        raise OSError("timed out")

    monkeypatch.setattr(main, "fetch_poster", broken)
    admin = account(4101)
    quiz = admin.get("/api/events").json()["events"][0]
    assert admin.get(quiz["poster"]).status_code == 502


def test_a_picture_elsewhere_is_never_fetched():
    from app.sdulife import fetch_poster
    for url in ("https://elsewhere.example/x.webp", "http://s3.twcstorage.ru/240b4d6f-sdu-life/a.webp",
                "https://s3.twcstorage.ru/other-bucket/a.webp", "https://s3.twcstorage.ru/240b4d6f-sdu-life/../x.svg"):
        with pytest.raises(SourceError):
            fetch_poster(url)


# what tesseract read off real SDU Life posters (11 November 2026), and what the
# page's reader takes from it: it fills the form, a person checks it
POSTER_TEXTS = {
    "Health Day MEDICAL CHECK-UP 12 | November 09:00-16:00 G-H block": ("09:00", "16:00", ["G-H block"]),
    "aiqyn A New Reality 24 қараша 17:50 Blue Hall": ("17:50", None, ["Blue Hall"]),
    "EDU JOB FAIR 2026 @ 11 NOVEMBER, 10:00-14:00 @ G-H BLOCK AREA": ("10:00", "14:00", ["G-H block"]),
    "NIGHT AT THE MUSEUM 27.11.2026 17:30-20:30 From WiFi zone to F block": ("17:30", "20:30", ["WiFi zone", "F block"]),
    "13/11/26 Qamqor Gala SDU | Red Hall | 18:00": ("18:00", None, ["Red Hall"]),
    "FILM HUNTER 12.11.2026 SDU LIFE": (None, None, []),
}


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node is not installed")
def test_the_pages_poster_reader_takes_times_and_places_not_dates():
    import subprocess
    from pathlib import Path
    script = Path(__file__).resolve().parent.parent / "static" / "poster-ocr.js"
    out = subprocess.run(["node", "-e", "const P = require(process.argv[1]);"
                          " const texts = JSON.parse(process.argv[2]);"
                          " console.log(JSON.stringify(texts.map((t) => P.readPoster(t))))",
                          str(script), json.dumps(list(POSTER_TEXTS))],
                         capture_output=True, text=True, check=True, timeout=30).stdout
    for found, (start, end, places) in zip(json.loads(out), POSTER_TEXTS.values()):
        assert (found["start"], found["end"]) == (start, end)
        assert [p.lower() for p in found["places"]] == [p.lower() for p in places]


# ------------------------------------------------- where an event's place is
@pytest.mark.parametrize("place, room", [
    ("Бочка С1", "D113"),               # hall C1, typed with a Cyrillic С
    ("Red Hall, SDU", "RED-HALL"),
    ("F202 аудитория", "F202"),
])
def test_a_place_that_names_a_room_lights_it_up(place, room):
    assert main.index.event_place(place)["room"]["room_number"] == room


@pytest.mark.parametrize("place", ["Mini Red Hall", "Shanyraq Zone", "SDU University", "online reading"])
def test_a_place_the_directory_doesnt_hold_is_not_taken_for_a_room_it_does(place):
    assert main.index.event_place(place) == {}


@pytest.mark.parametrize("place, blocks, shown", [
    ("G block аллея", ["G"], "G"),
    ("G-H block", ["G", "H"], "G"),
    ("Коридор SDU (от блока D до блока F)", ["D", "E", "F"], "E"),
    ("D-F block-тар арасы", ["D", "E", "F"], "E"),
    ("блок Е, 2 этаж", ["E"], "E"),       # a Cyrillic Е
    ("в блоке D", ["D"], "D"),            # "в" is a word, not block B
])
def test_a_place_that_names_blocks_shows_the_block(place, blocks, shown):
    assert main.index.event_place(place) == {"blocks": blocks, "block": shown}


def test_sdu_life_centre_is_a_building_of_its_own():
    for place in ("SDU LIFE CENTRE", "SDU Life Center", "Лайф центр"):
        assert main.index.event_place(place) == {"building": "SDU Life Centre"}


def test_an_event_in_a_block_opens_the_block_and_one_in_life_centre_says_where_it_is(live):
    live._fetch = lambda: page([{**EVENTS[0], "location": "G block аллея"},
                                {**EVENTS[1], "location": "SDU LIFE CENTRE"}])
    c = account(4102)
    events = c.get("/api/events").json()["events"]
    quiz, health = events[0], events[1]
    assert quiz["room"] is None and quiz["where"] == "Block G"
    assert health["where"] == "a separate building"
    a = c.get("/api/search", params={"q": "ZHAUAP BER!"}).json()
    assert a["kind"] == "block" and a["block"]["building_id"] == "G" and a["map"]
    assert a["occasion"]["title"] == "ZHAUAP BER!" and "Block G" in a["summary"]
    b = c.get("/api/search", params={"q": "Health Day"}).json()
    # SDU Life Centre is off the floor plans: the Campus view lights it, with the walk there
    assert b["kind"] == "event" and "SDU Life Centre" in b["summary"]
    assert b["map"]["floor"] == 0 and b["map"]["code"] == "SDU-LIFE" and b["map"]["walk"]
    assert b["occasion"]["title"] == "Health Day"


def test_a_long_text_on_a_row_of_its_own_is_put_back():
    # Next.js writes "$2b" in the field and the text after the rows, "2b:T<bytes, hex>,<text>",
    # one straight after another with no line between them
    first, second = "Film Hunter — кино байқауы 🎬", "Venue: SDU University, Blue Hall"
    rows = f'2b:T{len(first.encode()):x},{first}2c:T{len(second.encode()):x},{second}'
    events = [{**EVENTS[0], "description": "$2b"}, {**EVENTS[1], "description": "$2c"}]
    body = page(events).replace(b"</body>",
        f"<script>self.__next_f.push([1,{json.dumps(chr(10) + rows, ensure_ascii=False)}])</script></body>".encode())
    quiz, health = parse_events(body)[:2]
    assert quiz["description"] == first
    assert health["description"] == second and health["place"] == "SDU University, Blue Hall"


@pytest.mark.parametrize("description, venue", [
    ("📅 Күні: 14.11.2026 ⏰ Басталуы: 10:00 📍 Өтетін орны: Sport Hall\nТіркел!", "Sport Hall"),
    ("📍 EVENT DETAILS\nVenue: SDU University, Blue Hall", "SDU University, Blue Hall"),
    ("Танцы!\n📍 Shanyraq Zone\n", "Shanyraq Zone"),
    ("📍 Орны: WI-Fi zone- F block", "WI-Fi zone- F block"),
    ("🥇 1st place: 200,000 KZT\n🥈 2-орын: 120 000 ₸\n📍 Format: Offline+Online", None),
    ("📍 Іс-шара қалай өтеді?\n📍 Өткізу форматы: Офлайн", None),
])
def test_the_venue_is_read_from_the_description(description, venue):
    assert venue_of(description) == venue


def test_a_vague_place_gives_way_to_the_descriptions_venue_but_a_clear_one_doesnt():
    events = [{**EVENTS[0], "location": "SDU LIFE CENTRE", "description": "Venue: SDU University, Blue Hall"},
              {**EVENTS[1], "location": "", "description": "📍 Өтетін орны: Sport Hall"},
              {**EVENTS[2], "location": "F202", "description": "Venue: Red Hall"}]
    assert [e["place"] for e in parse_events(page(events))] == ["SDU University, Blue Hall", "Sport Hall", "F202"]


def test_the_wi_fi_zone_is_the_lobby_of_block_c():
    assert main.index.event_place("Wi-fi zone") == {"blocks": ["C"], "block": "C"}
    assert main.index.event_place("WI-Fi zone- F block") == {"blocks": ["C", "D", "E", "F"], "block": "E"}


# ------------------------------------------------------- the campus grounds
def test_the_map_carries_the_campus_grounds_round_the_main_building():
    c = account(4102)
    data = c.get("/api/map").json()
    assert [f["floor"] for f in data["floors"]] == [1, 2, 3]
    site = data["site"]
    assert site["site"] is True and {r["code"] for r in site["rooms"]} == {"SDU-LIFE", "STUDENT-HOUSE"}
    # the main building is floor 1's own outline, moved into the grounds
    assert len(site["areas"]) == len(data["floors"][0]["areas"])
    xs = [p[0] for r in site["rooms"] for p in r["points"]] + [p[0] for a in site["areas"] for p in a["points"]]
    ys = [p[1] for r in site["rooms"] for p in r["points"]] + [p[1] for a in site["areas"] for p in a["points"]]
    assert 0 <= min(xs) and max(xs) <= site["width"] and 0 <= min(ys) and max(ys) <= site["height"]
    life = next(r for r in site["rooms"] if r["code"] == "SDU-LIFE")
    main_x = [p[0] for a in site["areas"] for p in a["points"]]
    # SDU Life Centre is west of the main building and south of it
    assert max(p[0] for p in life["points"]) < min(main_x)
    assert min(p[1] for p in life["points"]) > max(p[1] for a in site["areas"] for p in a["points"])


@pytest.mark.parametrize("question, code", [
    ("SDU Life", "SDU-LIFE"), ("Where is SDU Life Centre?", "SDU-LIFE"),
    ("общежитие", "STUDENT-HOUSE"), ("where is the dormitory", "STUDENT-HOUSE"),
])
def test_a_building_of_the_grounds_is_found_by_name(question, code):
    a = main.index.search(question)
    assert a["kind"] == "site" and a["map"]["code"] == code and a["map"]["floor"] == 0 and a["map"]["walk"]


def test_a_room_is_still_a_room_not_a_building_of_the_grounds():
    assert main.index.search("Red Hall")["kind"] == "room"


@pytest.mark.parametrize("place, hall", [("Sport Hall", "Sport Hall"), ("SDU University, Blue Hall", "Blue Hall"),
                                         ("спортзал", "Sport Hall")])
def test_sport_hall_and_blue_hall_are_in_sdu_life_centre(place, hall):
    assert main.index.event_place(place) == {"building": "SDU Life Centre", "hall": hall}


def test_an_event_in_blue_hall_is_shown_at_sdu_life_centre(live):
    live._fetch = lambda: page([{**EVENTS[0], "location": "SDU LIFE CENTRE",
                                 "description": "Venue: SDU University, Blue Hall"}])
    c = account(4102)
    quiz = c.get("/api/events").json()["events"][0]
    assert quiz["place"] == "SDU University, Blue Hall" and quiz["where"] == "SDU Life Centre"
    a = c.get("/api/search", params={"q": "ZHAUAP BER!"}).json()
    assert a["map"]["code"] == "SDU-LIFE" and "in Blue Hall, in SDU Life Centre" in a["summary"]
    for question in ("Blue Hall", "where is Sport Hall"):
        assert main.index.search(question)["map"]["code"] == "SDU-LIFE"
