"""
Keep the three translation files whole (US21, US22).

    python3 tools/i18n.py            # write static/i18n/en.json, list what ru and kk lack
    python3 tools/i18n.py --check    # the same, without writing; fails if a file lacks a text

Every text the site shows is found where it is written:

  * "pages":   the texts and label attributes of static/*.html;
  * "script":  t("..."), tn(n, "...", "...") and tr("...") in static/*.js, texts
               marked /* i18n */, and the names the floor plans carry (rooms,
               halls, exits), which the map shows;
  * "answers": t(...), tn(...) and AuthError(...) in app/*.py, and the names
               and words of the campus data the answers are made of.

en.json is written from them: each key is its own English text (a counted one
lists its two English forms). ru.json and kk.json are the team's: this lists
every text they lack, every one they keep that is no longer used, and every
translation whose {placeholders} differ from the English.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDULIFE_SYNC", "0")

I18N = ROOT / "static" / "i18n"
LETTER = re.compile(r"[A-Za-z]")
LABEL_ATTRS = {"placeholder", "aria-label", "title", "alt", "label", "data-label"}


def key_of(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------------- pages
class _Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self.raw = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.raw += 1
        is_description = tag == "meta" and dict(attrs).get("name") == "description"
        for name, value in attrs:
            if value and (name in LABEL_ATTRS or (is_description and name == "content")):
                self.found.append(key_of(value))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.raw:
            self.raw -= 1

    def handle_data(self, data):
        if not self.raw:
            self.found.append(key_of(data))


def page_texts() -> dict:
    out = {}
    for page in sorted((ROOT / "static").glob("*.html")):
        parser = _Collect()
        parser.feed(page.read_text(encoding="utf-8"))
        for text in parser.found:
            if text and LETTER.search(text):
                out[text] = text
    return out


# ------------------------------------------------------------------ script
JS_STRING = r'"((?:[^"\\]|\\.)*)"'
JS_CALL = re.compile(r"(?<![\w.])(?:t|tr|window\.t)\(\s*" + JS_STRING)
JS_COUNTED = re.compile(r"(?<![\w.])tn\(\s*[^,]+,\s*" + JS_STRING + r"\s*,\s*" + JS_STRING)
JS_MARKED = re.compile(r"/\*\s*i18n\s*\*/\s*" + JS_STRING)


def _js(text: str) -> str:
    return json.loads(f'"{text}"')


def script_texts() -> dict:
    out: dict = {}
    for script in sorted((ROOT / "static").glob("*.js")):
        if script.name == "i18n.js":
            continue
        source = script.read_text(encoding="utf-8")
        for m in JS_CALL.finditer(source):
            out[_js(m.group(1))] = _js(m.group(1))
        for m in JS_MARKED.finditer(source):
            out[_js(m.group(1))] = _js(m.group(1))
        for m in JS_COUNTED.finditer(source):
            out[_js(m.group(1))] = [_js(m.group(1)), _js(m.group(2))]
    # i18n.js writes a few itself
    for text in ("Language", "Language: {name}. Change language"):
        out[text] = text
    out.update({k: k for k in map_texts()})
    from app.engine import DAY_NAMES
    out.update({d: d for d in DAY_NAMES})
    return out


def map_texts() -> set[str]:
    """The names the plans carry, which the map shows in the interface language."""
    from app.main import campus_map
    found: set[str] = set()
    for floor in campus_map.floor_list():
        for room in floor["rooms"]:
            for key in ("label", "service", "sub"):
                if room.get(key):
                    found.add(room[key])
        for feature in floor["features"]:
            if feature.get("label"):
                found.add(feature["label"])
        for lm in floor["landmarks"]:
            found.add(lm["name"])
        for block in floor.get("blocks", []):
            if block.get("name"):
                found.add(block["name"])
    grounds = campus_map.grounds()
    for g in grounds.get("grounds", []):
        if g.get("label"):
            found.add(g["label"])
    for b in grounds.get("buildings", []):
        found.update((b["label"], b["sub"]))
    for label in grounds.get("labels", []):
        found.add(label["text"])
        if label.get("sub"):
            found.add(label["sub"])
    # a code is the same in every language
    return {text for text in found if LETTER.search(text) and not re.fullmatch(r"[A-I]\d{3}(?:/[A-I]\d{3})?", text)}


# ----------------------------------------------------------------- answers
def _const(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def answer_texts() -> dict:
    out: dict = {}
    for module in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = _name(node.func)
            if name in ("t", "AuthError"):
                text = _const(node.args[0])
                if text is not None:
                    out[text] = text
                elif isinstance(node.args[0], ast.IfExp):          # t("a" if x else "b")
                    for branch in (node.args[0].body, node.args[0].orelse):
                        if _const(branch) is not None:
                            out[_const(branch)] = _const(branch)
            elif name == "tn" and len(node.args) >= 3:
                one, other = _const(node.args[1]), _const(node.args[2])
                if one is not None and other is not None:
                    out[one] = [one, other]
            elif name == "append" and isinstance(node.func, ast.Attribute) \
                    and _name(node.func.value) == "problems":      # the password's rules
                arg = node.args[0]
                text = _const(arg) or (_const(arg.elts[0]) if isinstance(arg, ast.Tuple) else None)
                if text:
                    out[text] = text
    out.update({k: k for k in data_texts()})
    return out


def data_texts() -> set[str]:
    """The words of the campus data that answers are made of."""
    import app.auth as auth
    import app.engine as engine
    import app.main as main
    import app.site as site
    found: set[str] = set()
    found.update(engine.DEPARTMENTS.values(), engine.ROOM_TYPES.values(), engine.CATEGORY_LABELS.values())
    found.update(label for _, label, _ in engine.SERVICE_GROUPS)
    found.update(label for _, label, _, _ in engine.ROOM_COLLECTIONS)
    found.update(engine.DAY_NAMES, (d[:3] for d in engine.DAY_NAMES), engine.MONTH_NAMES, engine.ORDINALS.values())
    found.update(engine.SPOKEN.values(), engine.SPOKEN.keys())
    found.update({engine.CODE_FORMAT_HINT, auth.EMAIL_HINT, main.RESET_SENT, "Other", "Room", "up", "down",
                  "the Medcenter", "Medcenter", engine.LIFE_CENTRE, "Place not announced"})
    index = main.index
    found.update(index.buildings.values())
    for room in index.rooms:
        if room.get("purpose"):
            found.add(room["purpose"])
        if engine.is_named(room):
            found.add(room["name"])
            found.add(engine.base_name(room["name"]))
    for svc in index.services.values():
        found.add(svc["name"])
        found.add(engine.base_name(svc["name"]))
        if svc.get("short_name"):
            found.add(svc["short_name"])
        if svc.get("notes"):
            found.add(svc["notes"])
    for items in index.landmarks.values():
        found.update(lm["name"] for lm in items)
    for b in site.BUILDINGS + site.SPOTS:
        found.update((b["label"], b["sub"], b["about"]))
        if b.get("spoken"):
            found.add(b["spoken"])
        found.update(b.get("halls", {}).values())
        for way in b["ways"]:
            found.update(way["say"])
    return {text for text in found if text and LETTER.search(text)}


# -------------------------------------------------------------------- files
def english() -> dict:
    return {"pages": page_texts(), "script": script_texts(), "answers": answer_texts()}


PLACEHOLDER = re.compile(r"\{(\w+)\}")


def holes(text) -> set[str]:
    texts = text if isinstance(text, list) else [text]
    return {name for t in texts for name in PLACEHOLDER.findall(t)}


def problems(en: dict, lang: str) -> dict:
    path = I18N / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = {"missing": [], "unused": [], "placeholders": []}
    for section, keys in en.items():
        have = data.get(section, {})
        for key, value in keys.items():
            if key not in have or not have[key]:
                report["missing"].append((section, key))
            # a door's or a hall's place in a row comes as a word ({nth}) and a number ({pos})
            elif holes(have[key]) - holes(value) - ({"pos"} if "nth" in holes(value) else set()):
                report["placeholders"].append((section, key))
        report["unused"] += [(section, key) for key in have if key not in keys]
    return report


def main(argv: list[str]) -> int:
    check = "--check" in argv
    en = english()
    text = json.dumps({s: dict(sorted(v.items())) for s, v in en.items()}, ensure_ascii=False, indent=1) + "\n"
    if not check:
        (I18N / "en.json").write_text(text, encoding="utf-8")
    failed = False
    for lang in ("ru", "kk"):
        report = problems(en, lang)
        for kind, items in report.items():
            if items:
                print(f"{lang}.json: {len(items)} {kind}")
                for section, key in items[:400]:
                    print(f"   [{section}] {key}")
        failed |= bool(report["missing"] or report["placeholders"])
    total = sum(len(v) for v in en.values())
    print(f"{total} texts: " + ", ".join(f"{len(v)} {k}" for k, v in en.items()))
    return 1 if failed and check else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
