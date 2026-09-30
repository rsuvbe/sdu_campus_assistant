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
    ("Is the dean's office open?", "Dean's Office"),
    ("I need a doctor", "Medcenter"),
    ("где столовая", "Cafeteria"),
])
def test_facility_types_are_understood(query, service):
    answer = index.search(query)
    assert answer["kind"] == "service" and answer["title"] == service


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
        # the two Medcenter rooms answer as the service they hold, which still
        # carries the building, the floor and the route
        expected = "service" if room["room_number"].startswith("MEDCENTER") else "room"
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
