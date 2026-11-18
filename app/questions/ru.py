"""Russian questions (US22). The parser reads most Russian itself (app/engine.py:
"где", "из ... в ...", "как пройти", "следующая пара", Cyrillic block letters);
this adds the words it does not know yet, with any ending: kinds of room
("лаборатории", "лекционный зал") and places asked for in another case
("до библиотеки", "в общежитии")."""
from __future__ import annotations

import re

# The regression list: the same rooms as en.py's and kk.py's.
REGRESSION = [
    ("Где D103?", "D103"),
    ("Где находится аудитория F204?", "F204"),
    ("Как пройти в G215?", "G215"),
    ("Где библиотека?", "LIBRARY"),
    ("Где столовая?", "CAFETERIA"),
    ("Где зал A1?", "D117"),
    ("Где Red Hall?", "RED-HALL"),
    ("Где медпункт?", "MEDCENTER-1"),
    ("Где гардероб?", "WARDROBE"),
    ("Где находится H304?", "H304"),
]

L = "a-zа-яё"
WORDS = [
    (rf"компьютерн[{L}]*\s+(?:класс|кабинет|аудитори)[{L}]*", "laboratory"),
    (rf"лаборатори[{L}]*", "laboratory"),
    (rf"лекционн[{L}]*\s+(?:зал|аудитори)[{L}]*", "lecture hall"),
    (rf"учебн[{L}]*\s+(?:пространств|зон)[{L}]*|коворкинг[{L}]*", "study space"),
    (rf"библиотек[{L}]*", "library"),
    # the names the plans give in English, as the Russian pages say them
    (rf"красн[{L}]*\s+столов[{L}]*", "red canteen"),
    (rf"красн[{L}]*\s+зал[{L}]*", "red hall"),
    (rf"сини[{L}]*\s+зал[{L}]*", "blue hall"),
    (rf"студенческ[{L}]*\s+дом[{L}]*", "student house"),
    (rf"студенческ[{L}]*\s+центр[{L}]*", "student center"),
    (rf"центр[{L}]*\s+дополнительн[{L}]*\s+образовани[{L}]*", "extension center"),
    (rf"эдвайзинг[{L}]*(?:-?\s*центр[{L}]*)?", "advising desk"),
    (rf"спортзал[{L}]*|спортивн[{L}]*\s+зал[{L}]*", "sport hall"),
    (rf"столов(?:ая|ой|ую|ые|ых)(?![{L}])", "cafeteria"),
    (rf"общежити[{L}]*|общаг[{L}]*", "dormitory"),
    (rf"медпункт[{L}]*|медцентр[{L}]*", "medcenter"),
    (rf"гардероб[{L}]*", "wardrobe"),
    (rf"справочн(?:ая|ой|ую)(?![{L}])", "information desk"),
    (rf"администраци[{L}]*", "administration"),
    (rf"мероприяти[{L}]*", "events"),
]
WORDS = [(re.compile(rf"(?<![{L}]){pattern}", re.I), word) for pattern, word in WORDS]
# "туалет для сотрудников" is its own place, "туалета" another case of "туалет"
STAFF_WC = re.compile(rf"(?<![{L}])туалет[{L}]*\s+для\s+сотрудник[{L}]*", re.I)
WC = re.compile(rf"(?<![{L}])туалет[{L}]*", re.I)


def rewrite(query: str) -> str:
    text = STAFF_WC.sub(" staff restroom ", query)
    text = WC.sub(" restroom ", text)
    for pattern, word in WORDS:
        text = pattern.sub(f" {word} ", text)
    return text
