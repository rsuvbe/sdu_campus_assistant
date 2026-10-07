"""
Vector floor plans, redrawn from the evacuation sheets.

The photographed sheets cannot be the map: each floor is split in two
(a "front" sheet with blocks C-E and a "back" sheet with F-H), and both are
covered in fire symbols, evacuation arrows and a Kazakh title block.

This module rebuilds every floor as one continuous drawing:

  * the two sheets are merged. Their x axes are aligned on the central
    corridor (taken from sheet_geometry) and the back sheet is pushed down by
    a constant that preserves the real gap between the last front wing and the
    first back wing, so the corridor runs unbroken from the lobby to Block H;
  * every room becomes a polygon. Nothing is invented: the centre of each
    polygon is the room's surveyed position in campus.db, and its size comes
    from the distance to its neighbours in the same row, so door order, row
    side, wing slope and adjacency are exactly what the plans show;
  * the fire equipment, arrows and title blocks are simply not drawn.

Coordinates are plan pixels (all six sheets share one scale) shifted so that
the drawing starts at (0, 0) for each floor. `CampusMap.to_map()` applies the
same transform to any sheet coordinate, which is how the search engine reports
a room's position on the vector map.
"""
from __future__ import annotations

import math

from .engine import BLOCK_ORDER, NORTH_BLOCKS, barrel_name, base_name, display_code, ask_text

# Vertical offset applied to the back sheet of each floor, in plan pixels.
# Each value keeps the block-to-block pitch measured on the front sheet
# (D wing -> E wing) between the last front wing and the first back wing.
BACK_DY = {1: 1215.0, 2: 1178.0, 3: 1060.0}

# Block I has no sheet of its own: it repeats the east half of Block H, one
# block further down the same corridor. Its rooms are drawn from Block H's
# geometry, moved down by the measured block-to-block pitch of that floor.

MARGIN = 110.0
# Extra room on the left so the big block letters get a gutter of their own.
MARGIN_LEFT = 250.0

# Room sizes in plan pixels. Half-extents along a row are derived from the gap
# to the neighbouring room and then clamped, so a lonely room cannot swell into
# the corridor and a tight row keeps its shared walls.
WING_DEPTH = {"upper": 88.0, "lower": 72.0}
WING_HALF = (11.0, 46.0)
CORRIDOR_ROOM_MIN_W = 26.0
CORRIDOR_HALF = (11.0, 27.0)
CORRIDOR_RUN_GAP = 60.0   # rooms further apart than this along the corridor get walls of their own
SPINE_HALF = 14.0
WEST_VOLUME_PAD = 38.0
# Two west wings closer than this are one wall on the plans, not two buildings
# with a strip of street between them: they meet at the lower wing's first room.
WEST_JOIN_GAP = 50.0
WEST_RECT = (40.0, 64.0, 30.0, 48.0)   # min w, max w, min h, max h

# Where a block's small west rooms sit in one narrow strip, they are the row of
# rooms built against the outer west wall, so they are drawn flush against it
# instead of floating: same left edge, height from the gap to the room above.
WALL_COLUMN_SPREAD = 100.0
WALL_COLUMN_W = 64.0
WALL_COLUMN_H = (24.0, 46.0)

# The traced circles are eased in a little and then shrunk further, if they
# need it, until nothing on the floor touches them.
BARREL_SCALE = 0.85
BARREL_MIN_R = 36.0
BARREL_CLEARANCE = 7.0

# The eight round lecture halls, known on campus as A1..D2. A circle traced
# from the sheet they are drawn on (centre x, centre y, radius, in that
# sheet's pixels) — their database coordinate is the label on the rim, not the
# middle of the hall, so it cannot be used as the centre.
BARRELS = {
    "D117": (252.0, 552.0, 80.0),    # A1
    "D116": (322.0, 700.0, 56.0),    # B1
    "D113": (248.0, 868.0, 78.0),    # C1
    "E117": (315.0, 1087.0, 56.0),   # D1
    "D218": (187.0, 641.0, 73.0),    # A2
    "D217": (258.0, 780.0, 57.0),    # B2
    "D214": (193.0, 930.0, 73.0),    # C2
    "E221": (260.0, 1131.0, 56.0),   # D2
    # One floor up the same four halls are study spaces. Fitted to the circles
    # on the floor-3 front sheet, whose labels sit in the middle of each hall.
    "STUDY-SPACE-1": (245.3, 551.1, 68.5),
    "STUDY-SPACE-2": (310.2, 683.0, 52.7),
    "STUDY-SPACE-3": (248.4, 829.0, 69.5),
    "STUDY-SPACE-4": (316.3, 1032.3, 53.1),
}

# The angled parts of Blocks G and H west of the corridor. Each is drawn in its
# own frame, so a row of rooms stays one straight, joined row: a frame is an
# origin and the angle of its first axis on the sheet, read off the walls.
FRAMES = {
    "G1": ((40.0, 600.0), 45.0),     # floor 1: G116-G114, the wing by the west exit
    "H1": ((78.0, 1119.0), -37.0),   # floor 1: H109-H111, round the rotunda
    "G2": ((20.0, 640.0), 42.0),     # floor 2: G219-G217
    "H2": ((49.6, 1085.2), -35.8),   # floor 2: H212-H214
}


def _fr(frame: str, a: float, b: float) -> tuple[float, float]:
    """A point given along (a) and across (b) a frame, in sheet pixels."""
    (ox, oy), deg = FRAMES[frame]
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (round(ox + a * c - b * s, 1), round(oy + a * s + b * c, 1))


def _box(frame: str, a0: float, a1: float, b0: float, b1: float, across: bool = False):
    """A room square to its frame. The first edge sets the label's direction:
    along the frame, or across it for rooms deeper than they are wide."""
    corners = [_fr(frame, a0, b0), _fr(frame, a1, b0), _fr(frame, a1, b1), _fr(frame, a0, b1)]
    return corners[3:] + corners[:3] if across else corners


