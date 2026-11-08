"""
The timetable on a page of its own (/schedule): the week as the student portal
draws it, a screenshot of the portal's Course Schedule read into classes, and
reminders before each class, in the browser and in the phone's calendar.

The screenshot is read in the browser (static/schedule-ocr.js with tesseract.js);
what that reader hands the server is checked here: rooms as an OCR misreads them,
the import, the calendar file. The reader's own table logic runs under Node when
Node is installed (the last tests), on a table made up here.
"""
import json
import re
import shutil
import subprocess
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import MAX_CLASSES
from app.engine import CAMPUS_TZ
from app.ics import first_meeting, timetable_calendar
from app.main import BASE_DIR, app, index, safe_next

STATIC = BASE_DIR / "static"
PASSWORD = "Campus#2026"
INF304 = {"subject": "INF 304 [04-P]", "day": 0, "start": "08:30", "end": "09:20", "room": "F202"}
ONLINE = {"subject": "CSS 280 [02-P]", "day": 0, "start": "18:30", "end": "19:20", "room": "VR 93", "outside": True}


def someone(number: int) -> TestClient:
    c = TestClient(app)
    res = c.post("/api/auth/register", json={"email": f"24030{number:04d}@sdu.edu.kz",
                                             "password": PASSWORD, "full_name": "Aidana Serikova"})
    assert res.status_code == 200, res.text
    return c


@pytest.fixture(scope="module")
def counter():
    return iter(range(1000, 9000))


@pytest.fixture()
def me(counter):
    return someone(next(counter))


@pytest.fixture()
def them(counter):
    return someone(next(counter))


@pytest.fixture()
def visitor():
    c = TestClient(app)
    c.post("/api/auth/guest")
    return c


# ------------------------------------------------------------- the page
def test_the_timetable_has_a_page_of_its_own(me):
    page = me.get("/schedule")
    assert page.status_code == 200 and "Your timetable" in page.text
    for script in ("schedule-ocr.js", "reminders.js", "schedule.js"):
        assert f"/static/{script}" in page.text


def test_a_visit_without_a_session_comes_back_to_the_page_after_signing_in():
    anon = TestClient(app)
    assert anon.get("/schedule", follow_redirects=False).headers["location"] == "/login?next=%2Fschedule"
    # a reminder's way to a class keeps its question through the sign-in
    res = anon.get("/?ask=How%20do%20I%20get%20to%20my%20next%20class%3F", follow_redirects=False)
    assert res.headers["location"] == "/login?next=%2F%3Fask%3DHow%2520do%2520I%2520get%2520to%2520my%2520next%2520class%253F"
    assert anon.get("/", follow_redirects=False).headers["location"] == "/login"


def test_signed_in_the_sign_in_page_sends_you_on_to_the_page_asked_for(me):
    assert me.get("/login?next=%2Fschedule", follow_redirects=False).headers["location"] == "/schedule"
    assert me.get("/login?next=%2F%2Fevil.example", follow_redirects=False).headers["location"] == "/"


@pytest.mark.parametrize("path, goes", [
    ("/schedule", "/schedule"),
    ("/?ask=How%20do%20I%20get%20to%20F202%3F", "/?ask=How%20do%20I%20get%20to%20F202%3F"),
    ("//evil.example", "/"),
    ("/\\evil.example", "/"),
    ("/\t/evil.example", "/"),
    ("/\n/evil.example", "/"),
    ("https://evil.example", "/"),
    ("evil.example", "/"),
    ("/login?next=/schedule", "/"),
    ("", "/"),
    (None, "/"),
])
def test_after_signing_in_only_a_path_on_this_site_is_followed(path, goes):
    assert safe_next(path) == goes


def test_every_page_behind_the_door_keeps_the_page_asked_for_and_loads_the_reminders():
    for name in ("index", "events", "profile", "schedule"):
        html = (STATIC / f"{name}.html").read_text()
        assert 'location.replace("/login?next="+encodeURIComponent(location.pathname+location.search))' in html, name
        assert "/static/reminders.js" in html, name


def test_the_main_page_and_the_profile_lead_to_the_timetable():
    assert 'href="/schedule"' in (STATIC / "index.html").read_text()
    assert 'href="/schedule"' in (STATIC / "profile.html").read_text()
    # an old link to the profile's timetable goes on to the page
    assert 'location.replace("/schedule")' in (STATIC / "profile.js").read_text()


def test_the_service_worker_is_served_from_the_root(me):
    res = me.get("/sw.js")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/javascript")
    assert res.headers["cache-control"] == "no-cache"
    assert "notificationclick" in res.text


