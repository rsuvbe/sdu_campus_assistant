"""
Sprint 5, checked story by story against the story sheet
(AI_Campus_Assistant_User_Stories_v2.xlsx): every responsibility, every QA
scenario, every test script marked (Pass) or (Fail), and the maintenance tasks
that can be checked by a program.

  US17 Manual Class Schedule Entry          US18 Where Is My Next Class
  US19 Campus Event List                    US20 Event Search and Date Filter

Nothing here reads the wall clock: the events are asked for at a moment given in
the test (`now=`), or, over HTTP, with app.engine.campus_now held at one.
"""
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import MAX_CLASSES
from app.engine import NEXT_CLASS_RE, CampusIndex, next_class, normalize
from app.main import BASE_DIR, DB_PATH, app, index, users

PROFILE_HTML = (BASE_DIR / "static" / "profile.html").read_text()
# the timetable moved from the profile to a page of its own, /schedule
SCHEDULE_HTML = (BASE_DIR / "static" / "schedule.html").read_text()
SCHEDULE_JS = (BASE_DIR / "static" / "schedule.js").read_text()
APP_JS = (BASE_DIR / "static" / "app.js").read_text()
INDEX_HTML = (BASE_DIR / "static" / "index.html").read_text()
EVENTS_HTML = (BASE_DIR / "static" / "events.html").read_text()
EVENTS_JS = (BASE_DIR / "static" / "events.js").read_text()
STYLES_CSS = (BASE_DIR / "static" / "styles.css").read_text()

PASSWORD = "Campus#2026"
CALCULUS = {"subject": "Calculus I", "day": 0, "start": "09:00", "end": "09:50", "room": "D103"}
# Monday 2 November 2026 is a Monday, in campus time
MONDAY = 2


def at(hhmm: str, day: int = MONDAY) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day:02d}T{hhmm}:00")


def someone(number: int) -> TestClient:
    """A client signed in as a fresh account, so no test sees another's week."""
    c = TestClient(app)
    res = c.post("/api/auth/register", json={"email": f"24010{number:04d}@sdu.edu.kz",
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


# ---------------------------------------------------------------- US17
def test_us17_a_class_holds_subject_weekday_times_and_a_room_of_the_directory(me):
    saved = me.post("/api/schedule", json=CALCULUS).json()
    assert (saved["subject"], saved["day"], saved["start"], saved["end"], saved["room"]) == (
        "Calculus I", 0, "09:00", "09:50", "D103")
    assert saved["day_name"] == "Monday"
    assert saved["where"] == "Floor 1 · Block D"


def test_us17_pass_a_user_adds_edits_and_deletes_and_the_changes_persist(me):
    added = me.post("/api/schedule", json=CALCULUS).json()
    assert [c["class_id"] for c in me.get("/api/schedule").json()["classes"]] == [added["class_id"]]

    edited = me.put(f"/api/schedule/{added['class_id']}", json={**CALCULUS, "room": "F204", "start": "10:00",
                                                                "end": "10:50"})
    assert edited.status_code == 200
    week = me.get("/api/schedule").json()["classes"]
    assert (week[0]["room"], week[0]["start"]) == ("F204", "10:00")

    assert me.delete(f"/api/schedule/{added['class_id']}").status_code == 200
    assert me.get("/api/schedule").json()["classes"] == []


def test_us17_scenario_1_the_class_is_still_there_after_logging_in_again(counter):
    email = f"24010{next(counter):04d}@sdu.edu.kz"
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Aidana Serikova"})
    c.post("/api/schedule", json=CALCULUS)
    c.post("/api/auth/logout")
    assert c.get("/api/schedule").status_code == 401

    c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert [e["subject"] for e in c.get("/api/schedule").json()["classes"]] == ["Calculus I"]


def test_us17_the_week_comes_back_in_day_and_time_order(me):
    for day, start, end in ((2, "09:00", "09:50"), (0, "14:00", "14:50"), (0, "09:00", "09:50")):
        me.post("/api/schedule", json={**CALCULUS, "day": day, "start": start, "end": end})
    assert [(c["day"], c["start"]) for c in me.get("/api/schedule").json()["classes"]] == [
        (0, "09:00"), (0, "14:00"), (2, "09:00")]


def test_us17_scenario_2_fail_a_user_cannot_read_another_users_schedule(me, them):
    theirs = them.post("/api/schedule", json=CALCULUS).json()["class_id"]
    res = me.get(f"/api/schedule/{theirs}")
    assert res.status_code == 404
    assert "Calculus" not in res.text and "D103" not in res.text
    assert me.get("/api/schedule").json()["classes"] == []
    assert me.get(f"/api/schedule?user_id={theirs}").json()["classes"] == []
    # the owner still can
    assert them.get(f"/api/schedule/{theirs}").json()["subject"] == "Calculus I"


def test_us17_verified_a_user_cannot_change_or_delete_another_users_class(me, them):
    theirs = them.post("/api/schedule", json=CALCULUS).json()["class_id"]
    assert me.put(f"/api/schedule/{theirs}", json={**CALCULUS, "subject": "Taken over"}).status_code == 404
    assert me.delete(f"/api/schedule/{theirs}").status_code == 404
    week = them.get("/api/schedule").json()["classes"]
    assert [c["subject"] for c in week] == ["Calculus I"]


@pytest.mark.parametrize("call", [
    lambda c: c.get("/api/schedule"),
    lambda c: c.get("/api/schedule/1"),
    lambda c: c.post("/api/schedule", json=CALCULUS),
    lambda c: c.put("/api/schedule/1", json=CALCULUS),
    lambda c: c.delete("/api/schedule/1"),
    lambda c: c.get("/api/rooms"),
])
def test_us17_a_timetable_needs_an_account(visitor, anon, call):
    assert call(visitor).status_code == 403
    assert call(anon).status_code == 401


@pytest.mark.parametrize("room", ["Z999", "D999", "204", "", "Narnia"])
def test_us17_fail_a_class_cannot_be_saved_with_a_room_not_in_the_directory(me, room):
    res = me.post("/api/schedule", json={**CALCULUS, "room": room})
    assert res.status_code == 400
    assert res.json()["detail"]["field"] == "room"
    assert me.get("/api/schedule").json()["classes"] == []


def test_us17_fail_an_edit_cannot_move_a_class_out_of_the_directory(me):
    added = me.post("/api/schedule", json=CALCULUS).json()
    assert me.put(f"/api/schedule/{added['class_id']}", json={**CALCULUS, "room": "Z999"}).status_code == 400
    assert me.get("/api/schedule").json()["classes"][0]["room"] == "D103"


@pytest.mark.parametrize("change,field", [
    ({"subject": "   "}, "subject"), ({"subject": "x" * 81}, "subject"),
    ({"day": 7}, "day"), ({"day": -1}, "day"),
    ({"start": "25:00"}, "start"), ({"start": "9am"}, "start"), ({"end": ""}, "end"),
    ({"start": "10:00", "end": "09:00"}, "end"), ({"start": "10:00", "end": "10:00"}, "end"),
])
def test_us17_every_field_is_checked_on_the_server(me, change, field):
    res = me.post("/api/schedule", json={**CALCULUS, **change})
    assert res.status_code == 400
    assert res.json()["detail"]["field"] == field


def test_us17_a_room_can_be_given_as_people_write_it(me):
    assert me.post("/api/schedule", json={**CALCULUS, "room": "d103"}).json()["room"] == "D103"
    assert me.post("/api/schedule", json={**CALCULUS, "room": "Д217"}).json()["room"] == "D217"
    hall = me.post("/api/schedule", json={**CALCULUS, "room": "A1"}).json()
    assert index.directory_room(hall["room"]) is index.by_code["a1"]


def test_us17_a_round_hall_is_called_by_the_name_people_use(me):
    saved = me.post("/api/schedule", json={**CALCULUS, "room": "A1"}).json()
    assert saved["room_label"] == "Hall A1 (D117)"
    assert "Hall A1" in next(r["label"] for r in me.get("/api/rooms").json() if r["value"] == "D117")


def test_us17_the_timetable_has_a_limit(counter):
    c = someone(next(counter))
    user = c.get("/api/auth/me").json()["user"]
    for _ in range(MAX_CLASSES):
        users.add_class(user["user_id"], {"subject": "S", "day": 0, "start": "09:00", "end": "09:50"}, "D103")
    res = c.post("/api/schedule", json=CALCULUS)
    assert res.status_code == 400
    assert str(MAX_CLASSES) in res.json()["detail"]["message"]


def test_us17_deleting_an_account_takes_its_timetable(counter):
    c = someone(next(counter))
    user = c.get("/api/auth/me").json()["user"]
    c.post("/api/schedule", json=CALCULUS)
    with users._connect() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user["user_id"],))
    assert users.classes(user["user_id"]) == []


