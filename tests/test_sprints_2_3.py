"""
Sprints 2 and 3, checked story by story against the story sheet
(AI_Campus_Assistant_User_Stories_v2.xlsx): every responsibility, every QA
scenario and every test script marked (Fail). Plus the half of US4 that
Sprint 1 carried over: changing the password from the profile.

  Sprint 2  US5 Room and Facility Directory   US6 Search by Room Code
            US7 Search by Name and Purpose    US8 Plain-Language Question Parsing
  Sprint 3  US9 Floor Plan Viewer             US10 Highlight the Found Room
            US11 Floor Switching, Zoom, Pan   US12 Lecture Hall Search by Common Name
"""
import math
import re
import sqlite3
from pathlib import Path

import pytest

from app.main import BASE_DIR, DB_PATH, campus_map, index
from conftest import TEST_EMAIL, TEST_NAME, TEST_PASSWORD

FLOORS = {f["floor"]: f for f in campus_map.floor_list()}
APP_JS = (BASE_DIR / "static" / "app.js").read_text()


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ======================================================== US5 Room directory
def test_us5_every_row_holds_code_block_floor_purpose_and_position(db):
    missing = db.execute(
        "SELECT r.room_number FROM rooms r JOIN floors f USING (floor_id)"
        " WHERE r.room_number IS NULL OR r.room_number = '' OR f.building_id IS NULL"
        " OR f.floor_number IS NULL OR r.purpose IS NULL OR r.purpose = ''"
        " OR r.x IS NULL OR r.y IS NULL").fetchall()
    assert missing == []


def test_us5_every_block_has_its_rooms_on_every_floor_its_plans_number(db):
    """Blocks D to I are numbered on all three floors. Block C's floor-3 rooms
    are drawn on the sheet without numbers, so floors 1 and 2 are all it has."""
    floors = {b: {int(f) for f in fs.split(",")} for b, fs in db.execute(
        "SELECT f.building_id, group_concat(DISTINCT f.floor_number) FROM rooms r"
        " JOIN floors f USING (floor_id) GROUP BY f.building_id")}
    for block in "DEFGHI":
        assert floors[block] == {1, 2, 3}, f"Block {block}"
    assert floors["C"] == {1, 2}


def test_us5_no_room_code_appears_twice(db):
    assert db.execute("SELECT room_number FROM rooms GROUP BY room_number HAVING count(*) > 1").fetchall() == []


def test_us5_the_database_itself_refuses_a_duplicate_code(tmp_path):
    copy = tmp_path / "campus.db"
    copy.write_bytes(Path(DB_PATH).read_bytes())
    conn = sqlite3.connect(copy)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO rooms (room_id, floor_id, room_number, purpose, x, y)"
                     " VALUES ('D-1-D103-dup', 'D-1', 'D103', 'Classroom', 1, 1)")
    conn.close()


def test_us5_the_database_is_rebuilt_from_the_versioned_sql_file(tmp_path):
    from tools.build_db import SQL, build, dump
    built = tmp_path / "rebuilt.db"
    build(SQL.read_text(), built)
    assert list(sqlite3.connect(built).iterdump()) == list(sqlite3.connect(DB_PATH).iterdump())
    assert SQL.read_text() == dump(), "campus.sql is out of date: run tools/build_db.py --dump"


def test_us5_the_loader_fails_loudly_on_a_duplicate(tmp_path):
    from tools.build_db import SQL, build
    sql = SQL.read_text().replace("COMMIT;", "INSERT INTO \"rooms\" (room_id, floor_id, room_number, purpose, x, y)"
                                  " VALUES('dup','D-1','D103','Classroom',1,1);\nCOMMIT;")
    with pytest.raises(SystemExit, match="UNIQUE"):
        build(sql, tmp_path / "broken.db")


