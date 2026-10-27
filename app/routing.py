"""
Walking routes through the building (US13 text directions between two rooms,
US14 directions from the main entrance).

A route runs on a corridor graph built from the same geometry the floor plans
are drawn from (app/floorplan.py), so it can only go where the plan has floor:

  * the central corridor of each floor is a chain of points down its centre;
  * every classroom wing is a chain down the middle of its wing corridor, from
    the central corridor to the far end of the wing;
  * a room opens onto the corridor it faces: a wing room onto its wing, a room
    along the central corridor onto that corridor;
  * the west side of the corridor (the round halls, the food court), the lobby,
    the Block B foyer and the exits are open floor. Each place there is joined
    to the central corridor by the shortest walk that goes round every room on
    the way: a visibility graph over the rooms' corners, checked against the
    building's outline, so no step passes through a room or leaves the building;
  * floors are joined only by staircases drawn on the evacuation sheets: the
    main lobby staircase (floors 1-2) and the stairwells at the far end of the
    Block D to H wings (floors 1-3).

The graph is built once at start-up. Routing is Dijkstra over it; a route is
then turned into steps that name corridors, blocks, turns, sides and stairs.
There is no live position and no re-routing while walking (US13, US14).
"""
from __future__ import annotations

import heapq
import math

from .engine import APPROXIMATE_SOURCES, NORTH_BLOCKS, NORTH_FOYER_Y, human_list, ordinal, spoken

MAIN_ENTRANCE = "EXIT_F1_MAIN"
# One flight of stairs, as a length of corridor (plan pixels). Most of a flight's
# cost is the climb, so a stairwell only wins when it saves real walking.
STAIR_COST = 160.0
CLEAR = 9.0             # how far an open-floor path keeps from a room's corner
SAMPLE = 9.0            # spacing of the indoor checks along a step
OPEN_REACH = 560.0      # longest single straight step across open floor
WING_REACH = 160.0      # an exit or stairwell this close to a wing's far end belongs to it
SHORT_LEG = 30.0        # a stretch of corridor shorter than this is just crossed
OPPOSITE_REACH = 45.0   # a door this close along the wing is "directly across"
SPIKE = 12.0            # a turn back sharper than 135 degrees this short is not drawn


# ------------------------------------------------------------------ geometry
def _inside(x: float, y: float, poly) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _orient(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _crosses(p1, p2, q1, q2) -> bool:
    """Whether two segments cross at a point inside both (touching does not count)."""
    return (_orient(q1, q2, p1) * _orient(q1, q2, p2) < 0
            and _orient(p1, p2, q1) * _orient(p1, p2, q2) < 0)


def _seg_dist(a, b, p) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1])


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def _dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _line(points: list) -> list:
    """A route as it is drawn: no point twice, no walking out to a point and
    back (past a stairwell to the wing's end and back to it), and no bend in the
    middle of a straight run, so the line turns only where the walk does."""
    out: list = []
    for p in points:
        if out and _dist(out[-1], p) < 0.5:
            continue
        out.append(p)
        while len(out) >= 3:
            a, b, c = out[-3:]
            if _dist(a, c) < 0.5:
                del out[-2:]                       # out and back to the same spot
                continue
            off = abs(_orient(a, c, b)) / _dist(a, c)
            ab, bc = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
            hook = (min(_dist(a, b), _dist(b, c)) < SPIKE
                    and ab[0] * bc[0] + ab[1] * bc[1] < -0.7 * _dist(a, b) * _dist(b, c))
            if off > 1.2 and not hook:
                break
            del out[-2]                            # b is on the straight line from a to c, or a hook
    return out


def _turn(h1, h2) -> str:
    """left / right / straight / back, for a walker heading h1 who turns to h2.
    Plan coordinates have y pointing down, so a positive cross product is a
    clockwise turn on the plan: a right turn."""
    angle = math.degrees(math.atan2(h1[0] * h2[1] - h1[1] * h2[0], h1[0] * h2[0] + h1[1] * h2[1]))
    if abs(angle) < 35:
        return "straight"
    if abs(angle) > 150:
        return "back"
    return "right" if angle > 0 else "left"


def _side(heading, frm, to) -> str:
    """Which hand a point is on for someone walking `heading` at `frm`."""
    return "right" if heading[0] * (to[1] - frm[1]) - heading[1] * (to[0] - frm[0]) > 0 else "left"


class _Shape:
    """A room as an obstacle. Shrunk by a hair, so a path that runs along a
    shared wall, or a door that sits on the wall, does not count as crossing it."""

    def __init__(self, code: str | None, points=None, circle=None) -> None:
        self.code = code
        self.circle = circle
        if circle:
            cx, cy, r = circle
            self.box = (cx - r, cy - r, cx + r, cy + r)
            self.poly = None
            return
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        self.raw = [tuple(p) for p in points]
        shrunk = []
        for x, y in points:
            ux, uy = _unit(cx - x, cy - y)
            shrunk.append((x + ux * 1.5, y + uy * 1.5))
        self.poly = shrunk
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.box = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, p) -> bool:
        if self.circle:
            cx, cy, r = self.circle
            return math.hypot(p[0] - cx, p[1] - cy) < r - 1.5
        x0, y0, x1, y1 = self.box
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and _inside(p[0], p[1], self.poly)

    def blocks(self, a, b) -> bool:
        x0, y0, x1, y1 = self.box
        if (max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1
                or max(a[1], b[1]) < y0 or min(a[1], b[1]) > y1):
            return False
        if self.circle:
            cx, cy, r = self.circle
            return _seg_dist(a, b, (cx, cy)) < r - 1.5
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if self.contains(a) or self.contains(b) or self.contains(mid):
            return True
        poly = self.poly
        return any(_crosses(a, b, poly[i - 1], poly[i]) for i in range(len(poly)))

    def corners(self) -> list[tuple[float, float]]:
        """Points just outside the room's convex corners: where a path bends round it."""
        if self.circle:
            cx, cy, r = self.circle
            return [(cx + (r + CLEAR) * math.cos(math.pi * k / 4),
                     cy + (r + CLEAR) * math.sin(math.pi * k / 4)) for k in range(8)]
        out = []
        pts = self.raw
        for i, v in enumerate(pts):
            p, n = pts[i - 1], pts[(i + 1) % len(pts)]
            a = _unit(v[0] - p[0], v[1] - p[1])
            b = _unit(n[0] - v[0], n[1] - v[1])
            bx, by = _unit(a[0] - b[0], a[1] - b[1])
            out.append((v[0] + bx * CLEAR * 1.4, v[1] + by * CLEAR * 1.4))
        return out


