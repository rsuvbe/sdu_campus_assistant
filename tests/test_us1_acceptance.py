"""
US1 — Conversational Location Search, checked line by line against the
story sheet and US1QATest.

Each test names the clause it covers, so a failure says which part of the
user story broke rather than which function did.
"""
import sqlite3
import time

import pytest

from app.main import DB_PATH, index


# ====================================================== US1QATest, Scenario 1
# "The user asks 'Where is room 204 in the Engineering building?'"
# "The assistant returns the building, floor, and nearest landmark for room 204"
# "The response is delivered within 5 seconds"
QA_SCENARIO_1 = "Where is room 204 in the Engineering building?"


def test_qa_scenario_1_returns_building_floor_and_landmark():
    answer = index.search(QA_SCENARIO_1)
    assert answer["kind"] == "room"
    assert answer["room"]["building_id"] == "F", "Engineering is Block F"
    assert answer["room"]["room_number"] == "F204"
    assert answer["room"]["floor_number"] == 2
    assert "Faculty of Engineering" in answer["room"]["building_name"]
    assert any(step.startswith("Landmark:") for step in answer["steps"])


def test_qa_scenario_1_is_answered_well_inside_five_seconds():
    started = time.perf_counter()
    index.search(QA_SCENARIO_1)
    assert time.perf_counter() - started < 5.0


def test_the_same_question_through_the_api(client):
    body = client.get("/api/search", params={"q": QA_SCENARIO_1}).json()
    assert body["kind"] == "room" and body["room"]["building_id"] == "F"
    assert body["elapsed_ms"] < 5000


# ====================================================== US1QATest, Scenario 2
def test_qa_scenario_2_says_not_found_and_suggests_real_rooms():
    answer = index.search("Where is room D199?")
    assert answer["kind"] == "not_found"
    assert "no room d199" in answer["summary"].lower()
    assert answer["suggestions"]
    for code in answer["suggestions"]:
        assert index.search(code)["kind"] == "room"


# ======================================= responsibility: parse room numbers,
# ======================================= department names and facility types
@pytest.mark.parametrize("query, expected", [
    # room numbers, written the way people write them
    ("Where is D103?", "D103"),
    ("кабинет Д217", "D217"),
    ("I need to find H304", "H304"),
    ("G-215", "G215"),
    # the round lecture halls by the name the campus uses
    ("Where is A1?", "D117"),
    ("hall C2", "D214"),
    # Block B, north of the lobby, and places known by a name
    ("Where is B114?", "B114"),
    ("кабинет Б114", "B114"),
    ("Where is Red Hall?", "Red Hall"),
    ("G318", "G318"),
])
def test_room_queries_are_understood(query, expected):
    assert index.search(query)["title"] == expected


@pytest.mark.parametrize("query, block", [
    ("Where is the Business School?", "G"),
    ("Where is the Faculty of Law?", "D"),
    ("Where is the Engineering building?", "F"),
    ("Faculty of Education and Humanities", "E"),
    ("Where is Block D?", "D"),
    ("где находится юридический факультет", "D"),
])
def test_department_and_building_names_are_understood(query, block):
    answer = index.search(query)
    assert answer["kind"] == "block", f"{query!r} was not recognised as a block"
    assert answer["block"]["building_id"] == block
    assert answer["block"]["rooms"] > 0 and answer["steps"]


@pytest.mark.parametrize("query, service", [
    ("Where is the library?", "Library"),
    ("Where can I get lunch?", "Cafeteria"),
    ("I need a doctor", "Medcenter"),
    ("где столовая", "Cafeteria"),
    ("Where can I get coffee?", "Red Coffee"),
    ("где донер", "Doner House"),
    # the more specific name wins over the generic "canteen"
    ("Where is the Red Canteen?", "Red Canteen (1st floor)"),
])
def test_facility_types_are_understood(query, service):
    answer = index.search(query)
    assert answer["kind"] == "service" and answer["title"] == service