def test_us17_task_the_schedule_table_is_keyed_by_user():
    conn = sqlite3.connect(users.path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(classes)")}
    fks = conn.execute("PRAGMA foreign_key_list(classes)").fetchall()
    conn.close()
    assert {"user_id", "subject", "day_of_week", "start_time", "end_time", "room_number"} <= cols
    assert [(f[2], f[3]) for f in fks] == [("users", "user_id")]


def test_us17_task_the_form_has_a_room_picker_from_the_directory(me):
    assert 'list="tt-rooms"' in SCHEDULE_HTML and "/api/rooms" in SCHEDULE_JS
    picked = me.get("/api/rooms").json()
    # whatever the picker offers is accepted, and leads to one room of its own
    rooms = [index.directory_room(p["value"]) for p in picked]
    assert all(rooms) and len({r["room_id"] for r in rooms}) == len(picked)
    assert {"D103", "F204"} <= {p["value"] for p in picked}
    assert not any("Restroom" in p["value"] for p in picked)


@pytest.mark.parametrize("room", ["I110", "Red Hall", "A1", "D103"])
def test_us17_a_class_opened_for_editing_can_be_saved_as_it_is(me, room):
    saved = me.post("/api/schedule", json={**CALCULUS, "room": room}).json()
    again = me.put(f"/api/schedule/{saved['class_id']}", json={**CALCULUS, "room": saved["room_value"]})
    assert again.status_code == 200 and again.json()["room"] == saved["room"]


def test_us17_task_the_timetable_page_builds_edits_and_deletes():
    for needle in ('id="tt-form"', 'id="tt-subject"', 'id="tt-day"', 'id="tt-start"', 'id="tt-end"', 'id="tt-room"'):
        assert needle in SCHEDULE_HTML
    assert 'method: editing ? "PUT" : "POST"' in SCHEDULE_JS and 'method: "DELETE"' in SCHEDULE_JS
    # and the profile leads there
    assert 'href="/schedule"' in PROFILE_HTML


# ---------------------------------------------------------------- US18
WEEK = [
    {"subject": "Calculus I", "day": 0, "start": "09:00", "end": "09:50", "room": "D103"},
    {"subject": "Physics", "day": 0, "start": "11:00", "end": "11:50", "room": "F204"},
    {"subject": "History", "day": 2, "start": "10:00", "end": "10:50", "room": "G108"},
]


def ask(when, classes=WEEK, q="Where is my next class?"):
    return index.search(q, now=when, timetable=lambda: classes)


@pytest.mark.parametrize("q", [
    "where is my next class", "Where's my next class?", "next class", "my next lecture",
    "what is my next lesson", "how do I get to my next class", "где моя следующая пара",
    "Следующая пара", "где мое следующее занятие", "моя пара",
])
def test_us18_task_the_parser_knows_the_next_class_intent(q):
    assert NEXT_CLASS_RE.search(q.lower())


@pytest.mark.parametrize("q", ["class", "D103", "computer lab", "next to the library", "lecture hall",
                               "Where is the classroom?", "Where is Library?", "пара"])
def test_us18_other_questions_are_not_taken_for_the_next_class(q):
    assert not NEXT_CLASS_RE.search(q.lower())


def test_us18_scenario_1_pass_the_room_and_start_time_of_the_next_class_are_shown():
    a = ask(at("08:00"))
    assert a["kind"] == "room" and a["title"] == "D103"
    assert a["occasion"]["title"] == "Calculus I"
    assert a["occasion"]["when"] == "Today, 09:00–09:50"
    assert a["summary"] == "Your next class is Calculus I, today at 09:00, in D103."


def test_us18_scenario_1_a_directions_action_is_offered():
    a = ask(at("08:00"))
    assert a["map"]["code"] == "D103"       # routeBlock offers the button from this code
    assert "data-directions" in APP_JS


def test_us18_verified_before_during_and_after_a_scheduled_class():
    assert ask(at("08:59"))["title"] == "D103"              # before it
    during = ask(at("09:30"))
    assert during["title"] == "F204"                        # it has begun: the next is the one after
    assert during["occasion"]["aside"] == "On now: Calculus I until 09:50"
    assert ask(at("10:00"))["title"] == "F204"              # after it, the next one
    assert ask(at("10:00"))["occasion"]["aside"] is None


@pytest.mark.parametrize("hhmm", ["09:00", "09:49", "09:50", "10:59"])
def test_us18_fail_a_class_that_has_begun_or_ended_is_never_the_next_one(hhmm):
    assert ask(at(hhmm))["occasion"]["title"] == "Physics"


def test_us18_fail_a_past_class_is_not_returned_at_any_minute_of_the_week():
    for day in range(7):
        for minute in range(0, 24 * 60, 5):
            now = datetime(2026, 11, MONDAY + day, minute // 60, minute % 60)
            _, c, days = next_class(WEEK, now)
            if days == 0:
                assert c["day"] == now.weekday() and c["start"] > now.strftime("%H:%M")
            # nothing else in the week starts sooner
            ahead = lambda e: ((e["day"] - now.weekday()) * 1440 + int(e["start"][:2]) * 60
                               + int(e["start"][3:]) - minute - 1) % (7 * 1440)
            assert ahead(c) == min(ahead(e) for e in WEEK)


def test_us18_the_day_is_said_the_way_you_would_say_it():
    assert ask(at("12:00"))["occasion"]["when"] == "On Wednesday, 10:00–10:50"
    assert ask(at("12:00", MONDAY + 1))["occasion"]["when"] == "Tomorrow, 10:00–10:50"
    # after the last class of the week it comes round to Monday, across Sunday
    assert ask(at("12:00", MONDAY + 2))["occasion"]["when"] == "On Monday, 09:00–09:50"
    assert ask(at("23:00", MONDAY + 6))["occasion"]["when"] == "Tomorrow, 09:00–09:50"


def test_us18_a_single_class_comes_round_next_week():
    only = [WEEK[0]]
    a = ask(at("09:30"), only)
    assert a["occasion"]["when"] == "Next Monday, 09:00–09:50"
    assert a["occasion"]["aside"] == "On now: Calculus I until 09:50"


def test_us18_the_day_and_time_are_campus_time():
    # 04:30 UTC on Monday is 09:30 in Almaty: Calculus has begun
    assert ask(datetime(2026, 11, 2, 4, 30, tzinfo=timezone.utc))["occasion"]["title"] == "Physics"
    # 19:30 UTC on Sunday is already Monday 00:30 in Almaty
    assert ask(datetime(2026, 11, 8, 19, 30, tzinfo=timezone.utc))["occasion"]["when"] == "Today, 09:00–09:50"


def test_us18_the_walk_starts_from_the_class_you_are_in():
    between = ask(at("09:30"))
    assert between["start"] == "D103"
    assert ask(at("10:30"))["start"] == "D103"             # still the latest class today
    assert ask(at("08:00"))["start"] is None               # no class yet: from the main entrance
    assert ask(at("12:00"))["start"] is None               # the next one is another day


def test_us18_a_route_question_carries_the_walk_from_there():
    a = ask(at("09:30"), q="How do I get to my next class?")
    assert a["directions"]["summary"].startswith("From D103 to F204")
    b = ask(at("08:00"), q="How do I get to my next class?")
    assert b["directions"]["summary"].lower().startswith("from the main entrance")


def test_us18_two_classes_in_one_room_need_no_walk():
    same = [WEEK[0], {**WEEK[1], "room": "D103"}]
    assert ask(at("09:30"), same)["start"] is None


def test_us18_scenario_2_fail_a_visitor_gets_an_explanation_not_an_error(visitor):
    res = visitor.get("/api/search", params={"q": "where is my next class"})
    assert res.status_code == 200
    a = res.json()
    assert a["kind"] == "needs_account"
    assert "account" in a["title"].lower()
    assert a["link"]["href"] == "/login"


def test_us18_scenario_2_the_login_link_reaches_the_login_page(visitor):
    res = visitor.get("/login", follow_redirects=False)
    assert res.status_code == 200
    assert "<form" in res.text


def test_us18_an_account_is_still_sent_on_from_the_login_page(me):
    assert me.get("/login", follow_redirects=False).status_code == 303


def test_us18_an_account_with_an_empty_timetable_is_sent_to_fill_it(me):
    a = me.get("/api/search", params={"q": "where is my next class"}).json()
    assert a["kind"] == "needs_account"
    assert a["link"]["href"] == "/schedule"


def test_us18_pass_end_to_end_a_student_with_a_schedule_gets_their_own_class(me, them):
    me.post("/api/schedule", json=CALCULUS)
    them.post("/api/schedule", json={**CALCULUS, "subject": "Someone else's", "room": "F204"})
    a = me.get("/api/search", params={"q": "next class"}).json()
    assert a["occasion"]["title"] == "Calculus I" and a["title"] == "D103"
    assert a["elapsed_ms"] >= 0


def test_us18_a_room_that_left_the_directory_does_not_break_the_answer():
    a = ask(at("08:00"), [{**WEEK[0], "room": "GONE1"}])
    assert a["kind"] == "needs_account"
    assert "GONE1" in a["summary"]
    assert a["link"]["href"] == "/schedule"


# ---------------------------------------------------------------- US19 and US20
# The campus has no real events on file and none are made up for it, so these tests
# run on rows of their own, in a copy of the database. They are inserted out of date
# order on purpose.
TEST_EVENTS = [
    ('EV_WINTER_CONCERT', 'Winter Concert', 'Student choir, orchestra and dance groups perform. Free entry; doors open 30 minutes before.', 'Red Hall', 'A-1-RED-HALL', '2026-12-18 18:00', '2026-12-18 20:00'),
    ('EV_ML_LECTURE', 'Guest Lecture: Machine Learning in Industry', 'A practising engineer from an Almaty company on how machine learning models are built, tested and kept running.', 'Hall D2', 'E-2-E221', '2026-11-10 15:00', '2026-11-10 16:30'),
    ('EV_NAURYZ', 'Nauryz Celebration', 'Songs, games and traditional food on the campus grounds to welcome the spring.', 'Campus grounds', None, '2027-03-22 12:00', '2027-03-22 15:00'),
    ('EV_OPEN_DOORS', 'Open Doors Day', 'Applicants and their families meet the faculties, tour the campus and put their questions to the admissions team.', 'Red Hall', 'A-1-RED-HALL', '2026-11-14 11:00', '2026-11-14 14:00'),
    ('EV_SCHOLARSHIP', 'Scholarship Application Workshop', 'How to prepare a scholarship application: documents, essays and deadlines, with time for questions.', 'Hall C1', 'D-1-D113', '2027-02-10 14:00', '2027-02-10 15:30'),
    ('EV_HACKATHON', '24-Hour Hackathon', 'Teams of up to four build a working prototype overnight, with mentors from the Faculty of Engineering visiting every hour.', 'Study Space 1', 'D-3-STUDY-SPACE-1', '2026-12-05 10:00', '2026-12-06 10:00'),
    ('EV_RUN', 'Autumn Campus Run', 'A 5 km loop around the campus grounds, open to all. Finishers receive a medal.', 'Campus grounds, by the main entrance', None, '2026-11-21 10:00', '2026-11-21 12:00'),
    ('EV_DEBATE', 'Debate Club Open Evening', 'Come and watch a practice round or join one. The motions are announced on the evening.', 'Hall B2', 'D-2-D217', '2027-01-20 17:00', '2027-01-20 19:00'),
    ('EV_BOOK_FAIR', 'Library Book Fair', 'New and second-hand books in English, Kazakh and Russian, with a swap table for textbooks.', 'Library', 'B-1-LIBRARY', '2026-11-24 10:00', '2026-11-26 17:00'),
    ('EV_EXCHANGE', 'Exchange Programmes Info Session', 'How to apply for a semester abroad: partner universities, deadlines, grades and language certificates.', 'Hall C2', 'D-2-D214', '2026-12-03 15:00', '2026-12-03 16:30'),
    ('EV_STUDY_NIGHT', 'Winter Exam Study Night', 'The Library stays open late with quiet floors, tutors for calculus and physics, and free tea.', 'Library', 'B-1-LIBRARY', '2027-01-12 18:00', '2027-01-12 22:00'),
    ('EV_TABLE_TENNIS', 'Table Tennis Open', 'A knockout for singles, open to every student and staff member. Bring sports shoes.', 'Table tennis room', 'F-1-TABLE-TENNIS', '2026-12-11 16:00', '2026-12-11 19:00'),
]
INSERT_EVENT = ("INSERT INTO events (event_id, title, description, place, room_id, starts_at, ends_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)")
# A Tuesday morning, campus time. The test events run from this day to March 2027.
NOV_10 = datetime(2026, 11, 10, 9, 0)
LECTURE = "Guest Lecture: Machine Learning in Industry"      # 10 Nov, 15:00-16:30, Hall D2
HACKATHON = "24-Hour Hackathon"                              # 5 Dec 10:00 to 6 Dec 10:00, Study Space 1
BOOK_FAIR = "Library Book Fair"                              # 24 Nov 10:00 to 26 Nov 17:00, Library
CONCERT = "Winter Concert"                                   # 18 Dec, 18:00-20:00, Red Hall
OUTDOORS = ["Autumn Campus Run", "Nauryz Celebration"]       # places that are not on the plans


@pytest.fixture(scope="module", autouse=True)
def _test_events(tmp_path_factory):
    """The app's index reads the test events for this module, then goes back."""
    copy = tmp_path_factory.mktemp("events") / "campus.db"
    copy.write_bytes(DB_PATH.read_bytes())
    conn = sqlite3.connect(copy)
    conn.executemany(INSERT_EVENT, TEST_EVENTS)
    conn.commit()
    conn.close()
    shipped = index.db_path, index.event_titles
    index.db_path, index.event_titles = copy, CampusIndex.load(copy).event_titles
    yield
    index.db_path, index.event_titles = shipped


def raw_events() -> list[dict]:
    """The events table read straight from the database, in the order the rows were inserted."""
    conn = sqlite3.connect(f"file:{index.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY rowid")]
    finally:
        conn.close()


def titles(**kwargs) -> list[str]:
    return [e["title"] for e in index.events(**kwargs)["events"]]


def expected(q=None, start=None, end=None, now=NOV_10) -> list[str]:
    """What the filter should return, worked out from the raw rows with plain Python
    and calendar dates, not with the query the engine runs."""
    stamp = now.strftime("%Y-%m-%d %H:%M")
    found = []
    for e in raw_events():
        if e["ends_at"] <= stamp:
            continue
        text = f"{e['title']} {e['description']}".lower()
        if any(word not in text for word in (q or "").lower().split()):
            continue
        first, last = date.fromisoformat(e["starts_at"][:10]), date.fromisoformat(e["ends_at"][:10])
        if (start and last < start) or (end and first > end):
            continue
        found.append(e)
    return [e["title"] for e in sorted(found, key=lambda e: (e["starts_at"], e["title"]))]


def index_with(tmp_path, *rows) -> CampusIndex:
    """A copy of the test database with more events in it, loaded as its own index."""
    copy = tmp_path / "campus.db"
    copy.write_bytes(index.db_path.read_bytes())
    conn = sqlite3.connect(copy)
    conn.executemany(INSERT_EVENT, rows)
    conn.commit()
    conn.close()
    return CampusIndex.load(copy)


@pytest.fixture()
def nov_10(monkeypatch):
    """The server's clock held at NOV_10, for the tests that go over HTTP."""
    monkeypatch.setattr("app.engine.campus_now", lambda now=None: NOV_10)


# ---------------------------------------------------------------- US19
def test_us19_each_event_stores_title_description_place_date_and_time():
    conn = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    conn.close()
    assert {"title", "description", "place", "starts_at", "ends_at", "room_id"} <= cols
    for e in raw_events():
        assert e["title"].strip() and e["description"].strip() and e["place"].strip()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", e["starts_at"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", e["ends_at"])
        assert e["starts_at"] < e["ends_at"]


