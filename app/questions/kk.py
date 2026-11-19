"""Kazakh questions (US22), put into the words the parser reads.

Kazakh marks "from" and "to" with endings, not words: "D103-тен F204-ке қалай
барамын?" is "from D103 to F204", "кітапханаға" is "to the library". So a
question is first split at those endings into where it starts and where it
goes, and then each place is put into the parser's words: "кітапхана" (with
any ending) is the library, "G блогы" is Block G, "3-қабат" is floor 3.

People type Kazakh three ways, and all three are read the same:
  * with the Kazakh letters: "кітапхана қайда";
  * without them, on a Russian keyboard: "китапхана кайда", or with a Latin
    "i" for "і": "кiтапхана";
  * in Latin letters: "kitaphana qaida", "asxanaga qalai baramyn".
So before anything else a question is written one way (`plain`): Latin words
are spelled in Cyrillic, and each Kazakh letter is folded into the Russian one
people type for it (қ -> к, і -> и, ә -> а, ң -> н, ғ -> г, ү ұ -> у, ө -> о,
һ -> х). Every pattern below is written in proper Kazakh and folded the same
way when it is compiled, so it matches all three.
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

# --------------------------------------------------------------- one spelling
FOLD = dict(zip("әғқңөұүһіӘҒҚҢӨҰҮҺІ", "агкноуухиагкноуухи"))


def fold(text: str) -> str:
    """Kazakh letters as the Russian keyboard types them: "қайда" -> "кайда"."""
    return "".join(FOLD.get(c, c) for c in text)


# Latin letters that look like Cyrillic ones, typed inside a Cyrillic word
# ("кiтапхана" with a Latin i, "мeдпункт" with a Latin e)
LOOKALIKE = dict(zip("aeiopcxyk", "аеиорсхук"))
CYR = re.compile(r"[а-яёәіңғүұқөһ]")

# Kazakh in Latin letters, spelled in Cyrillic: the official alphabet ("qalaı",
# "kitaphana"), the one people write in chats ("qalai", "asxana", "jataqhana")
# and the transcription ("zhatakhana", "dәretkhana"). Longer spellings first.
LATIN_PAIRS = [
    ("shch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("gh", "г"), ("ts", "ц"),
    ("ia", "я"), ("ya", "я"), ("iu", "ю"), ("yu", "ю"), ("io", "ё"),
    ("ä", "а"), ("á", "а"), ("ə", "а"), ("ә", "а"), ("ö", "о"), ("ó", "о"), ("ü", "у"), ("ú", "у"),
    ("ū", "у"), ("ğ", "г"), ("ñ", "н"), ("ń", "н"), ("ı", "ы"), ("ş", "ш"), ("ç", "ч"), ("ý", "й"),
    ("a", "а"), ("b", "б"), ("c", "с"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"), ("h", "х"),
    ("i", "и"), ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
    ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("w", "у"), ("x", "х"),
    ("y", "ы"), ("z", "з"),
]
LATIN_SPELLING = re.compile("|".join(re.escape(a) for a, _ in LATIN_PAIRS))
LATIN_CYR = dict(LATIN_PAIRS)
VOWELS = "аеиоуыэюяё"
# Latin words that stay as they are: the names the plans give in English, and
# what the English parser already reads
KEEP_LATIN = {"red", "blue", "hall", "canteen", "coffee", "doner", "house", "market", "wifi", "wi", "fi",
              "zone", "sdu", "life", "centre", "center", "moodle", "it", "study", "space", "mini",
              "shanyraq", "ay", "no", "atm", "hub", "lab", "print", "printer", "cafe", "café"}
# A word in Latin letters that can only be Kazakh: a "q" that isn't "qu", or a
# word a location question is made of. tests: "Wo ist D103?" stays English.
LATIN_KAZAKH = re.compile(
    r"(?<![a-zäöüğıñşçáóúūə])(?:[a-z]*q(?!u)[a-zäöüğıñşçáóúūə]*|"
    r"k[ae][iy]da\w*|kai\s+jerde|kalai|kalay|kitap[hx]ana\w*|as[hx]ana\w*|ashkhana\w*|kabat\w*|"
    r"blog[yı]\w*|korpus[yı]\w*|baramyn|baram|barsam|jetemin|jetem|jetu|d[aäeə]ret[kh]*hana\w*|"
    r"[ae]jet[kh]*hana\w*|jata[kq]hana\w*|zhata[kq]hana\w*|kireberis\w*|saba[gq]\w*|kelesi|"
    r"[a-z]*[ğıñşūə][a-z]*|auditoriia\w*|auditoriya\w*|kabineti\w*|bolme\w*|zaly\w*|"
    r"medpunkt\w*|dekanat\w*|zert[kh]*hana\w*|tamak\w*|ashyk|zhabyk|jabyk|(?:is-?)?shara\w*|"
    r"[a-i]\s?\d{3}\s?-?\s?(?:ten|tan|den|dan|nen|nan|ke|ka|ge|ga|qa))"
    r"(?![a-zäöüğıñşçáóúūə])")   # no re.I: under it "ı" would match the "i" of "is"


def _latin_word(word: str) -> str:
    low = word.lower()
    if low in KEEP_LATIN or len(low) == 1 or re.fullmatch(r"[a-i]\d+|\d+\w*", low):
        return word         # a name, a block letter, a code ("D103", "A1")
    out = LATIN_SPELLING.sub(lambda m: LATIN_CYR[m.group(0)], low)
    # "i" and "y" after a vowel and before a consonant or the end are "й": "qaida", "qalai"
    return re.sub(r"(?<=[аеоуэюяё])[иы](?=[^аеиоуыэюяё]|$)", "й", out)


def is_latin_kazakh(text: str) -> bool:
    return bool(LATIN_KAZAKH.search((text or "").lower()))


def plain(text: str) -> str:
    """A question in one spelling: lower case, Cyrillic, the Kazakh letters folded."""
    text = text.lower()
    latin = is_latin_kazakh(text)

    def word(m: re.Match) -> str:
        w = m.group(0)
        cyr = len(CYR.findall(w))
        if cyr and (cyr * 2 > len(w) or not latin):
            # a Cyrillic word with Latin lookalikes typed into it
            return "".join(LOOKALIKE.get(c, c) for c in w)
        return _latin_word(w) if latin else w

    text = re.sub(r"[^\W\d_]+", word, text)
    return fold(text)


# ------------------------------------------------------------------ patterns
L = "a-zа-яё"                   # a letter of a word, once the Kazakh letters are folded


def rx(pattern: str) -> re.Pattern:
    """A pattern written in Kazakh, for a question in one spelling."""
    return re.compile(fold(pattern), re.I)


ABLATIVE = r"(?:дан|ден|тан|тен|нан|нен)"                  # "from"
DATIVE = r"(?:ға|ге|қа|ке|на|не|а|е)"                      # "to"
LOCATIVE = r"(?:да|де|та|те|нда|нде)"                       # "at"
GO = r"(?:қалай|қайтіп|қай\s+жолмен|қайдан\s+барамын)"      # "how"
# an ending is written on the word, after a hyphen, or after a space behind a code: "F204 тен"
CUT = r"(?:-|(?<=\d)\s)?"

# a start and a destination: "D103-тен F204-ке (қалай барамын)", "кітапханадан асханаға"
# ("қайдан", "where from", is a question word, not a start)
FROM_TO = rx(rf"^(?P<a>.+?)(?<!қай){CUT}{ABLATIVE}\s+(?P<b>.+?){CUT}{DATIVE}(?=\s|$)(?P<rest>.*)$")
# where you are, then where you're going: "мен F204-темін, G215 қайда", "F204-те тұрмын, G215-ке қалай барамын"
HERE_THERE = rx(rf"^(?:мен\s+)?(?P<a>\S+?){CUT}{LOCATIVE}(?:мын|мін|быз|біз)?(?:\s+(?:тұрмын|отырмын|тұрмыз))?"
                rf"\s*[,.;]?\s+(?P<b>.+?)\s*(?:{CUT}{DATIVE}\s+{GO}.*|\s+қайда.*)$")
# only a destination: "G215-ке қалай барамын", "кітапханаға қалай жетемін"
TO = rx(rf"^(?P<b>.+?){CUT}{DATIVE}\s+{GO}(?![{L}]).*$")
# "D103-ке жол" (the way to D103), "G215 ге жол көрсет"
TO_WAY = rx(rf"^(?P<b>.+?){CUT}{DATIVE}\s+(?:дейін\s+)?(?:жол|бағыт)[{L}]*.*$")
# what's near a place: "G101 жанындағы дәретхана", "D103-ке ең жақын асхана"
NEAR = rx(rf"^(?P<a>.+?)\s*(?:{CUT}{DATIVE}\s+ең\s+жақын|\s+(?:жанындағы|қасындағы|маңындағы|жанында|"
          rf"қасында|маңында|жанынан|қасынан|маңайындағы|жақын\s+жердегі))\s+(?P<b>.+)$")
NEAREST = rx(rf"(?<![{L}])(?:ең\s+)?жақын(?:ырақ)?\s+")

# Kazakh words for places and kinds of room, with any ending, and the parser's
# words for them. The longer first: "қызметкерлер дәретханасы" before "дәретхана".
PLACES = [
    (rf"қызметкерлер(?:дің)?\s+(?:дәретхана|әжетхана|туалет)[{L}]*", "staff restroom"),
    (rf"(?:д[әаэе]ретхана|ә(?:д)?жетхана|туалет|жуынатын\s+бөлме|санузел)[{L}]*", "restroom"),
    (rf"кітап(?:х|қ)ана[{L}]*", "library"),
    # the names the plans give in English, as the Kazakh pages say them
    (rf"қызыл\s+асхана[{L}]*", "red canteen"),
    (rf"қызыл\s+зал[{L}]*", "red hall"),
    (rf"көк\s+зал[{L}]*", "blue hall"),
    (rf"студент(?:тер)?\s+у[йи][{L}]*", "student house"),
    (rf"қосымша\s+білім(?:\s+беру)?\s+орталы[{L}]*", "extension center"),
    (rf"эдвайзинг[{L}]*(?:\s+орталы[{L}]*)?", "advising desk"),
    (rf"(?:тамақ\s+(?:ішетін|ішуге|ішу|ішем[{L}]*)(?:\s+(?:жер|орын)[{L}]*)?|тамақтан[{L}]*|"
     rf"ас(?:х|қ|ш)ана[{L}]*|аш(?:х)?ана[{L}]*|буфет[{L}]*|столов[{L}]*)", "cafeteria"),
    (rf"(?:медпункт|мед\s+пункт|медорталық|медициналық\s+(?:орталы|пункт)[{L}]*|дәрігер|медбике|"
     rf"емхана|медицина)[{L}]*", "medcenter"),
    (rf"(?:гардероб|киім[{L}]*(?:\s+(?:ілетін|ілгіш|тапсыр|қалдыр|ауыстыр)[{L}]*)?(?:\s+(?:орын|жер)[{L}]*)?)[{L}]*",
     "wardrobe"),
    (rf"(?:дүкен|магазин)[{L}]*", "shop"),
    (rf"(?:анықтама\s+(?:үстел|бюро)|ақпарат\s+(?:үстел|орталы)|ресепшн|ресепшен)[{L}]*", "information desk"),
    (rf"(?:ректорат|ректор)[{L}]*", "rector's office"),
    (rf"әкімшілік[{L}]*", "administration"),
    (rf"(?:студенттік|студенттер)\s+орталы[{L}]*", "student center"),
    (rf"(?:кеңесші|эдвайзер)[{L}]*", "advising desk"),
    (rf"үстел\s+теннис[{L}]*", "table tennis"),
    (rf"(?:деканат|декан)[{L}]*", "dean's office"),
    (rf"компь?ютер(?:лік)?\s+(?:сынып|кабинет|зертхана|класс)[{L}]*", "laboratory"),
    (rf"зертхана[{L}]*|лаборатория[{L}]*", "laboratory"),
    (rf"(?:дәрісхана|лекция(?:лық)?\s+зал)[{L}]*", "lecture hall"),
    (rf"(?:оқу\s+(?:кеңістіг|кеңістік|залы|зал)|коворкинг)[{L}]*", "study space"),
    (rf"(?:жатақхана|жатахана|общежити|общага)[{L}]*", "dormitory"),
    (rf"(?:басты\s+|бас\s+|негізгі\s+|орталық\s+)?кіреберіс[{L}]*", "main entrance"),
    (rf"(?:шығатын\s+(?:есік|жер)|шығу\s+есіг|шығыс\s+есіг|шығу\s+жол)[{L}]*", "nearest exit"),
    (rf"баспалдақ[{L}]*", "stairs"),
    (rf"спорт\s*зал[{L}]*", "sport hall"),
    (rf"wi-?\s?fi\s+аймағ[{L}]*|вай\s*фай[{L}]*(?:\s+аймағ[{L}]*)?|шаңырақ[{L}]*", "wi-fi zone"),
    (rf"(?:іс-?\s?шара|шара)[{L}]*", "events"),
    (rf"(?:басып\s+шығар|көшірме|ксерокс|принтер)[{L}]*", "printer"),
    # a school, for "whose dean's office"
    (rf"инженерия(?:\s+және\s+жаратылыстану(?:\s+ғылымдар[{L}]*)?)?(?:\s+факультет[{L}]*)?", "engineering"),
    (rf"(?:ақпараттық\s+технология[{L}]*|it(?![{L}]))(?:\s+(?:және\s+)?(?:қолданбалы\s+математика[{L}]*))?"
     rf"(?:\s+(?:мектеб|факультет)[{L}]*)?", "it"),
    (rf"(?:бизнес|құқық|заң|әлеуметтік\s+ғылым)[{L}]*(?:\s+(?:мектеб|факультет)[{L}]*)?", "law"),
    (rf"(?:педагогика|білім\s+беру|гуманитар)[{L}]*(?:\s+(?:ғылым[{L}]*\s+)?(?:мектеб|факультет)[{L}]*)?", "education"),
]
PLACES = [(rx(rf"(?<![{L}]){pattern}"), word) for pattern, word in PLACES]

ORDINAL_FLOORS = {fold(k): v for k, v in {"бірінші": "1", "екінші": "2", "үшінші": "3"}.items()}
HALL_LETTERS = {"а": "a", "б": "b", "в": "b", "с": "c", "д": "d"}
RULES = [
    # the next class: "келесі сабағым", "келесі дәріс", "менің сабағым", "қазір қандай сабақ"
    (rx(rf"(?:келесі|менің|қазір(?:гі)?|қандай|бүгінгі)\s+(?:сабағ|сабақ|дәріс|пара|лекция|семинар)[{L}]*"),
     " my next class "),
    (rx(rf"(?<![{L}])сабағым[{L}]*"), " my next class "),
    # a code with an ending: "D103-тен", "Д217-ге", "F204ке", "D103 ке"
    (rx(rf"(?<![{L}])([a-iа-яё])\s?-?\s?(\d{{3}})(?:-[{L}]+|(?:тен|тан|ден|дан|нен|нан|ке|ка|ге|га|те|та|де|да|"
        rf"ның|нің|тың|тің|дың|дің|ны|ні|ты|ті|ды|ді|ы|і|ға|ге|қа|ке)(?![{L}])|[{L}]+)?"), r" \1\2 "),
    (rx(rf"(\d{{3}})\s+(?:тен|тан|ден|дан|нен|нан|ке|ка|ге|га|те|та|де|да|ға|қа)(?![{L}])"), r"\1 "),
    # a round hall: "A1 залы", "А1 залына", "A1-ге", "А1" in Cyrillic
    (rx(rf"(?<![{L}\d])([a-dа-д][12])\s*-?\s*зал[{L}]*"), r" hall \1 "),
    (rx(rf"(?<![{L}\d])([a-dа-д][12])-[{L}]+"), r"\1"),
    (rx(rf"(?<![{L}\d])([абвсд])([12])(?![{L}\d])"), lambda m: f" {HALL_LETTERS[m.group(1)]}{m.group(2)} "),
    # floors: "3-қабат", "3 қабатта", "үшінші қабатқа"
    (rx(rf"(\d)\s*-?\s*(?:ші|шы|інші|ыншы)?\s*қабат[{L}]*"), r" floor \1 "),
    (rx(rf"(бірінші|екінші|үшінші)\s+қабат[{L}]*"), lambda m: f" floor {ORDINAL_FLOORS[m.group(1).lower()]} "),
    # blocks: "G блогы", "G блогындағы", "F корпусы"
    (rx(rf"(?<![{L}])([a-iа-яё])\s*-?\s*(?:блог|блок|корпус)[{L}]*"), r" block \1 "),
    # the room's own word after a code or a name: "аудиториясы", "бөлмесі", "кабинеті"
    (rx(rf"(?<![{L}])(?:аудитори|бөлме|кабинет|ғимарат)[{L}]*"), " "),
]
# what a question asks, said in other words, and words that say nothing about the place
WHERE = rx(rf"(?<![{L}])(?:қайда|қай\s+(?:жерде|жақта|қабатта|блокта|корпуста|ғимаратта|аудиторияда)|"
           rf"қайдан|қайдасың|қайдасыз|қайда\s+екен|қай\s+жер)(?![{L}])")
HOURS = rx(rf"(?<![{L}])(?:ашық|жабық|қашан|жұмыс\s+(?:уақыт|кесте|істей)[{L}]*|неше(?:де)?|сағат[{L}]*|"
           rf"ашыла|жабыла)[{L}]*")
FILLER = rx(rf"(?<![{L}])(?:орналасқан|орналасты|орналасады|табуға|табамын|табу|тапшы|тап|табыңыз|болады|"
            rf"бола\s+ма|болама|керек|маған|бізге|мен|менің|көрсетіңіз|көрсетші|көрсет|айтыңызшы|айтшы|айт|"
            rf"бар|жоқ|ма|ме|ба|бе|па|пе|ші|шы|екен[{L}]*|өтінем|өтінемін|рахмет|сәлем|сәлеметсіз\s+бе|"
            rf"жетемін|жетем|жетуге|барамын|барам|барсам|баруға|бару|жету|кіремін|жол|жолы|бағыт|дейін|"
            rf"сонда|осы|ол|бұл|тұрмын|отырмын|ішінде|жерде|жер|орын)(?![{L}])")


def place(text: str) -> str:
    """A place as the parser reads it: "кітапханадан" -> "library", "D103-тен" -> "D103"."""
    text = f" {text} "
    for pattern, word in PLACES:
        text = pattern.sub(f" {word} ", text)
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    text = WHERE.sub(" ", text)
    text = FILLER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" ?.!,;")


def rewrite(query: str) -> str:
    q = re.sub(r"\s+", " ", plain(query).strip()).strip(" ?.!")
    m = FROM_TO.match(q)
    if m and place(m["a"]) and place(m["b"]):
        return f"from {place(m['a'])} to {place(m['b'])}"
    m = HERE_THERE.match(q)
    if m and place(m["a"]) and place(m["b"]):
        return f"I'm in {place(m['a'])}, where is {place(m['b'])}"
    m = NEAR.match(q)
    if m and place(m["a"]) and place(m["b"]):
        return f"nearest {place(m['b'])} to {place(m['a'])}"
    m = TO.match(q) or TO_WAY.match(q)
    if m and place(m["b"]):
        return f"how do I get to {place(m['b'])}"
    asks_where = bool(WHERE.search(q))
    hours = HOURS.search(q)
    nearest = NEAREST.search(q)
    found = place(NEAREST.sub(" ", q))
    if "my next class" in found:
        return "where is my next class"
    if re.search(rf"(?<![{L}]){fold(GO)}(?![{L}])", q):
        return f"how do I get to {found}"
    if nearest:
        return f"nearest {found}"
    if hours and not asks_where:
        # "кітапхана ашық па", "кітапхана қашан ашылады": the answer gives the hours
        found = HOURS.sub(" ", found).strip()
        return f"is {found} open" if found else "what's open now"
    return f"where is {found}" if asks_where else found