# Rooms whose shape the row logic cannot guess — an irregular hall, a room
# squeezed between others, a block that does not hang off the corridor — are
# drawn from an outline traced on their sheet (in that sheet's pixels). Most were
# traced with a flood fill from the room's printed label out to its walls.
#
# Blocks A and B are not on the floor-1 front sheet: they were traced on
# plans/floor1_north.jpg, a wider print of the same floor, and carried over to
# front-sheet pixels with an affine fit on nine shared points (lobby corners,
# stairs, the round halls), worst residual 6 px. What each room is comes from
# the colour campus map (plans/floor1_colour.jpg): its icons and block colours.
OUTLINES = {
    # floor 1, Block A: Red Hall and the rooms behind its stage
    "RED-HALL": [(837, -16), (1079, -17), (1081, 295), (1020, 296), (1020, 337),
                 (882, 338), (882, 297), (839, 297)],
    # floor 1, Block B, north of the lobby. The Library is the reading hall plus
    # everything east of it up to the covered passage: the passage up its east
    # side and the exit at its end are the Library's own. Drawn square to the
    # foyer, like the rest of the block.
    "LIBRARY": [(470, -60), (659, -60), (659, -135), (744, -135), (744, 105), (470, 105)],
    "B114": [(400, 52), (466, 52), (466, 105), (400, 105)],
    "RESTROOM-B": [(624, 197), (673, 196), (673, 218), (624, 218)],
    "ADMINISTRATION": [(632, 244), (671, 244), (672, 288), (632, 289)],
    # floor 1, the lobby (Block C)
    "INFO-DESK": [(201, 166), (238, 201), (220, 219), (185, 185)],
    "WARDROBE": [(86, 286), (115, 257), (185, 325), (156, 355)],
    # floor 1, Block F west side (back sheet): the food court, laid out as the
    # colour map draws it and squared up on one grid — Doner House down the west
    # side, the Red Canteen seating and the Red Coffee bar beside it, the
    # dining hall (Cafeteria) across the full width below, then table tennis and
    # the shop beside it, which is Ay Market.
    "DONER-HOUSE": [(120, 40), (175, 40), (175, 188), (120, 188)],
    "RED-CANTEEN": [(175, 40), (327, 40), (327, 150), (175, 150)],
    "RED-COFFEE": [(175, 150), (327, 150), (327, 188), (175, 188)],
    "CAFETERIA": [(120, 188), (327, 188), (327, 381), (120, 381)],
    "TABLE-TENNIS": [(120, 395), (270, 395), (270, 465), (120, 465)],
    "AY-MARKET": [(280, 395), (327, 395), (327, 430), (280, 430)],
    # floor 1, Blocks G and H west side (back sheet): G116, G115 and G114 are one
    # angled row sharing its walls; G113 and G112 stand square below it; H110,
    # H111 and H109 are the corners of the rotated block round the rotunda.
    "G116": _box("G1", 80, 147, -90, 25, across=True),
    "G115": _box("G1", 147, 210, -90, 25, across=True),
    "G114": _box("G1", 210, 280, -90, 25, across=True),
    "G113": [(216, 860), (274, 860), (274, 980), (216, 980)],
    "G112": [(274, 860), (326, 860), (326, 980), (274, 980)],
    "H110": _box("H1", 0, 78, 0, 80),
    "H111": _box("H1", 112, 192, 0, 82),
    "H109": _box("H1", 0, 85, 108, 148),
    # floor 1, Block D: the Advising Desk on the corridor's west wall, across from D109
    "ADVISING-DESK": [(366, 772), (398, 772), (398, 818), (366, 818)],
    # floor 2, the same two blocks one floor up (back sheet)
    "G219": _box("G2", 60, 121, -95, 15, across=True),
    "G218": _box("G2", 121, 181, -95, 15, across=True),
    "G217": _box("G2", 181, 249, -95, 15, across=True),
    "G216": [(183, 853), (236, 853), (236, 962), (183, 962)],
    "G215": [(236, 853), (283, 853), (283, 962), (236, 962)],
    "H213": _box("H2", 0, 72, 0, 75),
    "H214": _box("H2", 101, 179, 0, 77),
    "H212": _box("H2", 0, 80, 100, 160),
    # floor 3, Block F west side (back sheet): the canteen's upper hall
    "RED-CANTEEN-3": [(110, 173), (346, 173), (346, 426), (110, 426)],
    # floor 3, Block G west side (back sheet): the slanted wing past the stairs
    "G322": [(183, 734), (219, 732), (222, 770), (188, 772)],
    "G321": [(188, 772), (222, 770), (224, 803), (192, 808)],
    "G320": [(184, 828), (235, 828), (235, 885), (184, 885)],
    "G319": [(184, 885), (235, 885), (235, 946), (184, 946)],
    "G318": [(246, 863), (288, 863), (288, 948), (246, 948)],
}
# Rooms the plans draw but nobody has named: the two rows south of the Block B
# foyer, which the colour map shows in Block B's colour next to its restroom and
# administration. Drawn plain, without a label or a route. Front-sheet pixels.
UNNAMED = {
    1: [
        ("S1_FRONT", [(540, 195), (581, 195), (581, 216), (540, 217)]),
        ("S1_FRONT", [(583, 195), (622, 195), (622, 217), (583, 218)]),
        ("S1_FRONT", [(675, 194), (716, 194), (716, 218), (675, 218)]),
        ("S1_FRONT", [(542, 244), (586, 243), (586, 288), (542, 288)]),
        ("S1_FRONT", [(588, 243), (628, 243), (629, 288), (588, 288)]),
        ("S1_FRONT", [(675, 244), (733, 244), (733, 288), (675, 288)]),
    ],
}
# The Block B foyer: the hall running east from the lobby to Red Hall, the
# space between the Library and Red Hall, and the covered passage running off
# north-east. Front-sheet pixels, traced like the Block B rooms above.
NORTH_WING = {
    1: [
        [(325, 111), (400, 105), (838, 105), (839, 297), (851, 297),
         (851, 346), (746, 349), (746, 297), (525, 304), (524, 185), (458, 268),
         (356, 196), (300, 132)],
        [(744, -16), (838, -16), (838, 105), (744, 105)],
        [(744, -25), (881, -133), (897, -117), (744, -3)],
    ],
}
# Blocks A and B sit side by side north of the lobby, so their letters cannot go
# in the left-hand gutter with the corridor's blocks: each gets a spot of its own
# beside its rooms (front-sheet pixels), and the Block buttons centre there.
NORTH_TAGS = {"A": (1190.0, 150.0), "B": (340.0, 0.0)}
# The outer walls of those blocks west of the corridor, so the building is the
# shape the plans draw (the angled wing, the rotated block) and not a rectangle
# round its rooms. (sheet, block) -> outline in that sheet's pixels.
WEST_OUTLINES = {
    ("S1_BACK", "G"): [(45, 470), (430, 470), (430, 980), (216, 980), (216, 860), _fr("G1", 280, 25),
                       _fr("G1", 0, 25), (45, 595)],
    ("S1_BACK", "H"): [_fr("H1", 0, 0), _fr("H1", 192, 0), (216, 980), (430, 980), (430, 1238),
                       _fr("H1", 0, 148)],
    ("S2_BACK", "G"): [(30, 535), (400, 535), (400, 975), (183, 975), (183, 853), _fr("G2", 249, 15),
                       _fr("G2", 0, 15), (30, 615)],
    ("S2_BACK", "H"): [_fr("H2", 0, 0), _fr("H2", 179, 0), (183, 975), (400, 975), (400, 1228),
                       _fr("H2", 0, 162)],
}
# Rooms whose name the plans print level even though the room is turned.
LEVEL_LABELS = {"H109", "H110", "H111", "H212", "H213", "H214"}
LABEL_CHAR_W = 8.5   # rough width of one label character at the plan's font size
# What a small room prints when its full name does not fit inside it.
SHORT_LABELS = {"Restroom": "WC", "Staff restroom": "Staff WC", "Administration": "Admin",
                "Information desk": "Info", "Ay Market": "Shop", "Table tennis": "Ping-pong"}
