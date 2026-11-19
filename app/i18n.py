"""
Interface languages (US21) and the language of a question (US22).

Every text the site shows comes from three translation files kept by the team,
static/i18n/en.json, ru.json and kk.json. Each holds three maps:

  * "pages": the texts of the pages themselves (static/*.html), put in place
    by the server before a page is sent (app/pages.py);
  * "script": what the pages' scripts write, sent with the page (static/i18n.js);
  * "answers": what the server writes — answers, routes, statuses, messages.

A key is the English text itself, with {placeholders}: "Floor {n}". A key with
counted forms has a list as its value: English [one, other], Russian [one, few,
many]; Kazakh has one form. Nothing is translated by a machine at run time: a key
a file lacks is shown in English, and tools/i18n.py lists what each file lacks.

The language of a request is the `sdu-lang` cookie the switch sets (English when
there is none). A question is answered in its own language when it has one
("Где D103?" in Russian even on the English interface); a bare code ("D103")
takes the interface's.
"""
from __future__ import annotations

import json
import re
import time
from contextvars import ContextVar
from pathlib import Path

LANGS = ("en", "ru", "kk")
DEFAULT = "en"
LANG_COOKIE = "sdu-lang"
I18N_DIR = Path(__file__).resolve().parent.parent / "static" / "i18n"

_lang: ContextVar[str] = ContextVar("lang", default=DEFAULT)
_files: dict[str, dict] = {}


SECTIONS = ("pages", "script", "answers")


def _path(lang: str) -> Path:
    return I18N_DIR / f"{lang}.json"


