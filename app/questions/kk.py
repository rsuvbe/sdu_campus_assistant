"""Kazakh questions (US22), put into the words the parser reads.

Kazakh marks "from" and "to" with endings, not words: "D103-тен F204-ке қалай
барамын?" is "from D103 to F204", "кітапханаға" is "to the library". So a
question is first split at those endings into where it starts and where it
goes, and then each place is put into the parser's words: "кітапхана" (with
any ending) is the library, "G блогы" is Block G, "3-қабат" is floor 3.
"""
from __future__ import annotations

import re

# The regression list: each question and the room it has to reach, the same
# rooms as en.py's and ru.py's (tests/test_sprint_6.py asks all three).
REGRESSION = [
    ("D103 қайда?", "D103"),
    ("F204 аудиториясы қайда орналасқан?", "F204"),
    ("G215-ке қалай барамын?", "G215"),
    ("Кітапхана қайда?", "LIBRARY"),
    ("Асхана қайда?", "CAFETERIA"),
    ("A1 залы қайда?", "D117"),
    ("Red Hall қайда?", "RED-HALL"),
    ("Медпункт қайда?", "MEDCENTER-1"),
    ("Гардероб қайда?", "WARDROBE"),
    ("H304 қайда орналасқан?", "H304"),
]

L = "a-zа-яёәіңғүұқөһ"          # a letter of a word, Latin or Kazakh Cyrillic
ABLATIVE = r"(?:дан|ден|тан|тен|нан|нен)"                  # "from"
DATIVE = r"(?:ға|ге|қа|ке|на|не|а|е)"                      # "to"
GO = r"(?:қалай|қайтіп|қай\s+жолмен)"                       # "how"

# a start and a destination: "D103-тен F204-ке (қалай барамын)", "кітапханадан асханаға"
FROM_TO = re.compile(rf"^(?P<a>.+?)-?{ABLATIVE}\s+(?P<b>.+?)-?{DATIVE}(?=\s|$)(?P<rest>.*)$")
# only a destination: "G215-ке қалай барамын", "кітапханаға қалай жетемін"
TO = re.compile(rf"^(?P<b>.+?)-?{DATIVE}\s+{GO}\b.*$")
# a destination after the verb: "қалай барамын D103-ке" is rare; "D103-ке жол" (the way to D103)
TO_WAY = re.compile(rf"^(?P<b>.+?)-?{DATIVE}\s+(?:дейін\s+)?(?:жол|бағыт)\w*.*$")

# Kazakh words for places and kinds of room, with any ending, and the parser's
# words for them. The longer first: "қызметкерлер дәретханасы" before "дәретхана".
PLACES = [
    (rf"қызметкерлер(?:дің)?\s+дәретхана[{L}]*", "staff restroom"),
    (rf"(?:дәретхана|әжетхана|жуынатын\s+бөлме)[{L}]*", "restroom"),
    (rf"кітапхана[{L}]*", "library"),
    (rf"асхана[{L}]*", "cafeteria"),
    (rf"(?:медпункт|медициналық\s+орталы[{L}]*|дәрігер)[{L}]*", "medcenter"),
    (rf"(?:гардероб|киім\s+іл(?:етін|гіш)[{L}]*)[{L}]*", "wardrobe"),
    (rf"дүкен[{L}]*", "shop"),
    (rf"(?:анықтама\s+үстел|анықтама\s+бюро|ақпарат\s+үстел)[{L}]*", "information desk"),
    (rf"әкімшілік[{L}]*", "administration"),
    (rf"(?:студенттік|студенттер)\s+орталы[{L}]*", "student center"),
    (rf"(?:кеңесші|эдвайзер)[{L}]*", "advising desk"),
    (rf"үстел\s+теннис[{L}]*", "table tennis"),
    (rf"деканат[{L}]*", "dean's office"),
    (rf"компьютер(?:лік)?\s+(?:сынып|кабинет|зертхана)[{L}]*", "laboratory"),
    (rf"зертхана[{L}]*", "laboratory"),
    (rf"(?:дәрісхана|лекция\s+зал)[{L}]*", "lecture hall"),
    (rf"оқу\s+(?:кеңістіг|кеңістік|залы)[{L}]*", "study space"),
    (rf"жатақхана[{L}]*", "dormitory"),
    (rf"(?:басты\s+|бас\s+|негізгі\s+|орталық\s+)?кіреберіс[{L}]*", "main entrance"),
    (rf"(?:спорт\s*зал)[{L}]*", "sport hall"),
    (rf"wi-?\s?fi\s+аймағ[{L}]*", "wi-fi zone"),
    (rf"іс-?\s?шара[{L}]*", "events"),
]
PLACES = [(re.compile(rf"(?<![{L}]){pattern}", re.I), word) for pattern, word in PLACES]

