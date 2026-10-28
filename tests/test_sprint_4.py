"""
Sprint 4, checked story by story against the story sheet
(AI_Campus_Assistant_User_Stories_v2.xlsx): every responsibility, every QA
scenario, every test script marked (Pass) or (Fail), and the maintenance tasks
that can be checked by a program.

  US13 Text Directions Between Two Rooms    US14 Directions from the Main Entrance
  US15 Campus Services Directory            US16 Opening Hours and Open-Now Status
"""
import math
import random
import re
import sqlite3
from datetime import datetime, timezone

import pytest

from app.engine import CAMPUS_TZ, SERVICE_GROUPS
from app.main import BASE_DIR, DB_PATH, campus_map, index, router
from app.routing import MAIN_ENTRANCE, _inside

APP_JS = (BASE_DIR / "static" / "app.js").read_text()
INDEX_HTML = (BASE_DIR / "static" / "index.html").read_text()
FLOORS = {f["floor"]: f for f in campus_map.floor_list()}
ROOMS = {r["room_number"]: r for r in index.rooms}
ENTRANCE = router.place("exit", MAIN_ENTRANCE)


def room(code):
    return router.place("room", code)


def route(a, b):
    return router.route(room(a) if isinstance(a, str) else a, room(b))


# a fixed sample of pairs across every floor and zone, the same on every run
PAIRS = random.Random(4).sample([(a, b) for a in ROOMS for b in ROOMS if a != b], 120)


# ======================================================== US13 Text directions
# responsibility: an ordered list of steps using corridors, stairs and block names
def test_us13_pass_a_request_between_two_known_rooms_returns_an_ordered_walkable_list():
    for a, b in PAIRS:
        r = route(a, b)
        assert r["steps"], f"no route from {a} to {b}"
        assert r["from"]["code"] == a and r["to"]["code"] == b
        assert len(r["steps"]) == len(r["step_floors"])
        # the drawn walk starts where the first step starts and ends at the door asked for
        assert r["legs"][0]["floor"] == ROOMS[a]["floor_number"]
        assert r["legs"][-1]["floor"] == ROOMS[b]["floor_number"]


def test_us13_every_room_can_be_reached_and_left():
    assert router.unreached == []
    assert set(router.room_node) == set(ROOMS)
    for code in ROOMS:
        assert router.route(ENTRANCE, room(code))["steps"], f"{code} cannot be reached from the entrance"
        assert route(code, "D103")["steps"] if code != "D103" else True


def test_us13_scenario_1_route_on_one_floor_names_corridors_blocks_or_turns():
    r = route("D101", "F104")
    assert r["floors"] == [1]
    words = ("corridor", "Block", "left", "right", "lobby", "wing", "door")
    for step in r["steps"]:
        assert any(w in step for w in words), step
    text = " ".join(r["steps"])
    assert "central corridor" in text and "Block F wing" in text
    assert "F104 is the" in r["steps"][-1] and "on your" in r["steps"][-1]


def test_us13_scenario_2_route_between_floors_names_the_stairs_and_the_target_floor():
    r = route("D101", "H304")
    assert r["floors"][0] == 1 and r["floors"][-1] == 3
    text = " ".join(r["steps"])
    assert re.search(r"stair", text) and "floor 3" in text
    assert r["stairs"], "the plan marks where the floor changes"


def test_us13_fail_no_route_between_floors_without_the_stairs():
    for a, b in PAIRS:
        r = route(a, b)
        if len(r["floors"]) > 1:
            text = " ".join(r["steps"]).lower()
            assert "stair" in text, f"{a} -> {b} changes floor without stairs"
            assert f"floor {r['floors'][-1]}" in text, f"{a} -> {b} never names the floor it ends on"


