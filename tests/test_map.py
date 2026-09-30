"""
The vector map: one continuous drawing per floor, with every room on it.
"""
import math

import pytest

from app.main import campus_map, index

FLOORS = {f["floor"]: f for f in campus_map.floor_list()}


def test_every_floor_is_one_merged_drawing():
    assert set(FLOORS) == {1, 2, 3}
    for floor in FLOORS.values():
        blocks = {b["id"] for b in floor["blocks"]}
        # front sheet (C-E) and back sheet (F-H) end up on the same drawing
        assert {"D", "E", "F", "G", "H"} <= blocks
        assert floor["width"] > 0 and floor["height"] > 0


def test_every_room_in_the_database_is_drawn_exactly_once():
    drawn = [shape["code"] for floor in FLOORS.values() for shape in floor["rooms"]]
    assert len(drawn) == len(set(drawn)) == len(index.rooms)
    assert set(drawn) == {room["room_number"] for room in index.rooms}


def test_shapes_stay_inside_the_canvas():
    for floor in FLOORS.values():
        for shape in floor["rooms"]:
            points = ([[shape["cx"], shape["cy"]]] if shape["kind"] == "circle" else shape["points"])
            for x, y in points:
                assert 0 < x < floor["width"], f"{shape['code']} is off the drawing"
                assert 0 < y < floor["height"], f"{shape['code']} is off the drawing"


def test_the_back_sheet_is_placed_below_the_front_one():
    """Blocks run C -> I down the same corridor, so their bands must not jump."""
    for floor in FLOORS.values():
        bands = [b for b in floor["blocks"] if not b["annex"]]
        tops = [b["y0"] for b in bands]
        assert tops == sorted(tops), f"blocks out of order on floor {floor['floor']}"


def test_block_i_continues_the_corridor_past_block_h():
    """The annex sits on the same corridor, one block below H, and only repeats
    the east half of it — H's west-side rooms have no counterpart."""
    for floor in FLOORS.values():
        annex = next(b for b in floor["blocks"] if b["id"] == "I")
        block_h = next(b for b in floor["blocks"] if b["id"] == "H")
        assert annex["annex"] is True
        assert annex["x"] == block_h["x"]
        assert annex["y0"] > block_h["y0"]
        assert all(shape["approx"] for shape in floor["rooms"] if shape["block"] == "I")


@pytest.mark.parametrize("code", ["I109", "I110", "I111", "I212", "I213", "I214"])
def test_the_west_half_of_block_h_is_not_repeated_in_block_i(code):
    _assert_gone(code)


@pytest.mark.parametrize("code", ["D114", "D115", "D118", "D215", "D216", "D219", "E116", "E220"])
def test_the_rooms_dropped_from_the_west_side_are_gone(code):
    _assert_gone(code)


def _assert_gone(code):
    from app.engine import normalize
    assert normalize(code) not in index.by_code
    assert all(code != shape["code"] for floor in FLOORS.values() for shape in floor["rooms"])


def test_the_west_wall_rooms_are_flush_against_the_wall():
    """D121, D122, D124 and D128 are the strip built against the outer west
    wall, so they share a left edge and it is the wall of their block."""
    floor1 = FLOORS[1]
    column = [s for s in floor1["rooms"] if s["code"] in ("D121", "D122", "D124", "D128")]
    assert len(column) == 4
    edges = {min(p[0] for p in s["points"]) for s in column}
    assert len(edges) == 1, "the wall rooms must line up"
    wall = edges.pop()
    assert any(min(p[0] for p in v["points"]) == wall for v in floor1["volumes"]), \
        "the shared edge must be the west wall of the block, not a line inside it"


def test_the_west_wall_rooms_do_not_overlap():
    floor1 = FLOORS[1]
    column = sorted((s for s in floor1["rooms"] if s["code"] in ("D121", "D122", "D124", "D128")),
                    key=lambda s: s["y"])
    for upper, lower in zip(column, column[1:]):
        assert max(p[1] for p in upper["points"]) <= min(p[1] for p in lower["points"]) + 0.1


