"""
Campus search + directions engine (US1 — Conversational Location Search).

Everything is loaded from data/campus.db once at startup into memory
(~250 rooms), so every request is answered in well under a millisecond
and the engine is safe to share between server threads.

How directions are derived (nothing is invented):
  * every plan sheet has a central corridor running top-to-bottom and
    classroom wings branching off to the right (sheet_geometry table);
  * inside a wing, rooms split into two rows around the wing corridor.
    Walking into the wing (to the right on the plan) the upper row is on
    your LEFT and the lower row on your RIGHT;
  * door order = order along the wing, counted from the central corridor;
  * "opposite" = the room in the other row at the closest position;
  * landmarks = exits (floor 1) and wing-end stairwells (floors 2-3).
"""
from __future__ import annotations

import difflib
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPUS_TZ = ZoneInfo("Asia/Almaty")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
            7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"}

DEPARTMENTS = {
    "LAW": "Faculty of Law & Social Sciences",
    "PHIL": "Faculty of Education & Humanities",
    "ENG": "Faculty of Engineering & Natural Sciences",
    "ECO": "SDU Business School",
    "MAIN": "Shared university space",
}
ROOM_TYPES = {"CLASS": "Classroom", "LAB": "Lab", "HALL": "Lecture hall",
              "SPEC": "Specialised room", "SPORT": "Sports hall", "FREEDOM": "Open space"}

# Cyrillic letters that look like block letters (people type "Д103", "Н304").
CYR_TO_LAT = str.maketrans({"с": "c", "д": "d", "е": "e", "ф": "f", "г": "g",
                            "н": "h", "и": "i", "і": "i"})
# a block letter C-I, not glued to a preceding letter, then 3 digits
CODE_RE = re.compile(r"(?<![^\W\d_])([c-i])\s?-?\s?(\d{3})(?!\d)")
BARE_NUMBER_RE = re.compile(r"(?<!\d)(\d{3})(?!\d)")
# The eight round lecture halls ("barrels") are also called A1..D2. The name is
# stored as a room alias in campus.db; this only finds it inside a sentence.
BARREL_RE = re.compile(r"(?<![a-z0-9])([a-d])\s?-?\s?([12])(?![0-9])")
BARREL_NAME_RE = re.compile(r"^[a-d][12]$")


def normalize(text: str) -> str:
    return re.sub(r"[\s\-_'’.]", "", text.strip().lower())


def ordinal(n: int) -> str:
    return ORDINALS.get(n, f"{n}th")


def display_code(room: dict) -> str:
    return "the Medcenter" if room["room_number"].startswith("MEDCENTER") else room["room_number"]


def barrel_name(room: dict) -> str | None:
    """The A1..D2 name of a round lecture hall, from its aliases in the database."""
    for alias in room.get("aliases", ()):
        if BARREL_NAME_RE.match(alias):
            return alias.upper()
    return None