# ---------------------------------------------- rooms as an OCR reads them
@pytest.mark.parametrize("read, room", [
    ("F202", "F202"),
    ("I 301", "I301"),          # as the portal writes it
    ("11301", "I301"),          # the house icon's colon and an I, read as ones
    ("11202", "I202"),
    ("S110", "I110"),           # the icon's crumbs read as an S
    ("1 F202", "F202"),         # a crumb left in front
    ("D214", "D214"),
    ("Hall A1", "D117"),
])
def test_a_room_misread_by_the_ocr_is_put_right_against_the_directory(read, room):
    found = index.resolve_room(read)
    assert found and found["room_number"] == room


@pytest.mark.parametrize("read", ["VR 93", "", "Online", "Z999"])
def test_a_room_that_is_not_on_campus_stays_as_written(read):
    assert index.resolve_room(read) is None


def test_the_import_preview_shows_where_each_room_is(me):
    rows = me.post("/api/schedule/rooms", json=[{"room": "11301"}, {"room": "VR 93"}]).json()
    assert rows[0] == {"read": "11301", "on_campus": True, "room_value": "I301", "room_label": "I301",
                       "where": "Floor 3 · Block I"}
    assert rows[1] == {"read": "VR 93", "on_campus": False, "room_value": "VR 93", "room_label": "VR 93",
                       "where": "Not on the campus plans"}


def test_a_visitor_cannot_use_the_import(visitor):
    assert visitor.post("/api/schedule/rooms", json=[{"room": "F202"}]).status_code == 403
    assert visitor.post("/api/schedule/import", json={"classes": [INF304]}).status_code == 403
    assert visitor.get("/api/schedule.ics").status_code == 403


# ------------------------------------------------------------ the import
def test_an_import_replaces_the_week(me):
    me.post("/api/schedule", json={**INF304, "subject": "Old class"})
    res = me.post("/api/schedule/import", json={"classes": [INF304, ONLINE]})
    assert res.status_code == 200
    week = me.get("/api/schedule").json()["classes"]
    assert [c["subject"] for c in week] == ["INF 304 [04-P]", "CSS 280 [02-P]"]
    online = week[1]
    assert (online["room"], online["on_campus"], online["where"]) == ("VR 93", False, "Not on the campus plans")


def test_an_import_can_add_to_the_week_instead(me):
    me.post("/api/schedule", json={**INF304, "subject": "Kept class"})
    me.post("/api/schedule/import", json={"classes": [ONLINE], "replace": False})
    assert [c["subject"] for c in me.get("/api/schedule").json()["classes"]] == ["Kept class", "CSS 280 [02-P]"]


def test_one_wrong_class_stops_the_whole_import_and_names_its_row(me):
    me.post("/api/schedule", json={**INF304, "subject": "Kept class"})
    bad = {**INF304, "start": "10:00", "end": "09:00"}
    res = me.post("/api/schedule/import", json={"classes": [INF304, bad]})
    assert res.status_code == 400
    assert res.json()["detail"]["row"] == 1 and res.json()["detail"]["field"] == "end"
    # nothing was replaced
    assert [c["subject"] for c in me.get("/api/schedule").json()["classes"]] == ["Kept class"]


def test_an_unknown_room_needs_to_be_marked_as_off_campus(me):
    res = me.post("/api/schedule/import", json={"classes": [{**ONLINE, "outside": False}]})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "room"
    res = me.post("/api/schedule", json={**ONLINE, "room": "  "})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "room"
    res = me.post("/api/schedule", json={**ONLINE, "room": "x" * 41})
    assert res.status_code == 400


def test_a_room_on_campus_is_saved_as_the_directory_has_it_even_when_marked_off_campus(me):
    saved = me.post("/api/schedule", json={**INF304, "room": "f202", "outside": True}).json()
    assert (saved["room"], saved["on_campus"]) == ("F202", True)


def test_an_import_respects_the_size_of_a_timetable(me):
    many = [{**INF304, "start": f"{8 + i % 12:02d}:30", "end": f"{8 + i % 12:02d}:50", "day": i % 6}
            for i in range(MAX_CLASSES + 1)]
    assert me.post("/api/schedule/import", json={"classes": many}).status_code == 422
    me.post("/api/schedule", json=INF304)
    res = me.post("/api/schedule/import", json={"classes": many[:MAX_CLASSES], "replace": False})
    assert res.status_code == 400 and str(MAX_CLASSES) in res.json()["detail"]["message"]