def _load(lang: str) -> dict:
    stamp = files_stamp()
    if _files.get("_stamp") != stamp:
        _files.clear()
        _files["_stamp"] = stamp
    if lang not in _files:
        try:
            data = json.loads(_path(lang).read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        _files[lang] = {name: data.get(name, {}) for name in SECTIONS}
    return _files[lang]


_stamp_seen = [0.0, 0.0]        # [checked at (monotonic), stamp]


def files_stamp() -> float:
    """When the translation files last changed (looked at once a second at most):
    a page or a map read before is read again after an edit, without a restart."""
    now = time.monotonic()
    if now - _stamp_seen[0] < 1.0:
        return _stamp_seen[1]
    stamp = 0.0
    for lang in LANGS:
        try:
            stamp = max(stamp, _path(lang).stat().st_mtime)
        except FileNotFoundError:
            pass
    _stamp_seen[:] = [now, stamp]
    return stamp


def page_strings(lang: str) -> dict:
    """The pages' own texts in a language."""
    return _load(clean(lang))["pages"] if clean(lang) != DEFAULT else {}


def script_strings(lang: str) -> dict:
    """What the pages' scripts write, in a language: sent with every page."""
    return _load(clean(lang))["script"] if clean(lang) != DEFAULT else {}


def clean(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT


def current() -> str:
    return _lang.get()


def set_lang(lang: str | None):
    """Answer in `lang` from here on, in this request. Returns the token to reset."""
    return _lang.set(clean(lang))


class use:
    """`with use("kk"): ...` — answers in Kazakh inside the block."""

    def __init__(self, lang: str | None) -> None:
        self.lang = clean(lang)

    def __enter__(self):
        self._token = _lang.set(self.lang)
        return self

    def __exit__(self, *exc):
        _lang.reset(self._token)


class _Keep(dict):
    """str.format_map that leaves an unknown {name} as it is."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fill(template: str, values: dict) -> str:
    return template.format_map(_Keep(values)) if values else template


def t(text: str, /, **values) -> str:
    """`text` in the request's language, its {placeholders} filled."""
    lang = _lang.get()
    found = _load(lang)["answers"].get(text) if lang != DEFAULT else None
    if isinstance(found, list):
        found = found[0] if found else None
    return _fill(found or text, values)


def plural_index(lang: str, n: int) -> int:
    n = abs(int(n))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    if lang == "kk":
        return 0
    return 0 if n == 1 else 1


def tn(n: int, one: str, other: str, /, **values) -> str:
    """A counted text: tn(3, "{n} room", "{n} rooms") — "3 rooms", "3 комнаты", "3 бөлме".
    The key is the English `one`; its value lists the language's forms."""
    lang = _lang.get()
    values = {"n": n, **values}
    forms = _load(lang)["answers"].get(one) if lang != DEFAULT else None
    if isinstance(forms, str):
        forms = [forms]
    if not forms:
        forms = [one, other]
        lang = DEFAULT
    index = min(plural_index(lang, n), len(forms) - 1)
    return _fill(forms[index], values)


def and_word() -> str:
    return t(" and ")


def human_list(items: list[str]) -> str:
    """"A, B and C" in the request's language."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + and_word() + items[-1]


# ------------------------------------------------- the language of a question
# Letters only Kazakh writes, and Kazakh words a location question is made of.
KK_LETTERS = re.compile(r"[әіңғүұқөһ]", re.I)
KK_WORDS = re.compile(r"(?<![^\W\d_])(?:қайда|қай\s+жерде|қалай|барамын|барам|баруға|бару|жетемін|жету|"
                      r"бөлме\w*|аудиториясы\w*|кабинеті\w*|кітапхана\w*|асхана\w*|сабағ\w*|сабақ\w*|"
                      r"келесі|дәріс\w*|қабат\w*|блогы\w*|корпусы\w*|ғимарат\w*|ашық\w*|жабық\w*|кіреберіс\w*|"
                      r"залы\w*|іс-?\s?шара\w*|шаралар\w*|дәретхана\w*|әжетхана\w*|жатақхана\w*|медбике\w*|деканаты\w*|"
                      r"мен|менің|маған|ма|ме|ба|бе|па|пе)(?![^\W\d_])", re.I)
# the same words as Kazakh is typed on a Russian keyboard: "кайда", "калай", "китапхана"
KK_WORDS_PLAIN = re.compile(KK_WORDS.pattern.translate(str.maketrans("әғқңөұүһі", "агкноуухи")), re.I)
# a room code with a Kazakh ending: "F204-ке", "D103 тен", "G215ге" (no Russian ending looks like these)
KK_CODE_ENDING = re.compile(r"(?<![^\W\d_])[a-iа-я]\s?\d{3}\s?-?\s?(?:тен|тан|ден|дан|нен|нан|ке|ка|ге|га|ға|қа|"
                            r"ның|нің|дың|дің|тың|тің)(?![^\W\d_])", re.I)
CYRILLIC = re.compile(r"[а-яё]", re.I)
LATIN_WORD = re.compile(r"(?<![^\W\d_])[a-z]{2,}(?![^\W\d_])", re.I)
# words that are a place's name or a code's letter, not a language: "Red Hall", "Block"
NAME_WORDS = {"red", "hall", "canteen", "coffee", "doner", "house", "ay", "market", "wifi", "wi", "fi",
              "zone", "sdu", "life", "centre", "center", "moodle", "it", "study", "space", "mini",
              "shanyraq", "medcenter", "no"}


# What makes Cyrillic Russian rather than a word both languages share ("кофе",
# "спортзал", "банкомат"): a Russian question word or preposition, or a Russian
# ending ("столовая", "находится", "пройти").
RU_MARKERS = re.compile(
    r"(?<![^\W\d_])(?:где|как|куда|когда|откуда|что|это|есть|ли|мне|мой|моя|мои|в|во|на|до|из|от|к|ко|"
    r"с|у|и|или|по|для|сегодня|завтра|сейчас|открыт\w*|закрыт\w*|можно|нужно|хочу)(?![^\W\d_])"
    r"|[а-яё]{2,}(?:ая|яя|ый|ий|ое|ее|ые|ие|ого|его|ому|ему|ть|ться|тся|ешь|ишь|ете|ите)(?![^\W\d_])",
    re.I)


def answer_lang(question: str, interface: str | None) -> str:
    """The language to answer a question in (US22): its own, or the interface's
    when it has none. Cyrillic with nothing Russian about it ("кофе", "спортзал")
    is as much Kazakh as Russian, so a Kazakh interface answers it in Kazakh."""
    asked = detect(question)
    if asked == "ru" and interface == "kk" and not RU_MARKERS.search(question or ""):
        return "kk"
    return asked or clean(interface)


def detect(question: str) -> str | None:
    """The language a question is written in, or None when it has none of its
    own: a code ("D103", "Д217"), a hall's name ("Red Hall")."""
    text = question or ""
    if KK_LETTERS.search(text) or KK_WORDS.search(text):
        return "kk"
    # Kazakh typed without its letters ("китапхана кайда", "кiтапхана") or in
    # Latin ones ("kitaphana qaida"): the same words, in one spelling
    from .questions.kk import is_latin_kazakh, plain
    if is_latin_kazakh(text) or KK_CODE_ENDING.search(text) or KK_WORDS_PLAIN.search(plain(text)):
        return "kk"
    # Cyrillic words, not a lone block letter typed in Cyrillic ("Д217")
    words = re.findall(r"[^\W\d_]+", text)
    if any(CYRILLIC.search(w) and len(w) > 1 for w in words):
        return "ru"
    latin = [w.lower() for w in LATIN_WORD.findall(text)]
    if any(w not in NAME_WORDS for w in latin):
        return "en"
    return None


# ------------------------------------------------------------------ middleware
def request_lang(cookie_header: str | None) -> str:
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == LANG_COOKIE:
            return clean(value.strip())
    return DEFAULT


class LanguageMiddleware:
    """Every request is answered in the interface language the cookie names."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cookie = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
        token = _lang.set(request_lang(cookie))
        scope.setdefault("state", {})["lang"] = _lang.get()
        try:
            await self.app(scope, receive, send)
        finally:
            _lang.reset(token)
