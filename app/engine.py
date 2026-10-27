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
  * landmarks = exits (floor 1) and wing-end stairwells (floors 2-3);
  * Blocks A and B are the exception: they sit north of the lobby, along a
    foyer that runs east from it, so their rooms are counted along that foyer.
"""
from __future__ import annotations

import difflib
import math
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def _campus_zone() -> ZoneInfo:
    """Campus time. Kazakhstan moved to UTC+5 in March 2024, and a server's own
    time-zone files can be older than that, so the copy bundled with the tzdata
    package (kept current in requirements.txt) is preferred to the system's."""
    try:
        from importlib.resources import files
        with files("tzdata.zoneinfo").joinpath("Asia/Almaty").open("rb") as fh:
            return ZoneInfo.from_file(fh, key="Asia/Almaty")
    except (ImportError, FileNotFoundError, ModuleNotFoundError):
        return ZoneInfo("Asia/Almaty")


CAMPUS_TZ = _campus_zone()
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
ROOM_TYPES = {"CLASS": "Classroom", "LAB": "Laboratory room", "HALL": "Lecture hall",
              "SPEC": "Specialised room", "SPORT": "Sport and games", "FREEDOM": "Open space",
              "FOOD": "Food and drink", "STUDY": "Study space", "LIBRARY": "Library",
              "WC": "Restroom", "WC_STAFF": "Restroom, staff only", "OFFICE": "Office",
              "INFO": "Information desk", "WARDROBE": "Wardrobe", "SHOP": "Shop", "ROOM": "Room"}

# Words that say nothing about what a room is for. What is left of a question
# after removing them is matched against each room's purpose and name.
PURPOSE_STOPWORDS = {
    "where", "what", "which", "who", "how", "the", "and", "any", "all", "every", "list", "show", "find",
    "need", "want", "get", "there", "here", "near", "nearest", "closest", "can", "you", "tell", "please",
    "are", "is", "a", "an", "of", "in", "on", "at", "to", "for", "me", "my", "i", "do", "does", "go",
    "floor", "block", "building", "campus", "sdu", "room", "rooms", "some", "with", "open", "now",
    "где", "как", "найти", "есть", "все", "мне", "нужен", "нужна", "нужно", "покажи",
}
# Where a question names a room it is coming from, not going to: "I'm in D101".
ORIGIN_RE = re.compile(r"(?:\b(?:in|at|from|near|by|leaving)|\bиз|\bв|\bот|около|возле|рядом с)"
                       r"\s+(?:room\s+|кабинет\w*\s+|аудитори\w*\s+)?$")
CODE_FORMAT_HINT = ("Room codes are a block letter (A to I) and three digits, the first of which is the "
                    "floor: D103 is on floor 1 of Block D.")

# Blocks that do not hang off the central corridor. Blocks A and B are reached
# through the lobby: a foyer runs east from it, with B114 and the Library on its
# north side, Block B's restroom and offices on its south side, and Red Hall
# (Block A) at the far end.
NORTH_BLOCKS = {"A", "B"}
# The foyer's centre line on the floor-1 front sheet; rooms above it are on
# your left as you walk in from the lobby.
NORTH_FOYER_Y = 140.0
BLOCK_ORDER = "ABCDEFGHI"

# Cyrillic letters that look like block letters (people type "Д103", "Н304").
CYR_TO_LAT = str.maketrans({"б": "b", "с": "c", "д": "d", "е": "e", "ф": "f", "г": "g",
                            "н": "h", "и": "i", "і": "i"})
# a block letter B-I, not glued to a preceding letter, then 3 digits
CODE_RE = re.compile(r"(?<![^\W\d_])([b-i])\s?-?\s?(\d{3})(?!\d)")
BARE_NUMBER_RE = re.compile(r"(?<!\d)(\d{3})(?!\d)")
# "block F", "в блоке F", "корпус Д": a block named by its letter inside a sentence
# which of several numbered places: "4", "No. 4", "№4", "#4", "four", "fourth"
TWIN_NUMBER_RE = re.compile(r"(?:\bno\.?|№|#|\bnumber|\bномер)?\s*(?<![\d])(?<!floor )(?<!floor)(?<!этаж )(?<!этаже )"
                            r"([1-9])(?!\s*(?:st|nd|rd|th)?\s*(?:floor|этаж))(?![\d])"
                            r"|\b(one|two|three|four|first|second|third|fourth|один|два|три|четыре|перв\w*|втор\w*|трет\w*|четв[её]рт\w*)\b"
                            r"(?!\s*(?:floor|этаж))")
TWIN_WORDS = {"one": 1, "first": 1, "один": 1, "перв": 1, "two": 2, "second": 2, "два": 2, "втор": 2,
              "three": 3, "third": 3, "три": 3, "трет": 3, "four": 4, "fourth": 4, "четыре": 4, "четв": 4}
# "No. 4" on its own: what the plan prints in a numbered hall
TWIN_ALONE_RE = re.compile(r"^\s*(?:no\.?|№|#|number|номер)\s*([1-9])\s*[?.!]*\s*$")
# "on the 3rd floor", "floor 3", "3 этаж", "на третьем этаже"
FLOOR_WORD_RE = re.compile(r"\b([1-3])(?:st|nd|rd|th)?\s*(?:floor|этаж)|\b(?:floor|этаж[а-яё]*)\s*([1-3])\b"
                           r"|\b(first|second|third|перв|втор|трет)\w*\s+(?:floor|этаж)")
FLOOR_WORDS = {"first": 1, "second": 2, "third": 3, "перв": 1, "втор": 2, "трет": 3}
BLOCK_WORD_RE = re.compile(r"(?:\bblock|блок[а-яё]*|корпус[а-яё]*)\s*-?\s*([a-iабсдефгни])(?![\w])")
BLOCK_LETTER = str.maketrans({"а": "a", "б": "b", "с": "c", "д": "d", "е": "e", "ф": "f",
                              "г": "g", "н": "h", "и": "i"})
# The eight round lecture halls ("barrels") are also called A1..D2. The name is
# stored as a room alias in campus.db; this only finds it inside a sentence.
BARREL_RE = re.compile(r"(?<![a-z0-9])([a-d])\s?-?\s?([12])(?![0-9])")
BARREL_NAME_RE = re.compile(r"^[a-d][12]$")
# Each school has its own dean's office. A question that asks for "the dean's
# office" without saying whose gets the choice; naming the school, its block or
# its faculty ("деканат юридического", "dean's office in Block F") picks one.
DEANERY = "deanery"
DEANERY_WORDS = ["dean's office", "deans office", "dean office", "deanery", "dean", "деканат", "декан"]
CATEGORY_LABELS = {
    "cafeteria": "Canteen", "cafe": "Café", "shop": "Shop", "library": "Library",
    "health_center": "Health centre", "student_services": "Student services", "information": "Information",
    "it_support": "IT support", DEANERY: "Dean's office", "office": "Office", "administrative": "Administration",
    "sport": "Sport", "wardrobe": "Wardrobe", "restroom": "Restroom",
}
# The services page, browsed by category (US15): each group gathers the
# categories a student looks for together. Every category is in exactly one.
SERVICE_GROUPS = [
    ("food", "Food and shops", ("cafeteria", "cafe", "shop")),
    ("study", "Library and study", ("library",)),
    ("health", "Health", ("health_center",)),
    ("students", "Student services", ("student_services", "information", "it_support")),
    ("deans", "Dean's offices", (DEANERY,)),
    ("offices", "Offices", ("office", "administrative")),
    ("facilities", "Facilities", ("sport", "wardrobe", "restroom")),
]
GROUP_OF = {cat: (key, label, n) for n, (key, label, cats) in enumerate(SERVICE_GROUPS) for cat in cats}
# Kinds of room the campus offers many of — the computer and science labs, the
# study spaces — listed on the services page beside the services themselves.
# They have no opening hours: they are booked for classes.
ROOM_COLLECTIONS = [
    ("LAB", "Laboratory rooms", "laboratory", "study"),
    ("STUDY", "Study spaces", "study space", "study"),
    ("HALL", "Lecture halls", "lecture hall", "study"),
]
# Block I has no plan: its east half is copied from Block H, its west half
# placed from a sketch of the floors. Either way the position is a guess.
APPROXIMATE_SOURCES = {"approximated_from_H", "sketch"}