def test_us19_events_live_in_the_projects_own_database_with_no_calendar_behind_them():
    assert CampusIndex.load(DB_PATH).db_path == DB_PATH
    assert len(raw_events()) == index.events(now=datetime(2026, 1, 1))["total"]
    sources = "".join((BASE_DIR / "app" / name).read_text().lower() for name in ("engine.py", "main.py"))
    assert not re.search(r"caldav|icalendar|google\.?calendar|googleapis|webcal", sources)


def test_us19_an_empty_table_says_so_and_nothing_is_made_up_to_fill_it(tmp_path):
    copy = tmp_path / "campus.db"
    copy.write_bytes(DB_PATH.read_bytes())
    conn = sqlite3.connect(copy)
    conn.execute("DELETE FROM events")
    conn.commit()
    conn.close()
    page = CampusIndex.load(copy).events(now=NOV_10)
    assert page["events"] == [] and page["total"] == 0
    assert "No upcoming events yet." in EVENTS_JS
    assert 'hidden = !data.total' in EVENTS_JS       # no search box over nothing


def test_us19_no_test_event_is_in_the_shipped_database():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    shipped = {r[0] for r in conn.execute("SELECT title FROM events")}
    conn.close()
    assert not shipped & {e[1] for e in TEST_EVENTS}