class _Floor:
    """One floor's walkable space: inside the building's outline, outside every room."""

    def __init__(self, plan: dict, shapes: list[_Shape]) -> None:
        self.shapes = shapes
        self.areas = []
        for area in plan["areas"]:
            xs = [p[0] for p in area["points"]]
            ys = [p[1] for p in area["points"]]
            self.areas.append(((min(xs), min(ys), max(xs), max(ys)), area["points"]))

    def indoors(self, p) -> bool:
        x, y = p
        return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] and _inside(x, y, poly)
                   for b, poly in self.areas)

    def free(self, p) -> bool:
        return self.indoors(p) and not any(s.contains(p) for s in self.shapes)

    def walkable(self, a, b, skip=()) -> bool:
        if any(s.blocks(a, b) for s in self.shapes if s not in skip):
            return False
        steps = max(2, int(_dist(a, b) // SAMPLE))    # a short step still has its middle checked
        return all(self.indoors((a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps))
                   for i in range(1, steps))


# -------------------------------------------------------------------- router
class Router:
    def __init__(self, index, campus_map) -> None:
        self.index = index
        self.map = campus_map
        self.rooms = {r["room_number"]: r for r in index.rooms}
        self.nodes: dict[str, dict] = {}
        self.adj: dict[str, list] = {}
        self.room_node: dict[str, str] = {}      # room number -> its node
        self.exits: dict[str, dict] = {}         # landmark id -> {name, node}
        self.wings: dict[tuple, dict] = {}       # (floor, block) -> wing corridor
        self.doors: dict[str, dict] = {}         # room number -> its door on a wing
        self.corridor_blocks: dict[int, list] = {}
        self.spines: dict[int, dict] = {}
        self.stairs: dict[str, dict] = {}        # node -> {core, name}
        self.unreached: list[str] = []           # rooms the graph could not join (tests keep it empty)
        self._geo: dict[int, _Floor] = {}
        self._lobby_centre: dict[int, tuple[float, float]] = {}
        self._shape: dict[tuple, _Shape] = {}
        for plan in campus_map.floor_list():
            self._build_floor(plan)
        self._join_floors()

    # ------------------------------------------------------------ building
    def _node(self, nid: str, floor: int, x: float, y: float, kind: str, **info) -> str:
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "floor": floor, "x": round(x, 1), "y": round(y, 1),
                               "kind": kind, **info}
            self.adj[nid] = []
        return nid

    def _edge(self, a: str, b: str, kind: str, cost: float | None = None, **info) -> None:
        if a == b:
            return
        na, nb = self.nodes[a], self.nodes[b]
        if cost is None:
            cost = math.hypot(nb["x"] - na["x"], nb["y"] - na["y"])
        edge = {"kind": kind, **info}
        self.adj[a].append((b, cost, edge))
        self.adj[b].append((a, cost, edge))

    def _pt(self, nid: str) -> tuple[float, float]:
        n = self.nodes[nid]
        return (n["x"], n["y"])

    def _tap(self, floor: int, y: float) -> str:
        """The point of the central corridor level with y."""
        spine = self.spines[floor]
        y = min(max(y, spine["y0"]), spine["y1"])
        nid = f"{floor}:s:{round(y)}"
        spine["taps"].add(nid)
        return self._node(nid, floor, spine["x"], round(y), "spine")

    def _build_floor(self, plan: dict) -> None:
        floor = plan["floor"]
        spine = plan["spines"][0]
        self.spines[floor] = {"x": spine["x"], "y0": spine["y0"], "y1": spine["y1"], "taps": set()}
        self.corridor_blocks[floor] = sorted((b for b in plan["blocks"] if not b["north"]),
                                             key=lambda b: b["y0"])
        shapes = []
        for r in plan["rooms"]:
            shape = (_Shape(r["code"], circle=(r["cx"], r["cy"], r["r"])) if r["kind"] == "circle"
                     else _Shape(r["code"], points=r["points"]))
            self._shape[(floor, r["code"])] = shape
            shapes.append(shape)
        shapes += [_Shape(None, points=f["points"]) for f in plan.get("fixtures", [])]
        geo = _Floor(plan, shapes)
        self._geo[floor] = geo
        atrium = next((f["points"] for f in plan["features"] if f["kind"] == "atrium"), None)
        if atrium:
            self._lobby_centre[floor] = (sum(p[0] for p in atrium) / len(atrium), sum(p[1] for p in atrium) / len(atrium))
        shape_of = {r["code"]: r for r in plan["rooms"]}

        wing_rooms, corridor_rooms, open_rooms = [], [], []
        for code, shape in shape_of.items():
            zone = self.rooms[code]["zone"]
            (wing_rooms if zone == "wing" else corridor_rooms if zone == "corridor" else open_rooms).append(shape)

        # ---- the wings: a chain down the middle of each wing corridor
        wings = []
        for c in plan["circulation"]:
            p0, p1, p2, p3 = c["points"]
            m = ((p0[0] + p3[0]) / 2, (p0[1] + p3[1]) / 2)
            e = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            wings.append({"m": m, "e": e, "rooms": []})
        unplaced = []
        for shape in wing_rooms:
            here = (shape["x"], shape["y"])
            best = min(wings, key=lambda w: _seg_dist(w["m"], w["e"], here), default=None)
            if best and _seg_dist(best["m"], best["e"], here) <= 90:
                best["rooms"].append(shape)
            else:
                unplaced.append(shape)
        for wing in wings:
            if not wing["rooms"]:
                continue
            blocks = [s["block"] for s in wing["rooms"]]
            block = max(set(blocks), key=blocks.count)
            m, e = wing["m"], wing["e"]
            dx, dy = e[0] - m[0], e[1] - m[1]
            length = math.hypot(dx, dy)
            mouth = self._tap(floor, m[1])
            end = self._node(f"{floor}:w:{block}:end", floor, e[0], e[1], "wing_end", block=block)
            record = {"floor": floor, "block": block, "m": self._pt(mouth), "e": e, "length": length,
                      "doors": [], "end": end, "mouth": mouth}
            chain = [(0.0, mouth), (1.0, end)]
            for shape in wing["rooms"]:
                code = shape["code"]
                t = ((shape["x"] - m[0]) * dx + (shape["y"] - m[1]) * dy) / (length * length)
                t = min(max(t, 0.03), 0.97)
                door_pt = (m[0] + dx * t, m[1] + dy * t)
                door = self._node(f"{floor}:d:{code}", floor, *door_pt, "door", room=code)
                room = self._node(f"{floor}:r:{code}", floor, shape["x"], shape["y"], "room", room=code)
                self._edge(room, door, "room", room=code)
                self.room_node[code] = room
                info = {"code": code, "t": t, "door": door_pt, "room": (shape["x"], shape["y"]),
                        "wing": (floor, block)}
                record["doors"].append(info)
                self.doors[code] = info
                chain.append((t, door))
            chain.sort()
            for (_, a), (_, b) in zip(chain, chain[1:]):
                self._edge(a, b, "wing", floor=floor, block=block)
            self.wings[(floor, block)] = record

        # ---- rooms that open straight onto the central corridor
        for shape in corridor_rooms + unplaced:
            code = shape["code"]
            here = (shape["x"], shape["y"])
            tap = self._tap(floor, shape["y"])
            if geo.walkable(here, self._pt(tap), skip=(self._shape[(floor, code)],)):
                room = self._node(f"{floor}:r:{code}", floor, *here, "room", room=code)
                self._edge(room, tap, "room", room=code, floor=floor)
                self.room_node[code] = room
            else:
                open_rooms.append(shape)

        # ---- open floor: the west side, the lobby, the foyer
        self._corners = self._visibility(floor, geo, open_rooms)
        for shape in open_rooms:
            code = shape["code"]
            room = self._node(f"{floor}:r:{code}", floor, shape["x"], shape["y"], "room", room=code)
            zone = self._open_zone(floor, code, shape["x"], shape["y"])
            self.nodes[room]["zone"] = zone
            if self._attach(floor, room, skip=(self._shape[(floor, code)],), zone=zone):
                self.room_node[code] = room
            else:
                self.unreached.append(code)

        # ---- exits and stairs
        for floor_id, items in self.index.landmarks.items():
            fl = self.index.floors[floor_id]
            if fl["floor_number"] != floor:
                continue
            for lm in items:
                if lm["type"] not in ("exit", "stairs"):
                    continue
                at = self.map.to_map(fl["sheet_id"], lm["x"], lm["y"])
                if at is None:
                    continue
                self._landmark(floor, geo, lm, fl["building_id"], at)

        # the lobby and the Block B foyer are each one open hall: what stands in
        # one (its entrance, its staircase, its desks, the doors along the foyer)
        # is also joined straight to the rest of it wherever nothing stands between
        for hall in ("lobby", "foyer"):
            places = [n for n, node in self.nodes.items() if node["floor"] == floor and node.get("zone") == hall]
            for k, a in enumerate(places):
                for b in places[k + 1:]:
                    pa, pb = self._pt(a), self._pt(b)
                    own = tuple(s for s in geo.shapes if s.contains(pa) or s.contains(pb)
                                or s.code in (self.nodes[a].get("room"), self.nodes[b].get("room")))
                    if geo.walkable(pa, pb, skip=own):
                        self._edge(a, b, "open", floor=floor, zone=hall)
                    elif hall == "foyer":
                        # the doors along the foyer face each other across it: a
                        # room set back from it is reached round the rooms on the way
                        self._walk_round(floor, a, b, hall)

        spine_taps = sorted(self.spines[floor]["taps"], key=lambda n: self.nodes[n]["y"])
        for a, b in zip(spine_taps, spine_taps[1:]):
            self._edge(a, b, "spine", floor=floor)

    def _open_zone(self, floor: int, code: str | None, x: float, y: float) -> str:
        room = self.rooms.get(code) if code else None
        if room and room["building_id"] in NORTH_BLOCKS:
            return "foyer"
        if room and room["building_id"] == "C":
            return "lobby"
        first = self.corridor_blocks[floor][0]
        if room is None and y < first["y0"] + (first["y1"] - first["y0"]) * 0.75 and x < self.spines[floor]["x"]:
            return "lobby"
        return "west"

    def _landmark(self, floor: int, geo: _Floor, lm: dict, block: str, at) -> None:
        kind = lm["type"]
        nid = self._node(f"{floor}:{kind}:{lm['landmark_id']}", floor, at[0], at[1], kind,
                         name=lm["name"], landmark=lm["landmark_id"], mark=(round(at[0], 1), round(at[1], 1)))
        inside = tuple(s for s in geo.shapes if s.contains(at))
        wing = self.wings.get((floor, block))
        near_end = wing and _dist(wing["e"], at) <= WING_REACH and "lobby" not in lm["name"]
        if near_end:
            if geo.walkable(wing["e"], at, skip=inside):
                self._edge(wing["end"], nid, "landing", floor=floor, block=block)
            else:
                # the mark sits inside the end room's drawing or past the outline: the
                # stairwell is taken from the wing's end itself, a step inside the corridor
                ux, uy = _unit(wing["m"][0] - wing["e"][0], wing["m"][1] - wing["e"][1])
                self.nodes[nid].update(x=round(wing["e"][0] + ux * 8, 1), y=round(wing["e"][1] + uy * 8, 1))
                self._edge(wing["end"], nid, "landing", floor=floor, block=block, cost=0.0)
        else:
            zone = self._open_zone(floor, None, at[0], at[1])
            start = nid
            centre = self._lobby_centre.get(floor)
            if kind == "exit" and zone == "lobby" and centre:
                # an entrance is a door in the wall: the walk starts a few steps
                # inside it, out in the lobby, not along the wall itself
                ux, uy = _unit(centre[0] - at[0], centre[1] - at[1])
                step = (at[0] + ux * 40, at[1] + uy * 40)
                if geo.free(step) and geo.walkable(at, step, skip=inside):
                    start = self._node(f"{nid}:in", floor, step[0], step[1], "open", zone=zone)
                    self._edge(nid, start, "open", floor=floor, src=nid, zone=zone)
                    inside = ()
            self.nodes[start]["zone"] = zone
            if not self._attach(floor, start, skip=inside, zone=zone) and not (
                    kind == "exit" and self._passage(floor, geo, nid, at, zone)):
                return
        if kind == "exit":
            self.exits[lm["landmark_id"]] = {"name": lm["name"], "node": nid}
        else:
            core = "lobby" if "lobby" in lm["name"] else f"wing:{block}"
            self.stairs[nid] = {"core": core, "name": lm["name"], "block": block}

    def _passage(self, floor: int, geo: _Floor, nid: str, at, zone: str) -> bool:
        """A side exit drawn outside the building's outline, at the end of a short
        passage between two wings: the passage runs straight to the central
        corridor, and it may not pass through a room."""
        spine = self.spines[floor]
        if not spine["y0"] <= at[1] <= spine["y1"]:
            return False
        target = (spine["x"], at[1])
        if abs(at[0] - target[0]) > 220 or any(s.blocks(at, target) for s in geo.shapes):
            return False
        self._edge(nid, self._tap(floor, at[1]), "open", floor=floor, src=nid, zone=zone)
        return True

    def _visibility(self, floor: int, geo: _Floor, open_rooms: list[dict]) -> dict:
        """Corners of the rooms on open floor, and which of them see each other."""
        codes = {s["code"] for s in open_rooms}
        points = []
        for shape in geo.shapes:
            if shape.code is None or shape.code in codes:
                points += [p for p in shape.corners() if geo.free(p)]
        sight = {i: [] for i in range(len(points))}
        for i, a in enumerate(points):
            for j in range(i + 1, len(points)):
                b = points[j]
                d = _dist(a, b)
                if d <= OPEN_REACH and geo.walkable(a, b):
                    sight[i].append((j, d))
                    sight[j].append((i, d))
        return {"points": points, "sight": sight}

    def _attach(self, floor: int, nid: str, skip=(), zone: str = "west") -> bool:
        """Join a place on open floor to the central corridor by the shortest walk
        round the rooms in between; the walk becomes a chain of its own."""
        geo = self._geo[floor]
        spine = self.spines[floor]
        start = self._pt(nid)
        points, sight = self._corners["points"], self._corners["sight"]

        def to_spine(p, skip_=()):
            if not spine["y0"] <= p[1] <= spine["y1"]:
                return None
            target = (spine["x"], p[1])
            return abs(p[0] - spine["x"]) if geo.walkable(p, target, skip=skip_) else None

        best = {}          # corner -> (cost, previous corner or None)
        heap = []
        direct = to_spine(start, skip)
        finish = (direct, None) if direct is not None else (math.inf, None)
        for i, p in enumerate(points):
            d = _dist(start, p)
            if d <= OPEN_REACH and geo.walkable(start, p, skip=skip):
                best[i] = (d, None)
                heapq.heappush(heap, (d, i))
        done = set()
        while heap:
            cost, i = heapq.heappop(heap)
            if i in done or cost >= finish[0]:
                continue
            done.add(i)
            out = to_spine(points[i])
            if out is not None and cost + out < finish[0]:
                finish = (cost + out, i)
            for j, d in sight[i]:
                if j not in best or cost + d < best[j][0]:
                    best[j] = (cost + d, i)
                    heapq.heappush(heap, (cost + d, j))
        if finish[0] == math.inf:
            return False
        trail = []
        i = finish[1]
        while i is not None:
            trail.append(points[i])
            i = best[i][1]
        trail.reverse()
        end_y = trail[-1][1] if trail else start[1]
        prev = nid
        for k, p in enumerate(trail):
            mid = self._node(f"{nid}:v{k}", floor, p[0], p[1], "open")
            self._edge(prev, mid, "open", floor=floor, src=nid, zone=zone)
            prev = mid
        self._edge(prev, self._tap(floor, end_y), "open", floor=floor, src=nid, zone=zone)
        return True

    def _walk_round(self, floor: int, a: str, b: str, zone: str) -> None:
        """Join two places on the same open floor by the shortest walk round the
        rooms between them, as a chain of its own."""
        geo = self._geo[floor]
        points, sight = self._corners["points"], self._corners["sight"]
        pa, pb = self._pt(a), self._pt(b)

        def own(n, p):
            return tuple(s for s in geo.shapes if s.contains(p) or s.code == self.nodes[n].get("room"))

        skip_a, skip_b = own(a, pa), own(b, pb)
        best, heap, done = {}, [], set()
        finish = (math.inf, None)
        for i, p in enumerate(points):
            d = _dist(pa, p)
            if d <= OPEN_REACH and geo.walkable(pa, p, skip=skip_a):
                best[i] = (d, None)
                heapq.heappush(heap, (d, i))
        while heap:
            cost, i = heapq.heappop(heap)
            if i in done or cost >= finish[0]:
                continue
            done.add(i)
            out = _dist(points[i], pb)
            if out <= OPEN_REACH and cost + out < finish[0] and geo.walkable(points[i], pb, skip=skip_b):
                finish = (cost + out, i)
            for j, d in sight[i]:
                if j not in best or cost + d < best[j][0]:
                    best[j] = (cost + d, i)
                    heapq.heappush(heap, (cost + d, j))
        if finish[1] is None:
            return
        trail, i = [], finish[1]
        while i is not None:
            trail.append(points[i])
            i = best[i][1]
        prev = a
        for k, p in enumerate(reversed(trail)):
            mid = self._node(f"{a}~{b}:v{k}", floor, p[0], p[1], "open")
            self._edge(prev, mid, "open", floor=floor, zone=zone)
            prev = mid
        self._edge(prev, b, "open", floor=floor, zone=zone)

    def _join_floors(self) -> None:
        cores: dict[str, list] = {}
        for nid, info in self.stairs.items():
            cores.setdefault(info["core"], []).append(nid)
        for nodes in cores.values():
            nodes.sort(key=lambda n: self.nodes[n]["floor"])
            for a, b in zip(nodes, nodes[1:]):
                fa, fb = self.nodes[a]["floor"], self.nodes[b]["floor"]
                self._edge(a, b, "stairs", cost=STAIR_COST * abs(fb - fa))

    # -------------------------------------------------------------- routing
    def place(self, kind: str, key: str) -> dict | None:
        """A start or end point: ("room", room number) or ("exit", landmark id)."""
        if kind == "exit" and key in self.exits:
            ex = self.exits[key]
            label = "the main entrance" if key == MAIN_ENTRANCE else f"the {ex['name']}"
            return {"kind": "exit", "key": key, "node": ex["node"], "label": label,
                    "floor": self.nodes[ex["node"]]["floor"]}
        if kind == "room" and key in self.room_node:
            room = self.rooms[key]
            return {"kind": "room", "key": key, "node": self.room_node[key], "label": spoken(room),
                    "floor": room["floor_number"], "building_id": room["building_id"]}
        return None

    def distance(self, a: dict, b: dict) -> float:
        path = self._shortest(a["node"], b["node"])
        return path[0] if path else math.inf

    def _shortest(self, src: str, dst: str):
        best = {src: (0.0, None, None)}
        heap = [(0.0, src)]
        done = set()
        while heap:
            cost, n = heapq.heappop(heap)
            if n in done:
                continue
            if n == dst:
                break
            done.add(n)
            for m, c, edge in self.adj[n]:
                # a room is a destination, not a corridor: never walk through one
                if self.nodes[m]["kind"] == "room" and m != dst:
                    continue
                if m not in best or cost + c < best[m][0]:
                    best[m] = (cost + c, n, edge)
                    heapq.heappush(heap, (cost + c, m))
        if dst not in best:
            return None
        nodes, edges = [dst], []
        while nodes[-1] != src:
            _, prev, edge = best[nodes[-1]]
            edges.append(edge)
            nodes.append(prev)
        return best[dst][0], nodes[::-1], edges[::-1]

    def route(self, start: dict, end: dict) -> dict:
        """The walk from one place to another, as steps and as lines on the plan."""
        base = {"kind": "route", "from": self._public(start), "to": self._public(end)}
        if start["node"] == end["node"]:
            return {**base, "steps": [f"You're already at {end['label']}."], "step_floors": [end["floor"]], "signs": [],
                    "legs": [], "stairs": [], "floors": [end["floor"]], "note": None,
                    "summary": f"You're already at {end['label']}."}
        found = self._shortest(start["node"], end["node"])
        if not found:
            return {**base, "steps": [], "step_floors": [], "signs": [], "legs": [], "stairs": [], "floors": [],
                    "note": None, "summary": f"There's no walk on the plans from {start['label']} "
                                             f"to {end['label']}."}
        _, nodes, edges = found
        legs = self._legs(nodes, edges)
        steps, signs, step_floors = self._describe(legs, start, end)
        # a step may open on a place's name: "the restroom opens straight onto..."
        steps = [step[0].upper() + step[1:] for step in steps]
        floors = []
        for n in nodes:
            f = self.nodes[n]["floor"]
            if not floors or floors[-1] != f:
                floors.append(f)
        lines, marks = [], []
        for n in nodes:
            node = self.nodes[n]
            if not lines or lines[-1]["floor"] != node["floor"]:
                lines.append({"floor": node["floor"], "points": []})
            pts = lines[-1]["points"]
            pts.append([node["x"], node["y"]])
        own = [self._shape.get((p["floor"], p["key"])) for p in (start, end) if p["kind"] == "room"]
        for line in lines:
            line["points"] = self._unhook(line["floor"], _line(line["points"]), [s for s in own if s])
        # a staircase is marked where the plan draws it; the line ends where you
        # step onto it, which is a few steps away when the plan's mark sits in
        # the end room's drawing
        for a, b in zip(nodes, nodes[1:]):
            na, nb = self.nodes[a], self.nodes[b]
            if na["floor"] != nb["floor"]:
                marks.append({"floor": na["floor"], "x": na["x"], "y": na["y"], "mark": list(na["mark"]),
                              "to": nb["floor"], "name": self.stairs[a]["name"]})
                marks.append({"floor": nb["floor"], "x": nb["x"], "y": nb["y"], "mark": list(nb["mark"]),
                              "to": na["floor"], "name": self.stairs[b]["name"], "arrive": True})
        approx = [p["label"] for p in (start, end) if p["kind"] == "room"
                  and self.rooms[p["key"]]["source"] in APPROXIMATE_SOURCES]
        note = ("Block I isn't digitised yet, so the last part of this route is a best guess."
                if approx else None)
        change = (f", floor {floors[0]} to floor {floors[-1]}" if len(floors) > 1
                  else f", all on floor {floors[0]}")
        return {**base, "steps": steps, "step_floors": step_floors, "signs": signs, "legs": lines,
                "stairs": marks, "floors": floors,
                "note": note, "summary": f"From {start['label']} to {end['label']}{change}."}

    def _unhook(self, floor: int, pts: list, own: list) -> list:
        """A turn back sharper than a right angle, where the walk could have cut
        straight across: the graph meets the central corridor only square on, so
        a walk from open floor can step past the corridor's middle and turn back.
        The line takes the straight way, when it passes through no room."""
        geo = self._geo[floor]
        out = list(pts)
        i = 1
        while i < len(out) - 1:
            a, b, c = out[i - 1], out[i], out[i + 1]
            ab, bc = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
            back = ab[0] * bc[0] + ab[1] * bc[1] < 0
            if back and geo.walkable(a, c, skip=tuple(own)):
                del out[i]
                i = max(1, i - 1)
            else:
                i += 1
        return out

    def _public(self, place: dict) -> dict:
        node = self.nodes[place["node"]]
        out = {"kind": place["kind"], "label": place["label"], "floor": place["floor"],
               "x": node["x"], "y": node["y"]}
        if place["kind"] == "room":
            out.update(code=place["key"], building_id=place["building_id"])
        else:
            out.update(exit=place["key"])
        return out

    # ---------------------------------------------------------- describing
    def _legs(self, nodes: list[str], edges: list[dict]) -> list[dict]:
        """The path cut into stretches along one corridor, one wing, one staircase."""
        legs: list[dict] = []
        for (a, b), edge in zip(zip(nodes, nodes[1:]), edges):
            kind = edge["kind"]
            key = (kind, edge.get("floor"), edge.get("block"), edge.get("src"), edge.get("room"))
            if kind == "landing":
                kind = "wing"
                key = ("wing", edge.get("floor"), edge.get("block"), None, None)
            if legs and legs[-1]["key"] == key:
                legs[-1]["nodes"].append(b)
            else:
                legs.append({"key": key, "kind": kind, "block": edge.get("block"), "src": edge.get("src"),
                             "zone": edge.get("zone"), "room": edge.get("room"),
                             "floor": edge.get("floor"), "nodes": [a, b]})
        for leg in legs:
            pts = [self._pt(n) for n in leg["nodes"]]
            leg["points"] = pts
            leg["length"] = sum(_dist(p, q) for p, q in zip(pts, pts[1:]))
            moves = [(p, q) for p, q in zip(pts, pts[1:]) if _dist(p, q) > 0.5]
            leg["head"] = _unit(moves[0][1][0] - moves[0][0][0], moves[0][1][1] - moves[0][0][1]) if moves else (0, 0)
            leg["tail"] = _unit(moves[-1][1][0] - moves[-1][0][0], moves[-1][1][1] - moves[-1][0][1]) if moves else (0, 0)
            leg["floor"] = self.nodes[leg["nodes"][0]]["floor"]
        return legs

    def _block_at(self, floor: int, y: float) -> dict:
        blocks = self.corridor_blocks[floor]
        holding = [b for b in blocks if b["y0"] <= y <= b["y1"]] or blocks
        return min(holding, key=lambda b: abs((b["y0"] + b["y1"]) / 2 - y))

    def _describe(self, legs: list[dict], start: dict, end: dict) -> tuple[list[str], list[dict], list[int]]:
        """Steps a person can follow while walking: one per corridor, wing or
        staircase, each saying which way to turn and where it ends."""
        steps: list[str] = []
        signs: list[dict] = []
        end_room = self.rooms.get(end["key"]) if end["kind"] == "room" else None
        # "floor": a floor just reached by stairs, said with the next step;
        # "cur": the floor each step is walked on, so the plan can follow the steps
        state = {"floor": None, "cur": start["floor"]}
        step_floors: list[int] = []

        def say(text: str) -> None:
            if state["floor"] and not text.startswith("At the"):
                text = f"On floor {state['floor']}, {text[0].lower()}{text[1:]}"
            state["floor"] = None
            steps.append(text)
            step_floors.append(state["cur"])

        def climb(i: int) -> tuple[str, int]:
            up, to_floor = self._stairs_change(legs, i)
            signs.append({"icon": "stairs", "text": f"Floor {to_floor}"})
            return up, to_floor

        def final(k: int) -> bool:
            return (end_room is not None and k < len(legs) and legs[k]["kind"] in ("room", "open")
                    and legs[k]["nodes"][-1] == end["node"])

        if start["kind"] == "exit":
            if start["key"] == MAIN_ENTRANCE:
                say("Come in through the main entrance into the main lobby.")
                signs.append({"icon": "entrance", "text": "Main entrance"})
            else:
                say(f"Come in by the {self.exits[start['key']]['name']}.")
                signs.append({"icon": "entrance", "text": "Entrance"})
        else:
            name = start["label"].removeprefix("the ")
            signs.append({"icon": "door", "text": name[0].upper() + name[1:]})

        leaving = start["kind"] == "room"
        label = start["label"]
        heading = None
        i = 0
        while i < len(legs):
            leg = legs[i]
            nxt = legs[i + 1] if i + 1 < len(legs) else None
            kind = leg["kind"]
            start_room = self.rooms.get(start["key"]) if leaving else None
            if final(i) and i == 0 and start_room and start_room["zone"] == end_room["zone"] == "north":
                steps.append(self._foyer_walk(start_room, end_room, label))
                step_floors.append(state["cur"])
                break
            if final(i):
                steps.append(self._arrival(legs, i, end_room, heading, state["floor"],
                                           label if leaving else None))
                step_floors.append(state["cur"])
                break

            if kind == "room":                      # out of the start room's door
                heading = leg["tail"]
                i += 1
                continue

            if kind == "stairs":
                up, to_floor = climb(i)
                say(f"Take the {self.stairs[leg['nodes'][0]]['name']} {up} to floor {to_floor}.")
                state["floor"] = state["cur"] = to_floor
                heading = None
                i += 1
                continue

            if kind == "open":
                first, last = self.nodes[leg["nodes"][0]], self.nodes[leg["nodes"][-1]]
                if nxt and nxt["kind"] == "stairs":
                    up, to_floor = climb(i + 1)
                    name = self.stairs[nxt["nodes"][0]]["name"]
                    lead = (f"Leave {label} and go" if leaving else
                            "Cross the main lobby" if leg["zone"] == "lobby" else "Go")
                    say(f"{lead} to the {name} and take it {up} to floor {to_floor}.")
                    state["floor"] = state["cur"] = to_floor
                    leaving, heading = False, None
                    i += 2
                    continue
                if last["kind"] == "spine":
                    k = i + 1
                    if k < len(legs) and legs[k]["kind"] == "spine":
                        k += 1
                    foyer_next = final(k) and end_room["zone"] == "north"
                    if leaving:
                        say(f"Leave {label} and cross to the central corridor." if not foyer_next
                            else f"Leave {label} and go back into the main lobby.")
                    elif foyer_next:
                        pass                        # the foyer step starts from the lobby itself
                    elif first["kind"] == "stairs" and i > 0 and legs[i - 1]["kind"] == "stairs":
                        say("At the top of the stairs, walk over to the central corridor." if self._went_up(legs, i)
                            else "At the bottom of the stairs, walk over to the central corridor.")
                    elif leg["zone"] == "lobby":
                        say("Cross the main lobby to the central corridor.")
                    else:
                        say("Walk over to the central corridor.")
                    leaving = False
                heading = leg["tail"]
                i += 1
                continue

            if kind == "wing":
                if final(i + 1):
                    i += 1                          # the arrival says it, from the way in
                    continue
                block = leg["block"]
                to_end = self.nodes[leg["nodes"][-1]]["kind"] in ("wing_end", "stairs")
                turn = _turn(heading, leg["head"]) if heading else "straight"
                if to_end:
                    if leaving:
                        lead = (f"Leave {label}, turn {turn} and walk to the far end of the Block {block} wing"
                                if turn in ("left", "right") else
                                f"Leave {label} and walk to the far end of the Block {block} wing")
                    elif turn in ("left", "right"):
                        lead = f"Turn {turn} into the Block {block} wing and walk to its far end"
                    else:
                        lead = f"Walk to the far end of the Block {block} wing"
                    if nxt and nxt["kind"] == "stairs":
                        up, to_floor = climb(i + 1)
                        say(f"{lead}; take the stairwell there {up} to floor {to_floor}.")
                        state["floor"] = state["cur"] = to_floor
                        leaving, heading = False, None
                        i += 2
                        continue
                    say(f"{lead}.")
                else:
                    if leaving:
                        say(f"Leave {label}, turn {turn} and walk back along the Block {block} wing "
                            f"to the central corridor." if turn in ("left", "right") else
                            f"Leave {label} and walk back along the Block {block} wing to the central corridor.")
                    else:
                        say(f"Walk back along the Block {block} wing to the central corridor.")
                leaving = False
                heading = leg["tail"]
                i += 1
                continue

            if kind == "spine":
                # the foyer is reached from the lobby: its own step says so
                to_foyer = (final(i + 1) and end_room["zone"] == "north" and not leaving
                            and i > 0 and legs[i - 1]["kind"] == "open" and legs[i - 1]["zone"] == "lobby")
                if leg["length"] < SHORT_LEG or to_foyer:
                    if leg["length"] > 0.5 and heading is None:
                        heading = leg["tail"]
                    i += 1
                    continue
                floor = leg["floor"]
                y0, y1 = leg["points"][0][1], leg["points"][-1][1]
                from_block, to_block = self._block_at(floor, y0), self._block_at(floor, y1)
                # where the corridor walk ends is the block of what comes next: the
                # wing it turns into, or the room it arrives at
                ahead = nxt["block"] if nxt and nxt["kind"] == "wing" else \
                    end_room["building_id"] if final(i + 1) and end_room["building_id"] not in NORTH_BLOCKS else None
                if ahead:
                    to_block = next((b for b in self.corridor_blocks[floor] if b["id"] == ahead), to_block)
                lo, hi = sorted((y0, y1))
                passed = [b["id"] for b in self.corridor_blocks[floor]
                          if lo < (b["y0"] + b["y1"]) / 2 < hi and b["id"] not in (from_block["id"], to_block["id"])]
                if y1 < y0:
                    passed.reverse()
                turn = _turn(heading, leg["head"]) if heading else "straight"
                if leaving:
                    lead = (f"Leave {label}, turn {turn} and follow the central corridor"
                            if turn in ("left", "right") else f"Leave {label} and follow the central corridor")
                elif turn in ("left", "right"):
                    lead = f"Turn {turn} into the central corridor and follow it"
                else:
                    lead = "Follow the central corridor"
                past = (f" past Block {passed[0]}" if len(passed) == 1 else
                        f" past Blocks {human_list(passed)}" if passed else "")
                towards_lobby = nxt is not None and nxt["kind"] == "open" and nxt["zone"] in ("lobby", "foyer")
                if towards_lobby and to_block["id"] == self.corridor_blocks[floor][0]["id"]:
                    target = " back towards the main lobby"
                elif to_block["id"] == from_block["id"]:
                    target = f" along Block {to_block['id']}"
                else:
                    target = f" to Block {to_block['id']}"
                say(f"{lead}{past}{target}.")
                leaving = False
                heading = leg["tail"]
                i += 1
                continue
            i += 1

        signs.extend(self._arrival_signs(end, end_room))
        return [s[0].upper() + s[1:] for s in steps], signs, step_floors

    def _stairs_change(self, legs: list[dict], i: int) -> tuple[str, int]:
        """"up"/"down" and the floor a run of stairs ends on (several flights merge)."""
        leg = legs[i]
        start = self.nodes[leg["nodes"][0]]["floor"]
        end = self.nodes[leg["nodes"][-1]]["floor"]
        return ("up" if end > start else "down"), end

    def _went_up(self, legs: list[dict], i: int) -> bool:
        for leg in reversed(legs[:i]):
            if leg["kind"] == "stairs":
                return self.nodes[leg["nodes"][-1]]["floor"] > self.nodes[leg["nodes"][0]]["floor"]
        return True

    def _arrival(self, legs: list[dict], i: int, room: dict, heading, new_floor: int | None,
                 leaving: str | None) -> str:
        """The last step: which door it is, said from the way the walker comes in."""
        code = spoken(room)
        number = room["room_number"]
        prev = legs[i - 1] if i > 0 else None
        on_floor = f"On floor {new_floor}, " if new_floor else ""

        def lead(text: str) -> str:
            text = on_floor + (text[0].lower() + text[1:] if on_floor else text)
            return text

        if number in self.doors and prev is not None and prev["kind"] == "wing":
            door = self.doors[number]
            wing = self.wings[door["wing"]]
            axis = _unit(wing["e"][0] - wing["m"][0], wing["e"][1] - wing["m"][1])
            backwards = prev["tail"][0] * axis[0] + prev["tail"][1] * axis[1] < 0
            walk = (-axis[0], -axis[1]) if backwards else axis

            def along(d):
                return 1 - d["t"] if backwards else d["t"]

            entry = self.nodes[prev["nodes"][0]]
            entry_at = along(self.doors[entry["room"]]) if entry["kind"] == "door" else -1.0
            mine = _side(walk, door["door"], door["room"])
            same = sorted((d for d in wing["doors"] if _side(walk, d["door"], d["room"]) == mine
                           and entry_at < along(d) <= along(door) + 1e-9), key=along)
            pos = len(same)
            before = [spoken(self.rooms[d["code"]]) for d in same[:-1]][-2:]
            last_on_side = not any(along(d) > along(door) for d in wing["doors"]
                                   if _side(walk, d["door"], d["room"]) == mine)
            others = [d for d in wing["doors"] if _side(walk, d["door"], d["room"]) != mine and d["code"] != number]
            opposite = min(others, key=lambda d: abs(along(d) - along(door)), default=None)
            if opposite and abs(along(opposite) - along(door)) * wing["length"] > OPPOSITE_REACH:
                opposite = None

            if entry["kind"] == "door":
                start_door = self.doors[entry["room"]]
                turn = _turn(heading, walk) if heading else "straight"
                if _side(walk, start_door["door"], start_door["room"]) != mine and \
                        abs(along(start_door) - along(door)) * wing["length"] <= OPPOSITE_REACH:
                    return f"Leave {leaving}: {code} is directly across the corridor."
                opening = f"Leave {leaving} and turn {turn}: " if turn in ("left", "right") else f"Leave {leaving}: "
                nth = "next" if pos == 1 else ordinal(pos)
                text = f"{code} is the {nth} door on your {mine}"
                text += f", just after {human_list(before)}." if before else "."
                return opening + text
            if entry["kind"] in ("wing_end", "stairs"):
                opening = lead(f"Walk back along the Block {wing['block']} wing: ")
                first_txt = "right by the stairwell" if entry["kind"] == "stairs" else "at the far end"
            else:
                turn = _turn(heading, walk) if heading else "straight"
                opening = lead(f"Turn {turn} into the Block {wing['block']} wing: " if turn in ("left", "right")
                               else f"Go into the Block {wing['block']} wing: ")
                first_txt = "right as you enter the wing"
            if pos == 1:
                text = f"{code} is the first door on your {mine}, {first_txt}."
            elif last_on_side and entry["kind"] == "spine":
                text = (f"{code} is the last door on your {mine}, at the far end of the wing — "
                        f"you'll pass {human_list(before)} on the way.")
            else:
                text = f"{code} is the {ordinal(pos)} door on your {mine}, just after {human_list(before)}."
            if opposite:
                text += f" Directly across the corridor is {spoken(self.rooms[opposite['code']])}."
            return opening + text

        opening = f"Leave {leaving}. " if leaving else ""
        if room["zone"] == "corridor":
            node = self.nodes[self.room_node[number]]
            walk = heading or (0.0, 1.0)
            side = _side(walk, (self.spines[node["floor"]]["x"], node["y"]), (node["x"], node["y"]))
            near = sorted((r for r in self.index.rooms if r["floor_id"] == room["floor_id"]
                           and r["zone"] == "corridor" and spoken(r) != code
                           and abs(r["y"] - room["y"]) <= 90),
                          key=lambda r: abs(r["y"] - room["y"]))
            above = [r for r in near if r["y"] < room["y"]][:1]
            below = [r for r in near if r["y"] > room["y"]][:1]
            if above and below:
                tail = f", between {spoken(above[0])} and {spoken(below[0])}."
            elif near:
                tail = f", next to {spoken(near[0])}."
            else:
                tail = "."
            return opening + lead(f"{code} opens straight onto the central corridor, on your {side}{tail}")
        across = self.index._across(room) if room["zone"] == "west" else None
        if leaving and across is not None and spoken(across) == leaving:
            return f"Leave {leaving}: {code} is directly across the central corridor."
        if room["zone"] == "north":
            return opening + lead(self.index._north_step(room, [], {}))
        return opening + lead(self.index._west_step(room, f"Block {room['building_id']}", [], {}))

    def _foyer_walk(self, start_room: dict, room: dict, leaving: str) -> str:
        """From one door on the Block B foyer to another, without going back to the lobby."""
        row = sorted((r for r in self.index.rooms if r["zone"] == "north"
                      and r["floor_number"] == room["floor_number"]), key=lambda r: r["x"])
        away = room["x"] > start_room["x"]          # away from the lobby, towards Red Hall
        lead = (f"Step out of {leaving} into the Block B foyer and walk "
                + ("away from the main lobby" if away else "back towards the main lobby"))
        if room is row[-1] and away:
            return f"{lead}: {spoken(room)} is at the far end of the foyer."
        north = room["y"] < NORTH_FOYER_Y
        side = ("left" if north else "right") if away else ("right" if north else "left")
        lo, hi = sorted((start_room["x"], room["x"]))
        passed = [r for r in row if r is not room and r is not start_room and lo < r["x"] < hi
                  and (r["y"] < NORTH_FOYER_Y) == north]
        passed.sort(key=lambda r: r["x"], reverse=not away)
        if not passed:
            return f"{lead}: {spoken(room)} is the next door on your {side}."
        return (f"{lead}: {spoken(room)} is the {ordinal(len(passed) + 1)} door on your {side}, "
                f"just after {human_list([spoken(r) for r in passed[-2:]])}.")

    def _arrival_signs(self, end: dict, room: dict | None) -> list[dict]:
        if room is None:
            return []
        label = end["label"].removeprefix("the ")       # a sign says "Restroom", not "The restroom"
        label = label[0].upper() + label[1:]
        if room["zone"] == "north":
            return [{"icon": "ahead", "text": "Block B foyer"}, {"icon": "door", "text": label}]
        if room["zone"] == "wing":
            return [{"icon": "ahead", "text": f"Block {room['building_id']} wing"}, {"icon": "door", "text": label}]
        return [{"icon": "ahead", "text": f"Block {room['building_id']}"}, {"icon": "door", "text": label}]