# ======================================================== US6 Room code
@pytest.mark.parametrize("code, block, floor", [
    ("D103", "D", 1), ("F204", "F", 2), ("G215", "G", 2), ("H304", "H", 3), ("E117", "E", 1)])
def test_us6_a_code_returns_exactly_its_room_with_block_floor_and_purpose(code, block, floor):
    answer = index.search(code)
    assert answer["kind"] == "room" and answer["room"]["room_number"] == code
    assert (answer["room"]["building_id"], answer["room"]["floor_number"]) == (block, floor)
    assert answer["room"]["purpose"]


def test_us6_an_unknown_code_says_not_found_and_shows_the_code_format():
    answer = index.search("D199")
    assert answer["kind"] == "not_found"
    assert "no room D199" in answer["summary"] and "block letter" in answer["summary"]


def test_us6_the_search_endpoint_answers_a_code(client):
    body = client.get("/api/search", params={"q": "D103"}).json()
    assert body["kind"] == "room" and body["room"]["floor_number"] == 1


# ======================================================== US7 Name and purpose
def test_us7_computer_lab_lists_every_lab_with_code_block_and_floor(db):
    labs = {r["room_number"] for r in db.execute("SELECT room_number FROM rooms WHERE purpose = 'Laboratory room'")}
    answer = index.search("computer lab")
    assert answer["kind"] == "list"
    assert {r["code"] for r in answer["results"]} == labs
    assert all(r["building_id"] and r["floor_number"] for r in answer["results"])


@pytest.mark.parametrize("upper, lower", [("COMPUTER LAB", "computer lab"), ("LIBRARY", "library"),
                                          ("Lecture Hall", "lecture hall")])
def test_us7_case_does_not_matter_and_the_order_is_the_same(upper, lower):
    a, b = index.search(upper), index.search(lower)
    assert a["kind"] == b["kind"] and a.get("title", "").lower() == b.get("title", "").lower()
    assert a.get("results") == b.get("results")


@pytest.mark.parametrize("word, purpose", [("classroom", "Classroom"), ("lab", "Laboratory room"), ("laboratory", "Laboratory room"),
                                           ("lecture hall", "Lecture hall"), ("office", "Office"),
                                           ("specialised room", "Specialised room")])
def test_us7_a_word_from_the_purpose_finds_those_rooms(db, word, purpose):
    expected = {r[0] for r in db.execute("SELECT room_number FROM rooms WHERE purpose = ?", (purpose,))}
    assert expected <= {r["code"] for r in index.search(word)["results"]}


def test_us7_results_are_ranked_closest_match_first():
    results = index.search("lecture hall")["results"]
    assert results[0]["purpose"] == "Lecture hall"
    # the ranking is deterministic: asking twice gives the same order
    assert results == index.search("lecture hall")["results"]


def test_us7_a_block_narrows_the_list():
    answer = index.search("labs in block F")
    assert answer["results"] and all(r["building_id"] == "F" for r in answer["results"])


def test_us7_the_list_travels_through_the_api(client):
    body = client.get("/api/search", params={"q": "computer lab"}).json()
    assert body["kind"] == "list" and len(body["results"]) >= 2


# ======================================================== US8 Plain language
@pytest.mark.parametrize("question, code", [
    ("where is D103", "D103"),
    ("how do I find D103", "D103"),
    ("which floor is D103 on", "D103"),
    ("where can I find room F207", "F207"),
    ("how to get to G215", "G215"),
    ("I need to get to H304", "H304"),
    ("D103 where?", "D103"),
    ("show me E117", "E117"),
    ("can you tell me where B114 is", "B114"),
    ("где находится Д217", "D217"),
])
def test_us8_ten_question_forms_reach_the_right_room(question, code):
    answer = index.search(question)
    assert answer["kind"] == "room" and answer["room"]["room_number"] == code