def _shapes(floor):
    out = []
    for r in FLOORS[floor]["rooms"]:
        if r["kind"] == "circle":
            out.append((r["code"], [(r["cx"] + (r["r"] - 2) * math.cos(2 * math.pi * k / 40),
                                     r["cy"] + (r["r"] - 2) * math.sin(2 * math.pi * k / 40)) for k in range(40)]))
        else:
            out.append((r["code"], r["points"]))
    return out


def _passes_through(p, q, poly):
    """Whether a straight step from p to q goes through the inside of a polygon
    (sampled every 3 px, a pixel in from its walls)."""
    n = max(2, int(math.dist(p, q) // 3))
    cx = sum(x for x, _ in poly) / len(poly)
    cy = sum(y for _, y in poly) / len(poly)
    inner = [(x + (cx - x) * 2 / max(math.dist((x, y), (cx, cy)), 1), y + (cy - y) * 2 / max(math.dist((x, y), (cx, cy)), 1))
             for x, y in poly]
    return any(_inside(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n, inner) for i in range(1, n))


def test_us13_fail_no_step_of_the_graph_passes_through_a_room():
    """Every edge a route can take, on every floor: it may enter only the room
    it leads to (its door), never another room or a closed area."""
    for floor in FLOORS:
        shapes = _shapes(floor)
        for a, edges in router.adj.items():
            na = router.nodes[a]
            if na["floor"] != floor:
                continue
            for b, _, edge in edges:
                nb = router.nodes[b]
                if nb["floor"] != floor or a > b:
                    continue
                own = {na.get("room"), nb.get("room"), edge.get("room")}
                src = router.nodes.get(edge.get("src") or "", {})
                own.add(src.get("room"))
                p, q = (na["x"], na["y"]), (nb["x"], nb["y"])
                for code, poly in shapes:
                    if code in own:
                        continue
                    # an exit or a stairwell may be marked inside a room's drawing
                    if any(_inside(*pt, poly) for pt in (p, q)) and {na["kind"], nb["kind"]} & {"exit", "stairs"}:
                        continue
                    assert not _passes_through(p, q, poly), f"floor {floor}: {a} -> {b} crosses {code}"


def test_us13_fail_no_route_walks_through_a_room_on_the_way():
    for a, b in PAIRS[:40]:
        _, nodes, _ = router._shortest(room(a)["node"], room(b)["node"])
        inner = [router.nodes[n] for n in nodes[1:-1]]
        assert not [n for n in inner if n["kind"] == "room"], f"{a} -> {b} walks through a room"


def test_us13_the_steps_stay_inside_the_building():
    """Corridor and open-floor steps run inside the building's outline (the
    passages out of the side exits are the only steps that start outdoors)."""
    for floor, plan in FLOORS.items():
        areas = [a["points"] for a in plan["areas"]]
        for a, edges in router.adj.items():
            na = router.nodes[a]
            if na["floor"] != floor or na["kind"] == "exit":
                continue
            for b, _, edge in edges:
                nb = router.nodes[b]
                if nb["floor"] != floor or nb["kind"] == "exit" or edge["kind"] == "stairs":
                    continue
                mx, my = (na["x"] + nb["x"]) / 2, (na["y"] + nb["y"]) / 2
                # within a wall's thickness (4 px) of the floor: the drawing leaves a hairline
                # between the corridor and the rooms that open onto it
                near = [(mx, my), (mx + 4, my), (mx - 4, my), (mx, my + 4), (mx, my - 4)]
                assert any(_inside(x, y, poly) for x, y in near for poly in areas), \
                    f"floor {floor}: {a} -> {b} leaves the building"


# task: build the corridor graph from the plan geometry
def test_us13_task_the_wing_corridors_run_down_the_middle_of_the_drawn_wings():
    for (floor, block), wing in router.wings.items():
        halls = FLOORS[floor]["circulation"]
        for door in wing["doors"]:
            assert any(_inside(*door["door"], h["points"]) for h in halls), \
                f"{door['code']}'s door is not in the Block {block} wing corridor on floor {floor}"


def test_us13_task_stairs_join_only_the_staircases_on_the_sheets():
    cores = {}
    for nid, info in router.stairs.items():
        cores.setdefault(info["core"], set()).add(router.nodes[nid]["floor"])
    assert cores == {"lobby": {1, 2}, **{f"wing:{b}": {1, 2, 3} for b in "DEFGH"},
                     # up from the hall over the food court into the 3rd-floor Red Canteen
                     "north Red Canteen staircase": {2, 3},
                     # from beside the table tennis on floor 1 straight up, no way off at floor 2
                     "Red Canteen staircase": {1, 3}}


# task: the shortest path over the graph
def test_us13_task_a_walk_inside_one_wing_stays_in_that_wing():
    r = route("D101", "D105")
    assert len(r["steps"]) == 1 and "D105 is the fourth door on your left" in r["steps"][0]
    assert route("D103", "D107")["steps"] == ["Leave D103: D107 is directly across the corridor."]


def test_us13_task_routes_are_as_long_both_ways():
    for a, b in PAIRS[:30]:
        assert math.isclose(router.distance(room(a), room(b)), router.distance(room(b), room(a)), rel_tol=1e-9)


# task: readable steps naming blocks, stairs and sides
def test_us13_task_the_last_step_counts_the_doors_from_the_way_you_come_in():
    # from the central corridor: counted from the wing's mouth, upper row on your left
    assert "D103 is the third door on your left, just after D101 and D102" in route("C110", "D103")["steps"][-1]
    # from the stairwell at the far end: counted from that end, and the sides swap
    last = route("G105", "G303")["steps"][-1]
    assert "On floor 3, walk back along the Block G wing" in last and "on your right" in last


def test_us13_a_question_with_a_start_and_a_destination_gets_the_walk():
    for q, frm, to in [("from G108 to F204", "G108", "F204"),
                       ("I'm in D101, where is D105?", "D101", "D105"),
                       ("How do I get to Red Hall from D217?", "D217", "Red Hall"),
                       ("из D101 в F204", "D101", "F204"),
                       ("Я в D101, где D105?", "D101", "D105")]:
        answer = index.search(q)
        assert answer["kind"] in ("room", "service")
        assert answer["directions"]["from"]["label"] == frm and answer["directions"]["to"]["label"] == to


def test_us13_the_nearest_of_several_places_with_one_name():
    answer = index.search("nearest restroom to G101")
    rooms = [r for r in index.rooms if r["name"] == "Restroom"]
    best = min(rooms, key=lambda r: router.distance(room("G101"), room(r["room_number"])))
    assert answer["directions"]["to"]["code"] == best["room_number"] == "RESTROOM-G"


# the route as it is drawn on the plan
def test_us13_the_drawn_line_turns_only_where_the_walk_does():
    for a, b in PAIRS:
        for leg in route(a, b)["legs"]:
            pts = leg["points"]
            for p, q, n in zip(pts, pts[1:], pts[2:]):
                u, v = (q[0] - p[0], q[1] - p[1]), (n[0] - q[0], n[1] - q[1])
                lu, lv = math.hypot(*u), math.hypot(*v)
                assert lu >= 0.5 and lv >= 0.5, f"{a} -> {b}: a point twice at {q}"
                # no corner in the middle of a straight run
                assert abs(u[0] * v[1] - u[1] * v[0]) / math.dist(p, n) > 1.2 or u[0] * v[0] + u[1] * v[1] < 0, \
                    f"{a} -> {b}: a bend that isn't one at {q}"
                # no short hook out past a stairwell and back
                if min(lu, lv) < 12:
                    assert u[0] * v[0] + u[1] * v[1] >= -0.7 * lu * lv, f"{a} -> {b} doubles back at {q}"


def test_us13_a_staircase_is_marked_where_the_plan_draws_it():
    r = route("G108", "F204")
    marks = {(lm["x"], lm["y"]) for lm in FLOORS[1]["landmarks"] + FLOORS[2]["landmarks"] if lm["type"] == "stairs"}
    assert len(r["stairs"]) == 2
    for m in r["stairs"]:
        assert tuple(m["mark"]) in marks, m
        # the line itself ends on the staircase's node, where you step onto it
        leg = next(l for l in r["legs"] if l["floor"] == m["floor"])
        assert [m["x"], m["y"]] in (leg["points"][0], leg["points"][-1])


def test_us13_the_line_runs_wall_to_wall_and_is_framed_with_its_stairs():
    # the line stops at the wall of the room it starts or ends in (never drops its last
    # stretch, which for a hall across open floor is most of the walk), its corners
    # are rounded, arrowheads point the way, and each staircase tag is in the frame
    assert "fromWall(pts, r.from.code)" in APP_JS and "fromWall([...pts].reverse(), r.to.code)" in APP_JS
    assert "roundedPath(pts, TRIP_CORNER)" in APP_JS and "chevrons(line, len, g)" in APP_JS
    assert "pts.push([mx - 150, my], [mx + 150, my])" in APP_JS
    # a route shown from a card pins that card's destination, not the last answer's
    assert "showRoute(d.directions, Number(b.dataset.routeFloor), d)" in APP_JS


def test_us13_the_line_never_steps_past_the_corridor_and_back():
    # from the lobby to B114 the walk used to step left of the central corridor's
    # middle and turn back; the line now takes the straight way round the corner
    pts = router.route(ENTRANCE, room("B114"))["legs"][0]["points"]
    for p, q, n in zip(pts, pts[1:], pts[2:]):
        dot = (q[0] - p[0]) * (n[0] - q[0]) + (q[1] - p[1]) * (n[1] - q[1])
        assert dot >= -0.17 * math.dist(p, q) * math.dist(q, n), f"turns back at {q}"     # sharper than 100 degrees


def test_us13_a_walk_along_the_foyer_stays_in_the_foyer():
    spine_x = FLOORS[1]["spines"][0]["x"]
    for a, b in (("RESTROOM-B", "RED-HALL"), ("RED-HALL", "B114"), ("B114", "LIBRARY")):
        r = route(a, b)
        assert all(abs(x - spine_x) > 1 for x, _ in r["legs"][0]["points"]), f"{a} -> {b} goes out to the corridor"
        assert len(r["steps"]) == 1 and "into the Block B foyer" in r["steps"][0]
        assert "main lobby" not in r["steps"][0].split(":")[1]
    assert route("RESTROOM-B", "RED-HALL")["steps"] == [
        "Step out of the restroom into the Block B foyer and walk away from the main lobby: "
        "Red Hall is at the far end of the foyer."]


def test_us13_places_named_for_what_they_are_take_the():
    steps = route("STAFF-RESTROOM-D", "D301")["steps"]
    assert steps[0].startswith("Leave the staff restroom")
    assert "Leave the table tennis room" in route("TABLE-TENNIS", "D301")["steps"][0]
    last = router.route(ENTRANCE, room("RESTROOM-B"))["steps"][-1]
    assert "The restroom is the first door on your right." in last
    assert "you'll pass B114 and the Library" in router.route(ENTRANCE, room("RED-HALL"))["steps"][-1]
    # a sign reads like a sign; a proper name keeps no article
    assert route("STAFF-RESTROOM-D", "D301")["signs"][0]["text"] == "Staff restroom"
    assert "Leave Red Hall" in route("RED-HALL", "D101")["steps"][0]
    for a, b in PAIRS:
        for step in route(a, b)["steps"]:
            assert step[0].isupper(), step


def test_us13_the_3rd_floor_red_canteen_is_reached_by_its_own_stairs_from_floor_2():
    # from the entrance: up the lobby staircase to floor 2, along the corridor to
    # Block F, across to the hall over the food court and up its staircase, which
    # comes up inside the canteen
    r = router.route(ENTRANCE, room("RED-CANTEEN-3"))
    assert r["floors"] == [1, 2, 3]
    assert [m["name"] for m in r["stairs"] if not m.get("arrive")] == [
        "main lobby staircase", "north Red Canteen staircase"]
    assert "take the north Red Canteen staircase up to floor 3" in r["steps"][-2]
    assert r["steps"][-1] == "On floor 3, the stairs come up inside Red Canteen (3rd floor)."
    assert "north Red Canteen staircase up to floor 3" in " ".join(route("F212", "RED-CANTEEN-3")["steps"])
    # from the table tennis, the staircase beside it runs straight up to the canteen
    r = route("TABLE-TENNIS", "RED-CANTEEN-3")
    assert r["floors"] == [1, 3] and [m["name"] for m in r["stairs"]] == ["Red Canteen staircase"] * 2


def test_us13_a_place_asked_for_by_its_floor_is_that_one():
    # "Red Canteen (3rd floor)" is not swapped for the nearer 1st-floor canteen; a
    # plain "Red Canteen" still goes to the nearer one
    for asked in ("RED-CANTEEN-3", "Red Canteen (3rd floor)", "red canteen 3rd floor"):
        assert index.directions(asked)["to"]["code"] == "RED-CANTEEN-3", asked
    assert index.directions("Red Canteen", "F304")["to"]["code"] == "RED-CANTEEN-3"
    assert index.directions("Red Canteen")["to"]["code"] == "RED-CANTEEN"
    assert index.directions("RED-CANTEEN", "F304")["to"]["code"] == "RED-CANTEEN"


def test_us13_deferred_no_live_positioning_or_rerouting():
    assert "geolocation" not in APP_JS and "watchPosition" not in APP_JS


# ======================================================== US14 From the entrance
def test_us14_pass_the_directions_action_returns_a_route_from_the_main_entrance(client):
    r = client.get("/api/route", params={"to": "D103"}).json()
    assert r["kind"] == "route" and r["from"]["exit"] == MAIN_ENTRANCE
    assert r["steps"][0].startswith("Come in through the main entrance")   # the first step names the entrance
    assert "D103 is the third door on your left" in r["steps"][-1]


@pytest.mark.parametrize("code", random.Random(14).sample(sorted(ROOMS), 25))
def test_us14_fail_the_default_route_never_starts_from_an_arbitrary_room(client, code):
    r = client.get("/api/route", params={"to": code}).json()
    assert r["from"]["exit"] == MAIN_ENTRANCE and "entrance" in r["steps"][0]


def test_us14_fail_changing_the_start_changes_the_route(client):
    default = client.get("/api/route", params={"to": "D103"}).json()
    moved = client.get("/api/route", params={"to": "D103", "from": "G108"}).json()
    assert moved["from"]["code"] == "G108" and moved["steps"] != default["steps"]
    assert moved["steps"][0].startswith("Leave G108")


@pytest.mark.parametrize("start", ["Main entrance", "", "вход", "the entrance"])
def test_us14_the_entrance_is_the_start_whatever_it_is_called(client, start):
    r = client.get("/api/route", params={"to": "F204", "from": start}).json()
    assert r["from"]["exit"] == MAIN_ENTRANCE


@pytest.mark.parametrize("start, kind", [("Library", "room"), ("A1", "room"), ("west entrance by Block G", "exit"),
                                         ("Red Canteen (3rd floor)", "room")])
def test_us14_the_start_can_be_any_room_or_entrance(client, start, kind):
    r = client.get("/api/route", params={"to": "D103", "from": start}).json()
    assert r["kind"] == "route" and r["from"]["kind"] == kind


def test_us14_an_unknown_start_or_destination_says_so(client):
    r = client.get("/api/route", params={"to": "D103", "from": "my dorm"}).json()
    assert r["kind"] == "route_error" and "my dorm" in r["title"]
    r = client.get("/api/route", params={"to": "Z999"}).json()
    assert r["kind"] == "route_error"


def test_us14_routes_need_a_session(anon):
    assert anon.get("/api/route", params={"to": "D103"}).status_code == 401


def test_us14_deferred_no_device_location_is_asked_for():
    assert "geolocation" not in APP_JS


# task: mark the main entrance as a named node in the corridor graph
def test_us14_task_the_main_entrance_is_a_node_of_the_graph():
    node = router.nodes[ENTRANCE["node"]]
    assert node["kind"] == "exit" and node["name"] == "main entrance by the lobby" and router.adj[node["id"]]


# task: a "how do I get there" action on every search result
@pytest.mark.parametrize("question", ["D103", "A1", "Library", "Cafeteria", "Block F", "restroom", "Medcenter"])
def test_us14_task_every_result_on_the_plan_can_be_routed_to(question):
    answer = index.search(question)
    assert answer["map"]["code"], "a result on the plan carries the room a route goes to"
    assert router.route(ENTRANCE, room(answer["map"]["code"]))["steps"]


def test_us14_task_the_card_offers_the_action_and_a_start_picker_defaulting_to_the_entrance():
    assert "How do I get there?" in APP_JS and "data-directions" in APP_JS
    assert 'list="places"' in APP_JS and '<datalist id="places">' in INDEX_HTML
    assert 'add("Main entrance")' in APP_JS
    # the route is fetched without a start, so the server's default (the entrance) applies
    assert "/api/route?" in APP_JS and '`&from=${encodeURIComponent(from)}` : ""' in APP_JS


def test_us14_how_do_i_get_to_asks_for_the_walk_from_the_entrance():
    answer = index.search("How do I get to G215?")
    assert answer["room"]["room_number"] == "G215"
    assert answer["directions"]["from"]["exit"] == MAIN_ENTRANCE


# ======================================================== US15 Services directory
SERVICES = [s for s in index.service_list() if s["kind"] == "service"]


def test_us15_each_service_stores_name_category_room_block_and_floor():
    for svc in SERVICES:
        assert svc["name"] and svc["category"] and svc["category_label"]
        loc = svc["location"]
        assert loc, f"{svc['name']} has no location"
        if "floor_number" in loc:
            assert loc["room"] and loc["building_id"] and loc["floor_number"] in (1, 2, 3)
        else:                         # one service with a room in many blocks: the restrooms
            assert loc["blocks"] and loc["floors"] and loc["count"] > 1


def test_us15_pass_every_category_lists_its_services_with_a_location(client):
    listing = client.get("/api/services").json()
    groups = {}
    for svc in listing:
        groups.setdefault(svc["group"], []).append(svc)
        assert svc["location"]["text"]
    assert list(groups) == [key for key, _, _ in SERVICE_GROUPS]     # in the page's order
    assert all(groups.values())


def test_us15_the_list_is_browsable_by_category():
    cats = {c for _, _, cats in SERVICE_GROUPS for c in cats}
    assert {s["category"] for s in SERVICES} <= cats, "every category belongs to a group"
    assert len(cats) == sum(len(c) for _, _, c in SERVICE_GROUPS), "and to only one"
    assert 'id="dir-filter"' in INDEX_HTML and "data-group" in APP_JS


def test_us15_fail_no_service_on_campus_is_missing_its_location():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ids = {r[0] for r in conn.execute("SELECT service_id FROM services")}
    conn.close()
    assert ids == {s["service_id"] for s in SERVICES}
    assert not [s["name"] for s in SERVICES if not s["location"]]


# the type a room is drawn as on the colour map, and the categories it can hold
FITS = {"FOOD": {"cafeteria", "cafe"}, "LIBRARY": {"library"}, "SHOP": {"shop"}, "SPORT": {"sport"},
        "INFO": {"information"}, "WARDROBE": {"wardrobe"}, "OFFICE": {"deanery", "administrative", "office",
                                                                       "student_services"}}


def test_us15_fail_no_service_is_filed_under_the_wrong_category():
    for svc in SERVICES:
        raw = index.services[svc["service_id"]]
        r = next((x for x in index.rooms if x["room_id"] == raw.get("room_id")), None)
        if r and r["type"] in FITS:
            assert svc["category"] in FITS[r["type"]], f"{svc['name']} ({r['type']}) filed as {svc['category']}"
    expect = {"Library": "study", "Cafeteria": "food", "Medcenter": "health", "Moodle help": "students",
              "Ay Market": "food", "Wardrobe": "facilities", "Restroom": "facilities"}
    for svc in SERVICES:
        if svc["name"] in expect:
            assert svc["group"] == expect[svc["name"]], svc["name"]
    deans = [s for s in SERVICES if s["group"] == "deans"]
    assert len(deans) == 3 and all(s["category"] == "deanery" for s in deans)


def test_us15_scenario_2_a_service_opens_on_the_plan_with_its_room_lit():
    for svc in SERVICES:
        answer = index.search(svc["ask"])
        assert answer["map"], f"{svc['name']} does not open on the plan"
        if answer["kind"] == "list":
            # a service in several rooms (the restrooms) opens with every one of them listed
            assert "code" not in svc["location"] and len(answer["results"]) == svc["location"]["count"]
            continue
        assert answer["kind"] in ("service", "room"), svc["name"]
        if "code" in svc["location"]:
            assert answer["map"]["code"] == svc["location"]["code"]
            assert answer["title"] == svc["name"]          # the name is shown in the result area
    assert "data-ask" in APP_JS and 'b.addEventListener("click", () => ask(b.dataset.ask))' in APP_JS


def test_us15_task_every_service_room_is_on_the_floor_plan_it_says():
    for svc in SERVICES:
        loc = svc["location"]
        if "code" in loc:
            point = campus_map.room_point(loc["code"])
            assert point and point["floor"] == loc["floor_number"], svc["name"]


def test_us15_the_page_also_lists_the_kinds_of_room_there_are_many_of():
    kinds = {s["name"]: s for s in index.service_list() if s["kind"] == "rooms"}
    assert {"Laboratory rooms", "Study spaces", "Lecture halls"} <= set(kinds)
    assert kinds["Laboratory rooms"]["location"]["count"] == 32
    assert index.search(kinds["Laboratory rooms"]["ask"])["kind"] == "list"


def test_us15_deferred_no_live_occupancy_or_queues():
    for svc in index.service_list():
        assert "occupancy" not in " ".join(svc)


# ======================================================== US16 Opening hours
TUE = datetime(2026, 10, 20, tzinfo=CAMPUS_TZ)     # a Tuesday in term


def status(name, when):
    return next(s for s in index.service_list(when) if s["name"] == name)


def test_us16_each_service_stores_weekday_opening_hours():
    for svc in SERVICES:
        assert svc["hours"], f"{svc['name']} has no hours"
        for h in svc["hours"]:
            assert re.fullmatch(r"\d\d:\d\d", h["open"]) and re.fullmatch(r"\d\d:\d\d", h["close"])
            assert h["open"] < h["close"]


def test_us16_pass_an_open_service_is_marked_open_and_a_closed_one_closed():
    at_ten = TUE.replace(hour=10)
    assert status("Library", at_ten)["open_now"] is True
    sunday_night = datetime(2026, 10, 25, 22, 0, tzinfo=CAMPUS_TZ)
    assert status("Cafeteria", sunday_night)["open_now"] is False


def test_us16_fail_a_service_with_no_stored_hours_is_not_shown_as_open():
    svc = dict(index.services["SVC_LIBRARY"], hours={})
    payload = index._service_payload(svc, TUE.replace(hour=10))
    assert payload["open_now"] is None and "aren't on file" in payload["status"]


def test_us16_fail_the_status_is_computed_in_campus_time_not_the_servers():
    # 13:00 UTC is 18:00 in Almaty: the library (08:30-17:30) is closed by then
    utc = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)
    assert status("Library", utc)["open_now"] is False
    # 04:00 UTC is 09:00 in Almaty: open
    assert status("Library", utc.replace(hour=4))["open_now"] is True


def test_us16_campus_time_is_utc_plus_five():
    # Kazakhstan has one zone, UTC+5, since 1 March 2024; stale time-zone files say +6
    assert TUE.utcoffset().total_seconds() == 5 * 3600


def test_us16_scenario_1_an_open_service_shows_its_closing_time():
    assert status("Library", TUE.replace(hour=10))["status"] == "Open until 17:30"


def test_us16_scenario_2_a_closed_service_shows_its_next_opening_time():
    assert status("Cafeteria", TUE.replace(hour=21))["status"] == "Closed, opens tomorrow at 08:00"
    assert status("Cafeteria", TUE.replace(hour=7))["status"] == "Closed, opens today at 08:00"
    friday_night = datetime(2026, 10, 23, 21, 0, tzinfo=CAMPUS_TZ)
    assert status("Library", friday_night)["status"] == "Closed, opens Monday at 08:30"


def test_us16_verified_three_times_of_day():
    morning, lunch, evening = (TUE.replace(hour=9), TUE.replace(hour=12, minute=45), TUE.replace(hour=18))
    assert status("Student Center", morning)["status"] == "Open until 12:30, back at 13:30 after lunch"
    assert status("Student Center", lunch)["status"] == "Lunch break, back at 13:30"
    assert status("Student Center", lunch)["open_now"] is False
    assert status("Student Center", evening)["open_now"] is False
    assert status("Ay Market", evening)["status"] == "Open until 20:00"


def test_us16_hours_not_confirmed_are_marked_and_not_counted_as_open():
    # the services page says which times are the team's guess, and counts as
    # "open now" only services whose hours are confirmed
    assert 'svc.hours_approximate && svc.hours?.length > 0' in APP_JS
    assert 'svc.open_now === true && !guessed(svc)' in APP_JS and "more probably" in APP_JS
    assert '`${guess ? "≈ " : ""}${shortStatus(svc)}`' in APP_JS
    assert "Hours the service" in APP_JS


def test_us16_the_services_page_shows_each_status():
    assert "lamp ${cls}" in APP_JS and "shortStatus(svc)" in APP_JS


# ============================================================ on a phone
STYLES = (BASE_DIR / "static" / "styles.css").read_text()


def test_phone_moving_the_plan_does_no_extra_work_per_touch():
    # the plan moves once a frame, and nothing is written that makes the browser
    # restyle every room on the plan as the finger moves
    assert "--inv" not in APP_JS
    assert "scheduleView();" in APP_JS and "zoomTo(state.view.s * ratio, mx, my, false, true)" in APP_JS
    # the sheet is measured when a drag starts, not on every move
    assert 'max: snapOffset("peek")' in APP_JS and "drag.max" in APP_JS
    # the ping round a found room stops after three
    assert "animation: ping 2s ease-out 3;" in STYLES and "ping 2s ease-out infinite" not in STYLES


def test_phone_the_frame_never_scrolls_off_the_bar():
    assert "overflow: hidden; overflow: clip;" in STYLES
    assert 'frame.addEventListener("scroll"' in APP_JS


def test_static_files_are_cached_and_pages_are_not(client):
    versioned = client.get("/static/app.js?v=1")
    assert versioned.status_code == 200
    assert "immutable" in versioned.headers["cache-control"] and "s-maxage" in versioned.headers["cache-control"]
    plain = client.get("/static/img/favicon.png")
    assert plain.headers["cache-control"] == "public, max-age=3600, s-maxage=86400"
    assert client.get("/").headers.get("cache-control") == "no-cache"
