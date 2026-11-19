"""
Kazakh search (US22), the way people actually type it: with the Kazakh letters,
without them on a Russian keyboard ("китапхана кайда"), with a Latin "i" for
"і" ("кiтапхана"), and in Latin letters ("kitaphana qaida"). Each question has
to reach the same place as its English twin.
"""
import pytest

from app import i18n
from app.main import index

# (Kazakh, English twin)
PAIRS = [
    ("D103 қайда", "where is D103"),
    ("D103 қай қабатта", "where is D103"),
    ("D103-ке қалай барамын", "how do I get to D103"),
    ("D103 ке қалай жетемін", "how do I get to D103"),
    ("F204-тен G215-ке қалай барамын", "from F204 to G215"),
    ("F204 тен G215 ке", "from F204 to G215"),
    ("Мен F204-темін, G215 қайда", "I'm in F204, where is G215"),
    ("кітапхана қайда", "where is the library"),
    ("кітапханаға қалай барамын", "how do I get to the library"),
    ("кітапхана ашық па", "is the library open"),
    ("асхана қайда", "where is the cafeteria"),
    ("тамақ ішетін жер қайда", "where is the cafeteria"),
    ("буфет қайда", "where is the cafeteria"),
    ("дәретхана қайда", "where is the restroom"),
    ("G101 жанындағы дәретхана", "nearest restroom to G101"),
    ("медбике қайда", "where is the medcenter"),
    ("киімді қайда тапсырамын", "where is the wardrobe"),
    ("инженерия факультетінің деканаты", "engineering dean's office"),
    ("ректорат қайда", "where is the rector's office"),
    ("жатақхана қайда", "where is the dormitory"),
    ("студенттер үйі қайда", "where is the student house"),
    ("компьютерлік сынып қайда", "where is the computer lab"),
    ("А1 қайда", "where is A1"),
    ("F корпусы", "block F"),
    ("G блогына қалай барамын", "how do I get to block G"),
    ("3-қабаттағы дәретхана", "restroom on floor 3"),
    ("келесі сабағым қайда", "where is my next class"),
    ("қазір қандай сабақ", "where is my next class"),
    ("іс-шаралар", "events"),
]

PLAIN = dict(zip("қәіңғүұөһ", "каингууох"))
LATIN = {"а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ж": "j", "з": "z",
         "и": "i", "й": "i", "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n", "ң": "n", "о": "o", "ө": "o",
         "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u", "ү": "u", "ф": "f", "х": "h", "һ": "h",
         "ш": "sh", "ы": "y", "і": "i", "э": "e", "ю": "iu", "я": "ia", "ь": ""}
SPELLINGS = {
    "kazakh letters": lambda s: s,
    "russian keyboard": lambda s: "".join(PLAIN.get(c, c) for c in s),
    "latin i": lambda s: s.replace("і", "i"),
    "latin letters": lambda s: "".join(LATIN.get(c, LATIN.get(c.lower(), c)) for c in s),
}


def where(answer):
    m = answer.get("map") or {}
    d = answer.get("directions") or {}
    return answer["kind"], m.get("code"), (d.get("from") or {}).get("code")


@pytest.mark.parametrize("spelling", SPELLINGS)
@pytest.mark.parametrize("kk, en", PAIRS)
def test_a_kazakh_question_reaches_the_place_its_english_twin_does(kk, en, spelling):
    asked = SPELLINGS[spelling](kk)
    answer = index.search(asked)
    assert where(answer) == where(index.search(en, lang="en")), asked
    assert answer["lang"] == "kk", asked


@pytest.mark.parametrize("question", ["китапхана кайда", "кiтапхана қайда", "kitaphana qaida",
                                      "asxanaga qalai baramyn", "F204 тен G215 ке", "ис-шаралар"])
def test_kazakh_without_its_letters_is_still_kazakh(question):
    assert i18n.detect(question) == "kk"


@pytest.mark.parametrize("question", ["где библиотека", "как пройти в D103", "из D101 в F204", "где буфет",
                                      "где корпус F", "ближайший туалет к G101"])
def test_russian_stays_russian(question):
    assert i18n.detect(question) == "ru"


@pytest.mark.parametrize("question", ["where is the library", "is the library open", "Wo ist D103?",
                                      "nearest restroom to G101"])
def test_english_stays_english(question):
    # under re.I a dotless "ı" would match the "i" of "is": Latin Kazakh is matched in lower case
    assert i18n.detect(question) == "en"
