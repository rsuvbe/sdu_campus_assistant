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

from .engine import barrel_name

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
SPINE_HALF = 14.0
WEST_VOLUME_PAD = 38.0
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
}
NARROW_ROOM = 38.0   # below this width a room's label is printed vertically

BLOCK_ORDER = "CDEFGHI"

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
    {"kind": "wardrobe", "label": "Wardrobe",
     "points": [(84, 262), (156, 228), (180, 296), (108, 330)]},
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

        for block_id in BLOCK_ORDER:
            in_block = [r for r in rooms if r["building_id"] == block_id]
            if not in_block:
                continue
            base_x = spine_x
            rows = self._block_shapes(in_block, base_x, shapes)
            circulation.extend(self._block_circulation(rows, base_x))
            for row in rows:
                if row["kind"] == "west":
                    x0, y0, x1, y1 = row["box"]
                    volumes.append({"points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]})
                elif row["kind"] == "barrel":
                    areas.append({"points": row["outline"]})
                else:
                    areas.append({"points": row["hull"]})
            ys = [r["_y"] for r in in_block]
            blocks.append({
                "id": block_id,
                "name": self._index.buildings.get(block_id, f"Block {block_id}"),
                "x": base_x, "y0": min(ys) - 70, "y1": max(ys) + 70,
                "annex": block_id == "I",
            })

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

        spines = [{"x": spine_x, "y0": min(b["y0"] for b in blocks) - 40,
                   "y1": max(b["y1"] for b in blocks) + 40}]

        # The lobby is part of the building, so it joins the envelope too.
        areas.append({"points": [list(pt) for pt in ATRIUM[floor]]})
        for spine in spines:
            areas.append({"points": [[spine["x"] - SPINE_HALF, spine["y0"]],
                                     [spine["x"] + SPINE_HALF, spine["y0"]],
                                     [spine["x"] + SPINE_HALF, spine["y1"]],
                                     [spine["x"] - SPINE_HALF, spine["y1"]]]})
        areas.extend({"points": list(a["points"])} for a in circulation + volumes)

        return self._normalise({
            "floor": floor, "rooms": shapes, "circulation": circulation, "volumes": volumes,
            "areas": areas,
            "blocks": blocks, "spines": spines, "landmarks": landmarks, "features": features,
        }, floor)

    # ----------------------------------------------------------- block parts
    def _block_shapes(self, rooms: list[dict], spine_x: float, out: list[dict]) -> list[dict]:
        rows: list[dict] = []

        wing = [r for r in rooms if r["zone"] == "wing"]
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

        corridor = sorted([r for r in rooms if r["zone"] == "corridor"], key=lambda r: r["_y"])
        if corridor:
            # These rooms open straight onto the central corridor, so they fill
            # the band the sheet leaves between the corridor wall and the wings.
            geo = self._index.sheets[corridor[0]["geo_sheet_id"]]
            width = max(geo["wing_min_x"] - geo["west_max_x"] - 10 - SPINE_HALF - 5,
                        CORRIDOR_ROOM_MIN_W)
            strip = _strip(corridor, (0.0, 1.0), width, CORRIDOR_HALF)
            narrow = width < NARROW_ROOM
            cx = spine_x + SPINE_HALF + width / 2 + 3
            top = bottom = None
            for room, points in strip["quads"]:
                lo, hi = min(p[1] for p in points), max(p[1] for p in points)
                top = lo if top is None else min(top, lo)
                bottom = hi if bottom is None else max(bottom, hi)
                out.append(self._shape(room, _rect(cx, (lo + hi) / 2, width, hi - lo),
                                       rotate=narrow))
            rows.append({"kind": "corridor", "hull": [
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

        plain = [r for r in west if r["room_id"] not in circles]
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

        _fit_barrels(circles, rects.values())

        for room in west:
            circle = circles.get(room["room_id"])
            if circle:
                out.append(self._shape(room, None, circle=tuple(circle)))
                rows.append({"kind": "barrel", "outline": _circle_outline(*circle)})
            else:
                cx, cy, w, h = rects[room["room_id"]]
                out.append(self._shape(room, _rect(cx, cy, w, h), center=(cx, cy)))

        rows.append({"kind": "west", "box": _west_box(circles.values(), rects.values(),
                                                      spine_x, wall_x is not None)})
        return rows

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
        label = "Medcenter" if room["room_number"].startswith("MEDCENTER") else room["room_number"]
        shape = {
            "code": room["room_number"], "label": label, "block": room["building_id"],
            "barrel": barrel_name(room),
            "type": room["type"], "department": room["department"],
            "approx": room["source"] == "approximated_from_H",
            "x": center[0] if center else room["_x"],
            "y": center[1] if center else room["_y"],
        }
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
        for area in plan["circulation"] + plan["volumes"] + plan["areas"]:
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
            block["tag_x"] = 118.0
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