@pytest.mark.parametrize("question, code", [
    ("I'm in D101, where is D105?", "D105"),
    ("from G108 to F204", "F204"),
    ("I am at E101, how do I get to H103", "H103"),
    ("Я в D101, где D105?", "D105"),
])
def test_us8_with_two_codes_the_one_asked_about_wins(question, code):
    assert index.search(question)["room"]["room_number"] == code


def test_us8_where_is_room_204_names_the_blocks_and_the_floor():
    answer = index.search("where is room 204")
    assert answer["kind"] == "ambiguous"
    assert "floor 2" in answer["summary"]
    assert {"D204", "F204", "G204"} <= set(answer["suggestions"])


def test_us8_an_unclear_question_says_so_and_shows_examples():
    answer = index.search("what should I do today")
    assert answer["kind"] == "no_match"
    assert "D103" in answer["summary"] and answer["suggestions"]


# ======================================================== US9 Floor plan
def _poly(shape):
    if shape["kind"] == "circle":
        return [(shape["cx"] + shape["r"] * math.cos(2 * math.pi * i / 32),
                 shape["cy"] + shape["r"] * math.sin(2 * math.pi * i / 32)) for i in range(32)]
    return [tuple(p) for p in shape["points"]]


def _area(p):
    return abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1] for i in range(len(p)))) / 2


def _clip(subject, clipper):
    """The part of `subject` inside `clipper` (Sutherland-Hodgman)."""
    if sum(clipper[i][0] * clipper[i - 1][1] - clipper[i - 1][0] * clipper[i][1] for i in range(len(clipper))) < 0:
        clipper = clipper[::-1]
    out = subject
    for i in range(len(clipper)):
        a, b = clipper[i - 1], clipper[i]
        inside = lambda q: (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) <= 0
        src, out = out, []
        for j in range(len(src)):
            cur, prev = src[j], src[j - 1]
            if inside(cur) != inside(prev):
                (x1, y1), (x2, y2), (x3, y3), (x4, y4) = prev, cur, a, b
                d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d if d else 0
                out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
            if inside(cur):
                out.append(cur)
        if not out:
            break
    return out


@pytest.mark.parametrize("b", [[(5, 5), (15, 5), (15, 15), (5, 15)], [(5, 15), (15, 15), (15, 5), (5, 5)]])
def test_us9_the_overlap_check_sees_an_overlap(b):
    """The check below must not pass by accident: two squares sharing a corner
    quarter overlap by 25, whichever way round either is drawn."""
    a = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert _area(_clip(a, b)) == pytest.approx(25)
    assert _area(_clip(a[::-1], b)) == pytest.approx(25)


@pytest.mark.parametrize("floor", [1, 2, 3])
def test_us9_no_two_rooms_overlap(floor):
    shapes = [(s["code"], _poly(s)) for s in FLOORS[floor]["rooms"]]
    clashes = []
    for i, (ca, pa) in enumerate(shapes):
        for cb, pb in shapes[i + 1:]:
            if (max(x for x, _ in pa) < min(x for x, _ in pb) or max(x for x, _ in pb) < min(x for x, _ in pa)
                    or max(y for _, y in pa) < min(y for _, y in pb) or max(y for _, y in pb) < min(y for _, y in pa)):
                continue
            inter = _clip(pa, pb)
            if len(inter) >= 3 and _area(inter) > 1.0:
                clashes.append((ca, cb, round(_area(inter))))
    assert clashes == []


