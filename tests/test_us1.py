"""
US1 — Conversational Location Search: automated acceptance tests.

Scenario 1 (US1QATest): 5 different natural-language questions return the
correct building and floor, each in under 5 seconds.
Scenario 2 (US1QATest): a room that doesn't exist gives a clear "not found"
answer plus nearby valid suggestions.

Run with:  pytest -v
"""
from datetime import datetime

import pytest

from app.engine import CAMPUS_TZ
from app.main import index


# ---------------------------------------------------------------- Scenario 1
@pytest.mark.parametrize("query, room, block, floor", [
    ("Where is room D103?", "D103", "D", 1),
    ("Где находится F207?", "F207", "F", 2),
    ("How do I get to G215?", "G215", "G", 2),
    ("I need to find H304", "H304", "H", 3),
    ("Кабинет Д217", "D217", "D", 2),        # Cyrillic lookalike letter
])
def test_scenario1_correct_building_and_floor(client, query, room, block, floor):
    res = client.get("/api/search", params={"q": query})
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "room"
    assert body["room"]["room_number"] == room
    assert body["room"]["building_id"] == block
    assert body["room"]["floor_number"] == floor
    assert body["elapsed_ms"] < 5000
    assert len(body["steps"]) >= 3, "answer should be step-by-step directions, not a bare fact"


def test_scenario1_wing_directions_use_real_neighbours():
    body = index.search("D103")
    wing_step = next(s for s in body["steps"] if "door" in s)
    assert "third door on your left" in wing_step
    assert "D101" in wing_step and "D102" in wing_step
    assert "D107" in wing_step  # the room directly across the corridor


def test_room_answer_carries_plan_coordinates():
    body = index.search("E205")
    plan = body["plan"]
    assert plan["image"].startswith("/static/plans/")
    assert 0 < plan["x"] < plan["width"] and 0 < plan["y"] < plan["height"]


# ---------------------------------------------------------------- Scenario 2
def test_scenario2_not_found_with_suggestions(client):
    body = client.get("/api/search", params={"q": "Where is room D199?"}).json()
    assert body["kind"] == "not_found"
    assert "D199" in body["summary"]
    assert 1 <= len(body["suggestions"]) <= 3
    for code in body["suggestions"]:
        assert index.search(code)["kind"] == "room", f"suggestion {code} must be a real room"


# ---------------------------------------------------------------- extras
def test_bare_number_asks_which_block():
    body = index.search("Room 204")
    assert body["kind"] == "ambiguous"
    assert {"D204", "E204", "F204", "G204", "H204"} <= set(body["suggestions"])


def test_block_i_is_flagged_as_approximate():
    body = index.search("I304")
    assert body["kind"] == "room"
    assert body["note"] and "Block H" in body["note"]
    assert body["plan"] is None


def test_service_open_and_closed_by_schedule():
    tuesday_3pm = datetime(2026, 9, 29, 15, 0, tzinfo=CAMPUS_TZ)
    tuesday_6pm = datetime(2026, 9, 29, 18, 0, tzinfo=CAMPUS_TZ)
    saturday = datetime(2026, 10, 3, 12, 0, tzinfo=CAMPUS_TZ)
    assert index.search("library", now=tuesday_3pm)["service"]["open_now"] is True
    assert index.search("library", now=tuesday_6pm)["service"]["open_now"] is False
    assert index.search("столовая", now=tuesday_6pm)["service"]["open_now"] is True
    assert index.search("cafeteria", now=saturday)["service"]["status"] == "Closed, opens Monday at 08:00"


def test_medcenter_has_route_but_no_invented_hours():
    body = index.search("medcenter")
    assert body["kind"] == "service"
    assert body["plan"] is not None
    assert body["service"]["hours"] == []


# ---------------------------------------------------------------- API surface
def test_health_and_sheets_and_home(client):
    assert client.get("/api/health").json()["status"] == "ok"
    sheets = client.get("/api/sheets").json()
    assert len(sheets) == 6
    assert all(s["rooms"] for s in sheets)
    home = client.get("/")
    assert home.status_code == 200 and "SDU Campus Assistant" in home.text
    assert client.get(sheets[0]["image"]).status_code == 200


def test_empty_query_is_rejected(client):
    assert client.get("/api/search", params={"q": ""}).status_code == 422