def test_us19_pass_upcoming_events_are_listed_in_date_order_with_place_and_time():
    page = index.events(now=NOV_10)
    assert page["count"] == page["total"] == len(raw_events())
    assert [e["starts_at"] for e in page["events"]] == sorted(e["starts_at"] for e in page["events"])
    first = page["events"][0]
    assert (first["title"], first["date"], first["time"], first["place"]) == (
        LECTURE, "Tue 10 Nov", "15:00–16:30", "Hall D2")
    assert all(e["place"] and re.fullmatch(r"\d\d:\d\d(–|( – ).+, )\d\d:\d\d", e["time"]) for e in page["events"])


def test_us19_fail_events_are_not_listed_in_insertion_order():
    inserted = [e["starts_at"] for e in raw_events()]
    assert inserted != sorted(inserted), "the seed has to be out of date order for this to prove anything"
    assert [e["starts_at"] for e in index.events(now=NOV_10)["events"]] == sorted(inserted)


def test_us19_events_that_start_together_are_ordered_by_title(tmp_path):
    idx = index_with(tmp_path, ("B", "Zebra talk", "x", "Hall", None, "2026-11-11 10:00", "2026-11-11 11:00"),
                               ("A", "Apple talk", "x", "Hall", None, "2026-11-11 10:00", "2026-11-11 11:00"))
    assert [e["title"] for e in idx.events(q="talk", now=NOV_10)["events"]] == ["Apple talk", "Zebra talk"]