def test_an_import_touches_only_your_own_week(me, them):
    them.post("/api/schedule", json={**INF304, "subject": "Their class"})
    me.post("/api/schedule/import", json={"classes": [INF304]})
    assert [c["subject"] for c in them.get("/api/schedule").json()["classes"]] == ["Their class"]


def test_an_empty_import_is_refused(me):
    assert me.post("/api/schedule/import", json={"classes": []}).status_code == 400


# -------------------------------------------------- the next class, off campus
def test_a_next_class_off_campus_says_so_and_leads_to_the_timetable():
    week = [{"class_id": 1, "subject": "CSS 280 [02-P]", "day": 0, "start": "18:30", "end": "19:20", "room": "VR 93"}]
    answer = index.search("where is my next class?", now=datetime(2026, 11, 2, 9, 0), timetable=lambda: week)
    assert "isn't on the campus plans" in answer["summary"]
    assert answer["link"]["href"] == "/schedule"


def test_the_way_to_the_next_class_is_asked_the_way_a_reminder_asks_it():
    week = [{"class_id": 1, "subject": "INF 304", "day": 0, "start": "10:30", "end": "11:20", "room": "F202"},
            {"class_id": 2, "subject": "INF 321", "day": 0, "start": "08:30", "end": "09:20", "room": "D214"}]
    answer = index.search("How do I get to my next class?", now=datetime(2026, 11, 2, 10, 20),
                          timetable=lambda: week)
    assert answer["map"]["code"] == "F202"
    # from the class before, not the entrance
    assert answer["start"] == "D214" and answer["directions"]


# ------------------------------------------------------------ the calendar
def test_the_calendar_file_holds_every_class_weekly_with_a_reminder(me):
    me.post("/api/schedule/import", json={"classes": [INF304, ONLINE]})
    res = me.get("/api/schedule.ics?lead=15")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/calendar")
    assert 'filename="sdu-timetable.ics"' in res.headers["content-disposition"]
    body = res.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert body.count("BEGIN:VEVENT") == 2 and body.count("RRULE:FREQ=WEEKLY") == 2
    assert body.count("TRIGGER:-PT15M") == 2
    # the way there for a class on campus, none for one that isn't
    unfolded = body.replace("\r\n ", "")
    assert "URL:http://testserver/?ask=How%20do%20I%20get%20to%20F202%3F" in unfolded
    assert unfolded.count("URL:") == 1
    assert "LOCATION:VR 93" in unfolded


def test_a_calendar_line_is_folded_at_75_octets(me):
    me.post("/api/schedule", json={**INF304, "subject": "Д" * 80})
    for line in me.get("/api/schedule.ics").text.split("\r\n"):
        assert len(line.encode()) <= 75


def test_the_reminder_lead_is_bounded(me):
    assert me.get("/api/schedule.ics?lead=121").status_code == 422
    assert me.get("/api/schedule.ics?lead=-1").status_code == 422
    assert "VALARM" not in me.get("/api/schedule.ics?lead=0").text


def test_calendar_times_are_campus_time_written_in_utc():
    """08:30 in Almaty is 03:30 UTC (UTC+5 since March 2024): a phone with old
    time-zone files would put an "Asia/Almaty" time an hour out."""
    entry = {"class_id": 7, "subject": "INF 304", "day": 0, "start": "08:30", "end": "09:20",
             "room_label": "F202", "room_value": "F202", "where": "Floor 2 · Block F", "on_campus": True}
    wednesday = datetime(2026, 11, 4, 12, 0, tzinfo=CAMPUS_TZ)
    body = timetable_calendar([entry], "https://site.example", 10, 1, now=wednesday)
    # the series starts this week's Monday, so the week under way is in it too
    assert "DTSTART:20261102T033000Z" in body and "DTEND:20261102T042000Z" in body
    assert "UID:class-7-1@sdu-campus-assistant" in body


def test_the_first_meeting_is_this_weeks_day():
    sunday = datetime(2026, 11, 8, 23, 0, tzinfo=CAMPUS_TZ)
    assert first_meeting(5, "09:30", sunday).isoformat() == "2026-11-07T09:30:00+05:00"


# ------------------------------------------- the screenshot reader, under Node
NODE = shutil.which("node")