@pytest.mark.parametrize("floor", [1, 2, 3])
def test_us9_the_outline_of_a_corridor_run_ends_with_its_rooms(floor):
    """The building outline behind a run of rooms on the corridor wall is cut to
    those rooms: no strip of it is left sticking out under the next wing."""
    rooms = [_poly(s) for s in FLOORS[floor]["rooms"] if s["kind"] == "rect"]
    tails = []
    for area in FLOORS[floor]["areas"]:
        pts = [tuple(p) for p in area["points"]]
        xs, ys = {x for x, _ in pts}, {y for _, y in pts}
        if len(pts) != 4 or len(xs) != 2 or len(ys) != 2:
            continue                                   # only plain upright boxes
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        inside = [r for r in rooms if abs(min(x for x, _ in r) - x0) < 0.5 and abs(max(x for x, _ in r) - x1) < 0.5
                  and min(y for _, y in r) >= y0 - 0.5 and max(y for _, y in r) <= y1 + 0.5]
        if len(inside) < 2:
            continue                                   # not a run of corridor rooms
        top, bottom = min(min(y for _, y in r) for r in inside), max(max(y for _, y in r) for r in inside)
        if y0 < top - 0.5 or y1 > bottom + 0.5:
            tails.append((round(x0), round(y0), round(y1), round(top), round(bottom)))
    assert tails == []


def test_us9_every_floor_is_one_drawing_with_blocks_in_corridor_order():
    for floor in FLOORS.values():
        along = [b for b in floor["blocks"] if not b.get("north") and not b["annex"]]
        assert [b["y0"] for b in along] == sorted(b["y0"] for b in along)
        assert {"D", "E", "F", "G", "H"} <= {b["id"] for b in floor["blocks"]}


def test_us9_the_plan_is_vector_data_not_the_scanned_sheets(client):
    body = client.get("/api/map").json()
    assert all("image" not in f for f in body["floors"])
    assert all(r["kind"] in ("rect", "circle") for f in body["floors"] for r in f["rooms"])


# ======================================================== US10 Highlight
@pytest.mark.parametrize("code, floor", [("D103", 1), ("F204", 2), ("H304", 3)])
def test_us10_the_answer_points_at_the_room_on_its_floor(code, floor):
    shape = next(s for s in FLOORS[floor]["rooms"] if s["code"] == code)
    answer = index.search(code)
    assert answer["map"]["floor"] == floor
    assert (answer["map"]["x"], answer["map"]["y"]) == pytest.approx((shape["x"], shape["y"]), abs=1)


def test_us10_the_client_switches_floor_highlights_clears_and_centres():
    assert "openFloor(d.map.floor, { focus:" in APP_JS            # switch to the room's floor
    assert 'classList.remove("is-target"' in APP_JS               # clear the old highlight
    assert 'target.classList.add("is-target")' in APP_JS          # highlight the new one
    assert "focusOn(focus.x, focus.y, ROOM_ZOOM, true)" in APP_JS  # bring it into view


# ======================================================== US11 Floors, zoom, pan
def test_us11_floor_buttons_redraw_without_reloading():
    assert "data-floor=" in APP_JS and "openFloor(Number(b.dataset.floor)" in APP_JS
    assert "location.reload" not in APP_JS


def test_us11_zoom_is_bounded():
    assert re.search(r"const MIN_ZOOM = [\d.]+", APP_JS) and re.search(r"const MAX_ZOOM = \d+", APP_JS)
    assert "Math.min(Math.max(scale, v.fit * MIN_ZOOM), v.fit * MAX_ZOOM)" in APP_JS


def test_us11_dragging_cannot_lose_the_plan():
    assert "function clampView()" in APP_JS and "clampView();" in APP_JS


def test_us11_two_fingers_pinch_to_zoom():
    assert "pointers.size === 2" in APP_JS and "startPinch()" in APP_JS


def test_us11_a_tap_is_not_a_drag():
    """The zoom buttons and the rooms sit on the plan: pressing them must not start
    a drag that captures the pointer and swallows their click, and the stage must
    not scroll when a button on it takes the focus."""
    assert 'if (e.target.closest("button, a")) return;' in APP_JS
    assert "Math.hypot(p.x - drag.x, p.y - drag.y) < DRAG_START" in APP_JS
    css = (BASE_DIR / "static" / "styles.css").read_text()
    assert re.search(r"\.stage \{[^}]*overflow: clip", css)