def test_us19_fail_past_events_do_not_appear_in_the_upcoming_list():
    later = datetime(2026, 12, 10, 12, 0)
    page = index.events(now=later)
    stamp = "2026-12-10 12:00"
    assert page["events"] and all(e["ends_at"] > stamp for e in page["events"])
    gone = {e["title"] for e in raw_events() if e["ends_at"] <= stamp}
    assert gone and gone.isdisjoint(titles(now=later))
    assert page["total"] == len(raw_events()) - len(gone)


def test_us19_verified_after_the_last_event_nothing_is_listed():
    page = index.events(now=datetime(2027, 3, 23))
    assert (page["events"], page["count"], page["total"]) == ([], 0, 0)


def test_us19_an_event_is_upcoming_until_the_minute_it_ends():
    for hhmm, listed, on_now in (("14:59", True, False), ("15:00", True, True), ("16:29", True, True),
                                 ("16:30", False, False), ("16:31", False, False)):
        now = datetime(2026, 11, 10, int(hhmm[:2]), int(hhmm[3:]))
        found = [e for e in index.events(now=now)["events"] if e["title"] == LECTURE]
        assert bool(found) is listed, hhmm
        if found:
            assert found[0]["on_now"] is on_now, hhmm


def test_us19_an_event_that_runs_past_midnight_says_when_it_ends():
    event = next(e for e in index.events(now=NOV_10)["events"] if e["title"] == HACKATHON)
    assert (event["date"], event["time"]) == ("Sat 5 Dec", "10:00 – Sun 6 Dec, 10:00")
    # still upcoming, and on now, the next morning
    during = datetime(2026, 12, 6, 8, 0)
    assert HACKATHON in titles(now=during)
    assert next(e for e in index.events(now=during)["events"] if e["title"] == HACKATHON)["on_now"] is True


def test_us19_the_clock_is_campus_time():
    # 10:30 UTC is 15:30 in Almaty: the lecture is on
    now = datetime(2026, 11, 10, 10, 30, tzinfo=timezone.utc)
    assert next(e for e in index.events(now=now)["events"] if e["title"] == LECTURE)["on_now"] is True
    # 12:00 UTC is 17:00 there: it is over
    assert LECTURE not in titles(now=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))


def test_us19_task_every_event_in_a_room_is_in_a_real_room_on_the_right_floor():
    by_id = {r["room_id"]: r for r in index.rooms}
    listed = {e["title"]: e for e in index.events(now=NOV_10)["events"]}
    in_rooms = [e for e in raw_events() if e["room_id"]]
    assert len(in_rooms) >= 8
    for e in in_rooms:
        room = by_id[e["room_id"]]                              # a room that is in the directory
        shown = listed[e["title"]]
        assert shown["room"] == room["room_number"]
        assert index.map.room_point(room["room_number"]), f"{e['title']}: not on the plan"
        assert shown["where"] == f"Floor {room['floor_number']} · Block {room['building_id']}"
        assert room["floor_id"] == f"{room['building_id']}-{room['floor_number']}"
    for title in OUTDOORS:
        assert listed[title]["room"] is None and listed[title]["where"] is None


EVENT_FIELDS = ("event_id", "title", "description", "place", "room_id", "starts_at", "ends_at")


@pytest.mark.parametrize("event", [dict(zip(EVENT_FIELDS, e)) for e in TEST_EVENTS if e[4]], ids=lambda e: e["event_id"])
def test_us19_scenario_2_pressing_an_event_in_a_known_room_highlights_it_and_names_the_event(event):
    room = next(r for r in index.rooms if r["room_id"] == event["room_id"])
    a = index.search(event["title"], now=NOV_10)
    assert a["kind"] == "room"
    assert a["map"]["code"] == room["room_number"]              # the plan lights this room
    assert a["map"]["floor"] == room["floor_number"]
    assert a["occasion"]["title"] == event["title"]            # and the card says why
    assert a["occasion"]["label"] == "Event"
    assert a["occasion"]["aside"] == event["description"]
    assert event["title"] in a["summary"]
    assert re.fullmatch(r"\w{3} \d{1,2} \w{3}, \d\d:\d\d.*\d\d:\d\d", a["occasion"]["when"])


def test_us19_scenario_2_the_page_asks_by_title_and_the_card_prints_the_event(nov_10, visitor):
    page = visitor.get("/api/events").json()
    assert page["events"]
    for ev in page["events"]:
        assert ev["ask"] == ev["title"]
        a = visitor.get("/api/search", params={"q": ev["ask"]}).json()
        assert a["occasion"]["title"] == ev["title"]
        if ev["room"]:
            assert a["kind"] == "room" and a["map"]["code"] == ev["room"]
    room_branch = APP_JS.split('if (d.kind === "room") {')[1].split('} else if (d.kind === "list")')[0]
    assert "${occasion(d)}" in room_branch


def test_us19_an_event_in_a_place_off_the_plans_gets_a_card_that_says_so():
    a = index.search("Nauryz Celebration", now=NOV_10)
    assert a["kind"] == "event" and a["title"] == "Nauryz Celebration"
    assert a["occasion"]["when"] == "Mon 22 Mar, 12:00–15:00"
    assert a["occasion"]["title"] == "Nauryz Celebration" and a["place"] == "Campus grounds"
    assert "Campus grounds" in a["summary"] and "isn't on the plans" in a["summary"] and not a.get("map")
    branch = APP_JS.split('d.kind === "event"')[1].split("} else {")[0]
    assert "occasion(d" in branch and "esc(d.summary)" in branch and 'classList.add("prompt"' in branch


def test_us19_the_event_card_folds_with_the_turn_without_losing_its_way_back():
    assert ".is-event .answer-foot { display: none; }" in STYLES_CSS
    assert ".turn.past .is-event .answer-foot { display: flex; }" in STYLES_CSS
    branch = APP_JS.split('d.kind === "event"')[1].split("} else {")[0]
    assert "foot(d, !!d.map" in branch                        # the foot holds the expand button (and, for
    # an event the Campus view shows, the way back to it on the plan)
    assert 'if (d.kind === "event") showStageMsg(' in APP_JS      # and the plan says there is nothing to show


def test_us19_a_title_only_answers_while_its_event_is_upcoming():
    assert index.search(LECTURE, now=datetime(2026, 11, 10, 16, 29))["occasion"]["title"] == LECTURE
    over = index.search(LECTURE, now=datetime(2026, 11, 10, 16, 30))
    assert "occasion" not in over and over["kind"] != "event"


def test_us19_a_title_is_matched_as_a_room_name_is_ignoring_case_and_spacing():
    for typed in ("winter concert", "WINTER  CONCERT", "winter-concert"):
        assert index.search(typed, now=NOV_10)["occasion"]["title"] == CONCERT