@pytest.mark.parametrize("query, block, floor", [
    ("Where is the library?", "B", 1),
    ("Where can I get lunch?", "F", 1),
    ("Where can I get coffee?", "F", 1),
])
def test_services_on_the_plans_come_with_a_route(query, block, floor):
    """The library and the cafeteria used to have no room; the new sheets place them."""
    answer = index.search(query)
    assert answer["room"]["building_id"] == block and answer["room"]["floor_number"] == floor
    assert answer["map"] and answer["map"]["floor"] == floor
    assert any(step.startswith("Landmark:") for step in answer["steps"])


def test_a_name_several_rooms_share_shows_the_first_and_lists_the_rest():
    answer = index.search("Where can I find a study space?")
    assert answer["kind"] == "room" and answer["title"] == "Study Space"
    assert answer["room"]["floor_number"] == 3
    assert answer["suggestions"] == ["Study Space 1", "Study Space 2", "Study Space 3", "Study Space 4"]
    lit = {h["room_number"] for h in answer["map"]["highlights"]}
    assert {"STUDY-SPACE-2", "STUDY-SPACE-3", "STUDY-SPACE-4"} <= lit
    # each suggestion brings back exactly that hall
    for n, text in enumerate(answer["suggestions"], start=1):
        assert index.search(text)["map"]["code"] == f"STUDY-SPACE-{n}"


def test_the_red_canteen_points_at_its_other_floor():
    answer = index.search("Red Canteen")
    assert answer["room"]["floor_number"] == 1 and "floor 3" in answer["note"]
    upstairs = index.search(answer["suggestions"][0])
    assert upstairs["kind"] == "room" and upstairs["room"]["floor_number"] == 3


def test_red_hall_is_block_a_reached_through_the_block_b_foyer():
    answer = index.search("Where is Red Hall?")
    assert answer["room"]["building_id"] == "A"
    route = " ".join(answer["steps"])
    assert "foyer" in route and "far end" in route
    assert "central corridor to Block B" not in route


@pytest.mark.parametrize("query, block", [
    ("Where is the toilet?", "B"),          # the first one from the lobby
    ("toilet in block G", "G"),
    ("туалет в блоке F", "F"),
    ("staff toilet", "D"),
])
def test_restrooms_are_found_and_the_named_block_wins(query, block):
    answer = index.search(query)
    assert answer["kind"] == "room" and answer["room"]["building_id"] == block
    assert len(answer["suggestions"]) >= 4, "the other restrooms are offered too"


@pytest.mark.parametrize("query, title", [
    ("Where is the information desk?", "Information desk"),
    ("гардероб", "Wardrobe"),
    ("student center", "Student Center"),
    ("ping pong", "Table tennis"),
    ("администрация", "Administration"),
])
def test_places_from_the_colour_map_are_found(query, title):
    answer = index.search(query)
    assert answer["kind"] == "service" and answer["title"] == title
    assert answer["map"], f"{title} should have a place on the plan"


def test_a_numbered_room_that_holds_a_service_stays_a_room():
    answer = index.search("D109")
    assert answer["kind"] == "room" and "Student Center" in answer["room"]["facts"]


# ============================ responsibility: single AND multi-turn dialogue
def test_a_number_alone_asks_which_block_and_remembers_the_question():
    first = index.search("Room 204")
    assert first["kind"] == "ambiguous"
    assert first["context"] == "204", "the answer has to carry what it asked about"
    assert {"D204", "E204", "F204", "G204", "H204"} <= set(first["suggestions"])


@pytest.mark.parametrize("reply, expected", [
    ("Engineering", "F204"),
    ("the Business School", "G204"),
    ("Block D", "D204"),
    ("D", "D204"),
])
def test_the_follow_up_turn_resolves_the_earlier_number(reply, expected):
    pending = index.search("Room 204")["context"]
    assert index.search(reply, context=pending)["title"] == expected


def test_the_follow_up_travels_through_the_api(client):
    first = client.get("/api/search", params={"q": "Room 204"}).json()
    second = client.get("/api/search", params={"q": "Engineering", "context": first["context"]}).json()
    assert second["kind"] == "room" and second["room"]["room_number"] == "F204"


def test_context_is_dropped_once_the_question_is_settled():
    assert index.search("D103")["context"] is None
    assert index.search("Where is the library?")["context"] is None