ORDINAL_FLOORS = {"бірінші": "1", "екінші": "2", "үшінші": "3"}
RULES = [
    # the next class: "келесі сабағым", "келесі дәріс", "менің сабағым"
    (re.compile(rf"(?:келесі|менің)\s+(?:сабағ|сабақ|дәріс|пара|лекция|семинар)[{L}]*", re.I), " my next class "),
    (re.compile(rf"(?<![{L}])сабағым[{L}]*", re.I), " my next class "),
    # a code with an ending: "D103-тен", "Д217-ге", "F204ке"
    (re.compile(rf"(?<![{L}])([a-iа-яё])\s?-?\s?(\d{{3}})\s*-?\s*[{L}]+", re.I), r"\1\2"),
    # a round hall: "A1 залы", "А1 залына", "A1-ге"
    (re.compile(rf"(?<![{L}\d])([a-dа-д][12])\s*-?\s*зал[{L}]*", re.I), r" hall \1 "),
    (re.compile(rf"(?<![{L}\d])([a-dа-д][12])-[{L}]+", re.I), r"\1"),
    # floors: "3-қабат", "3 қабатта", "үшінші қабатқа"
    (re.compile(rf"(\d)\s*-?\s*(?:ші|шы|інші|ыншы)?\s*қабат[{L}]*", re.I), r" floor \1 "),
    (re.compile(rf"(бірінші|екінші|үшінші)\s+қабат[{L}]*", re.I), lambda m: f" floor {ORDINAL_FLOORS[m.group(1).lower()]} "),
    # blocks: "G блогы", "G блогындағы", "F корпусы"
    (re.compile(rf"(?<![{L}])([a-iа-яё])\s*-?\s*(?:блог|блок|корпус)[{L}]*", re.I), r" block \1 "),
    # the room's own word after a code or a name: "аудиториясы", "бөлмесі", "кабинеті"
    (re.compile(rf"(?<![{L}])(?:аудитория|бөлме|кабинет)[{L}]*", re.I), " "),
]
# what a question asks, said in other words, and words that say nothing about the place
WHERE = re.compile(rf"(?<![{L}])(?:қайда|қай\s+жерде)(?![{L}])", re.I)
FILLER = re.compile(rf"(?<![{L}])(?:орналасқан|орналасты|табуға|табамын|табу|болады|бола\s+ма|"
                    rf"керек|маған|көрсетіңіз|көрсет|айтыңызшы|айтшы|бар|ма|ме|ба|бе|па|пе|ашық|жабық|"
                    rf"жетемін|барамын|барам|баруға|бару|жету|жол|жолы|бағыт|дейін)(?![{L}])", re.I)


def place(text: str) -> str:
    """A place as the parser reads it: "кітапханадан" -> "library", "D103-тен" -> "D103"."""
    text = f" {text} "
    for pattern, word in PLACES:
        text = pattern.sub(f" {word} ", text)
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    text = WHERE.sub(" ", text)
    text = FILLER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" ?.!,")


def rewrite(query: str) -> str:
    q = re.sub(r"\s+", " ", query.strip().lower()).strip(" ?.!")
    m = FROM_TO.match(q)
    if m:
        return f"from {place(m['a'])} to {place(m['b'])}"
    m = TO.match(q) or TO_WAY.match(q)
    if m:
        return f"how do I get to {place(m['b'])}"
    asks_where = bool(WHERE.search(q))
    found = place(q)
    if "my next class" in found:
        return "where is my next class"
    if re.search(rf"(?<![{L}]){GO}(?![{L}])", q):
        return f"how do I get to {found}"
    return f"where is {found}" if asks_where else found
