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
    """Blocks run C -> I down the same corridor, so their bands must not jump.
    (A and B sit side by side north of the lobby, off the corridor.)"""
    for floor in FLOORS.values():
        bands = [b for b in floor["blocks"] if not b["annex"] and not b["north"]]
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


# Block I has no plan: its west side is not copied from Block H, and the two
# offices the university names there (I113, I214) are not drawn either.
@pytest.mark.parametrize("code", ["I109", "I110", "I111", "I212", "I213", "I113", "I214"])
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


# --------------------------------------------- the October 2026 sheet update
def _shape(code):
    return next(s for floor in FLOORS.values() for s in floor["rooms"] if s["code"] == code)


def test_block_b_sits_north_of_the_lobby_off_the_corridor():
    floor1 = FLOORS[1]
    bands = {b["id"]: b for b in floor1["blocks"]}
    assert bands["B"]["north"] and bands["B"]["y1"] < bands["D"]["y0"]
    # the central corridor still starts at Block C, not up in the foyer
    assert floor1["spines"][0]["y0"] > bands["B"]["y0"]
    assert any(f["kind"] == "foyer" for f in floor1["features"])
    hall, library, b114 = _shape("RED-HALL"), _shape("LIBRARY"), _shape("B114")
    assert b114["x"] < library["x"] < hall["x"], "B114, the Library, then Red Hall walking east"


def test_named_rooms_are_labelled_with_their_name():
    assert _shape("RED-HALL")["label"] == "Red Hall"
    assert _shape("STUDY-SPACE-1")["label"] == "Study Space"
    assert _shape("STUDY-SPACE-1")["ask"] == "Study Space 1"


@pytest.mark.parametrize("code", ["STUDY-SPACE-1", "STUDY-SPACE-2", "STUDY-SPACE-3", "STUDY-SPACE-4"])
def test_the_floor_3_study_spaces_are_the_round_halls(code):
    shape = _shape(code)
    assert shape["kind"] == "circle" and shape["r"] >= 40
    assert index.search(code)["map"]["floor"] == 3


def test_traced_rooms_keep_the_layout_of_their_sheet():
    # G318 is the room east of G319 and G320, not a fifth box in their column
    assert _shape("G318")["x"] > max(_shape("G319")["x"], _shape("G320")["x"])
    assert _shape("G322")["y"] < _shape("G321")["y"] < _shape("G320")["y"] < _shape("G319")["y"]
    # Red Coffee is under Red Canteen, Doner House to their west
    assert _shape("RED-CANTEEN")["y"] < _shape("RED-COFFEE")["y"]
    assert _shape("DONER-HOUSE")["x"] < _shape("RED-CANTEEN")["x"]
    # names too long for a narrow room stand upright, as on the sheet
    assert _shape("DONER-HOUSE")["angle"] == 90



# ------------------------------------------- the colour map, and nothing cut
def _inside(x, y, points):
    """Ray casting: is (x, y) inside the polygon?"""
    hit = False
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def test_the_library_takes_in_its_own_exit():
    library = _shape("LIBRARY")
    exit_ = next(lm for lm in FLOORS[1]["landmarks"] if "Library" in lm["name"])
    assert _inside(exit_["x"], exit_["y"], library["points"]), \
        "the north exit is at the end of the Library's own passage"


def test_red_hall_is_block_a():
    assert _shape("RED-HALL")["block"] == "A"
    tags = {b["id"]: (b["tag_x"], b["tag_y"]) for b in FLOORS[1]["blocks"]}
    assert tags["A"] != tags["B"], "the two north blocks need letters of their own"


@pytest.mark.parametrize("code", ["G116", "G115", "G114"])
def test_the_diagonal_g_rooms_sit_on_their_own_printed_labels(code):
    shape = _shape(code)
    room = next(r for r in index.rooms if r["room_number"] == code)
    point = campus_map.to_map(room["sheet_id"], room["x"], room["y"])
    assert _inside(*point, shape["points"]), f"{code}'s point is outside its own room"


@pytest.mark.parametrize("block", ["B", "D", "E", "F", "G"])
def test_every_block_on_floor_1_has_its_restroom(block):
    assert any(s["code"] == f"RESTROOM-{block}" for s in FLOORS[1]["rooms"])


def test_only_the_block_b_rows_are_drawn_without_a_name():
    """Unnamed shapes are the six rooms south of the Block B foyer, nothing else:
    floors 2 and 3 are drawn from their rooms alone."""
    assert len(FLOORS[1]["fixtures"]) == 6
    assert FLOORS[2]["fixtures"] == [] and FLOORS[3]["fixtures"] == []
    b = next(blk for blk in FLOORS[1]["blocks"] if blk["id"] == "B")
    for fixture in FLOORS[1]["fixtures"]:
        for x, y in fixture["points"]:
            assert b["y0"] - 100 < y < b["y1"] + 100