NARROW_ROOM = 38.0   # below this width a room's label is printed vertically

# The lobby/atrium at the top of the building has no rooms in the database, so
# its outline is traced from the sheets by hand, in front-sheet pixels.
ATRIUM = {
    1: [(78, 168), (262, 104), (300, 132), (356, 196), (458, 268),
        (458, 470), (300, 470), (150, 402), (78, 330)],
    2: [(60, 430), (128, 268), (318, 214), (400, 336), (400, 548), (150, 566)],
    3: [(92, 318), (300, 168), (452, 300), (452, 442), (196, 442)],
}
LOBBY_FEATURES = [
    {"kind": "wifi", "label": "Wi-Fi Zone", "cx": 300.0, "cy": 250.0, "r": 76.0},
]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def _row_direction(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares direction of a row of rooms, as a unit vector pointing east."""
    if len(points) < 2:
        return (1.0, 0.0)
    mx = sum(p[0] for p in points) / len(points)
    my = sum(p[1] for p in points) / len(points)
    sxx = sum((p[0] - mx) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    if sxx < 1e-6:
        return (1.0, 0.0)
    return _unit(1.0, sxy / sxx)


def _split_rows(rooms: list[dict]) -> list[list[dict]]:
    """Split a block's wing into its upper and lower row on the widest y gap."""
    if len(rooms) < 2:
        return [rooms]
    ys = sorted(r["_y"] for r in rooms)
    gaps = [(ys[i + 1] - ys[i], (ys[i + 1] + ys[i]) / 2) for i in range(len(ys) - 1)]
    gap, split = max(gaps)
    if gap < 25:
        return [rooms]
    upper = [r for r in rooms if r["_y"] < split]
    lower = [r for r in rooms if r["_y"] >= split]
    return [row for row in (upper, lower) if row]


def _strip(rooms: list[dict], u: tuple[float, float], depth: float,
           half_range: tuple[float, float]) -> dict:
    """Lay a row of rooms out as a strip of quads sharing their party walls."""
    ox = sum(r["_x"] for r in rooms) / len(rooms)
    oy = sum(r["_y"] for r in rooms) / len(rooms)
    n = (-u[1], u[0])
    ordered = sorted(rooms, key=lambda r: (r["_x"] - ox) * u[0] + (r["_y"] - oy) * u[1])
    along = [(r["_x"] - ox) * u[0] + (r["_y"] - oy) * u[1] for r in ordered]
    default = half_range[1] * 1.2
    quads = []
    for i, s in enumerate(along):
        back_gap = s - along[i - 1] if i > 0 else (along[1] - s if len(along) > 1 else default)
        fwd_gap = along[i + 1] - s if i < len(along) - 1 else (s - along[i - 1] if len(along) > 1 else default)
        left = s - _clamp(back_gap / 2, *half_range)
        right = s + _clamp(fwd_gap / 2, *half_range)
        corners = [(left, -depth / 2), (right, -depth / 2), (right, depth / 2), (left, depth / 2)]
        quads.append((ordered[i], [(ox + u[0] * t + n[0] * d, oy + u[1] * t + n[1] * d)
                                   for t, d in corners]))
    return {"quads": quads, "o": (ox, oy), "u": u, "n": n, "depth": depth,
            "s0": min(along), "s1": max(along)}


def _circle_outline(cx: float, cy: float, r: float, steps: int = 48) -> list[list[float]]:
    """A circle as a polygon, so it can join the building envelope."""
    return [[cx + r * math.cos(2 * math.pi * i / steps),
             cy + r * math.sin(2 * math.pi * i / steps)] for i in range(steps)]


def _rect(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def _strip_is_narrow(strip: dict) -> bool:
    """True when a row's rooms are too thin for a horizontal label."""
    widths = [math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) for _, q in strip["quads"]]
    return min(widths) < NARROW_ROOM


def _hull(strip: dict, pad: float = 0.0) -> list[list[float]]:
    """The outline of a finished strip, used to build the building envelope."""
    points = [point for _, quad in strip["quads"] for point in quad]
    (ox, oy), u, n = strip["o"], strip["u"], strip["n"]
    along = [(px - ox) * u[0] + (py - oy) * u[1] for px, py in points]
    perp = [(px - ox) * n[0] + (py - oy) * n[1] for px, py in points]
    box = [(min(along) - pad, min(perp)), (max(along) + pad, min(perp)),
           (max(along) + pad, max(perp)), (min(along) - pad, max(perp))]
    return [[ox + u[0] * a + n[0] * b, oy + u[1] * a + n[1] * b] for a, b in box]


def _fit_barrels(circles: dict[str, list[float]], rects) -> None:
    """Shrink halls until they clear every room and every other hall."""
    def cap(key: str, limit: float) -> None:
        circles[key][2] = max(BARREL_MIN_R, min(circles[key][2], limit))

    for key, (cx, cy, _) in list((k, tuple(v)) for k, v in circles.items()):
        for rx, ry, rw, rh in rects:
            dx = max(rx - rw / 2 - cx, 0.0, cx - (rx + rw / 2))
            dy = max(ry - rh / 2 - cy, 0.0, cy - (ry + rh / 2))
            cap(key, math.hypot(dx, dy) - BARREL_CLEARANCE)

    keys = list(circles)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ax, ay, ar = circles[a]
            bx, by, br = circles[b]
            room_for_both = math.hypot(bx - ax, by - ay) - BARREL_CLEARANCE
            if ar + br > room_for_both > 0:
                share = room_for_both / (ar + br)
                cap(a, ar * share)
                cap(b, br * share)


def _slab_extent(points, x0: float, x1: float) -> tuple[float, float] | None:
    """How far down and up a polygon reaches between two vertical lines."""
    ys: list[float] = []
    n = len(points)
    for i in range(n):
        (ax, ay), (bx, by) = points[i - 1], points[i]
        if x0 <= ax <= x1:
            ys.append(ay)
        for x in (x0, x1):
            if (ax - x) * (bx - x) < 0:
                ys.append(ay + (by - ay) * (x - ax) / (bx - ax))
    return (min(ys), max(ys)) if ys else None


def _fit_corridor_runs(shapes: list[dict], areas: list[dict]) -> None:
    """A run of rooms along the corridor wall stops where the rooms of the next
    wing begin: the run keeps its order and proportions and is squeezed between
    the rooms above and below it, so no room is drawn under another. The run's
    piece of the building outline is cut to the same size."""
    runs: dict[tuple, list[dict]] = {}
    for shape in shapes:
        key = shape.pop("_run", None)
        if key is not None:
            runs.setdefault(key, []).append(shape)
    for members in runs.values():
        x0 = min(p[0] for m in members for p in m["points"])
        x1 = max(p[0] for m in members for p in m["points"])
        lo = min(p[1] for m in members for p in m["points"])
        hi = max(p[1] for m in members for p in m["points"])
        top, bottom, east, ends = lo, hi, x1, x1
        for other in shapes:
            if other in members or not other.get("points"):
                continue
            extent = _slab_extent(other["points"], x0, x1)
            if not extent or extent[1] <= lo + 1 or extent[0] >= hi - 1:
                continue
            middle = (extent[0] + extent[1]) / 2
            if lo < middle < hi:
                # a room beside the run, not above or below it: the run's
                # east wall stops at that room's west wall
                east = min(east, min(p[0] for p in other["points"]))
            else:
                ends = min(ends, min(p[0] for p in other["points"]))
                if middle < (lo + hi) / 2:
                    top = max(top, extent[1])
                else:
                    bottom = min(bottom, extent[0])
        if bottom - top < CORRIDOR_HALF[0] * 2 * len(members):
            # no room to squeeze the run in: it keeps its height and stops at
            # the wing's west wall instead
            top, bottom, east = lo, hi, ends
        scale = (bottom - top) / (hi - lo)
        for m in members:
            m["points"] = [[min(px, east), round(top + (py - lo) * scale, 1)]
                           for px, py in m["points"]]
            m["x"] = round(sum(px for px, _ in m["points"]) / 4, 1)
            m["y"] = round(top + (m["y"] - lo) * scale, 1)
    for area in areas:
        members = runs.get(area.pop("_run", None))
        if members:
            xs = [p[0] for m in members for p in m["points"]]
            ys = [p[1] for m in members for p in m["points"]]
            area["points"] = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]


