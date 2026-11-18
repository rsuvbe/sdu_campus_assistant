"""
The question patterns of each language (US22), one file per language, kept by
the team: en.py, ru.py, kk.py.

The parser (app/engine.py) reads English and much of Russian. A question in
another language is first put into words it reads — "D103-тен F204-ке қалай
барамын?" becomes "from D103 to F204" — and then answered like any other, in
the language it was asked in. Nothing goes to a translation service: each file
is a list of patterns and the words they stand for.
"""
from __future__ import annotations

import re

from . import en, kk, ru

LANGUAGES = {"en": en, "ru": ru, "kk": kk}


def rewrite(query: str, lang: str | None) -> str:
    """The question in words the parser reads. A question in English, or in no
    language at all ("D103"), comes back as it was."""
    module = LANGUAGES.get(lang or "")
    if module is None:
        return query
    out = module.rewrite(query)
    return re.sub(r"\s+", " ", out).strip() or query
