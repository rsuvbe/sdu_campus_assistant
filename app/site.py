"""
The campus grounds: the main building with the buildings around it, for the map's
"Campus" view. The floor plans draw only the main building; SDU Life Centre and
the Student House stand apart from it. They are drawn under every floor, so the
map is the whole campus, and an event there is shown on it.

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

# Buildings that are destinations: a code, a name, the words people use for it,
# the halls inside, and the ways to it from the main building. A way leaves by
# an exit of floor 1 (its name on the plans) and walks the traced points to the
# door; `say` is the walk outside, step by step.
BUILDINGS = [
    {"code": "SDU-LIFE", "label": "SDU Life Centre", "sub": "separate building",
     "aliases": ["sdu life", "sdu life centre", "sdu life center", "life centre", "life center",
                 "лайф центр", "сду лайф"],
     "halls": {"sport hall": "Sport Hall", "спортзал": "Sport Hall", "спорт зал": "Sport Hall",
               "blue hall": "Blue Hall"},
     "about": "SDU Life Centre stands on its own, south-west of the main building, past the sports "
              "grounds; Sport Hall and Blue Hall are in it.",
     "outline": [(209, 837), (315, 837), (315, 952), (209, 952)],
     "ways": [
         {"exit": "west entrance by Block G",
          "walk": [(403, 561), (350, 561), (350, 817), (262, 817), (262, 837)],
          "say": ["Outside, walk west to the drive.",
                  "Turn left and follow the drive south, past the sports grounds.",
                  "At the end of the drive turn right: SDU Life Centre is the building in front of you."]},
         {"exit": "west exit beside Doner House",
          "walk": [(411, 474), (350, 474), (350, 817), (262, 817), (262, 837)],
          "say": ["Outside, walk west to the drive.",
                  "Turn left and follow the drive south, past the sports grounds.",
                  "At the end of the drive turn right: SDU Life Centre is the building in front of you."]},
     ]},
    {"code": "STUDENT-HOUSE", "label": "Student House", "sub": "dormitory, 1/2", "spoken": "the Student House",
     "aliases": ["student house", "dormitory", "dorm", "hostel", "общежитие", "общага", "жатақхана"],
     "halls": {},
     "about": "The Student House, the dormitory, is the building west of the main one, across the drive.",
     "outline": [(163, 305), (252, 300), (252, 368), (180, 368), (180, 400), (209, 400), (209, 384),
                 (224, 384), (224, 422), (268, 422), (268, 410), (310, 410), (310, 480), (282, 480),
                 (282, 568), (237, 568), (237, 584), (197, 584), (197, 510), (225, 510), (225, 451),
                 (180, 451), (180, 470), (140, 470), (140, 423), (136, 423), (136, 400), (163, 400)],
     "ways": [
         {"exit": "west exit beside Doner House",
          "walk": [(411, 474), (350, 474), (350, 445), (310, 445)],
          "say": ["Outside, walk west across the drive: the Student House is in front of you."]},
         {"exit": "west entrance by Block G",
          "walk": [(403, 561), (350, 561), (350, 470), (310, 470)],
          "say": ["Outside, walk west to the drive and turn right.",
                  "Follow the drive north a little way: the Student House is on your left."]},
         {"exit": "main entrance by the lobby",
          "walk": [(400, 189), (350, 205), (350, 440), (310, 440)],
          "say": ["Outside, walk west to the drive and turn left.",
                  "Follow the drive south: the Student House is on your right."]},
     ]},
]

# Places of the main building the plans draw but don't list as rooms: shown
# exactly, and reached by their nearest door
SPOTS = [
    {"code": "WIFI-ZONE", "label": "Wi-Fi Zone", "sub": "main lobby, Block C", "feature": "wifi",
     "spoken": "the Wi-Fi Zone",
     "aliases": ["wi-fi zone", "wifi zone", "wi fi zone", "wi-fi", "wifi", "wi fi", "вай-фай зона",
                 "вайфай зона", "вай фай зона", "вайфай", "shanyraq zone", "shanyraq", "shaniraq zone",
                 "шанырак", "шанырак зона", "шаңырақ", "шаңырақ зона"],
     "about": "The Wi-Fi Zone, also called Shanyraq Zone, is the round area in the main lobby (Block C), "
              "just inside the main entrance.",
     "ways": [{"exit": "main entrance by the lobby", "inside": True,
               "say": ["The Wi-Fi Zone is the round area of the main lobby, by the main entrance."]}]},
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
    return next((b for b in BUILDINGS + SPOTS if b["code"] == code), None)


def _words(text: str) -> str:
    return " " + " ".join(text.casefold().replace("?", " ").replace(",", " ").split()) + " "


def find_place(text: str) -> tuple[dict, str | None] | None:
    """The building or spot a question names ("SDU Life", "общежитие", "Wi-Fi
    zone"), with the hall in it it named ("Blue Hall"), or None. A code ("SDU-LIFE")
    names it too."""
    key = _words(text)
    for b in BUILDINGS + SPOTS:
        if text.strip().upper() == b["code"]:
            return b, None
        for name, hall in b.get("halls", {}).items():
            if f" {name} " in key:
                return b, hall
        if any(f" {a} " in key for a in b["aliases"]):
            return b, None
    return None


def find_building(text: str) -> dict | None:
    found = find_place(text)
    return found[0] if found else None


def outline_map(code: str) -> dict:
    """What an answer about a building puts on the map: the building lit, and the
    walk to it from the main building's nearest door."""
    b = building(code)
    points = [to_site(*p) for p in b["outline"]]
    x, y = _centre(points)
    way = b["ways"][0]
    return {"floor": 1, "site": True, "code": code, "room_number": b["label"], "label": b["label"],
            "x": x, "y": y, "radius": None, "highlights": [], "landmark": None,
            "walk": [to_site(*p) for p in way["walk"]], "walk_from": way["exit"]}


site_map = outline_map


def build_grounds() -> dict:
    """The grounds round the main building, in the floors' frame: drawn under
    every floor, so the map is one campus and a floor only changes the inside."""
    buildings = []
    for b in BUILDINGS:
        points = [to_site(*p) for p in b["outline"]]
        x, y = _centre(points)
        buildings.append({"code": b["code"], "label": b["label"], "sub": b["sub"], "ask": b["label"],
                          "x": x, "y": y, "points": points})
    # over the wings, east of the corridor: clear of the Student House's name
    main_x, main_y = from_plan(600, 1480)
    return {
        "buildings": buildings,
        "others": [[to_site(*p) for p in o] for o in OTHER_BUILDINGS],
        "grounds": [{"label": g["label"], "points": [to_site(*p) for p in g["outline"]]} for g in GROUNDS],
        "roads": [{"kind": r["kind"], "points": [to_site(*p) for p in r["points"]]} for r in ROADS],
        # seen only when the whole campus is in view, where the rooms can't be read
        "labels": [{"text": "Main building", "sub": "Blocks A–I", "x": main_x, "y": main_y}],
    }