def human_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class CampusIndex:
    def __init__(self) -> None:
        self.buildings: dict[str, str] = {}
        self.sheets: dict[str, dict] = {}
        self.floors: dict[str, dict] = {}
        self.rooms: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.landmarks: dict[str, list[dict]] = {}
        self.services: dict[str, dict] = {}
        self.building_aliases: list[tuple[str, str]] = []   # (alias, building_id), longest first
        self.map = None          # CampusMap, attached after load (see app/main.py)

    def attach_map(self, campus_map) -> None:
        """Let answers carry positions on the redrawn vector plan as well."""
        self.map = campus_map

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, db_path: str | Path) -> "CampusIndex":
        idx = cls()
        conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            idx._load(conn)
        finally:
            conn.close()
        return idx

    def _load(self, conn: sqlite3.Connection) -> None:
        self.buildings = {r["building_id"]: r["name"] for r in conn.execute("SELECT * FROM buildings")}

        for r in conn.execute("""SELECT p.*, g.west_max_x, g.wing_min_x
                                 FROM plan_sheets p LEFT JOIN sheet_geometry g USING (sheet_id)"""):
            self.sheets[r["sheet_id"]] = dict(r)

        for r in conn.execute("SELECT * FROM floors"):
            self.floors[r["floor_id"]] = dict(r)

        for r in conn.execute("""SELECT r.*, f.building_id, f.floor_number, f.sheet_id
                                 FROM rooms r JOIN floors f USING (floor_id)"""):
            room = dict(r)
            room["aliases"] = []
            room["geo_sheet_id"] = self._geometry_sheet(room)
            room["zone"] = self._zone(room)
            self.rooms.append(room)
            self.by_code[normalize(room["room_number"])] = room

        by_id = {room["room_id"]: room for room in self.rooms}
        for r in conn.execute("SELECT ra.alias, ra.room_id FROM room_aliases ra"):
            room = by_id.get(r["room_id"])
            if room:
                room["aliases"].append(normalize(r["alias"]))
                self.by_code.setdefault(normalize(r["alias"]), room)

        aliases = [(normalize(r["alias"]), r["building_id"])
                   for r in conn.execute("SELECT building_id, alias FROM building_aliases")]
        self.building_aliases = sorted(aliases, key=lambda a: -len(a[0]))

        for r in conn.execute("SELECT * FROM landmarks"):
            self.landmarks.setdefault(r["floor_id"], []).append(dict(r))

        for r in conn.execute("SELECT * FROM services"):
            self.services[r["service_id"]] = {**dict(r), "hours": {}, "aliases": []}
        for r in conn.execute("SELECT * FROM service_hours"):
            self.services[r["service_id"]]["hours"][r["day_of_week"]] = (r["open_time"], r["close_time"])
        for r in conn.execute("SELECT * FROM service_aliases"):
            self.services[r["service_id"]]["aliases"].append(normalize(r["alias"]))

    def _geometry_sheet(self, room: dict) -> str | None:
        # Block I has no digitised plan of its own; it mirrors Block H.
        if room["building_id"] == "I":
            h_floor = self.floors.get(f"H-{room['floor_number']}")
            return h_floor["sheet_id"] if h_floor else None
        return room["sheet_id"]

    def _zone(self, room: dict) -> str:
        geo = self.sheets.get(room["geo_sheet_id"] or "")
        if not geo or geo.get("wing_min_x") is None:
            return "unknown"
        if room["x"] >= geo["wing_min_x"]:
            return "wing"
        if room["x"] <= geo["west_max_x"]:
            return "west"
        return "corridor"

    # ---------------------------------------------------------------- public
    def stats(self) -> dict:
        return {
            "rooms": len(self.rooms),
            "blocks": len(self.buildings),
            "floors": len({f["floor_number"] for f in self.floors.values()}),
            "measured_rooms": sum(1 for r in self.rooms if r["source"] != "approximated_from_H"),
        }

    def sheet_list(self) -> list[dict]:
        out = []
        for sid, s in self.sheets.items():
            if not s.get("image_path"):
                continue
            rooms = [{"room_number": r["room_number"], "x": r["x"], "y": r["y"], "building_id": r["building_id"]}
                     for r in self.rooms if r["sheet_id"] == sid]
            out.append({
                "sheet_id": sid, "floor_number": s["floor_number"], "section": s["section"],
                "image": f"/static/{s['image_path']}", "width": s["width_px"], "height": s["height_px"],
                "blocks": sorted({r["building_id"] for r in rooms}), "rooms": rooms,
            })
        return sorted(out, key=lambda s: (s["floor_number"], s["section"] != "front"))

    def service_list(self, now: datetime | None = None) -> list[dict]:
        return [self._service_payload(s, now) for s in self.services.values()]

    def search(self, query: str, now: datetime | None = None, context: str | None = None) -> dict:
        """Answer a question. `context` is the room number a previous answer
        asked the user to pick a block for, so "204" then "Engineering" works."""
        t0 = time.perf_counter()
        result = self._search(query, now, context)
        result.setdefault("context", None)
        result["query"] = query
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        return result

    # --------------------------------------------------------------- search
    def _search(self, query: str, now: datetime | None, context: str | None = None) -> dict:
        lowered = query.lower().translate(CYR_TO_LAT)
        qn = normalize(query)

        m = CODE_RE.search(lowered)
        if m:
            code = m.group(1) + m.group(2)
            room = self.by_code.get(code)
            if room:
                return self._room_answer(room)
            return self._not_found(code.upper())

        m = BARREL_RE.search(lowered)
        if m:
            hall = self.by_code.get(m.group(1) + m.group(2))
            if hall:
                return self._room_answer(hall)

        # "room 204 in the Engineering building" — and the same thing split over
        # two turns, where the number came from the question before this one.
        blocks = self._buildings_in(qn, normalize(lowered))
        found_number = BARE_NUMBER_RE.search(query)
        digits = found_number.group(1) if found_number else (context or None)
        if digits and blocks:
            rooms = [self.by_code[key] for key in (normalize(b + digits) for b in blocks)
                     if key in self.by_code]
            if len(rooms) == 1:
                return self._room_answer(rooms[0])
            if rooms:
                return self._ambiguous(digits, rooms)
            if len(blocks) == 1:
                return self._not_found(f"{blocks[0]}{digits}")

        for svc in self.services.values():
            if any(alias in qn for alias in svc["aliases"]) or normalize(svc["name"]) in qn:
                return self._service_answer(svc, now)

        if found_number:
            matches = [r for r in self.rooms
                       if re.search(rf"(?<!\d){found_number.group(1)}$", r["room_number"])]
            matches = [r for r in matches if r["source"] != "approximated_from_H"] or matches
            if len(matches) == 1:
                return self._room_answer(matches[0])
            if matches:
                return self._ambiguous(found_number.group(1), matches)

        if blocks:
            return self._block_answer(blocks[0])

        return {
            "kind": "no_match",
            "title": "I couldn't tell which place you mean",
            "summary": "Try a room code like D103 or H304, a faculty such as the Business School, "
                       "or a service like library, cafeteria, dean's office or medcenter.",
            "suggestions": ["D103", "G215", "Business School", "Library"],
        }

    def _buildings_in(self, qn: str, latin: str) -> list[str]:
        """Which blocks a question names, most specific alias first."""
        found: list[str] = []
        for alias, building_id in self.building_aliases:
            if alias and alias in qn and building_id not in found:
                found.append(building_id)
        # a one-letter reply to "which block did you mean?"
        if not found and re.fullmatch(r"[c-i]", latin):
            found.append(latin.upper())
        return found

    def _ambiguous(self, digits: str, matches: list[dict]) -> dict:
        codes = sorted(r["room_number"] for r in matches)
        return {
            "kind": "ambiguous",
            "title": f"Several blocks have a room {digits}",
            "summary": f"There's a {digits} in {len(codes)} blocks — {human_list(codes)}. "
                       f"Which one did you mean? Naming the block or the faculty is enough.",
            "suggestions": codes,
            "context": digits,
        }

    def _block_answer(self, building_id: str) -> dict:
        """Where a whole block or faculty is, when the question names no room."""
        rooms = [r for r in self.rooms if r["building_id"] == building_id]
        name = self.buildings.get(building_id, f"Block {building_id}")
        floors = sorted({r["floor_number"] for r in rooms})
        entry = min((r for r in rooms if r["zone"] == "wing"),
                    key=lambda r: (r["floor_number"], r["x"]), default=rooms[0])
        directions = self._room_answer(entry)
        floor_text = ("floor " + str(floors[0]) if len(floors) == 1
                      else f"floors {floors[0]} to {floors[-1]}")
        return {
            "kind": "block",
            "title": f"Block {building_id}",
            "summary": f"{name}. {len(rooms)} rooms on {floor_text}; "
                       f"its wings start at {entry['room_number']}.",
            "block": {"building_id": building_id, "name": name,
                      "floors": floors, "rooms": len(rooms)},
            "steps": directions["steps"][:3],
            "map": directions["map"],
            "suggestions": sorted(r["room_number"] for r in rooms
                                  if r["zone"] == "wing" and r["floor_number"] == floors[0])[:4],
            "note": None,
        }

    def _not_found(self, code: str) -> dict:
        close = difflib.get_close_matches(code.lower(), list(self.by_code.keys()), n=6, cutoff=0.5)
        seen, suggestions = set(), []
        for key in close:
            rn = self.by_code[key]["room_number"]
            if rn not in seen and not rn.startswith("MEDCENTER"):
                seen.add(rn)
                suggestions.append(rn)
        suggestions = suggestions[:3]
        summary = f"There's no room {code} on the evacuation plans I've digitised."
        if suggestions:
            summary += f" The closest real rooms are {human_list(suggestions)} — one of those might be the one you need."
        return {"kind": "not_found", "title": f"No room {code} on file", "summary": summary, "suggestions": suggestions}

    # ------------------------------------------------------------ directions
    def _room_answer(self, room: dict) -> dict:
        bid, floor = room["building_id"], room["floor_number"]
        building_name = self.buildings.get(bid, f"Block {bid}")
        code = display_code(room)
        steps: list[str] = []
        highlights: list[dict] = []

        steps.append("Come in through the main entrance into the Block C lobby (Wi-Fi Zone and wardrobe) "
                     "— the central corridor starts here and runs past every block.")
        if floor == 1:
            steps.append("Stay on the ground floor (floor 1).")
        else:
            steps.append(f"Go up to floor {floor}. There are stairs along the central corridor "
                         f"and at the far end of every wing.")

        block_label = f"Block {bid}"
        if bid == "I":
            steps.append("Keep going down the central corridor past Block H — Block I carries on from there "
                         "and repeats the Block H layout, without its west-side rooms.")

        zone = room["zone"]
        if zone == "wing":
            if bid != "I":
                steps.append(f"Follow the central corridor to {block_label} and turn into the {block_label} wing.")
            steps.append(self._wing_step(room, highlights))
        elif zone == "corridor":
            steps.append(self._corridor_step(room, block_label, highlights))
        elif zone == "west":
            steps.append(self._west_step(room, block_label, highlights))
        else:
            steps.append(f"Find {code} in {block_label}.")

        landmark = self._nearest_landmark(room)
        if landmark:
            if zone == "wing" and landmark["x"] > room["x"] + 15:
                where = "a little further along the wing"
            elif zone == "wing" and landmark["x"] < room["x"] - 15:
                where = "just back towards the central corridor"
            else:
                where = "close by"
            steps.append(f"Landmark: the {landmark['name']} is {where} — handy if you get turned around.")
        else:
            steps.append(f"Landmark: {self._fallback_landmark(room)} — handy if you get turned around.")

        dept = DEPARTMENTS.get(room.get("department") or "")
        rtype = ROOM_TYPES.get(room.get("type") or "")
        hall = barrel_name(room)
        facts = [f"{rtype} {hall} — one of the round \u201cbarrels\u201d"] if hall and rtype else \
                ([rtype] if rtype else [])
        if dept and dept.split(" ")[-1] not in building_name:  # only when it differs from the block's own faculty
            facts.append(dept)

        note = None
        if room["source"] == "approximated_from_H":
            note = ("Block I isn't digitised yet — this position is copied from the matching Block H room, "
                    "so treat the door order as a best guess.")

        plan = None
        sheet = self.sheets.get(room["sheet_id"])
        if sheet and sheet.get("image_path"):
            plan = {
                "sheet_id": room["sheet_id"], "floor_number": floor, "section": sheet["section"],
                "image": f"/static/{sheet['image_path']}", "width": sheet["width_px"], "height": sheet["height_px"],
                "x": room["x"], "y": room["y"], "highlights": highlights,
                "landmark": {"name": landmark["name"], "type": landmark["type"],
                             "x": landmark["x"], "y": landmark["y"]} if landmark else None,
            }

        return {
            "kind": "room",
            "map": self._map_payload(room, highlights, landmark),
            "title": code,
            "summary": (f"{code}{f' (hall {hall})' if hall else ''} is on floor {floor} "
                        f"of {building_name}."),
            "room": {"room_number": code, "building_id": bid, "building_name": building_name,
                     "floor_number": floor, "zone": zone, "facts": facts, "source": room["source"]},
            "steps": steps, "note": note, "plan": plan, "suggestions": [],
        }

    def _map_payload(self, room: dict, highlights: list[dict], landmark: dict | None) -> dict | None:
        """The same answer, in the coordinates of the redrawn vector floor plan."""
        if self.map is None:
            return None
        here = self.map.room_point(room["room_number"])
        if here is None:
            return None
        payload = {"floor": room["floor_number"], "room_number": display_code(room),
                   "x": here["x"], "y": here["y"], "radius": here["r"],
                   "highlights": [], "landmark": None}
        for hl in highlights:
            point = self.map.room_point(hl["room_number"])
            if point:
                payload["highlights"].append({"room_number": hl["room_number"],
                                              "role": hl["role"], "x": point["x"], "y": point["y"]})
        if landmark:
            point = self.map.to_map(room["sheet_id"], landmark["x"], landmark["y"])
            if point:
                payload["landmark"] = {"name": landmark["name"], "type": landmark["type"],
                                       "x": point[0], "y": point[1]}
        return payload

    def _same_floor(self, room: dict, zone: str) -> list[dict]:
        return [r for r in self.rooms if r["floor_id"] == room["floor_id"] and r["zone"] == zone]

    def _wing_step(self, room: dict, highlights: list[dict]) -> str:
        wing = self._same_floor(room, "wing")
        ys = sorted(r["y"] for r in wing)
        split = None
        gaps = [(ys[i + 1] - ys[i], (ys[i + 1] + ys[i]) / 2) for i in range(len(ys) - 1)]
        if gaps and max(gaps)[0] >= 25:
            split = max(gaps)[1]
        if split is None:
            row, other = wing, []
            side = None
        else:
            upper = [r for r in wing if r["y"] < split]
            lower = [r for r in wing if r["y"] >= split]
            row, other = (upper, lower) if room["y"] < split else (lower, upper)
            side = "left" if room["y"] < split else "right"

        row = sorted(row, key=lambda r: r["x"])
        pos = row.index(room) + 1
        before = [r["room_number"] for r in row[:pos - 1]][-2:]
        code = display_code(room)
        side_txt = f" on your {side}" if side else ""

        if pos == 1:
            sentence = f"{code} is the first door{side_txt}, right as you enter the wing."
        elif pos == len(row):
            sentence = (f"{code} is the last door{side_txt}, at the far end of the wing — "
                        f"you'll pass {human_list(before)} on the way.")
        else:
            sentence = f"{code} is the {ordinal(pos)} door{side_txt}, just after {human_list(before)}."

        for rn in before:
            r = next(x for x in row if x["room_number"] == rn)
            highlights.append({"room_number": rn, "x": r["x"], "y": r["y"], "role": "passed"})

        if other:
            opp = min(other, key=lambda r: abs(r["x"] - room["x"]))
            if abs(opp["x"] - room["x"]) <= 45:
                sentence += f" Directly across the corridor is {opp['room_number']}."
                highlights.append({"room_number": opp["room_number"], "x": opp["x"], "y": opp["y"], "role": "opposite"})
        return sentence

    def _peers(self, room: dict) -> list[dict]:
        """Other rooms drawn on the same sheet; the two Medcenter rooms don't count as each other's neighbour."""
        is_med = room["room_number"].startswith("MEDCENTER")
        return [r for r in self.rooms if r["sheet_id"] == room["sheet_id"] and r is not room
                and not (is_med and r["room_number"].startswith("MEDCENTER"))]

    def _corridor_step(self, room: dict, block_label: str, highlights: list[dict]) -> str:
        peers = [r for r in self._peers(room) if r["zone"] == "corridor" and abs(r["y"] - room["y"]) <= 90]
        above = sorted([r for r in peers if r["y"] < room["y"]], key=lambda r: room["y"] - r["y"])[:1]
        below = sorted([r for r in peers if r["y"] > room["y"]], key=lambda r: r["y"] - room["y"])[:1]
        for r in above + below:
            highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "neighbour"})
        code = display_code(room)
        base = (f"When you reach {block_label}, look along the central corridor itself — "
                f"{code} opens straight onto it rather than into a wing.")
        if above and below:
            return base + f" It's between {display_code(above[0])} and {display_code(below[0])}."
        if above or below:
            return base + f" It's right next to {display_code((above or below)[0])}."
        return base

    def _west_step(self, room: dict, block_label: str, highlights: list[dict]) -> str:
        peers = [r for r in self._peers(room) if r["zone"] == "west"]
        # prefer neighbours from the same block, fall back to anything on the sheet
        near = sorted(peers, key=lambda r: (r["building_id"] != room["building_id"],
                                            (r["x"] - room["x"]) ** 2 + (r["y"] - room["y"]) ** 2))[:2]
        for r in near:
            highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "neighbour"})
        code = display_code(room)
        if room["building_id"] in ("D", "E") and room["floor_number"] in (1, 2):
            place = "the round lecture halls (the \"barrels\")"
        else:
            place = "the rooms on that side"
        sentence = (f"At {block_label}, cross to the opposite side of the central corridor from the classroom wings — "
                    f"{code} is among {place}.")
        if near:
            sentence += f" Look for it next to {human_list([display_code(r) for r in near])}."
        return sentence

    def _fallback_landmark(self, room: dict) -> str:
        """US1 wants a recognisable landmark with every answer. Where no exit or
        stairwell is close enough, the room's own surroundings are the landmark."""
        block = f"Block {room['building_id']}"
        if room["zone"] == "west":
            halls = [r for r in self.rooms if r["floor_id"] == room["floor_id"]
                     and r is not room and barrel_name(r)]
            if halls:
                near = min(halls, key=lambda r: (r["x"] - room["x"]) ** 2 + (r["y"] - room["y"]) ** 2)
                return (f"the round lecture halls on that side of the corridor — the nearest is "
                        f"{near['room_number']}, the one everyone calls {barrel_name(near)}")
        if room["zone"] == "corridor":
            return f"the central corridor itself, along the {block} stretch of it"
        if room["building_id"] == "I":
            return "the far end of the central corridor, past Block H"
        return f"the mouth of the {block} wing, where it opens off the central corridor"

    def _nearest_landmark(self, room: dict) -> dict | None:
        candidates = self.landmarks.get(room["floor_id"], [])
        if room["building_id"] == "I":
            candidates = []  # no plan of our own, don't point at Block H's exits
        best, best_d = None, None
        for lm in candidates:
            d = ((lm["x"] - room["x"]) ** 2 + (lm["y"] - room["y"]) ** 2) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = lm, d
        return best if best_d is not None and best_d <= 320 else None

    # --------------------------------------------------------------- services
    def _service_payload(self, svc: dict, now: datetime | None) -> dict:
        now = now or datetime.now(CAMPUS_TZ)
        hours = svc["hours"]
        status, open_now = "Opening hours aren't on file yet", None
        if hours:
            dow, hhmm = now.weekday(), now.strftime("%H:%M")
            today = hours.get(dow)
            if today and today[0] <= hhmm < today[1]:
                open_now, status = True, f"Open until {today[1]}"
            else:
                open_now = False
                if today and hhmm < today[0]:
                    status = f"Closed, opens today at {today[0]}"
                else:
                    for i in range(1, 8):
                        d = (dow + i) % 7
                        if d in hours:
                            when = "tomorrow" if i == 1 else DAY_NAMES[d]
                            status = f"Closed, opens {when} at {hours[d][0]}"
                            break
        table = [{"day": DAY_NAMES[d], "open": o, "close": c} for d, (o, c) in sorted(hours.items())]
        return {"service_id": svc["service_id"], "name": svc["name"], "category": svc["category"],
                "open_now": open_now, "status": status, "hours": table, "hours_approximate": True}

    def _service_answer(self, svc: dict, now: datetime | None) -> dict:
        payload = self._service_payload(svc, now)
        note = ("Opening hours are approximate for now — exact timetables come in a later sprint."
                if payload["hours"] else None)
        result = {"kind": "service", "title": svc["name"], "service": payload, "suggestions": [], "note": note}
        room = next((r for r in self.rooms if r["room_id"] == svc.get("room_id")), None)
        if room:
            directions = self._room_answer(room)
            result.update({"summary": f"{svc['name']} is on floor {room['floor_number']} of "
                                      f"{self.buildings.get(room['building_id'])}. {payload['status']}.",
                           "steps": directions["steps"], "plan": directions["plan"],
                           "map": directions["map"], "room": directions["room"]})
        else:
            result.update({"summary": f"{payload['status']}. Its exact room isn't on the digitised plans yet.",
                           "steps": [], "plan": None, "map": None})
        return result