def _west_box(circles, rects, spine_x: float, flush_left: bool) -> list[float]:
    """The west wing's outline: everything drawn in it, and the corridor to its east."""
    xs: list[float] = []
    ys: list[float] = []
    for cx, cy, r in circles:
        xs += [cx - r, cx + r]
        ys += [cy - r, cy + r]
    for cx, cy, w, h in rects:
        xs += [cx - w / 2, cx + w / 2]
        ys += [cy - h / 2, cy + h / 2]
    # a wall column IS the west wall, so it is not padded away from it
    left = min(xs) - (0.0 if flush_left else 18.0)
    return [left, min(ys) - WEST_VOLUME_PAD,
            max(max(xs) + WEST_VOLUME_PAD, spine_x), max(ys) + WEST_VOLUME_PAD]


def _bounds(points) -> tuple[float, float, float, float]:
    """A traced outline as (centre x, centre y, width, height)."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys))


def _nearest_gap(room: dict, peers: list[dict]) -> float:
    best = 1e9
    for other in peers:
        if other is room:
            continue
        best = min(best, math.hypot(other["_x"] - room["_x"], other["_y"] - room["_y"]))
    return 140.0 if best > 1e8 else best


class CampusMap:
    """All three floors as vector geometry, built once at start-up."""

    def __init__(self, index) -> None:
        self._index = index
        self._placement: dict[str, tuple[float, float]] = {}
        self._points: dict[str, dict] = {}
        self.floors: dict[int, dict] = {}
        self._build()

    # ------------------------------------------------------------- transform
    def to_map(self, sheet_id: str | None, x: float, y: float) -> tuple[float, float] | None:
        """Sheet pixel -> vector map pixel, or None for a sheet we cannot place."""
        place = self._placement.get(sheet_id or "")
        if place is None:
            return None
        return (x + place[0], y + place[1])

    def room_point(self, room_number: str) -> dict | None:
        """Where a room ended up on the drawing: its centre and, for a hall, its radius."""
        return self._points.get(room_number)

    def floor_list(self) -> list[dict]:
        return [self.floors[f] for f in sorted(self.floors)]

    # ----------------------------------------------------------------- build
    def _build(self) -> None:
        sheets = self._index.sheets
        for floor in sorted({s["floor_number"] for s in sheets.values()}):
            front = next(s for s in sheets.values()
                         if s["floor_number"] == floor and s["section"] == "front")
            back = next(s for s in sheets.values()
                        if s["floor_number"] == floor and s["section"] == "back")
            annex = next((s for s in sheets.values()
                          if s["floor_number"] == floor and s["section"] == "I_approx_from_H"), None)
            front_mid = (front["west_max_x"] + front["wing_min_x"]) / 2
            back_mid = (back["west_max_x"] + back["wing_min_x"]) / 2
            dx = front_mid - back_mid
            self._placement[front["sheet_id"]] = (0.0, 0.0)
            self._placement[back["sheet_id"]] = (dx, BACK_DY[floor])
            if annex:
                self._placement[annex["sheet_id"]] = (
                    dx, BACK_DY[floor] + self._block_pitch(floor, back["sheet_id"]))
            self.floors[floor] = self._build_floor(floor, front["west_max_x"] + 10.0)

    def _block_pitch(self, floor: int, sheet_id: str) -> float:
        """How far apart two neighbouring blocks sit on a sheet, measured G to H."""
        tops: dict[str, float] = {}
        for room in self._index.rooms:
            if room["floor_number"] == floor and room["sheet_id"] == sheet_id and room["zone"] == "wing":
                bid = room["building_id"]
                tops[bid] = min(tops.get(bid, room["y"]), room["y"])
        if "G" in tops and "H" in tops:
            return tops["H"] - tops["G"]
        return 400.0

    def _floor_rooms(self, floor: int) -> list[dict]:
        out = []
        for room in self._index.rooms:
            if room["floor_number"] != floor:
                continue
            placed = self.to_map(room["sheet_id"], room["x"], room["y"])
            if placed is None:
                continue
            out.append({**room, "_x": placed[0], "_y": placed[1]})
        return out

    def _build_floor(self, floor: int, spine_x: float) -> dict:
        rooms = self._floor_rooms(floor)
        shapes: list[dict] = []
        circulation: list[dict] = []
        volumes: list[dict] = []
        areas: list[dict] = []
        blocks: list[dict] = []
        west_boxes: list[dict] = []

        for block_id in BLOCK_ORDER:
            in_block = [r for r in rooms if r["building_id"] == block_id]
            if not in_block:
                continue
            base_x = spine_x
            rows = self._block_shapes(in_block, base_x, shapes)
            circulation.extend(self._block_circulation(rows, base_x))
            for row in rows:
                if row["kind"] == "west" and "points" in row:
                    volumes.append({"points": row["points"]})
                elif row["kind"] == "west":
                    volumes.append({"box": list(row["box"]), "top": row.get("top")})
                    west_boxes.append(volumes[-1])
                elif row["kind"] == "barrel":
                    areas.append({"points": row["outline"]})
                else:
                    areas.append({"points": row["hull"], "_run": row.get("run")})
            ys = [r["_y"] for r in in_block]
            blocks.append({
                "id": block_id,
                "name": self._index.buildings.get(block_id, f"Block {block_id}"),
                "x": base_x, "y0": min(ys) - 70, "y1": max(ys) + 70,
                "annex": block_id == "I",
                "north": block_id in NORTH_BLOCKS,
            })
            if block_id in NORTH_TAGS:
                tag = self.to_map(in_block[0]["sheet_id"], *NORTH_TAGS[block_id])
                blocks[-1].update({"tag_x": tag[0], "tag_y": tag[1]})

        # close the strip between two west wings that stand wall to wall (Block E's
        # round hall D1 and the food court under it): both walls move to the top
        # of the lower wing's first room
        west_boxes.sort(key=lambda v: v["box"][1])
        for upper, lower in zip(west_boxes, west_boxes[1:]):
            gap = lower["box"][1] - upper["box"][3]
            if 0 < gap <= WEST_JOIN_GAP and lower["top"] is not None:
                upper["box"][3] = lower["box"][1] = lower["top"]
        # a wing set back between two wings that both reach further west leaves
        # a notch in the outer wall (Block E between Blocks D and F): the wall
        # runs straight on instead, as far west as the shallower neighbour
        for above, wing, below in zip(west_boxes, west_boxes[1:], west_boxes[2:]):
            joined = (wing["box"][1] - above["box"][3] <= WEST_JOIN_GAP
                      and below["box"][1] - wing["box"][3] <= WEST_JOIN_GAP)
            if joined and above["box"][0] < wing["box"][0] and below["box"][0] < wing["box"][0]:
                wing["box"][0] = max(above["box"][0], below["box"][0])
        for volume in volumes:
            if "box" in volume:
                x0, y0, x1, y1 = volume.pop("box")
                volume.pop("top", None)
                volume["points"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

        _fit_corridor_runs(shapes, areas)

        landmarks = []
        for floor_id, items in self._index.landmarks.items():
            if self._index.floors[floor_id]["floor_number"] != floor:
                continue
            sheet_id = self._index.floors[floor_id]["sheet_id"]
            for lm in items:
                placed = self.to_map(sheet_id, lm["x"], lm["y"])
                if placed:
                    landmarks.append({"name": lm["name"], "type": lm["type"],
                                      "x": placed[0], "y": placed[1]})

        features = [{"kind": "atrium", "points": [list(p) for p in ATRIUM[floor]],
                     "label": "Main lobby" if floor == 1 else "Atrium — open to the lobby below"}]
        if floor == 1:
            for item in LOBBY_FEATURES:
                feature = dict(item)
                if "points" in feature:
                    feature["points"] = [list(p) for p in feature["points"]]
                features.append(feature)
        for outline in NORTH_WING.get(floor, []):
            features.append({"kind": "foyer", "points": [list(p) for p in outline], "label": ""})

        fixtures = []
        for sheet_id, outline in UNNAMED.get(floor, []):
            moved = [self.to_map(sheet_id, x, y) for x, y in outline]
            fixtures.append({"points": [list(p) for p in moved]})

        # Block B is reached through the lobby, not along the central corridor.
        along = [b for b in blocks if not b["north"]]
        spines = [{"x": spine_x, "y0": min(b["y0"] for b in along) - 40,
                   "y1": max(b["y1"] for b in along) + 40}]

        # The lobby and the foyer are part of the building, so they join the envelope too.
        areas.append({"points": [list(pt) for pt in ATRIUM[floor]]})
        areas.extend({"points": [list(pt) for pt in outline]} for outline in NORTH_WING.get(floor, []))
        for spine in spines:
            areas.append({"points": [[spine["x"] - SPINE_HALF, spine["y0"]],
                                     [spine["x"] + SPINE_HALF, spine["y0"]],
                                     [spine["x"] + SPINE_HALF, spine["y1"]],
                                     [spine["x"] - SPINE_HALF, spine["y1"]]]})
        areas.extend({"points": list(a["points"])} for a in circulation + volumes + fixtures)

        return self._normalise({
            "floor": floor, "rooms": shapes, "fixtures": fixtures,
            "circulation": circulation, "volumes": volumes,
            "areas": areas,
            "blocks": blocks, "spines": spines, "landmarks": landmarks, "features": features,
        }, floor)

    # ----------------------------------------------------------- block parts
    def _block_shapes(self, rooms: list[dict], spine_x: float, out: list[dict]) -> list[dict]:
        rows: list[dict] = []

        traced: dict[str, list[tuple[float, float]]] = {}
        for room in rooms:
            outline = OUTLINES.get(room["room_number"])
            if outline is None and room["zone"] == "north":
                # nothing traced yet: a plain box where the plan prints its name
                outline = _rect(room["x"], room["y"], 60.0, 40.0)
            if outline is None:
                continue
            # the traced outline, moved by the same offset as the room itself
            points = [(x + room["_x"] - room["x"], y + room["_y"] - room["y"]) for x, y in outline]
            traced[room["room_id"]] = points
            out.append(self._shape(room, points, rotate=self._label_turns(room, points)))
            if room["zone"] != "west":
                rows.append({"kind": "traced", "hull": [list(p) for p in points]})

        wing = [r for r in rooms if r["zone"] == "wing" and r["room_id"] not in traced]
        wing_rows = [row for row in _split_rows(wing) if row]
        top_y = min((r["_y"] for r in wing), default=0.0)
        for row in wing_rows:
            kind = "upper" if min(r["_y"] for r in row) == top_y else "lower"
            u = _row_direction([(r["_x"], r["_y"]) for r in row])
            strip = _strip(row, u, WING_DEPTH[kind], WING_HALF)
            narrow = _strip_is_narrow(strip)
            for room, points in strip["quads"]:
                out.append(self._shape(room, points, rotate=narrow))
            rows.append({"kind": kind, "hull": _hull(strip), **strip})

        corridor = sorted([r for r in rooms if r["zone"] == "corridor" and r["room_id"] not in traced],
                          key=lambda r: r["_y"])
        if corridor:
            # These rooms open straight onto the central corridor, so they fill
            # the band the sheet leaves between the corridor wall and the wings.
            geo = self._index.sheets[corridor[0]["geo_sheet_id"]]
            width = max(geo["wing_min_x"] - geo["west_max_x"] - 10 - SPINE_HALF - 5,
                        CORRIDOR_ROOM_MIN_W)
            strip = _strip(corridor, (0.0, 1.0), width, CORRIDOR_HALF)
            narrow = width < NARROW_ROOM
            cx = spine_x + SPINE_HALF + width / 2 + 3
            runs: list[list[float]] = []
            for room, points in strip["quads"]:
                lo, hi = min(p[1] for p in points), max(p[1] for p in points)
                out.append(self._shape(room, _rect(cx, (lo + hi) / 2, width, hi - lo),
                                       rotate=narrow, center=(cx, (lo + hi) / 2)))
                # rooms far apart along the corridor (a restroom at one wing mouth,
                # E110 a block further on) are separate pieces of wall, not one long box
                if runs and lo - runs[-1][1] <= CORRIDOR_RUN_GAP:
                    runs[-1][1] = max(runs[-1][1], hi)
                else:
                    runs.append([lo, hi])
                out[-1]["_run"] = (room["building_id"], len(runs))
            for n, (top, bottom) in enumerate(runs, 1):
                rows.append({"kind": "corridor", "run": (corridor[0]["building_id"], n), "hull": [
                    [cx - width / 2, top], [cx + width / 2, top],
                    [cx + width / 2, bottom], [cx - width / 2, bottom]]})

        west = [r for r in rooms if r["zone"] == "west"]
        if not west:
            return rows
        circles: dict[str, list[float]] = {}
        for room in west:
            barrel = BARRELS.get(room["room_number"])
            if barrel:
                # the traced circle, moved by the same offset as the room itself
                circles[room["room_id"]] = [barrel[0] + room["_x"] - room["x"],
                                            barrel[1] + room["_y"] - room["y"],
                                            barrel[2] * BARREL_SCALE]

        plain = [r for r in west if r["room_id"] not in circles and r["room_id"] not in traced]
        wall_x = None
        if plain and max(r["_x"] for r in plain) - min(r["_x"] for r in plain) < WALL_COLUMN_SPREAD:
            wall_x = min(r["_x"] for r in plain)

        rects: dict[str, tuple[float, float, float, float]] = {}
        for room in plain:
            if wall_x is not None:
                gaps = [abs(other["_y"] - room["_y"]) for other in plain if other is not room]
                height = _clamp(min(gaps) * 0.9, *WALL_COLUMN_H) if gaps else WALL_COLUMN_H[1]
                rects[room["room_id"]] = (wall_x, room["_y"], WALL_COLUMN_W, height)
            else:
                gap = _nearest_gap(room, plain)
                rects[room["room_id"]] = (room["_x"], room["_y"],
                                          _clamp(gap * 0.95, WEST_RECT[0], WEST_RECT[1]),
                                          _clamp(gap * 0.72, WEST_RECT[2], WEST_RECT[3]))

        # traced rooms take up room on that side too: halls give way to them, and
        # the west wing's outline has to take them in
        boxes = list(rects.values()) + [_bounds(traced[r["room_id"]]) for r in west
                                        if r["room_id"] in traced]
        _fit_barrels(circles, boxes)

        for room in west:
            if room["room_id"] in traced:
                continue
            circle = circles.get(room["room_id"])
            if circle:
                out.append(self._shape(room, None, circle=tuple(circle)))
                rows.append({"kind": "barrel", "outline": _circle_outline(*circle)})
            else:
                cx, cy, w, h = rects[room["room_id"]]
                out.append(self._shape(room, _rect(cx, cy, w, h), center=(cx, cy)))

        outline = WEST_OUTLINES.get((west[0]["sheet_id"], west[0]["building_id"]))
        if outline:
            moved = [self.to_map(west[0]["sheet_id"], x, y) for x, y in outline]
            rows.append({"kind": "west", "points": [list(p) for p in moved]})
            return rows
        if len(west) == 1 and not circles and west[0]["room_id"] in traced:
            # one hall on its own (the 3rd-floor Red Canteen): its walls are the
            # wing's walls, straight across to the corridor, with no margin round it
            cx, cy, w, h = boxes[0]
            rows.append({"kind": "west", "box": [cx - w / 2, cy - h / 2, spine_x, cy + h / 2]})
            return rows
        rows.append({"kind": "west", "box": _west_box(circles.values(), boxes,
                                                      spine_x, wall_x is not None),
                     # where its first room begins, for joining it to the wing above
                     "top": min([cy - r for _, cy, r in circles.values()]
                                + [cy - h / 2 for _, cy, _, h in boxes])})
        return rows

    def _service_label(self, room: dict) -> str | None:
        """The office a numbered room holds, in a few words ("Student Center"), so
        the plan says what is behind the door. Named rooms already say it."""
        svc = self._index.service_of(room)
        if not svc or display_code(room) != room["room_number"]:
            return None
        return svc.get("short_name") or svc["name"]

    @staticmethod
    def _label_turns(room: dict, points) -> bool:
        """Turn the label upright when the room is taller than wide and the
        name does not fit across it — "Cafeteria" and "Doner House" on the sheet."""
        _, _, w, h = _bounds(points)
        label = base_name(display_code(room))
        if label in SHORT_LABELS and len(label) * LABEL_CHAR_W > max(w, h) - 6:
            label = SHORT_LABELS[label]
        return h > w and len(label) * LABEL_CHAR_W > w

    def _block_circulation(self, rows: list[dict], spine_x: float) -> list[dict]:
        """The wing corridor: the gap the two rows of a block leave between them."""
        upper = next((r for r in rows if r["kind"] == "upper"), None)
        lower = next((r for r in rows if r["kind"] == "lower"), None)
        if not upper or not lower:
            return []

        def point(row, s, side):
            ox, oy = row["o"]
            return [ox + row["u"][0] * s + row["n"][0] * side * row["depth"] / 2,
                    oy + row["u"][1] * s + row["n"][1] * side * row["depth"] / 2]

        def at_spine(row):
            return (spine_x - row["o"][0]) / (row["u"][0] or 1.0)

        east = max(upper["s1"], lower["s1"])
        return [{"points": [point(upper, at_spine(upper), 1), point(upper, east, 1),
                            point(lower, east, -1), point(lower, at_spine(lower), -1)]}]

    def _shape(self, room: dict, points, circle=None, rotate: bool | None = None,
               center: tuple[float, float] | None = None) -> dict:
        label = "Medcenter" if room["room_number"].startswith("MEDCENTER") else display_code(room)
        # "Red Canteen (3rd floor)": the name on the room, the floor on a line under it
        sub = label[len(base_name(label)):].strip(" ()") or None
        label = base_name(label)
        if points and label in SHORT_LABELS:
            _, _, w, h = _bounds(points)
            if len(label) * LABEL_CHAR_W > max(w, h) - 6:
                label = SHORT_LABELS[label]
        shape = {
            "code": room["room_number"], "label": label, "sub": sub, "ask": ask_text(room),
            "service": self._service_label(room),
            "block": room["building_id"],
            "barrel": barrel_name(room),
            "type": room["type"], "department": room["department"],
            "approx": room["source"] == "approximated_from_H",
            "x": center[0] if center else room["_x"],
            "y": center[1] if center else room["_y"],
        }
        if center is None and points and len(points) == 4:
            # a room drawn as one quad carries its name in the middle, not at the
            # spot the sheet happens to print it
            shape["x"] = sum(px for px, _ in points) / 4
            shape["y"] = sum(py for _, py in points) / 4
        if circle:
            # a hall's database coordinate is the label on its rim, so anything
            # that points at the room points at the middle of the circle
            shape.update({"kind": "circle", "cx": circle[0], "cy": circle[1], "r": circle[2],
                          "x": circle[0], "y": circle[1]})
        else:
            # Labels follow the wall they belong to, and narrow rooms get the
            # vertical label the printed plans use for the same rooms.
            (x0, y0), (x1, y1) = points[0], points[1]
            angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
            turn = rotate if rotate is not None else math.hypot(x1 - x0, y1 - y0) < NARROW_ROOM
            if turn:
                angle += 90
            if room["room_number"] in LEVEL_LABELS:
                angle = 0.0
            shape.update({"kind": "rect", "angle": round(angle, 1),
                          "points": [[round(px, 1), round(py, 1)] for px, py in points]})
        return shape

    # ------------------------------------------------------------- normalise
    def _normalise(self, plan: dict, floor: int) -> dict:
        xs: list[float] = []
        ys: list[float] = []
        for shape in plan["rooms"]:
            if shape["kind"] == "circle":
                xs += [shape["cx"] - shape["r"], shape["cx"] + shape["r"]]
                ys += [shape["cy"] - shape["r"], shape["cy"] + shape["r"]]
            else:
                xs += [p[0] for p in shape["points"]]
                ys += [p[1] for p in shape["points"]]
        for fixture in plan["fixtures"]:
            xs += [p[0] for p in fixture["points"]]
            ys += [p[1] for p in fixture["points"]]
        for feature in plan["features"]:
            if "points" in feature:
                xs += [p[0] for p in feature["points"]]
                ys += [p[1] for p in feature["points"]]
            else:
                xs += [feature["cx"] - feature["r"], feature["cx"] + feature["r"]]
                ys += [feature["cy"] - feature["r"], feature["cy"] + feature["r"]]
        dx = MARGIN_LEFT - min(xs)
        dy = MARGIN - min(ys)

        for sheet_id, (sx, sy) in list(self._placement.items()):
            if self._index.sheets[sheet_id]["floor_number"] == floor:
                self._placement[sheet_id] = (sx + dx, sy + dy)

        def move_points(points):
            return [[round(p[0] + dx, 1), round(p[1] + dy, 1)] for p in points]

        for shape in plan["rooms"]:
            shape["x"] = round(shape["x"] + dx, 1)
            shape["y"] = round(shape["y"] + dy, 1)
            if shape["kind"] == "circle":
                shape["cx"] = round(shape["cx"] + dx, 1)
                shape["cy"] = round(shape["cy"] + dy, 1)
                shape["r"] = round(shape["r"], 1)
            else:
                shape["points"] = move_points(shape["points"])
        for area in plan["circulation"] + plan["volumes"] + plan["areas"] + plan["fixtures"]:
            area["points"] = move_points(area["points"])
        for feature in plan["features"]:
            if "points" in feature:
                feature["points"] = move_points(feature["points"])
            else:
                feature["cx"] = round(feature["cx"] + dx, 1)
                feature["cy"] = round(feature["cy"] + dy, 1)
        for lm in plan["landmarks"]:
            lm["x"] = round(lm["x"] + dx, 1)
            lm["y"] = round(lm["y"] + dy, 1)
        for block in plan["blocks"]:
            block["x"] = round(block["x"] + dx, 1)
            block["y0"] = round(block["y0"] + dy, 1)
            block["y1"] = round(block["y1"] + dy, 1)
            if "tag_y" in block:
                block["tag_x"] = round(block["tag_x"] + dx, 1)
                block["tag_y"] = round(block["tag_y"] + dy, 1)
                xs_in = [r["x"] for r in plan["rooms"] if r["block"] == block["id"]]
                block["focus_x"] = round(sum(xs_in) / len(xs_in), 1)
            else:
                block["tag_x"] = 118.0
                block["tag_y"] = round((block["y0"] + block["y1"]) / 2, 1)
                block["focus_x"] = round(block["x"] + 250, 1)
        for spine in plan["spines"]:
            spine["x"] = round(spine["x"] + dx, 1)
            spine["y0"] = round(spine["y0"] + dy, 1)
            spine["y1"] = round(spine["y1"] + dy, 1)

        for shape in plan["rooms"]:
            self._points[shape["code"]] = {"floor": floor, "x": shape["x"], "y": shape["y"],
                                           "r": shape.get("r")}

        plan["width"] = round(max(xs) + dx + MARGIN, 1)
        plan["height"] = round(max(ys) + dy + MARGIN, 1)
        plan["spine_half"] = SPINE_HALF
        return plan