# ============ responsibility: building, floor and nearest landmark, always
def test_every_room_answer_names_building_floor_and_a_landmark():
    for room in index.rooms:
        answer = index.search(room["room_number"])
        assert answer["room"]["building_id"] == room["building_id"]
        assert answer["room"]["floor_number"] == room["floor_number"]
        assert answer["room"]["building_name"]
        assert any(s.startswith("Landmark:") for s in answer["steps"]), \
            f"{room['room_number']} comes back without a landmark"


# =================================== test script (Fail): no location for a
# =================================== valid room, or the wrong building
def test_no_existing_room_is_ever_reported_as_missing():
    for room in index.rooms:
        answer = index.search(room["room_number"])
        # a room that houses a service (the Medcenter, the Library) answers as
        # that service, which still carries the building, the floor and the route
        expected = "service" if index.hosted_service(room) else "room"
        assert answer["kind"] == expected, f"{room['room_number']} exists but was not found"
        assert answer["room"]["building_id"] == room["building_id"]


def test_no_room_is_ever_put_in_the_wrong_building():
    wrong = [r["room_number"] for r in index.rooms
             if index.search(r["room_number"])["room"]["building_id"] != r["building_id"]]
    assert wrong == []


# =================================== constraint: read-only access to the data
def test_the_campus_database_is_opened_read_only():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM rooms")
    finally:
        conn.close()


# ======================= campus offices and their hours (given 2026-10-05)
from datetime import datetime          # noqa: E402

from app.engine import CAMPUS_TZ       # noqa: E402


def _at(day, hour, minute=0):
    """A moment in Almaty time; 5 Oct 2026 is a Monday."""
    return datetime(2026, 10, 5 + day, hour, minute, tzinfo=CAMPUS_TZ)


@pytest.mark.parametrize("query, title, room", [
    ("Where is the student center?", "Student Center", "D109"),
    ("advising desk", "Advising Desk", "Advising Desk"),
    ("I have a question about Moodle", "Moodle help", "F105"),
    ("extension center", "Extension Center", "F109"),
    ("school of information technologies", "School of Information Technologies and Applied Mathematics", "F212"),
    ("school of social sciences", "School of Social Sciences, Business and Law", "D212"),
    ("Center for Multidisciplinary Education", "Center for Multidisciplinary Education", "H210"),
    ("educational methodical center", "Educational Methodical Center", "H107"),
])
def test_every_office_is_found_where_the_university_says(query, title, room):
    answer = index.search(query)
    assert answer["kind"] == "service" and answer["title"] == title
    assert answer["room"]["room_number"] == room and answer["map"]


@pytest.mark.parametrize("query", ["strategic development department", "inclusive education office",
                                   "I113", "I214"])
def test_the_block_i_offices_are_gone(query):
    """Block I has no plan, so its two offices (I113, I214) are not in the
    directory at all: neither as rooms nor as services."""
    answer = index.search(query)
    assert answer["kind"] != "service" and "I113" not in str(answer.get("room")) and "I214" not in str(answer.get("room"))
    names = {svc["name"] for svc in index.services.values()}
    assert not names & {"Strategic Development Department", "Inclusive Education Office"}


@pytest.mark.parametrize("moment, status", [
    (_at(0, 8, 0), "Closed, opens today at 08:30"),
    (_at(0, 9, 0), "Open until 12:30, back at 13:30 after lunch"),
    (_at(0, 12, 45), "Lunch break, back at 13:30"),
    (_at(0, 16, 0), "Open until 17:30"),
    (_at(4, 18, 0), "Closed, opens Monday at 08:30"),
])
def test_the_lunch_break_is_part_of_the_status(moment, status):
    assert index.search("student center", now=moment)["service"]["status"] == status


def test_the_library_has_no_lunch_break_and_exact_hours():
    svc = index.search("library", now=_at(0, 13, 0))["service"]
    assert svc["status"] == "Open until 17:30" and not svc["hours_approximate"]
    assert svc["hours"][0] == {"day": "Monday", "open": "08:30", "close": "17:30", "break": None}


