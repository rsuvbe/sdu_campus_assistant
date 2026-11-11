"""
The campus grounds: the main building with the buildings around it, for the map's
"Campus" view. The floor plans draw only the main building; SDU Life Centre and
the Student House stand apart from it, and an event there is shown here.

Traced from a city map of the campus (the user's screenshot of 11 November 2026,
north up). The main building on it lies over our floor 1 at 4.5 plan units to a
pixel, so everything traced is put into the plan's own units with that and the
same origin; the main building itself is floor 1's outline, not the trace.
The shapes are a sketch of the grounds: buildings, sports grounds and the drives
between them, not their rooms.
"""
from __future__ import annotations

SCALE = 4.5                      # plan units per pixel of the traced map
PHOTO_ORIGIN = (395.0, 130.0)    # the pixel at floor 1's (214, 110)
PLAN_ORIGIN = (214.0, 110.0)
# the grounds reach west and south of the main building: shifted so all of it is >= 0
SHIFT = (1140.0, 420.0)
SIZE = (2660.0, 4460.0)

# Buildings that are destinations: a code, a name, the words people use for it
BUILDINGS = [
    {"code": "SDU-LIFE", "label": "SDU Life Centre", "sub": "separate building",
     "aliases": ["sdu life", "sdu life centre", "sdu life center", "life centre", "life center",
                 "лайф центр", "сду лайф"],
     "about": "SDU Life Centre stands on its own, south-west of the main building, past the sports "
              "grounds. From the west entrance by Block G, walk west to the drive and south along it.",
     "outline": [(209, 837), (315, 837), (315, 952), (209, 952)],
     "door": (262, 837)},
    {"code": "STUDENT-HOUSE", "label": "Student House", "sub": "dormitory, 1/2",
     "aliases": ["student house", "dormitory", "dorm", "hostel", "общежитие", "общага", "жатақхана"],
     "about": "The Student House, the dormitory, is the building west of the main one, across the "
              "drive from the Doner House exit.",
     "outline": [(163, 305), (252, 300), (252, 368), (180, 368), (180, 400), (209, 400), (209, 384),
                 (224, 384), (224, 422), (268, 422), (268, 410), (310, 410), (310, 480), (282, 480),
                 (282, 568), (237, 568), (237, 584), (197, 584), (197, 510), (225, 510), (225, 451),
                 (180, 451), (180, 470), (140, 470), (140, 423), (136, 423), (136, 400), (163, 400)],
     "door": (225, 451)},
]

# a building on the map nobody has named for us: drawn, not a destination
OTHER_BUILDINGS = [[(134, 636), (170, 636), (170, 741), (134, 741)]]

GROUNDS = [
    {"label": "Sports ground", "outline": [(207, 670), (305, 670), (305, 735), (207, 735)]},
    {"label": None, "outline": [(207, 627), (266, 627), (266, 658), (207, 658)]},
    {"label": None, "outline": [(270, 637), (304, 637), (304, 656), (270, 656)]},
    {"label": None, "outline": [(120, 313), (158, 313), (158, 392), (120, 392)]},
]

ROADS = [
    {"kind": "drive", "points": [(137, 211), (600, 28)]},
    {"kind": "drive", "points": [(600, 28), (632, 28), (652, 48), (652, 245), (640, 262), (608, 268),
                                 (600, 290), (600, 570)]},
    {"kind": "drive", "points": [(350, 72), (350, 765)]},
    {"kind": "drive", "points": [(110, 612), (350, 612)]},
    {"kind": "drive", "points": [(112, 817), (388, 817)]},
    {"kind": "drive", "points": [(157, 817), (157, 968)]},
    {"kind": "edge", "points": [(113, 612), (113, 1188), (578, 1182), (568, 815)]},
    {"kind": "edge", "points": [(565, 670), (662, 670), (662, 200)]},
]