def test_us19_no_event_title_is_also_a_room_a_hall_an_alias_or_a_service():
    taken = set(index.by_code) | set(index.named) | {a for a, _ in index.building_aliases}
    for svc in index.services.values():
        taken |= {normalize(svc["name"]), *svc["aliases"]}
    for e in raw_events():
        assert normalize(e["title"]) not in taken, e["title"]
    assert len({normalize(e["title"]) for e in raw_events()}) == len(raw_events())


def test_us19_rooms_and_services_are_still_answered_as_before():
    assert index.search("Red Hall", now=NOV_10)["kind"] == "room"
    assert "occasion" not in index.search("Red Hall", now=NOV_10)
    assert index.search("D103", now=NOV_10)["title"] == "D103"
    assert index.search("Library", now=NOV_10)["kind"] == "service"


@pytest.mark.parametrize("q", ["events", "Events", "what's on this week", "what is on", "Any events on campus?",
                               "мероприятия", "Какие события в университете", "афиша"])
def test_us19_a_question_about_events_is_pointed_at_the_events_page(q):
    a = index.search(q, now=NOV_10)
    assert a["kind"] == "needs_account" and a["title"] == "Campus events"
    assert a["link"] == {"href": "/events", "label": "See upcoming events"}
    assert "d.link" in APP_JS


def test_us19_the_events_have_a_page_of_their_own_linked_from_the_main_page(me, anon):
    res = me.get("/events")
    assert res.status_code == 200 and 'id="ev-list"' in res.text
    assert anon.get("/events", follow_redirects=False).headers["location"] == "/login?next=%2Fevents"
    assert 'id="ev-list"' not in INDEX_HTML
    tip = re.search(r'<p class="welcome-tip">.*?</p>', INDEX_HTML, re.S).group(0)
    assert 'href="/events"' in tip
    assert 'class="events-link" href="/events"' in INDEX_HTML


def test_us19_a_press_on_the_events_page_opens_the_map_with_the_event():
    assert 'href="/?ask=${encodeURIComponent(ev.ask)}"' in EVENTS_JS
    assert 'new URLSearchParams(location.search).get("ask")' in APP_JS


def test_us19_visitors_and_accounts_can_read_the_events_and_a_stranger_cannot(nov_10, visitor, me, anon):
    for who in (visitor, me):
        res = who.get("/api/events")
        assert res.status_code == 200
        assert res.json()["count"] == len(raw_events())
    assert anon.get("/api/events").status_code == 401


def test_us19_over_http_the_list_is_in_date_order_with_place_and_time(nov_10, visitor):
    page = visitor.get("/api/events").json()
    assert [e["title"] for e in page["events"]] == expected()
    assert {"event_id", "title", "description", "place", "room", "date", "time", "starts_at", "ends_at",
            "on_now", "where", "ask"} <= set(page["events"][0])


# ---------------------------------------------------------------- US20
def test_us20_a_word_matches_the_title():
    assert titles(q="hackathon", now=NOV_10) == [HACKATHON]
    assert "hackathon" not in next(e for e in raw_events() if e["title"] == HACKATHON)["description"].lower()


def test_us20_a_word_matches_the_description():
    assert titles(q="medal", now=NOV_10) == ["Autumn Campus Run"]
    assert titles(q="tutors", now=NOV_10) == ["Winter Exam Study Night"]
    for e in raw_events():
        if e["title"] in ("Autumn Campus Run", "Winter Exam Study Night"):
            assert "medal" not in e["title"].lower() and "tutors" not in e["title"].lower()


def test_us20_every_word_must_be_there_but_not_in_the_same_place():
    assert titles(q="library fair", now=NOV_10) == [BOOK_FAIR]
    assert titles(q="library tutors", now=NOV_10) == ["Winter Exam Study Night"]      # title word + description word
    assert titles(q="hackathon tutors", now=NOV_10) == []


def test_us20_case_and_extra_spaces_do_not_matter():
    assert titles(q="  LiBrArY   BOOK ", now=NOV_10) == titles(q="library book", now=NOV_10) == [BOOK_FAIR]


def test_us20_cyrillic_words_match_whatever_the_case(tmp_path):
    idx = index_with(tmp_path, ("RU", "День открытых дверей", "Встреча с абитуриентами в Красном зале",
                                "Красный зал", None, "2026-11-12 11:00", "2026-11-12 13:00"))
    for q in ("день", "ДЕНЬ", "Открытых", "АБИТУРИЕНТ", "красном ЗАЛЕ", "дверей ДЕНЬ"):
        assert [e["title"] for e in idx.events(q=q, now=NOV_10)["events"]] == ["День открытых дверей"], q
    assert idx.events(q="день ночь", now=NOV_10)["events"] == []
    assert idx.search("ДЕНЬ ОТКРЫТЫХ ДВЕРЕЙ", now=NOV_10)["kind"] == "event"


def test_us20_percent_and_underscore_are_ordinary_characters(tmp_path):
    for q in ("%", "_", "a%", "l_brary", "%%"):
        assert titles(q=q, now=NOV_10) == [], q
    idx = index_with(tmp_path, ("PC", "100% Club", "Members only", "Hall", None, "2026-11-12 11:00", "2026-11-12 13:00"),
                               ("US", "Open_Mic", "Songs", "Hall", None, "2026-11-13 11:00", "2026-11-13 13:00"))
    assert [e["title"] for e in idx.events(q="100%", now=NOV_10)["events"]] == ["100% Club"]
    assert idx.events(q="10_", now=NOV_10)["events"] == []
    assert [e["title"] for e in idx.events(q="open_", now=NOV_10)["events"]] == ["Open_Mic"]
    assert idx.events(q="openxmic", now=NOV_10)["events"] == []


def test_us20_a_quote_in_the_search_is_only_text():
    assert titles(q="' OR 1=1 --", now=NOV_10) == []
    assert titles(q='"; DROP TABLE events; --', now=NOV_10) == []
    assert len(titles(now=NOV_10)) == len(raw_events())


def test_us20_pass_this_week_narrows_the_list_to_the_week():
    week = index.events(now=NOV_10)["ranges"]["week"]
    assert week == {"from": "2026-11-09", "to": "2026-11-15"}
    start, end = (date.fromisoformat(week[k]) for k in ("from", "to"))
    found = titles(start=start, end=end, now=NOV_10)
    assert found == [LECTURE, "Open Doors Day"] == expected(start=start, end=end)
    assert len(found) < index.events(now=NOV_10)["total"]


def test_us20_pass_a_word_search_narrows_the_list_and_the_count_says_how_far():
    page = index.events(q="library", now=NOV_10)
    assert [e["title"] for e in page["events"]] == [BOOK_FAIR, "Winter Exam Study Night"]
    assert (page["count"], page["total"]) == (2, 12)
    assert "of ${data.total} upcoming events" in EVENTS_JS