def run_reader(script: str) -> object:
    js = (STATIC / "schedule-ocr.js").as_posix()
    code = f"const O = require({json.dumps(js)});\n{script}"
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def portal_words(cells: dict, times: dict) -> tuple[dict, list]:
    """A made-up Course Schedule as an OCR would hand it back: the grid's lines,
    and words with their boxes. `cells` maps (column, row) to the lines of a cell."""
    xs = [27, 85, 200, 316, 431, 547, 662, 778]
    ys = [149, 184] + [184 + 55 * i for i in range(1, 15)]
    words = []

    def word(text, x, y):
        words.append({"text": text, "bbox": {"x0": x - 10, "y0": y - 6, "x1": x + 10, "y1": y + 6}})

    for col, day in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa"], start=1):
        word(day, (xs[col] + xs[col + 1]) / 2, 166)
    for row, (start, end) in times.items():
        top = ys[row + 1]
        word(start, 56, top + 12)
        if end:
            word(end, 56, top + 28)
    for (col, row), lines in cells.items():
        top = ys[row + 1]
        for n, line in enumerate(lines):
            x = xs[col] + 20
            for token in line.split():
                word(token, x, top + 12 + n * 16)
                x += 25
    return {"xs": xs, "ys": ys}, words


@pytest.mark.skipif(not NODE, reason="Node isn't installed")
def test_the_reader_puts_each_cell_in_its_day_and_hour_and_joins_a_class_over_two_hours():
    grid, words = portal_words(
        cells={
            (1, 0): ["INF 304 (04.P]", "1 F202"],          # Monday 08:30, an icon crumb before the room
            (2, 1): ["INF 376 [03-N]", ": 11202"],         # Tuesday 09:30 ...
            (2, 2): ["INF 376 [03-N]", ": 11202"],         # ... and 10:30: one class
            (4, 3): ["INF 451 [15-7]", ": F304"],          # Thursday 11:30, P read as 7
            (1, 10): ["CSS 280 [02-P]", ": VR 93"],        # Monday 18:30, online
        },
        times={0: ("08:30", "09:20"), 1: ("09:30", None), 2: ("10:30", "11:20"),
               3: ("1:30", None),                          # 11:30 read as 1:30
               10: ("18:30", "19:20")})
    found = run_reader(f"console.log(JSON.stringify(O.readTable({json.dumps(words)}, {json.dumps(grid)}, 1)))")
    assert found["problem"] is None
    assert found["classes"] == [
        {"subject": "INF 304", "section": "04-P", "room": "1 F202", "day": 0, "start": "08:30", "end": "09:20"},
        {"subject": "CSS 280", "section": "02-P", "room": "VR 93", "day": 0, "start": "18:30", "end": "19:20"},
        {"subject": "INF 376", "section": "03-N", "room": "11202", "day": 1, "start": "09:30", "end": "11:20"},
        {"subject": "INF 451", "section": "15-P", "room": "F304", "day": 3, "start": "11:30", "end": "12:20"},
    ]
    # and the rooms as read go to the server, which finds them
    assert [index.read_room(c["room"], 40)["room_value"] for c in found["classes"]] == ["F202", "VR 93", "I202", "F304"]


@pytest.mark.skipif(not NODE, reason="Node isn't installed")
def test_the_reader_finds_the_table_by_its_yellow_lines_and_wipes_the_icons():
    script = """
      const w = 60, h = 40, data = new Uint8ClampedArray(w * h * 4).fill(255);
      const put = (x, y, rgb) => { const i = (y * w + x) * 4; data[i] = rgb[0]; data[i + 1] = rgb[1]; data[i + 2] = rgb[2]; };
      for (const x of [2, 20, 40, 58]) for (let y = 0; y < h; y++) put(x, y, [250, 209, 99]);
      for (const y of [1, 15, 30, 39]) for (let x = 0; x < w; x++) put(x, y, [250, 209, 99]);
      put(10, 8, [0, 0, 255]);      // a letter in the portal's blue
      put(11, 8, [40, 40, 40]);     // a grey one
      put(30, 8, [0, 28, 47]);      // the house icon
      put(31, 8, [230, 170, 120]);  // the teacher's face
      const g = O.findGrid({ width: w, height: h, data });
      const p = O.prepare({ width: w, height: h, data }, 1);
      const at = (x, y) => p.data[(y * w + x) * 4];
      console.log(JSON.stringify({ g, ink: [at(10, 8), at(11, 8), at(30, 8), at(31, 8), at(2, 20)] }));
    """
    out = run_reader(script)
    assert out["g"] == {"xs": [2, 20, 40, 58], "ys": [1, 15, 30, 39]}
    # text stays black; icons and the yellow lines turn white
    assert out["ink"] == [0, 0, 255, 255, 255]