def test_us11_switching_floors_keeps_the_zoom():
    assert "const before = state.floor ? { ...state.view } : null;" in APP_JS
    assert "if (zoomed) focusOn(spot.x, spot.y, before.s, false);" in APP_JS


# ======================================================== US12 Hall names
HALLS = {"A1": "D117", "A2": "D218", "B1": "D116", "B2": "D217",
         "C1": "D113", "C2": "D214", "D1": "E117", "D2": "E221"}


@pytest.mark.parametrize("name, code", sorted(HALLS.items()))
def test_us12_every_hall_answers_to_its_name_with_its_code_and_round_highlight(name, code):
    answer = index.search(name)
    assert answer["room"]["room_number"] == code
    assert f"hall {name}" in answer["summary"]                    # the code is shown with the name
    shape = next(s for f in FLOORS.values() for s in f["rooms"] if s["code"] == code)
    assert shape["kind"] == "circle"
    assert answer["map"]["radius"] == pytest.approx(shape["r"])   # the highlight covers the whole hall
    assert (answer["map"]["x"], answer["map"]["y"]) == pytest.approx((shape["cx"], shape["cy"]))


# ======================================================== US4 (carried over)
@pytest.fixture()
def member():
    """A fresh signed-in account of its own, so changing its password is safe."""
    from fastapi.testclient import TestClient
    from app.main import app, users
    with users._connect() as conn:
        conn.execute("DELETE FROM users WHERE email = '444555666@sdu.edu.kz'")
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "444555666@sdu.edu.kz", "password": TEST_PASSWORD,
                                           "full_name": TEST_NAME})
        yield c


NEW_PASSWORD = "Steppe#2027"


def test_us4_the_password_changes_and_the_new_one_signs_in(member):
    res = member.post("/api/profile/password",
                      json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD})
    assert res.status_code == 200
    member.post("/api/auth/logout")
    bad = member.post("/api/auth/login", json={"email": "444555666@sdu.edu.kz", "password": TEST_PASSWORD})
    assert bad.status_code == 400, "the old password must stop working"
    ok = member.post("/api/auth/login", json={"email": "444555666@sdu.edu.kz", "password": NEW_PASSWORD})
    assert ok.status_code == 200


@pytest.mark.parametrize("current", ["", "Wrong#12345"])
def test_us4_no_change_without_the_right_current_password(member, current):
    res = member.post("/api/profile/password", json={"current_password": current, "new_password": NEW_PASSWORD})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "current_password"
    member.post("/api/auth/logout")
    assert member.post("/api/auth/login", json={"email": "444555666@sdu.edu.kz",
                                                "password": TEST_PASSWORD}).status_code == 200


def test_us4_the_new_password_follows_the_rules(member):
    res = member.post("/api/profile/password", json={"current_password": TEST_PASSWORD, "new_password": "short"})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "new_password"


def test_us4_other_devices_are_signed_out_this_one_stays(member):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as other:
        other.post("/api/auth/login", json={"email": "444555666@sdu.edu.kz", "password": TEST_PASSWORD})
        assert other.get("/api/auth/me").status_code == 200
        member.post("/api/profile/password", json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD})
        assert other.get("/api/auth/me").status_code == 401
        assert member.get("/api/auth/me").status_code == 200


def test_us4_a_visitor_has_no_password_to_change(anon):
    anon.post("/api/auth/guest")
    res = anon.post("/api/profile/password", json={"current_password": "x", "new_password": NEW_PASSWORD})
    assert res.status_code == 403


def test_us4_logout_returns_to_login_and_the_app_asks_again(member):
    member.post("/api/auth/logout")
    assert member.get("/api/auth/me").status_code == 401
    assert member.get("/", follow_redirects=False).headers["location"] == "/login"


def test_us4_the_profile_page_is_there(member, anon):
    page = member.get("/profile")
    assert page.status_code == 200 and "Change password" in page.text
    assert anon.get("/profile", follow_redirects=False).headers["location"] == "/login"
