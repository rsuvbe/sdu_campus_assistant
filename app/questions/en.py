"""English questions: the parser's own language (app/engine.py), so nothing is
put into other words. Its patterns live in the engine: TRIP_RES, ROUTE_WORDS_RE,
NEXT_CLASS_RE, EVENTS_RE, FLOOR_WORD_RE, BLOCK_WORD_RE."""

# The regression list: each question and the room it has to reach (tests/test_sprint_6.py
# asks the same rooms in all three languages).
REGRESSION = [
    ("Where is D103?", "D103"),
    ("Where is room F204?", "F204"),
    ("How do I get to G215?", "G215"),
    ("Where is the library?", "LIBRARY"),
    ("Where is the cafeteria?", "CAFETERIA"),
    ("Where is hall A1?", "D117"),
    ("Where is Red Hall?", "RED-HALL"),
    ("Where is the medcenter?", "MEDCENTER-1"),
    ("Where is the wardrobe?", "WARDROBE"),
    ("Where is H304?", "H304"),
]


def rewrite(query: str) -> str:
    return query