# ------------------------------------------------------------------- barrels
BARRELS = {"A1": "D117", "A2": "D218", "B1": "D116", "B2": "D217",
           "C1": "D113", "C2": "D214", "D1": "E117", "D2": "E221"}


@pytest.mark.parametrize("name, code", sorted(BARRELS.items()))
def test_every_barrel_is_drawn_as_a_circle_and_answers_to_its_name(name, code):
    shape = next(s for floor in FLOORS.values() for s in floor["rooms"] if s["code"] == code)
    assert shape["kind"] == "circle", f"{code} ({name}) must be a round hall"
    assert shape["r"] >= 40, f"{code} ({name}) is drawn too small to read as a barrel"
    assert shape["barrel"] == name

    answer = index.search(f"Where is {name}?")
    assert answer["kind"] == "room" and answer["title"] == code
    assert index.search(name.lower())["title"] == code


def _rect_bounds(shape):
    xs = [p[0] for p in shape["points"]]
    ys = [p[1] for p in shape["points"]]
    return min(xs), min(ys), max(xs), max(ys)


def _gap_to_hall(hall, other):
    """How far `other` is from the edge of the round hall; negative means they overlap."""
    if other["kind"] == "circle":
        centres = math.hypot(other["cx"] - hall["cx"], other["cy"] - hall["cy"])
        return centres - hall["r"] - other["r"]
    x0, y0, x1, y1 = _rect_bounds(other)
    dx = max(x0 - hall["cx"], 0.0, hall["cx"] - x1)
    dy = max(y0 - hall["cy"], 0.0, hall["cy"] - y1)
    return math.hypot(dx, dy) - hall["r"]


def test_no_hall_runs_into_another_room():
    for floor in FLOORS.values():
        for hall in (s for s in floor["rooms"] if s["kind"] == "circle"):
            for other in floor["rooms"]:
                if other is hall:
                    continue
                assert _gap_to_hall(hall, other) >= 0, \
                    f"{hall['code']} overlaps {other['code']} on floor {floor['floor']}"


def test_every_hall_stays_inside_its_wing():
    """A circle drawn past the wall would hang outside the building."""
    for floor in FLOORS.values():
        for hall in (s for s in floor["rooms"] if s["kind"] == "circle"):
            assert any(x0 - 0.5 <= hall["cx"] - hall["r"] and hall["cx"] + hall["r"] <= x1 + 0.5
                       and y0 - 0.5 <= hall["cy"] - hall["r"] and hall["cy"] + hall["r"] <= y1 + 0.5
                       for x0, y0, x1, y1 in (_rect_bounds(v) for v in floor["volumes"])), \
                f"{hall['code']} sticks out of the west wing on floor {floor['floor']}"


def test_barrel_names_do_not_swallow_room_codes():
    assert index.search("D103")["title"] == "D103"
    assert index.search("Where is D105?")["title"] == "D105"


def test_wing_rooms_keep_their_door_order():
    """D101..D105 are one row: same order, left to right, as on the sheet."""
    floor1 = FLOORS[1]
    row = [s for s in floor1["rooms"] if s["code"] in ("D101", "D102", "D103", "D104", "D105")]
    assert [s["code"] for s in sorted(row, key=lambda s: s["x"])] == \
           ["D101", "D102", "D103", "D104", "D105"]


def test_search_answers_point_at_the_drawn_room():
    answer = index.search("D103")
    shape = next(s for s in FLOORS[1]["rooms"] if s["code"] == "D103")
    assert answer["map"]["floor"] == 1
    assert answer["map"]["x"] == pytest.approx(shape["x"], abs=1)
    assert answer["map"]["y"] == pytest.approx(shape["y"], abs=1)
    assert {h["room_number"] for h in answer["map"]["highlights"]} == {"D101", "D102", "D107"}


def test_api_map_is_served(client):
    body = client.get("/api/map").json()
    assert [f["floor"] for f in body["floors"]] == [1, 2, 3]
    assert body["floors"][0]["rooms"]