def test_ay_market_keeps_its_weekend_hours():
    market = index.search("ay market", now=_at(5, 19, 0))["service"]   # Saturday evening
    assert market["status"] == "Closed, opens tomorrow at 08:00"
    closes = {h["day"]: h["close"] for h in market["hours"]}
    assert closes["Saturday"] == closes["Sunday"] == "18:00"


@pytest.mark.parametrize("query", ["ay market", "shop", "магазин"])
def test_ay_market_is_the_shop_by_the_food_court(query):
    answer = index.search(query)
    assert answer["service"]["name"] == "Ay Market"
    assert (answer["map"]["code"], answer["map"]["floor"]) == ("AY-MARKET", 1)


@pytest.mark.parametrize("query", ["wardrobe", "table tennis"])
def test_the_wardrobe_and_table_tennis_stay_open_until_half_past_eight(query):
    svc = index.search(query, now=_at(1, 19, 0))["service"]
    assert svc["status"] == "Open until 20:30" and not svc["hours_approximate"]
    assert {h["day"]: (h["open"], h["close"]) for h in svc["hours"]} == {
        day: ("08:30", "20:30") for day in
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")}


def test_there_is_no_stationery_shop_and_g113_is_a_plain_classroom():
    assert "Stationery shop" not in {s["name"] for s in index.services.values()}
    answer = index.search("G113")
    assert answer["kind"] == "room" and not answer.get("service")


# Ay Market is the only place the university says is open on a Sunday.
OPEN_ON_SUNDAY = {"Ay Market"}


def test_on_a_sunday_only_ay_market_is_open():
    sunday = _at(6, 12, 0)
    for svc in index.services.values():
        payload = index._service_payload(svc, sunday)
        expected = svc["name"] in OPEN_ON_SUNDAY
        assert payload["open_now"] is expected, f"{svc['name']} on a Sunday"
        assert ("Sunday" in {h["day"] for h in payload["hours"]}) is expected


def test_every_service_has_hours_now():
    """Where the university gave none, the campus default applies: 08:30-17:30."""
    for svc in index.services.values():
        assert svc["hours"], f"{svc['name']} has no opening hours"


def test_an_office_in_two_rooms_names_both_and_lights_both():
    answer = index.search("extension center")
    assert "F109 and F110" in answer["note"]
    assert "F110" in {h["room_number"] for h in answer["map"]["highlights"]}
    assert "Extension Center" in index.search("F110")["room"]["facts"]


def test_the_application_window_comes_with_the_school():
    assert "10:00–11:00 and 14:00–15:00" in index.search("school of it")["service"]["notes"]


def test_the_advising_desk_is_across_the_corridor_from_d109():
    answer = index.search("advising desk")
    assert answer["route"][-1]["text"] == "Opposite D109"
    assert any("directly across from D109" in step for step in answer["steps"])


# ============ the dean's offices: one per school, so "деканат" asks whose
DEAN_OFFICES = {"School of Information Technologies and Applied Mathematics",
                "School of Social Sciences, Business and Law",
                "Center for Multidisciplinary Education"}


@pytest.mark.parametrize("query", ["Is the dean's office open?", "Где деканат?", "deanery"])
def test_a_dean_question_without_a_school_offers_all_three(query):
    answer = index.search(query)
    assert answer["kind"] == "ambiguous"
    assert set(answer["suggestions"]) == DEAN_OFFICES
    for name in answer["suggestions"]:          # each choice leads to its office
        assert index.search(name)["title"] == name


@pytest.mark.parametrize("query, office", [
    ("dean's office in Block F", "School of Information Technologies and Applied Mathematics"),
    ("деканат юридического факультета", "School of Social Sciences, Business and Law"),
    ("деканат школы IT", "School of Information Technologies and Applied Mathematics"),
    ("dean's office Block H", "Center for Multidisciplinary Education"),
])
def test_naming_the_school_or_its_block_picks_its_dean_office(query, office):
    answer = index.search(query)
    assert answer["kind"] == "service" and answer["title"] == office
    assert answer["service"]["category_label"] == "Dean's office"