# A west-side room this close to the corridor stands against the corridor wall.
# A question that names where the asker starts as well as where they are going
# ("from G108 to F204", "I'm in D101, where is D105?", "из D101 в F204"): the
# answer is the destination, with the walk from the start (US13).
TRIP_RES = [
    re.compile(r"\b(?:nearest|closest)\s+(?P<b>.+?)\s+(?:from|to|near|for)\s+(?P<a>.+)$"),
    re.compile(r"ближайш\w*\s+(?P<b>.+?)\s+(?:от|к|около|возле|рядом с)\s+(?P<a>.+)$"),
    re.compile(r"\bbetween\s+(?P<a>.+?)\s+and\s+(?P<b>.+)$"),
    re.compile(r"\bfrom\s+(?P<a>.+?)\s+(?:to|till|until)\s+(?P<b>.+)$"),
    # the destination first: "how do I get to Red Hall from D217", "way to the library from G108"
    re.compile(r"(?:\bget\s+to|\bgo\s+to|\bwalk\s+to|\bway\s+to|\breach|\bfind|\bto)\s+(?P<b>.+?)\s+from\s+(?P<a>.+)$"),
    re.compile(r"^(?P<b>[^,]+?)\s+from\s+(?P<a>[^,]+)$"),
    re.compile(r"(?:^|\s)(?:в|во|до|к|ко)\s+(?P<b>.+?)\s+(?:из|от)\s+(?P<a>.+)$"),
    re.compile(r"^(?:route|directions|way)?\s*:?\s*(?P<a>[^,]+?)\s*(?:->|→|=>|—>|–>)\s*(?P<b>.+)$"),
    re.compile(r"\b(?:i'?m|i am|we'?re|we are)\s+(?:in|at|near|by|next to)\s+(?P<a>.+?)\s*[,.;]?\s*"
               r"(?:where(?:'s|\s+is)|how\s+(?:do|can|should)\s+i\s+get\s+to|how\s+to\s+get\s+to|"
               r"how\s+to\s+find|take\s+me\s+to|get\s+to)\s+(?P<b>.+)$"),
    re.compile(r"\bя\s+(?:в|во|у|около|возле|рядом с)\s+(?P<a>.+?)\s*[,.;]?\s*"
               r"(?:где|как\s+(?:пройти|дойти|попасть|добраться)(?:\s+(?:в|во|до|к|ко))?)\s+(?P<b>.+)$"),
    re.compile(r"(?:^|\s)(?:из|от)\s+(?P<a>.+?)\s+(?:в|во|до|к|ко)\s+(?P<b>.+)$"),
]
# A question that asks for the way, not only the place: it gets the walk from
# the main entrance, which is where a route starts unless told otherwise (US14).
ROUTE_WORDS_RE = re.compile(r"how\s+(?:do|can|should)\s+i\s+get|how\s+to\s+get|directions|\broute\b|"
                            r"\bway\s+to\b|take\s+me|как\s+(?:пройти|дойти|попасть|добраться)|маршрут|дорог")
ENTRANCE_WORDS = ("entrance", "main entrance", "the main entrance", "front door", "main door", "the entrance",
                  "вход", "главный вход", "центральный вход", "кіреберіс", "басты кіреберіс")
PLACE_FILLER_RE = re.compile(r"^(?:the|room|аудитори[яюи]|кабинет[а-я]*)\s+|[\s?!.,;:]+$")

WALL_ROOM_REACH = 30.0
# How far away a room on the west side can be and still be called its neighbour.
WEST_NEIGHBOUR_REACH = 250.0


def normalize(text: str) -> str:
    return re.sub(r"[\s\-_'’.()]", "", text.strip().lower())


ENTRANCE_KEYS = {normalize(w) for w in ENTRANCE_WORDS}


