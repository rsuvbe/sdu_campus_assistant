"""
The pages in the interface language (US21).

A page's own text is in English in static/*.html. Before it is sent, every text
between tags and every label attribute (placeholder, aria-label, title, alt,
the description) is looked up in the language's "pages" map and replaced; the
page's <html lang> is set; and the "script" map — the texts the page's scripts
write — is put in the page for static/i18n.js. So the page arrives in its
language whole: nothing flashes in English first, and nothing is translated by
a machine on the way.
"""
from __future__ import annotations

import functools
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from . import i18n

LABEL_ATTRS = {"placeholder", "aria-label", "title", "alt", "label", "data-label"}
SPACE = re.compile(r"\s+")


def key_of(text: str) -> str:
    """A text as the translation files keep it: its words, one space apart."""
    return SPACE.sub(" ", text).strip()


class _Translator(HTMLParser):
    """Re-emits the page as it was, with its texts in the language."""

    def __init__(self, words: dict) -> None:
        super().__init__(convert_charrefs=True)
        self.words = words
        self.out: list[str] = []
        self.raw = 0                 # inside <script> or <style>: left alone

    def _say(self, text: str) -> str:
        key = key_of(text)
        found = self.words.get(key) if key else None
        if not found:
            return html.escape(text, quote=False)
        lead = text[:len(text) - len(text.lstrip())]
        tail = text[len(text.rstrip()):]
        return lead + html.escape(found, quote=False) + tail

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if tag in ("script", "style"):
            self.raw += 1
        is_description = tag == "meta" and dict(attrs).get("name") == "description"
        for name, value in attrs:
            if value and (name in LABEL_ATTRS or (is_description and name == "content")):
                found = self.words.get(key_of(value))
                if found:
                    raw = self._replace_attr(raw, name, found)
        self.out.append(raw)

    @staticmethod
    def _replace_attr(raw: str, name: str, value: str) -> str:
        pattern = re.compile(rf'(\s{re.escape(name)}=)("[^"]*"|\'[^\']*\')')
        return pattern.sub(lambda m: f'{m.group(1)}"{html.escape(value, quote=True)}"', raw, count=1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.raw:
            self.raw -= 1
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data if self.raw else self._say(data))

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def unknown_decl(self, data):
        self.out.append(f"<![{data}]>")


def translate_html(source: str, lang: str) -> str:
    lang = i18n.clean(lang)
    strings = i18n.page_strings(lang)
    if lang != i18n.DEFAULT and strings:
        parser = _Translator(strings)
        parser.feed(source)
        parser.close()
        source = "".join(parser.out)
    source = re.sub(r"<html\b[^>]*>", f'<html lang="{lang}">', source, count=1)
    payload = json.dumps({"lang": lang, "strings": i18n.script_strings(lang)}, ensure_ascii=False,
                         separators=(",", ":")).replace("</", "<\\/")
    script = f"<script>window.SDU_I18N={payload}</script>"
    return source.replace("<head>", "<head>\n" + script, 1)


@functools.lru_cache(maxsize=64)
def _render(path: str, mtime_ns: int, lang: str, files_stamp: float) -> bytes:
    return translate_html(Path(path).read_text(encoding="utf-8"), lang).encode("utf-8")


def render(path: Path, lang: str) -> bytes:
    """The page at `path` in `lang`, kept until the page or the translations change."""
    return _render(str(path), path.stat().st_mtime_ns, i18n.clean(lang), i18n.files_stamp())