def test_small_rooms_print_a_short_name_that_fits():
    assert _shape("RESTROOM-B")["label"] == "WC"
    assert _shape("RED-HALL")["label"] == "Red Hall"


def test_the_two_red_canteens_are_labelled_with_their_floor():
    first, third = _shape("RED-CANTEEN"), _shape("RED-CANTEEN-3")
    assert (first["label"], first["sub"]) == ("Red Canteen", "1st floor")
    assert (third["label"], third["sub"]) == ("Red Canteen", "3rd floor")
    assert index.search("Red Canteen 3rd floor")["map"]["floor"] == 3


@pytest.mark.parametrize("code", ["LIBRARY", "B114", "RED-CANTEEN", "RED-CANTEEN-3", "RED-COFFEE",
                                  "DONER-HOUSE", "CAFETERIA", "TABLE-TENNIS", "AY-MARKET"])
def test_these_rooms_are_drawn_square(code):
    """Every edge runs straight across or straight down the plan."""
    pts = _shape(code)["points"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        assert abs(x0 - x1) < 0.5 or abs(y0 - y1) < 0.5, f"{code} has a slanted edge"


def test_the_library_reaches_east_to_the_covered_passage():
    library, b114, hall = _shape("LIBRARY"), _shape("B114"), _shape("RED-HALL")
    right = max(p[0] for p in library["points"])
    assert min(p[0] for p in library["points"]) >= max(p[0] for p in b114["points"])
    assert right > library["x"] and right < min(p[0] for p in hall["points"])


def test_the_food_court_shares_its_edges():
    """Doner House, Red Canteen, Red Coffee and the Cafeteria sit on one grid:
    no corner of one sticks out past the line of the next."""
    box = {c: _rect_bounds(_shape(c)) for c in ("DONER-HOUSE", "RED-CANTEEN", "RED-COFFEE", "CAFETERIA")}
    assert box["DONER-HOUSE"][2] == box["RED-CANTEEN"][0] == box["RED-COFFEE"][0]
    assert box["RED-CANTEEN"][2] == box["RED-COFFEE"][2] == box["CAFETERIA"][2]
    assert box["DONER-HOUSE"][0] == box["CAFETERIA"][0]
    assert box["RED-CANTEEN"][3] == box["RED-COFFEE"][1]
    assert box["RED-COFFEE"][3] == box["DONER-HOUSE"][3] == box["CAFETERIA"][1]


# ------------------------------- the angled G wings and the rotated H blocks
def _shared_wall(a, b):
    """Two rooms of one row share a wall: two corners of one are corners of the other."""
    pa = {(round(x), round(y)) for x, y in _shape(a)["points"]}
    pb = {(round(x), round(y)) for x, y in _shape(b)["points"]}
    return len(pa & pb) >= 2


@pytest.mark.parametrize("row", [("G116", "G115", "G114"), ("G219", "G218", "G217"),
                                 ("G113", "G112"), ("G216", "G215")])
def test_the_g_rows_are_one_joined_row(row):
    for a, b in zip(row, row[1:]):
        assert _shared_wall(a, b), f"{a} and {b} should share a wall, as on the plan"


@pytest.mark.parametrize("code, angle", [("G116", 45), ("G219", 42), ("H110", -37), ("H213", -35.8)])
def test_the_turned_rooms_follow_their_wing(code, angle):
    """Every edge runs along the wing or square across it, at the wing's angle."""
    pts = _shape(code)["points"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        edge = math.degrees(math.atan2(y1 - y0, x1 - x0))
        off = (edge - angle) % 90
        assert min(off, 90 - off) < 1.0, f"{code} has an edge off its wing's angle"


@pytest.mark.parametrize("floor, block", [(1, "G"), (1, "H"), (2, "G"), (2, "H")])
def test_the_west_blocks_have_the_outline_of_the_plan_not_a_box(floor, block):
    """The angled wing and the rotated block give the outline slanted walls."""
    rooms = [s for s in FLOORS[floor]["rooms"] if s["block"] == block and s["kind"] == "rect"]
    cx = min(s["x"] for s in rooms)
    volume = next(v for v in FLOORS[floor]["volumes"]
                  if min(p[0] for p in v["points"]) <= cx <= max(p[0] for p in v["points"])
                  and min(p[1] for p in v["points"]) <= rooms[0]["y"] <= max(p[1] for p in v["points"]))
    pts = volume["points"]
    slanted = [1 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]) if abs(x0 - x1) > 1 and abs(y0 - y1) > 1]
    assert slanted, f"floor {floor} block {block} is still drawn as a rectangle"