def base_name(name: str) -> str:
    """A place's name without the floor note: "Red Canteen (3rd floor)" -> "Red Canteen"."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name or "")


def ordinal(n: int) -> str:
    return ORDINALS.get(n, f"{n}th")


def is_named(room: dict) -> bool:
    """A place known by a name rather than a room number (Library, Red Hall)."""
    return bool(room.get("name")) and room["name"] != room["room_number"] \
        and not room["room_number"].startswith("MEDCENTER")


def display_code(room: dict) -> str:
    if room["room_number"].startswith("MEDCENTER"):
        return "the Medcenter"
    return room["name"] if is_named(room) else room["room_number"]


# Places whose name says what they are rather than what they are called: in a
# sentence they take "the" ("leave the staff restroom", not "leave Staff restroom").
SPOKEN = {
    "Restroom": "the restroom", "Staff restroom": "the staff restroom", "Cafeteria": "the cafeteria",
    "Wardrobe": "the wardrobe", "Information desk": "the information desk",
    "Table tennis": "the table tennis room", "Administration": "the Administration",
    "Library": "the Library", "Advising Desk": "the Advising Desk", "Study Space": "the Study Space",
}


def distinct_name(room: dict) -> str:
    """A room's name, told apart from the others that share it: "Study Space 2",
    "Restroom, Block D". Any other room keeps its own name."""
    return room.get("distinct") or display_code(room)


def spoken(room: dict, start: bool = False) -> str:
    """A room's name as it is said in a sentence: "the restroom", "Red Hall", "D103",
    "Study Space 2"."""
    name = display_code(room)
    twin = room.get("distinct")
    name = twin if twin and ", Block " not in twin else SPOKEN.get(name, name)
    return name[0].upper() + name[1:] if start else name


def ask_text(room: dict) -> str:
    """What to type to get exactly this room back: "Study Space 2", "Red Hall", "D103"."""
    if room["room_number"].startswith("MEDCENTER"):
        return "Medcenter"
    if is_named(room):
        if room["name"] != base_name(room["name"]):
            return room["name"]          # "Red Canteen (3rd floor)" already says which one
        return " ".join(w.capitalize() for w in room["room_number"].split("-"))
    return room["room_number"]


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
        self.named: dict[str, list[dict]] = {}   # normalised name -> rooms that carry it
        self.map = None          # CampusMap, attached after load (see app/main.py)
        self.router = None       # Router, attached after the map (see app/main.py)

    def attach_map(self, campus_map) -> None:
        """Let answers carry positions on the redrawn vector plan as well."""
        self.map = campus_map

    def attach_router(self, router) -> None:
        """Let answers carry walking routes (US13, US14)."""
        self.router = router

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

        for room in sorted(self.rooms, key=self._walk_order):
            if is_named(room):
                self.named.setdefault(normalize(base_name(room["name"])), []).append(room)
        # rooms that share a name are told apart wherever they are named: the four
        # study spaces by their number (from the lobby end), the restrooms by block
        for twins in self.named.values():
            if len(twins) < 2:
                continue
            for room in twins:
                if room["name"] != base_name(room["name"]):
                    continue                    # "Red Canteen (3rd floor)" already says which
                number = re.search(r"-(\d+)$", room["room_number"])
                room["distinct"] = (f"{room['name']} {number.group(1)}" if number
                                    else f"{room['name']}, Block {room['building_id']}")

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
            self.services[r["service_id"]] = {**dict(r), "hours": {}, "aliases": [], "more_rooms": []}
        # a day can hold several intervals: a lunch break is the gap between two
        for r in conn.execute("SELECT * FROM service_hours ORDER BY open_time"):
            self.services[r["service_id"]]["hours"].setdefault(r["day_of_week"], []).append(
                (r["open_time"], r["close_time"]))
        has_rooms = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'service_rooms'").fetchone()
        for r in (conn.execute("SELECT * FROM service_rooms") if has_rooms else []):
            self.services[r["service_id"]]["more_rooms"].append(r["room_id"])
        for r in conn.execute("SELECT * FROM service_aliases"):
            self.services[r["service_id"]]["aliases"].append(normalize(r["alias"]))

    @staticmethod
    def _walk_order(room: dict) -> tuple:
        """Floor, then block along the corridor, then position on the sheet."""
        return (room["floor_number"], BLOCK_ORDER.find(room["building_id"]), room["y"])

    def _geometry_sheet(self, room: dict) -> str | None:
        # Block I has no digitised plan of its own; it mirrors Block H.
        if room["building_id"] == "I":
            h_floor = self.floors.get(f"H-{room['floor_number']}")
            return h_floor["sheet_id"] if h_floor else None
        return room["sheet_id"]

    def _zone(self, room: dict) -> str:
        if room["building_id"] in NORTH_BLOCKS:
            return "north"
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
            "measured_rooms": sum(1 for r in self.rooms if r["source"] not in APPROXIMATE_SOURCES),
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
        """The services page: every service with where it is and whether it is
        open, in category order, then the kinds of room there are many of."""
        out = [self._service_payload(s, now) for s in self.services.values()]
        for rtype, label, ask, group in ROOM_COLLECTIONS:
            rooms = sorted((r for r in self.rooms if r["type"] == rtype), key=self._walk_order)
            if not rooms:
                continue
            key, group_label, order = next((k, l, n) for n, (k, l, _) in enumerate(SERVICE_GROUPS) if k == group)
            out.append({
                "kind": "rooms", "service_id": f"ROOMS_{rtype}", "name": label, "short_name": None,
                "category": rtype.lower(), "category_label": label,
                "group": key, "group_label": group_label, "group_order": order,
                "open_now": None, "status": f"{len(rooms)} rooms, booked for classes", "hours": [],
                "hours_approximate": False, "notes": None, "ask": ask,
                "location": self._spread(rooms),
            })
        # services first within a group, the kinds of room after them
        out.sort(key=lambda s: (s["group_order"], s["kind"] == "rooms", s["category_label"] or "", s["name"]))
        return out

    def _spread(self, rooms: list[dict]) -> dict:
        """Where a set of rooms is, in one line: the blocks and floors they cover."""
        blocks = sorted({r["building_id"] for r in rooms}, key=BLOCK_ORDER.find)
        floors = sorted({r["floor_number"] for r in rooms})
        blk = (f"Block {blocks[0]}" if len(blocks) == 1 else
               f"Blocks {blocks[0]}–{blocks[-1]}" if len(blocks) > 2 and
               "".join(blocks) in BLOCK_ORDER else f"Blocks {human_list(blocks)}")
        flr = (f"Floor {floors[0]}" if len(floors) == 1 else
               f"Floors {floors[0]}–{floors[-1]}" if floors == list(range(floors[0], floors[-1] + 1))
               else f"Floors {human_list([str(f) for f in floors])}")
        return {"count": len(rooms), "blocks": blocks, "floors": floors, "text": f"{blk} · {flr}"}

    def _service_location(self, svc: dict) -> dict | None:
        """Room, block and floor of a service; for one with a room in many blocks
        (the restrooms), the blocks and floors it covers."""
        room = next((r for r in self.rooms if r["room_id"] == svc.get("room_id")), None)
        if room:
            return {"room": display_code(room), "code": room["room_number"],
                    "building_id": room["building_id"], "floor_number": room["floor_number"],
                    "text": f"Block {room['building_id']} · Floor {room['floor_number']}"
                            + (f" · {room['room_number']}" if not is_named(room)
                               and not room["room_number"].startswith("MEDCENTER") else "")}
        rooms = self.named.get(normalize(svc["name"]), [])
        return self._spread(rooms) if rooms else None

    def search(self, query: str, now: datetime | None = None, context: str | None = None) -> dict:
        """Answer a question. `context` is the room number a previous answer
        asked the user to pick a block for, so "204" then "Engineering" works."""
        t0 = time.perf_counter()
        result = self._trip(query, now) or self._search(query, now, context)
        if (self.router and "directions" not in result and ROUTE_WORDS_RE.search(query.lower())
                and self._place_of(result)):
            result["directions"] = self.router.route(self.entrance(), self._place_of(result))
        result.setdefault("context", None)
        result["query"] = query
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        return result

    # ------------------------------------------------------------ directions
    def entrance(self) -> dict:
        from .routing import MAIN_ENTRANCE
        return self.router.place("exit", MAIN_ENTRANCE)

    def _place_of(self, answer: dict) -> dict | None:
        """The room an answer puts on the plan, as a place a route can end at
        (of several places with one name, the first; a start picks the nearest)."""
        if not self.router or (answer.get("kind") not in ("room", "service", "block")
                               and not answer.get("several")):
            return None
        code = (answer.get("map") or {}).get("code")
        return self.router.place("room", code) if code else None

    def resolve_place(self, text: str | None) -> tuple[dict | None, dict | None]:
        """Where a route starts or ends, from what someone typed: the main
        entrance (also when nothing is typed), an exit by its name, or anything
        the search understands. Returns (place, the search answer if it failed)."""
        raw = PLACE_FILLER_RE.sub("", (text or "").strip())
        raw = PLACE_FILLER_RE.sub("", raw)
        key = normalize(raw)
        if not key or key in ENTRANCE_KEYS:
            return self.entrance(), None
        for exit_id, ex in self.router.exits.items():
            if key in (normalize(ex["name"]), normalize("the " + ex["name"])):
                return self.router.place("exit", exit_id), None
        answer = self._search(raw, None)
        place = self._place_of(answer)
        return place, (None if place else answer)

    def _nearest_of_name(self, origin: dict, dest: dict, now: datetime | None,
                         asked: str = "") -> tuple[dict, dict | None]:
        """Several rooms share a name (restrooms, study spaces): from a known start,
        the one to walk to is the nearest, not the first from the lobby. A question
        that names which one ("Red Canteen 3rd floor", RED-CANTEEN-3) gets that one."""
        room = next(r for r in self.rooms if r["room_number"] == dest["key"])
        # "Study Space 4", STUDY-SPACE-4, "Red Canteen 3rd floor" name which one:
        # only a name any of them answers to ("study space") is the nearest
        if not is_named(room) or asked.strip().upper() == room["room_number"] or (
                asked and normalize(asked) != normalize(base_name(room["name"]))):
            return dest, None
        same = self.named.get(normalize(base_name(room.get("name") or ""))) if is_named(room) else None
        if not same or len(same) < 2:
            return dest, None
        places = [p for p in (self.router.place("room", r["room_number"]) for r in same) if p]
        best = min(places, key=lambda p: self.router.distance(origin, p))
        if best["key"] == dest["key"]:
            return dest, None
        chosen = next(r for r in same if r["room_number"] == best["key"])
        answer = self._room_or_service(chosen, now)
        answer["note"] = " ".join(filter(None, [
            answer.get("note"), f"The plans mark {len(same)} places called {base_name(room['name'])}; "
                                f"this is the nearest one to {origin['label']}."]))
        answer["suggestions"] = [ask_text(r) for r in same]
        return best, answer

    def _trip(self, query: str, now: datetime | None) -> dict | None:
        """A question that names a start and a destination: the destination's
        answer, with the walk from the start. None when it is not such a question."""
        if not self.router:
            return None
        lowered = query.lower().strip()
        m = next((m for m in (r.search(lowered) for r in TRIP_RES) if m), None)
        if not m:
            return None
        frm, to = m.group("a"), m.group("b")
        answer = self._search(PLACE_FILLER_RE.sub("", to.strip()), now)
        dest = self._place_of(answer)
        if not dest:
            return None
        origin, _ = self.resolve_place(frm)
        note = None
        if origin is None:
            origin = self.entrance()
            note = (f"I couldn't tell where \u201c{frm.strip(' ,.?')}\u201d is, so the route starts at "
                    f"the main entrance. Pick your start under the route to change it.")
        elif answer.get("several"):
            dest, answer = self._nearest_of_several(origin, answer["several"], now)
        else:
            dest, nearer = self._nearest_of_name(origin, dest, now, PLACE_FILLER_RE.sub("", to.strip()))
            if nearer:
                answer = nearer
        if answer.get("several"):
            # no start to measure from: the first of them, on a card of its own
            answer = self._room_or_service(next(r for r in self.rooms if r["room_number"] == dest["key"]), now)
        answer["directions"] = self.router.route(origin, dest)
        if note:
            answer["directions"]["note"] = " ".join(filter(None, [note, answer["directions"].get("note")]))
        return answer

    def directions(self, to: str, frm: str | None = None) -> dict:
        """GET /api/route: the walk to a place, from the main entrance unless a
        start is given (US14: the start can be any room)."""
        dest_answer = self._search(PLACE_FILLER_RE.sub("", (to or "").strip()), None)
        dest = self._place_of(dest_answer)
        if not dest:
            return {"kind": "route_error", "title": f"I couldn't find \u201c{to}\u201d",
                    "summary": "Name the place you're going to the way you'd search for it: a room code "
                               "like D103, a hall like A1, or a service like the library.",
                    "suggestions": dest_answer.get("suggestions", [])}
        origin, failed = self.resolve_place(frm)
        if origin is None:
            return {"kind": "route_error", "title": f"I couldn't tell where \u201c{frm}\u201d is",
                    "summary": "Start from a room code like D103, a named place like the Library, "
                               "or the main entrance.",
                    "suggestions": (failed or {}).get("suggestions", [])}
        if dest_answer.get("several"):
            dest, _ = self._nearest_of_several(origin, dest_answer["several"], None)
        else:
            dest, _ = self._nearest_of_name(origin, dest, None, PLACE_FILLER_RE.sub("", (to or "").strip()))
        return self.router.route(origin, dest)

    def _nearest_of_several(self, origin: dict, codes: list[str], now: datetime | None) -> tuple[dict, dict]:
        """Of several places that answer a question, the one nearest the start, and
        its card, which says there are others."""
        places = [p for p in (self.router.place("room", c) for c in codes) if p]
        best = min(places, key=lambda p: self.router.distance(origin, p))
        room = next(r for r in self.rooms if r["room_number"] == best["key"])
        answer = self._room_or_service(room, now)
        others = [ask_text(r) for r in self.rooms if r["room_number"] in codes]
        answer["note"] = " ".join(filter(None, [
            answer.get("note"), f"The plans mark {len(codes)} places like this; "
                                f"this is the nearest one to {origin['label']}."]))
        answer["suggestions"] = others
        return best, answer

    # --------------------------------------------------------------- search
    def _search(self, query: str, now: datetime | None, context: str | None = None) -> dict:
        lowered = query.lower().translate(CYR_TO_LAT)
        qn = normalize(query)

        # exactly a room's code or alias: "D103", "A1", "Red Hall", "Study Space 2" —
        # unless it is the name several places share ("Red Canteen"): then all of them
        room = self.by_code.get(qn)
        if room:
            twins = self.named.get(qn, []) if is_named(room) else []
            if len(twins) > 1 and room in twins and query.strip().upper() != room["room_number"]:
                return self._named_answer(twins, now, floors=self._floors_in(query), query=query)
            return self._room_or_service(room, now)

        m = self._target(lowered, list(CODE_RE.finditer(lowered)))
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
        blocks = self._buildings_in(qn, normalize(lowered), query.lower())
        found_number = self._target(query.lower(), list(BARE_NUMBER_RE.finditer(query)))
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

        # the most specific service wins: "red canteen" before "canteen"
        best, best_len, best_alias = None, 0, ""
        for svc in self.services.values():
            for alias in svc["aliases"] + [normalize(svc["name"])]:
                if alias in qn and len(alias) > best_len:
                    best, best_len, best_alias = svc, len(alias), alias
        # a named room asked for more exactly than any service: "how do I get to red
        # canteen 3rd floor" is the 3rd-floor hall, not the 1st-floor Red Canteen
        named_room, named_len = None, best_len
        for alias, room in self.by_code.items():
            if len(alias) > named_len and is_named(room) and alias in qn \
                    and not re.search(re.escape(alias) + r"(?<=\d)(?:\d|st|nd|rd|th)", qn):
                # "studyspace3" is not in "study space 3rd floor"
                named_room, named_len = room, len(alias)
        if named_room:
            return self._room_or_service(named_room, now)
        generic = max((len(normalize(w)) for w in DEANERY_WORDS if normalize(w) in qn), default=0)
        # a school named in the question settles whose dean's office it is
        if generic and (best is None or best["category"] != DEANERY):
            return self._deanery_answer(blocks, now)
        if best:
            if not best.get("room_id") and normalize(best["name"]) in self.named:
                # restrooms: one service, a room in almost every block
                return self._named_answer(self.named[normalize(best["name"])], now, blocks,
                                          self._floors_in(query), query)
            home = next((r for r in self.rooms if r["room_id"] == best.get("room_id")), None)
            if home is not None and is_named(home) and not blocks:
                twins = self.named.get(normalize(base_name(home["name"])), [home])
                # a word that is also part of other places' names: "canteen" is the
                # Cafeteria, and the two Red Canteens too
                alike = [] if best_alias == normalize(base_name(home["name"])) else [
                    r for key, rooms in self.named.items() if best_alias in key for r in rooms if r not in twins]
                if alike:
                    return self._several(twins + alike, now, f"{len(twins + alike)} places for \u201c{query.strip(' ?.!')}\u201d")
                if len(twins) > 1:
                    # "Red Canteen": one on floor 1, one on floor 3
                    return self._named_answer(twins, now, blocks, self._floors_in(query), query)
            return self._service_answer(best, now)

        names = [name for name in self.named if name in qn]
        if names:
            return self._named_answer(self.named[max(names, key=len)], now, blocks, self._floors_in(query), query)

        if found_number:
            matches = [r for r in self.rooms
                       if re.search(rf"(?<!\d){found_number.group(1)}$", r["room_number"])]
            matches = [r for r in matches if r["source"] not in APPROXIMATE_SOURCES] or matches
            if len(matches) == 1:
                return self._room_answer(matches[0])
            if matches:
                return self._ambiguous(found_number.group(1), matches)

        alone = TWIN_ALONE_RE.match(lowered)
        if alone:
            n = alone.group(1)
            halls = [r for r in self.rooms if re.search(rf" {n}$", r.get("distinct") or "")]
            if len(halls) == 1:
                return self._room_or_service(halls[0], now)

        listing = self._purpose_answer(lowered, blocks)
        if listing:
            # every match one of several places with one name ("No4 study"): that group
            codes = {r["code"] for r in listing["results"]}
            group = next((rooms for rooms in self.named.values()
                          if len(rooms) > 1 and codes == {r["room_number"] for r in rooms}), None)
            if group:
                return self._named_answer(group, now, blocks, self._floors_in(query), query)
            return listing

        if blocks:
            return self._block_answer(blocks[0])

        return {
            "kind": "no_match",
            "title": "I couldn't tell which place you mean",
            "summary": "Try a room code like D103 or H304, a faculty such as the Business School, "
                       "or a service like library, cafeteria, dean's office or medcenter.",
            "suggestions": ["D103", "G215", "Red Hall", "Library"],
        }

    def _deanery_answer(self, blocks: list[str], now: datetime | None) -> dict:
        """'Where is the dean's office?' — whose? One per school."""
        by_id = {r["room_id"]: r for r in self.rooms}
        offices = sorted((s for s in self.services.values() if s["category"] == DEANERY),
                         key=lambda s: self._walk_order(by_id[s["room_id"]]))
        mine = [s for s in offices if by_id[s["room_id"]]["building_id"] in blocks]
        if len(mine) == 1:
            return self._service_answer(mine[0], now)
        where = [f"{s['name']} ({display_code(by_id[s['room_id']])}, floor "
                 f"{by_id[s['room_id']]['floor_number']})" for s in offices]
        return {
            "kind": "ambiguous",
            "title": "Each school has its own dean's office",
            "summary": f"There are {len(offices)}: {human_list(where)}. Which school are you in?",
            "suggestions": [s["name"] for s in offices],
        }

    @staticmethod
    def _floors_in(query: str) -> list[int]:
        """Which floors a question names: "on the 3rd floor", "floor 1", "3 этаж"."""
        found = []
        for m in FLOOR_WORD_RE.finditer(query.lower()):
            digit = m.group(1) or m.group(2)
            n = int(digit) if digit else FLOOR_WORDS[m.group(3)]
            if n not in found:
                found.append(n)
        return found

    def _buildings_in(self, qn: str, latin: str, raw: str = "") -> list[str]:
        """Which blocks a question names, most specific alias first."""
        found: list[str] = []
        for alias, building_id in self.building_aliases:
            if alias and alias in qn and building_id not in found:
                found.append(building_id)
        for m in BLOCK_WORD_RE.finditer(raw):
            letter = m.group(1).translate(BLOCK_LETTER).upper()
            if letter in self.buildings and letter not in found:
                found.append(letter)
        # a one-letter reply to "which block did you mean?"
        if not found and re.fullmatch(r"[a-i]", latin):
            found.append(latin.upper())
        return found

    @staticmethod
    def _target(text: str, matches: list) -> "re.Match | None":
        """Of several room codes in one question, the one asked about: not the
        one the asker is in ("I'm in D101, where is D105?"), else the last."""
        if len(matches) < 2:
            return matches[0] if matches else None
        going = [m for m in matches if not ORIGIN_RE.search(text[:m.start()])]
        return (going or matches)[-1]

    def _ambiguous(self, digits: str, matches: list[dict]) -> dict:
        codes = sorted(r["room_number"] for r in matches)
        floors = sorted({r["floor_number"] for r in matches})
        on = (f"all on floor {floors[0]}" if len(floors) == 1
              else f"on floors {human_list([str(f) for f in floors])}")
        return {
            "kind": "ambiguous",
            "title": f"Several blocks have a room {digits}",
            "summary": f"There's a {digits} in {len(codes)} blocks: {human_list(codes)}, {on}. "
                       f"Which one did you mean? Naming the block or the faculty is enough.",
            "suggestions": codes,
            "context": digits,
        }

    def _purpose_answer(self, lowered: str, blocks: list[str]) -> dict | None:
        """Every room whose purpose or name holds a word of the question ("computer
        lab", "lecture halls in Block D"), the closest textual match first."""
        words = [w for w in re.findall(r"[a-zа-яёәіңғүұқөһ']+", lowered)
                 if len(w) >= 3 and w not in PURPOSE_STOPWORDS]
        if not words:
            return None
        phrase = " ".join(words)
        stems = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]   # "labs" finds "Laboratory room"
        scored = []
        for room in self.rooms:
            if blocks and room["building_id"] not in blocks:
                continue
            purpose = (room.get("purpose") or "").lower()
            name = (room.get("name") or "").lower() if is_named(room) else ""
            hits = [w for w in stems if w in purpose or w in name]
            if not hits:
                continue
            score = len(hits)
            if purpose == phrase or name == phrase:
                score += 3            # the whole question is the purpose: "lecture hall"
            elif phrase in purpose or phrase in name:
                score += 2
            if any(purpose.startswith(w) or name.startswith(w) for w in hits):
                score += 1
            scored.append((score, room))
        if not scored:
            return None
        top = max(s for s, _ in scored)
        rooms = [r for s, r in sorted(scored, key=lambda sr: (-sr[0], self._walk_order(sr[1])))
                 if s >= top - 1]                     # keep the close matches, drop the stragglers
        first = rooms[0]
        what = first.get("purpose") or "room"
        where = f" in Block {human_list(blocks)}" if blocks else ""
        answer = self._room_answer(first)
        if answer.get("map"):
            for r in rooms[1:]:
                point = self.map.room_point(r["room_number"])
                if point and point["floor"] == first["floor_number"]:
                    answer["map"]["highlights"].append({"room_number": r["room_number"], "role": "neighbour",
                                                        "x": point["x"], "y": point["y"]})
        return {
            "kind": "list",
            "title": f"{len(rooms)} {'match' if len(rooms) == 1 else 'matches'} for \u201c{phrase}\u201d{where}",
            "summary": f"Every room whose purpose or name matches, closest first. The first is "
                       f"{display_code(first)}, a {what.lower()} on floor {first['floor_number']} of Block "
                       f"{first['building_id']}; tap any other to see its way.",
            "results": [{"room_number": display_code(r).removeprefix("the ").capitalize()
                         if r["room_number"].startswith("MEDCENTER") else display_code(r),
                         "code": r["room_number"], "ask": ask_text(r), "purpose": r.get("purpose"),
                         "building_id": r["building_id"], "floor_number": r["floor_number"]} for r in rooms],
            "map": answer.get("map"), "route": answer.get("route"), "room": answer.get("room"),
            "suggestions": [],
        }

    def _block_answer(self, building_id: str) -> dict:
        """Where a whole block or faculty is, when the question names no room."""
        rooms = [r for r in self.rooms if r["building_id"] == building_id]
        name = self.buildings.get(building_id, f"Block {building_id}")
        floors = sorted({r["floor_number"] for r in rooms})
        entry = min((r for r in rooms if r["zone"] in ("wing", "north")),
                    key=lambda r: (r["floor_number"], r["x"]), default=rooms[0])
        directions = self._room_answer(entry)
        floor_text = ("floor " + str(floors[0]) if len(floors) == 1
                      else f"floors {floors[0]} to {floors[-1]}")
        start = "you reach it through the foyer, at" if entry["zone"] == "north" else "its wings start at"
        return {
            "kind": "block",
            "title": f"Block {building_id}",
            "summary": f"{name}. {len(rooms)} room{'s' if len(rooms) != 1 else ''} on {floor_text}; "
                       f"{start} {display_code(entry)}.",
            "block": {"building_id": building_id, "name": name,
                      "floors": floors, "rooms": len(rooms)},
            "steps": directions["steps"][:3],
            "route": directions["route"],
            "map": directions["map"],
            "suggestions": [ask_text(r) for r in sorted(
                (r for r in rooms if r["zone"] in ("wing", "north") and r["floor_number"] == floors[0]),
                key=lambda r: r["x"])][:4],
            "note": None,
        }

    def _not_found(self, code: str) -> dict:
        close = difflib.get_close_matches(code.lower(), list(self.by_code.keys()), n=6, cutoff=0.5)
        seen, suggestions = set(), []
        for key in close:
            near = self.by_code[key]
            rn = near["room_number"]
            if rn not in seen and not rn.startswith("MEDCENTER") and not is_named(near):
                seen.add(rn)
                suggestions.append(rn)
        suggestions = suggestions[:3]
        summary = f"There's no room {code} on the evacuation plans I've digitised. {CODE_FORMAT_HINT}"
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
                         "and its classroom wings repeat the Block H layout.")

        zone = room["zone"]
        door: dict = {}
        if zone == "wing":
            if bid != "I":
                steps.append(f"Follow the central corridor to {block_label} and turn into the {block_label} wing.")
            steps.append(self._wing_step(room, highlights, door))
        elif zone == "corridor":
            steps.append(self._corridor_step(room, block_label, highlights))
        elif zone == "west":
            steps.append(self._west_step(room, block_label, highlights, door))
        elif zone == "north":
            steps.append(self._north_step(room, highlights, door))
        else:
            steps.append(f"Find {code} in {block_label}.")
        route = self._route(room, door)

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
        svc = self.service_of(room)
        if svc and svc["name"] != display_code(room):
            facts.append(svc["name"])

        note = None
        if room["source"] == "approximated_from_H":
            note = ("Block I isn't digitised yet — this position is copied from the matching Block H room, "
                    "so treat the door order as a best guess.")
        elif room["source"] == "sketch":
            note = ("Block I isn't digitised yet — this room is placed from a sketch of the floor, "
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

        name = distinct_name(room)
        return {
            "kind": "room",
            "map": self._map_payload(room, highlights, landmark),
            "title": name,
            "summary": (f"{name}{f' (hall {hall})' if hall else ''} is on floor {floor} "
                        f"of {building_name}."),
            "room": {"room_number": name, "building_id": bid, "building_name": building_name,
                     "purpose": room.get("purpose"),
                     "floor_number": floor, "zone": zone, "facts": facts, "source": room["source"]},
            "steps": steps, "route": route, "note": note, "plan": plan, "suggestions": [],
        }

    def _map_payload(self, room: dict, highlights: list[dict], landmark: dict | None) -> dict | None:
        """The same answer, in the coordinates of the redrawn vector floor plan."""
        if self.map is None:
            return None
        here = self.map.room_point(room["room_number"])
        if here is None:
            return None
        payload = {"floor": room["floor_number"], "room_number": distinct_name(room),
                   "code": room["room_number"],
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

    def _wing_step(self, room: dict, highlights: list[dict], door: dict | None = None) -> str:
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
        if door is not None:
            door.update(pos=pos, side=side, last=pos == len(row) and pos > 1)
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

    def _route(self, room: dict, door: dict) -> list[dict]:
        """The answer as a directional sign: three or four short panels, each an
        arrow and a few words, read left to right like the signs in the corridor.
        The sentences in `steps` say the same thing in full."""
        bid, floor, zone = room["building_id"], room["floor_number"], room["zone"]
        route = [{"icon": "entrance", "text": "Main lobby"}]
        if floor > 1:
            route.append({"icon": "stairs", "text": f"Floor {floor}"})
        if zone == "north":
            route.append({"icon": "ahead", "text": "Block B foyer"})
        elif zone == "wing":
            route.append({"icon": "ahead", "text": f"Block {bid} wing"})
        else:
            route.append({"icon": "ahead", "text": f"Block {bid}"})

        if door.get("last"):
            route.append({"icon": "ahead", "text": "Far end" if zone == "north" else "Last door"})
        elif door.get("pos"):
            side = door.get("side")
            text = f"{ordinal(door['pos']).capitalize()} door" + (f", {side}" if side else "")
            route.append({"icon": side or "ahead", "text": text})
        elif zone == "corridor":
            route.append({"icon": "door", "text": "On the corridor"})
        elif zone == "west" and door.get("opposite"):
            route.append({"icon": "door", "text": f"Opposite {door['opposite']}"})
        elif zone == "west":
            route.append({"icon": "door", "text": "Across the corridor"})
        return route

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
        code = spoken(room)
        base = (f"When you reach {block_label}, look along the central corridor itself — "
                f"{code} opens straight onto it rather than into a wing.")
        if above and below:
            return base + f" It's between {spoken(above[0])} and {spoken(below[0])}."
        if above or below:
            return base + f" It's right next to {spoken((above or below)[0])}."
        return base

    def _across(self, room: dict) -> dict | None:
        """For a room built against the corridor's west wall: the corridor room
        facing it on the other side, if one is close."""
        geo = self.sheets.get(room["geo_sheet_id"] or "")
        if not geo or room["x"] < geo["west_max_x"] - WALL_ROOM_REACH:
            return None
        facing = [r for r in self.rooms if r["floor_id"] == room["floor_id"] and r["zone"] == "corridor"]
        best = min(facing, key=lambda r: abs(r["y"] - room["y"]), default=None)
        return best if best and abs(best["y"] - room["y"]) <= 40 else None

    def _west_step(self, room: dict, block_label: str, highlights: list[dict],
                   door: dict | None = None) -> str:
        code = spoken(room)
        opposite = self._across(room)
        if opposite:
            highlights.append({"room_number": opposite["room_number"], "x": opposite["x"],
                               "y": opposite["y"], "role": "opposite"})
            if door is not None:
                door["opposite"] = display_code(opposite)
            return (f"When you reach {block_label}, keep to the left-hand wall of the central corridor — "
                    f"{code} is right there, directly across from {spoken(opposite)}.")
        if room["building_id"] == "C" and room["floor_number"] == 1:
            near = sorted((r for r in self._peers(room) if r["zone"] == "west" and r["building_id"] == "C"),
                          key=lambda r: (r["x"] - room["x"]) ** 2 + (r["y"] - room["y"]) ** 2)[:1]
            for r in near:
                highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "neighbour"})
            return (f"{spoken(room, start=True)} is in the main lobby itself, on the entrance side"
                    + (f", next to {spoken(near[0])}." if near else "."))
        if room["building_id"] in ("D", "E") and room["floor_number"] in (1, 2):
            place = "the round lecture halls (the \"barrels\")"
        elif room["building_id"] in ("D", "E") and room["floor_number"] == 3:
            place = "the round study spaces"
        else:
            place = "the rooms on that side"
        sentence = (f"At {block_label}, cross to the opposite side of the central corridor from the classroom wings — "
                    f"{code} is among {place}.")

        twins = self._twins(room)
        if twins:
            # four rooms all called "Study Space": say which one, not "next to Study Space"
            pos = twins.index(room)
            for r in twins[max(pos - 1, 0):pos] + twins[pos + 1:pos + 2]:
                highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "neighbour"})
            return sentence + (f" There are {len(twins)} of them on this floor; this is the "
                               f"{ordinal(pos + 1)} from the lobby end.")

        peers = [r for r in self._peers(room) if r["zone"] == "west"
                 and math.hypot(r["x"] - room["x"], r["y"] - room["y"]) <= WEST_NEIGHBOUR_REACH]
        # prefer neighbours from the same block, fall back to anything close on the sheet
        near = sorted(peers, key=lambda r: (r["building_id"] != room["building_id"],
                                            (r["x"] - room["x"]) ** 2 + (r["y"] - room["y"]) ** 2))[:2]
        for r in near:
            highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "neighbour"})
        if near:
            sentence += f" Look for it next to {human_list([spoken(r) for r in near])}."
        return sentence

    def _twins(self, room: dict) -> list[dict]:
        """The rooms on this floor that share the room's name, in walking order —
        empty unless there is more than one."""
        if not is_named(room):
            return []
        same = [r for r in self.named.get(normalize(base_name(room["name"])), [])
                if r["floor_number"] == room["floor_number"]]
        return same if len(same) > 1 else []

    def _north_step(self, room: dict, highlights: list[dict], door: dict | None = None) -> str:
        """Blocks A and B: count the doors along the foyer that runs east from the lobby."""
        row = sorted((r for r in self.rooms if r["zone"] == "north"
                      and r["floor_number"] == room["floor_number"]), key=lambda r: r["x"])
        code = spoken(room, start=True)       # it starts the sentence after the intro
        intro = ("From the lobby, go through to the Block B foyer — the wide hall that runs east "
                 "from the lobby's north-east side.")
        if room is row[-1] and len(row) > 1:
            if door is not None:
                door.update(pos=len(row), side=None, last=True)
            before = [r for r in row[:-1] if r["y"] < NORTH_FOYER_Y][-2:] or row[-3:-1]
            for r in before:
                highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "passed"})
            return (f"{intro} {code} is at the far end of it; you'll pass "
                    f"{human_list([spoken(r) for r in before])} on the way.")
        north = room["y"] < NORTH_FOYER_Y
        side = "left" if north else "right"
        same = [r for r in row[:-1] if (r["y"] < NORTH_FOYER_Y) == north]
        pos = same.index(room) + 1
        if door is not None:
            door.update(pos=pos, side=side, last=False)
        before = same[:pos - 1][-2:]
        for r in before:
            highlights.append({"room_number": r["room_number"], "x": r["x"], "y": r["y"], "role": "passed"})
        if pos == 1:
            return f"{intro} {code} is the first door on your {side}."
        return (f"{intro} {code} is the {ordinal(pos)} door on your {side}, just after "
                f"{human_list([spoken(r) for r in before])}.")

    def _fallback_landmark(self, room: dict) -> str:
        """US1 wants a recognisable landmark with every answer. Where no exit or
        stairwell is close enough, the room's own surroundings are the landmark."""
        block = f"Block {room['building_id']}"
        if room["zone"] == "north":
            return "the main lobby with the Wi-Fi Zone, at the west end of the foyer"
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
        if room["zone"] == "north":
            # Blocks A and B share one foyer, and its exits
            candidates = [lm for fid, items in self.landmarks.items()
                          if self.floors[fid]["building_id"] in NORTH_BLOCKS
                          and self.floors[fid]["floor_number"] == room["floor_number"] for lm in items]
        if room["building_id"] == "I":
            candidates = []  # no plan of our own, don't point at Block H's exits
        best, best_d = None, None
        for lm in candidates:
            if lm["name"].lower() == display_code(room).lower():
                continue  # the wardrobe is no landmark for the wardrobe
            d = ((lm["x"] - room["x"]) ** 2 + (lm["y"] - room["y"]) ** 2) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = lm, d
        return best if best_d is not None and best_d <= 320 else None

    # --------------------------------------------------------------- services
    def _service_payload(self, svc: dict, now: datetime | None) -> dict:
        # opening hours are campus time: a moment given in any other zone (a UTC
        # server clock) is turned into Almaty time first; a naive one already is
        now = now.astimezone(CAMPUS_TZ) if now and now.tzinfo else (now or datetime.now(CAMPUS_TZ))
        hours = svc["hours"]
        status, open_now = "Opening hours aren't on file yet", None
        if hours:
            dow, hhmm = now.weekday(), now.strftime("%H:%M")
            today = hours.get(dow, [])
            current = next(((o, c) for o, c in today if o <= hhmm < c), None)
            later = [o for o, _ in today if o > hhmm]
            if current:
                open_now = True
                # "until 12:30" before lunch would read as closing for the day
                gap = next((o for o, _ in today if o >= current[1]), None)
                status = (f"Open until {current[1]}, back at {gap} after lunch" if gap
                          else f"Open until {current[1]}")
            elif later and today and today[0][0] <= hhmm:
                open_now, status = False, f"Lunch break, back at {later[0]}"
            elif later:
                open_now, status = False, f"Closed, opens today at {later[0]}"
            else:
                open_now = False
                for i in range(1, 8):
                    d = (dow + i) % 7
                    if hours.get(d):
                        when = "tomorrow" if i == 1 else DAY_NAMES[d]
                        status = f"Closed, opens {when} at {hours[d][0][0]}"
                        break
        table = []
        for d, intervals in sorted(hours.items()):
            breaks = [f"{intervals[i][1]}–{intervals[i + 1][0]}" for i in range(len(intervals) - 1)]
            table.append({"day": DAY_NAMES[d], "open": intervals[0][0], "close": intervals[-1][1],
                          "break": breaks[0] if breaks else None})
        group, group_label, order = GROUP_OF.get(svc["category"], ("other", "Other", len(SERVICE_GROUPS)))
        return {"kind": "service", "service_id": svc["service_id"], "name": svc["name"],
                "short_name": svc.get("short_name"),
                "category": svc["category"], "category_label": CATEGORY_LABELS.get(svc["category"]),
                "group": group, "group_label": group_label, "group_order": order,
                "open_now": open_now, "status": status, "hours": table,
                "hours_approximate": not svc.get("hours_confirmed"),
                "notes": svc.get("notes"), "ask": svc["name"],
                "location": self._service_location(svc)}

    def _service_answer(self, svc: dict, now: datetime | None) -> dict:
        payload = self._service_payload(svc, now)
        notes = (["These opening hours are the team's best reading and not yet confirmed by the service itself."]
                 if payload["hours"] and payload["hours_approximate"] else [])
        room = next((r for r in self.rooms if r["room_id"] == svc.get("room_id")), None)
        more = [r for r in self.rooms if r["room_id"] in svc["more_rooms"]]
        if room and more:
            notes.append(f"It takes {human_list([display_code(room)] + [display_code(r) for r in more])}; "
                         f"the route goes to {display_code(room)}, the next door is the same office.")
        others = [r for r in self.named.get(normalize(base_name(room["name"])), [])
                  if r["floor_number"] != room["floor_number"]] if room else []
        if others:
            notes.append(f"The plans also mark {base_name(svc['name'])} on floor "
                         f"{human_list(sorted({str(r['floor_number']) for r in others}))}.")
        result = {"kind": "service", "title": svc["name"], "service": payload,
                  "suggestions": [ask_text(r) for r in others], "note": " ".join(notes) or None}
        if room:
            directions = self._room_answer(room)
            result.update({"summary": f"{svc['name']} is on floor {room['floor_number']} of "
                                      f"{self.buildings.get(room['building_id'])}. {payload['status']}.",
                           "steps": directions["steps"], "route": directions["route"],
                           "plan": directions["plan"],
                           "map": directions["map"], "room": directions["room"]})
            if directions.get("note"):   # e.g. Block I's position is a copy of Block H's
                result["note"] = " ".join(filter(None, [result["note"], directions["note"]]))
            for r in more:
                point = self.map.room_point(r["room_number"]) if self.map else None
                if point and result["map"]:
                    result["map"]["highlights"].append({"room_number": r["room_number"], "role": "neighbour",
                                                        "x": point["x"], "y": point["y"]})
        else:
            result.update({"summary": f"{payload['status']}. Its exact room isn't on the digitised plans yet.",
                           "steps": [], "plan": None, "map": None})
        return result

    def service_of(self, room: dict) -> dict | None:
        """The service a room houses. Rooms of one place on the same floor (the
        two Medcenter rooms) share it; the same name on another floor does not."""
        by_id = {r["room_id"]: r for r in self.rooms}
        for svc in self.services.values():
            if room["room_id"] in svc["more_rooms"]:
                return svc
            home = by_id.get(svc.get("room_id"))
            if home and (home is room or (home["floor_number"] == room["floor_number"]
                                          and display_code(home) == display_code(room))):
                return svc
        return None

    def hosted_service(self, room: dict) -> dict | None:
        """The service a room answers as. A place known by its name (the Library,
        the Medcenter) is the service; a numbered room that also holds one (D109,
        home of Student Support) stays a room and names the service among its facts."""
        named = is_named(room) or room["room_number"].startswith("MEDCENTER")
        return self.service_of(room) if named else None

    def _room_or_service(self, room: dict, now: datetime | None) -> dict:
        """A room that is a service answers as the service, hours included."""
        svc = self.hosted_service(room)
        return self._service_answer(svc, now) if svc else self._room_answer(room)

    @staticmethod
    def _twin_numbers_in(query: str) -> list[int]:
        """The numbers a question gives for one of several numbered places."""
        found = []
        for m in TWIN_NUMBER_RE.finditer(query.lower()):
            if m.group(1):
                n = int(m.group(1))
            else:
                word = m.group(2)
                n = TWIN_WORDS.get(word) or next((v for k, v in TWIN_WORDS.items() if word.startswith(k)), None)
            if n and n not in found:
                found.append(n)
        return found

    def _named_answer(self, rooms: list[dict], now: datetime | None,
                      blocks: list[str] | None = None, floors: list[int] | None = None,
                      query: str = "") -> dict:
        """A place asked for by name. Several rooms can share one ("Study Space",
        "Restroom", "Red Canteen"): the one whose number the question gives
        ("study space No. 4"), the ones in the block or on the floor it names,
        or else every one of them, so none is missed."""
        numbered = {int(re.search(r"(\d+)$", r["distinct"]).group(1)): r for r in rooms
                    if re.search(r" \d+$", r.get("distinct") or "")}
        picked = [numbered[n] for n in self._twin_numbers_in(query) if n in numbered]
        if len(picked) == 1:
            return self._room_or_service(picked[0], now)
        inside = [r for r in rooms if r["building_id"] in (blocks or [])]
        rooms = inside or rooms
        rooms = [r for r in rooms if r["floor_number"] in (floors or [])] or rooms
        if len(rooms) == 1:
            return self._room_or_service(rooms[0], now)
        name = base_name(rooms[0]["name"])
        where = f" in Block {human_list(blocks)}" if inside else ""
        return self._several(rooms, now, f"{len(rooms)} places called {name}{where}")

    def _several(self, rooms: list[dict], now: datetime | None, title: str) -> dict:
        """Several places that answer one question, all of them: a short list, each
        with where it is (and whether it is open), and every one on the first's
        floor lit on the plan. A tap on one opens it, with the way there."""
        first = rooms[0]
        floors = sorted({r["floor_number"] for r in rooms})
        blocks = sorted({r["building_id"] for r in rooms})
        where = ("All on floor " + str(floors[0]) if len(floors) == 1
                 else "On floors " + human_list([str(f) for f in floors]))
        where += f", in Block{'s' if len(blocks) > 1 else ''} {human_list(blocks)}"
        answer = self._room_or_service(first, now)
        if answer.get("map"):
            shown = {h["room_number"] for h in answer["map"]["highlights"]}
            for r in rooms[1:]:
                point = self.map.room_point(r["room_number"])
                if point and point["floor"] == first["floor_number"] and r["room_number"] not in shown:
                    answer["map"]["highlights"].append({"room_number": r["room_number"], "role": "neighbour",
                                                        "x": point["x"], "y": point["y"]})
        results = []
        for r in rooms:
            svc = self.service_of(r)
            status = self._service_payload(svc, now) if svc else None
            results.append({"room_number": distinct_name(r).removeprefix("the ").capitalize()
                            if r["room_number"].startswith("MEDCENTER") else distinct_name(r),
                            "code": r["room_number"], "ask": ask_text(r), "purpose": r.get("purpose"),
                            "status": status["status"] if status and status["hours"] else None,
                            "open": status["open_now"] if status and status["hours"] else None,
                            "building_id": r["building_id"], "floor_number": r["floor_number"]})
        shown_floor = (f" The plan shows the ones on floor {first['floor_number']}."
                       if len(floors) > 1 and answer.get("map") else "")
        return {
            "kind": "list", "title": title,
            "summary": f"{where}. Tap one to see it on the plan and the way there.{shown_floor}",
            "results": results, "several": [r["room_number"] for r in rooms],
            "map": answer.get("map"), "route": answer.get("route"), "room": answer.get("room"),
            "suggestions": [],
        }