def test_us20_scenario_1_word_search_shows_only_matching_events_and_the_count(nov_10, visitor):
    page = visitor.get("/api/events", params={"q": "library"}).json()
    assert page["count"] == len(page["events"]) == 2 and page["total"] == 12
    for e in page["events"]:
        assert "library" in f"{e['title']} {e['description']}".lower()
    assert 'id="ev-count"' in EVENTS_HTML and 'aria-live="polite"' in EVENTS_HTML.split('id="ev-count"')[1][:80]


def test_us20_scenario_2_this_week_shows_only_events_inside_this_week(nov_10, visitor):
    week = visitor.get("/api/events").json()["ranges"]["week"]       # what the This week chip sends
    page = visitor.get("/api/events", params={"from": week["from"], "to": week["to"]}).json()
    assert page["count"] == 2
    for e in page["events"]:
        assert week["from"] <= e["starts_at"][:10] <= week["to"]
    assert 'data-range="week"' in EVENTS_HTML and "eventsView.ranges?.[key]" in EVENTS_JS


def test_us20_fail_the_filter_never_returns_an_event_outside_the_range():
    day = timedelta(days=1)
    for first in (date(2026, 11, 10) + n * day for n in range(0, 140, 3)):
        for length in (0, 1, 6, 20):
            last = first + length * day
            for e in index.events(start=first, end=last, now=NOV_10)["events"]:
                assert date.fromisoformat(e["starts_at"][:10]) <= last, (first, last, e["title"])
                assert date.fromisoformat(e["ends_at"][:10]) >= first, (first, last, e["title"])
            assert titles(start=first, end=last, now=NOV_10) == expected(start=first, end=last), (first, last)


def test_us20_the_range_includes_its_first_and_last_day():
    on = lambda a, b: titles(start=a, end=b, now=NOV_10)
    assert on(date(2026, 12, 18), date(2026, 12, 18)) == [CONCERT]
    assert on(date(2026, 12, 18), date(2026, 12, 20)) == [CONCERT]
    assert on(date(2026, 12, 15), date(2026, 12, 18)) == [CONCERT]
    assert on(date(2026, 12, 17), date(2026, 12, 17)) == []
    assert on(date(2026, 12, 19), date(2026, 12, 19)) == []


def test_us20_an_event_that_runs_into_the_range_counts_as_inside_it():
    on = lambda a, b: titles(start=a, end=b, now=NOV_10)
    assert on(date(2026, 12, 6), date(2026, 12, 6)) == [HACKATHON]        # the morning it ends
    assert on(date(2026, 12, 4), date(2026, 12, 5)) == [HACKATHON]        # the day it starts
    assert on(date(2026, 12, 4), date(2026, 12, 4)) == []
    assert on(date(2026, 12, 7), date(2026, 12, 7)) == []
    assert on(date(2026, 11, 25), date(2026, 11, 25)) == [BOOK_FAIR]      # the middle of three days


def test_us20_an_event_that_ended_at_midnight_does_not_reach_into_the_next_day(tmp_path):
    idx = index_with(tmp_path, ("LATE", "Late film", "x", "Hall", None, "2026-11-16 21:00", "2026-11-17 00:00"))
    assert idx.events(q="film", start=date(2026, 11, 16), end=date(2026, 11, 16), now=NOV_10)["count"] == 1
    assert idx.events(q="film", start=date(2026, 11, 17), end=date(2026, 11, 17), now=NOV_10)["count"] == 0


def test_us20_a_range_with_one_end_is_open_on_the_other():
    assert titles(start=date(2027, 2, 1), now=NOV_10) == ["Scholarship Application Workshop", "Nauryz Celebration"]
    assert titles(end=date(2026, 11, 14), now=NOV_10) == [LECTURE, "Open Doors Day"]


def test_us20_the_range_never_brings_back_a_past_event():
    assert titles(start=date(2026, 11, 1), end=date(2026, 11, 14), now=datetime(2026, 11, 14, 14, 0)) == []
    assert titles(start=date(2026, 11, 1), end=date(2026, 11, 14), now=datetime(2026, 11, 14, 11, 30)) == ["Open Doors Day"]


def test_us20_a_word_and_a_period_narrow_together():
    assert titles(q="library", start=date(2026, 11, 20), end=date(2026, 12, 31), now=NOV_10) == [BOOK_FAIR]
    assert titles(q="library", start=date(2026, 12, 1), end=date(2026, 12, 31), now=NOV_10) == []


def test_us20_the_week_runs_from_monday_to_sunday_in_campus_time():
    def week(now):
        return index.events(now=now)["ranges"]["week"]
    assert week(datetime(2026, 11, 9, 0, 0)) == {"from": "2026-11-09", "to": "2026-11-15"}          # Monday
    assert week(datetime(2026, 11, 15, 23, 59)) == {"from": "2026-11-09", "to": "2026-11-15"}       # Sunday
    assert week(datetime(2026, 11, 16, 0, 0)) == {"from": "2026-11-16", "to": "2026-11-22"}
    # 20:00 UTC on a Sunday is already Monday in Almaty
    assert week(datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)) == {"from": "2026-11-16", "to": "2026-11-22"}
    assert week(datetime(2026, 12, 31, 12, 0)) == {"from": "2026-12-28", "to": "2027-01-03"}        # over New Year


def test_us20_the_events_of_this_week_stop_at_sunday_night_and_start_on_monday(tmp_path):
    idx = index_with(tmp_path,
                     ("SUN", "Sunday late", "x", "Hall", None, "2026-11-15 22:00", "2026-11-15 23:30"),
                     ("MON", "Monday early", "x", "Hall", None, "2026-11-16 00:30", "2026-11-16 02:00"))

    def this_week(now):
        week = idx.events(now=now)["ranges"]["week"]
        return [e["title"] for e in idx.events(start=date.fromisoformat(week["from"]),
                                               end=date.fromisoformat(week["to"]), now=now)["events"]]
    assert this_week(NOV_10) == [LECTURE, "Open Doors Day", "Sunday late"]
    assert this_week(datetime(2026, 11, 16, 0, 10)) == ["Monday early", "Autumn Campus Run"]


def test_us20_today_and_this_month_are_counted_in_campus_time():
    ranges = lambda now: index.events(now=now)["ranges"]
    assert ranges(NOV_10)["today"] == {"from": "2026-11-10", "to": "2026-11-10"}
    assert ranges(NOV_10)["month"] == {"from": "2026-11-10", "to": "2026-11-30"}
    assert ranges(datetime(2026, 12, 31, 8, 0))["month"] == {"from": "2026-12-31", "to": "2026-12-31"}
    assert ranges(datetime(2027, 2, 10, 8, 0))["month"] == {"from": "2027-02-10", "to": "2027-02-28"}
    assert ranges(datetime(2027, 1, 12, 8, 0))["month"] == {"from": "2027-01-12", "to": "2027-01-31"}
    today = ranges(NOV_10)["today"]
    assert titles(start=date.fromisoformat(today["from"]), end=date.fromisoformat(today["to"]), now=NOV_10) == [LECTURE]