# The way from the main building to SDU Life Centre: out of the west entrance by
# Block G, west to the drive, south along it, and across to the centre's door
WALKS = {"SDU-LIFE": {"from": "west entrance by Block G",
                      "points": [(403, 561), (350, 561), (350, 817), (262, 817), (262, 837)]},
         "STUDENT-HOUSE": {"from": "west exit beside Doner House",
                           "points": [(411, 474), (350, 474), (350, 440), (310, 440)]}}


def to_site(x: float, y: float) -> list[float]:
    """A pixel of the traced map, in the Campus view's units."""
    return [round(PLAN_ORIGIN[0] + (x - PHOTO_ORIGIN[0]) * SCALE + SHIFT[0], 1),
            round(PLAN_ORIGIN[1] + (y - PHOTO_ORIGIN[1]) * SCALE + SHIFT[1], 1)]


def from_plan(x: float, y: float) -> list[float]:
    """A point of floor 1, in the Campus view's units."""
    return [round(x + SHIFT[0], 1), round(y + SHIFT[1], 1)]


def _centre(points: list[list[float]]) -> tuple[float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def building(code: str) -> dict | None:
    return next((b for b in BUILDINGS if b["code"] == code), None)


def find_building(text: str) -> dict | None:
    """The building a question names ("SDU Life", "общежитие"), or None."""
    key = " ".join(text.casefold().replace("?", " ").split())
    for b in BUILDINGS:
        if any(key == a or f" {a} " in f" {key} " for a in b["aliases"]):
            return b
    return None


def site_map(code: str) -> dict:
    """What an answer about a building puts on the Campus view: the building lit,
    and the walk to it from the main building's nearest door."""
    b = building(code)
    points = [to_site(*p) for p in b["outline"]]
    x, y = _centre(points)
    walk = WALKS.get(code)
    return {"floor": 0, "site": True, "code": code, "room_number": b["label"], "label": b["label"],
            "x": x, "y": y, "radius": None, "highlights": [], "landmark": None,
            "walk": [to_site(*p) for p in walk["points"]] if walk else None,
            "walk_from": walk["from"] if walk else None}


def build_site(floor1: dict) -> dict:
    """The Campus view, shaped like a floor so the map draws it the same way."""
    rooms = []
    for b in BUILDINGS:
        points = [to_site(*p) for p in b["outline"]]
        x, y = _centre(points)
        rooms.append({"code": b["code"], "label": b["label"], "sub": b["sub"], "ask": b["label"],
                      "service": None, "block": None, "barrel": None, "type": "BUILDING",
                      "department": None, "approx": False, "x": x, "y": y, "kind": "rect",
                      "angle": 0, "points": points})
    shifted = lambda pts: [from_plan(*p) for p in pts]   # noqa: E731
    main_x, main_y = from_plan(560, 1480)
    return {
        "floor": 0, "site": True, "name": "Campus",
        "width": SIZE[0], "height": SIZE[1], "spine_half": floor1["spine_half"],
        "areas": [{**a, "points": shifted(a["points"])} for a in floor1["areas"]],
        "volumes": [], "circulation": [], "spines": [], "features": [],
        "fixtures": [{"points": [to_site(*p) for p in o]} for o in OTHER_BUILDINGS],
        "rooms": rooms, "blocks": [],
        "landmarks": [{**lm, "x": from_plan(lm["x"], lm["y"])[0], "y": from_plan(lm["x"], lm["y"])[1]}
                      for lm in floor1["landmarks"] if lm["type"] == "exit"],
        "grounds": [{"label": g["label"], "points": [to_site(*p) for p in g["outline"]]} for g in GROUNDS],
        "roads": [{"kind": r["kind"], "points": [to_site(*p) for p in r["points"]]} for r in ROADS],
        "labels": [{"text": "Main building", "sub": "Blocks A–I", "x": main_x, "y": main_y}]
                  + [{"text": b["id"], "x": from_plan(b["tag_x"], b["tag_y"])[0],
                      "y": from_plan(b["tag_x"], b["tag_y"])[1], "letter": True} for b in floor1["blocks"]],
    }