@pytest.mark.parametrize("q,start,end,now", [
    (None, None, None, NOV_10),
    ("library", None, None, NOV_10),
    ("hall", None, None, NOV_10),
    ("a", date(2026, 12, 1), date(2027, 1, 31), NOV_10),
    ("workshop info", None, None, NOV_10),
    ("session", date(2026, 12, 3), date(2026, 12, 3), NOV_10),
    (None, date(2026, 11, 9), date(2026, 11, 15), NOV_10),
    (None, date(2026, 11, 24), None, datetime(2026, 11, 25, 12, 0)),
    (None, None, date(2026, 11, 30), datetime(2026, 11, 22, 0, 0)),
    ("tea", date(2026, 12, 5), date(2027, 1, 12), datetime(2026, 12, 6, 9, 0)),
    ("zzzz", None, None, NOV_10),
    ("campus", date(2027, 3, 1), date(2027, 3, 31), NOV_10),
])
def test_us20_verified_filtered_results_match_the_raw_event_table(q, start, end, now):
    got = index.events(q=q, start=start, end=end, now=now)
    assert [e["title"] for e in got["events"]] == expected(q, start, end, now)
    assert got["count"] == len(got["events"])
    assert got["total"] == len(expected(None, None, None, now))


def test_us20_verified_over_http_the_same_filters_give_the_same_rows(nov_10, visitor):
    for params, args in (({"q": "library"}, ("library", None, None)),
                         ({"from": "2026-12-01", "to": "2026-12-31"}, (None, date(2026, 12, 1), date(2026, 12, 31))),
                         ({"q": "hall", "from": "2026-11-20"}, ("hall", date(2026, 11, 20), None))):
        page = visitor.get("/api/events", params=params).json()
        assert [e["title"] for e in page["events"]] == expected(*args)


def test_us20_each_search_is_a_query_to_the_events_table_not_a_list_kept_in_memory(tmp_path):
    idx = index_with(tmp_path)
    assert idx.events(q="rocket", now=NOV_10)["count"] == 0
    conn = sqlite3.connect(idx.db_path)
    conn.execute("INSERT INTO events (event_id, title, description, place, starts_at, ends_at)"
                 " VALUES ('NEW', 'Rocket club', 'Build and fly', 'Pitch', '2026-11-20 10:00', '2026-11-20 12:00')")
    conn.commit()
    conn.close()
    assert [e["title"] for e in idx.events(q="rocket", now=NOV_10)["events"]] == ["Rocket club"]
    assert 'mode=ro' in (BASE_DIR / "app" / "engine.py").read_text().split("def events(")[1]


def test_us20_fail_an_empty_result_is_a_message_and_a_way_back_not_a_blank_page(nov_10, visitor):
    page = visitor.get("/api/events", params={"q": "zzzz"}).json()
    assert page["events"] == [] and page["count"] == 0 and page["total"] == len(TEST_EVENTS)
    assert "No upcoming events match" in EVENTS_JS and "Clear search and dates" in EVENTS_JS
    assert EVENTS_JS.count("ev-empty") >= 2 and ".ev-empty" in STYLES_CSS


def test_us20_a_failed_request_leaves_the_section_and_says_so():
    assert "Couldn't load the events" in EVENTS_JS and "Try again" in EVENTS_JS
    events_js = EVENTS_JS.split("async function loadEvents()")[1].split("function eventRow")[0]
    assert "hidden = true" not in events_js
    assert "seq !== eventsView.seq" in events_js                      # a late answer to an old search is dropped


def test_us20_the_search_waits_for_a_pause_in_typing():
    assert "EVENT_TYPING_DELAY = 200" in EVENTS_JS
    assert re.search(r'\$\("#ev-q"\)\.addEventListener\("input".*?setTimeout\(loadEvents, EVENT_TYPING_DELAY\)', EVENTS_JS, re.S)


@pytest.mark.parametrize("params,field", [
    ({"from": "2026-13-01"}, "from"), ({"from": "tomorrow"}, "from"), ({"from": "2026-1-5"}, "from"),
    ({"from": "20261105"}, "from"), ({"to": "2026-11-31"}, "to"), ({"to": "11/12/2026"}, "to"),
    ({"from": "2026-12-01", "to": "2026-11-01"}, "to"),
])
def test_us20_dates_the_server_cannot_read_or_that_run_backwards_are_refused(visitor, params, field):
    res = visitor.get("/api/events", params=params)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["field"] == field and detail["message"]


def test_us20_a_range_of_one_day_and_an_empty_range_value_are_fine(nov_10, visitor):
    assert visitor.get("/api/events", params={"from": "2026-11-14", "to": "2026-11-14"}).json()["count"] == 1
    assert visitor.get("/api/events", params={"from": "", "to": "", "q": ""}).json()["count"] == 12


def test_us20_the_search_text_has_a_limit(visitor):
    assert visitor.get("/api/events", params={"q": "x" * 200}).status_code == 200
    assert visitor.get("/api/events", params={"q": "x" * 201}).status_code == 422


def test_us20_task_the_page_has_a_search_box_and_a_date_range_control():
    for needle in ('id="ev-q"', 'type="search"', 'id="ev-from"', 'id="ev-to"', 'type="date"', 'for="ev-q"',
                   'for="ev-from"', 'for="ev-to"'):
        assert needle in EVENTS_HTML
    chips = re.findall(r'<button type="button" class="chip" data-range="(\w*)" aria-pressed="(\w+)">([^<]+)<', EVENTS_HTML)
    assert chips == [("", "true", "All"), ("today", "false", "Today"), ("week", "false", "This week"),
                     ("month", "false", "This month")]
    assert "setAttribute(\"aria-pressed\"" in EVENTS_JS.split("async function loadEvents()")[1]


def test_us20_changing_the_dates_by_hand_clears_the_chips():
    setup = EVENTS_JS.split("function setupEvents()")[1].split("async function loadEvents()")[0]
    assert re.search(r'\[from, to\]\.forEach.*?eventsView\.chip = null', setup, re.S)
    load = EVENTS_JS.split("async function loadEvents()")[1]
    assert 'eventsView.chip ?? (fields.from || fields.to ? null : "")' in load


def test_us20_the_rows_stay_legible_at_phone_width():
    row = STYLES_CSS.split(".ev-row { padding")[1].split(".ev-empty, .ev-error")[0]
    assert "white-space: normal" in row and "overflow-wrap: anywhere" in row
    assert ".ev-field input {" in STYLES_CSS and "height: 44px" in STYLES_CSS.split(".ev-field input {")[1][:160]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in STYLES_CSS.split(".ev-dates")[1][:120]


@pytest.mark.parametrize("q", ["what is on floor 2", "what's on the third floor?", "what is on the second floor of block D"])
def test_us19_a_question_about_a_floor_is_not_taken_for_events(q):
    assert index.search(q).get("title") != "Campus events"
