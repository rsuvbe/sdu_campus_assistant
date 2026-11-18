"""
Sprint 6, checked story by story against the story sheet (Новая таблица.xlsx):
every responsibility, QA scenario and (Pass)/(Fail) test script of US21 to US24,
and the maintenance tasks a program can check.

  US21 Interface Language Switch            US22 Search in Kazakh and Russian
  US23 Search History and Favourites        US24 Mobile Layout
"""
import json
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import i18n
from app.main import BASE_DIR, app, index, users
from app.pages import translate_html
from app.questions import en as en_questions, kk as kk_questions, ru as ru_questions

STATIC = BASE_DIR / "static"
I18N = STATIC / "i18n"
PAGES = {"/": "index.html", "/events": "events.html", "/profile": "profile.html",
         "/schedule": "schedule.html", "/login": "auth.html"}
APP_JS = (STATIC / "app.js").read_text()
I18N_JS = (STATIC / "i18n.js").read_text()
STYLES = (STATIC / "styles.css").read_text()
PASSWORD = "Campus#2026"


def files() -> dict:
    return {lang: json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8")) for lang in i18n.LANGS}


def someone(number: int, lang: str | None = None) -> TestClient:
    c = TestClient(app)
    if lang:
        c.cookies.set(i18n.LANG_COOKIE, lang)
    email = f"24060{number:04d}@sdu.edu.kz"
    res = c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Aidana Serikova"})
    if res.status_code != 200:
        res = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return c


@pytest.fixture(scope="module")
def counter():
    return iter(range(1000, 9000))


@pytest.fixture()
def me(counter):
    return someone(next(counter))


@pytest.fixture()
def them(counter):
    return someone(next(counter))


@pytest.fixture()
def visitor():
    c = TestClient(app)
    c.post("/api/auth/guest")
    return c


def in_lang(client: TestClient, lang: str) -> TestClient:
    client.cookies.set(i18n.LANG_COOKIE, lang)
    return client


# ------------------------------------------------------------------ US21
def test_us21_constraint_three_local_translation_files_kept_by_the_team():
    assert sorted(p.name for p in I18N.glob("*.json")) == ["en.json", "kk.json", "ru.json"]
    for lang, data in files().items():
        assert set(data) == {"pages", "script", "answers"}, lang


def test_us21_task_every_interface_text_is_in_every_file():
    """tools/i18n.py finds every text where it is written (the pages, t() in the
    scripts and on the server) and lists what a file lacks: nothing."""
    import tools.i18n as tool
    en = tool.english()
    assert files()["en"] == {s: dict(sorted(v.items())) for s, v in en.items()}, "en.json is up to date"
    for lang in ("ru", "kk"):
        report = tool.problems(en, lang)
        assert not report["missing"], (lang, report["missing"][:5])
        assert not report["placeholders"], (lang, report["placeholders"][:5])


def test_us21_no_machine_translation_at_run_time():
    source = (BASE_DIR / "app" / "i18n.py").read_text() + (BASE_DIR / "app" / "pages.py").read_text()
    assert not re.search(r"urllib|requests|httpx|http\.client|translate\.google|deepl", source)
    # a text no file has is shown in English, not sent off to be translated
    with i18n.use("kk"):
        assert i18n.t("A sentence nobody has translated yet.") == "A sentence nobody has translated yet."


def test_us21_scenario_1_the_page_switches_to_kazakh_and_survives_a_reload(me):
    english = me.get("/")
    assert '<html lang="en">' in english.text and "Where do you need to be?" in english.text
    in_lang(me, "kk")
    for _ in range(2):                          # and again, as a reload
        page = me.get("/")
        assert '<html lang="kk">' in page.text
        assert "Қайда бару керек?" in page.text and "Where do you need to be?" not in page.text
        assert "<title>SDU Кампус көмекшісі</title>" in page.text
    # the switch keeps the choice for a year, for the server to read on every page
    assert "sdu-lang=${id}; path=/; max-age=31536000" in I18N_JS


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_us21_scenario_2_no_english_label_remains_on_any_page(me, lang):
    """Every page in Russian and Kazakh: no text of the English page is left, and
    each page's title is translated."""
    from tools.i18n import _Collect
    english_texts = files()["en"]["pages"]
    translated = files()[lang]["pages"]
    in_lang(me, lang)
    for path, name in PAGES.items():
        page = me.get(path) if path != "/login" else TestClient(app, cookies={i18n.LANG_COOKIE: lang}).get(path)
        assert page.status_code == 200, path
        collector = _Collect()
        collector.feed(page.text)
        left = {t for t in collector.found if t in english_texts and translated.get(t) != t
                and re.search(r"[A-Za-z]{2,}", t)}
        assert not left, (path, sorted(left)[:5])
        title = re.search(r"<title>(.*?)</title>", page.text).group(1)
        assert title == translated[re.search(r"<title>(.*?)</title>",
                                             (STATIC / name).read_text()).group(1)], path


def test_us21_the_scripts_get_their_texts_with_the_page(me):
    page = in_lang(me, "ru").get("/").text
    data = json.loads(re.search(r"window\.SDU_I18N=(\{.*?\})</script>", page).group(1).replace("<\\/", "</"))
    assert data["lang"] == "ru" and data["strings"]["How do I get there?"] == "Как пройти?"
    # every page loads the lookup before its own scripts
    for name in PAGES.values():
        html = (STATIC / name).read_text()
        assert html.index("/static/i18n.js") < html.index("/static/theme.js"), name
        assert "data-lang-switch" in html, name


def test_us21_fail_some_labels_stay_in_english_the_server_answers_in_the_language_too(me):
    in_lang(me, "kk")
    services = me.get("/api/services").json()
    assert {s["group_label"] for s in services} >= {"Тамақ және дүкендер", "Деканаттар"}
    lib = next(s for s in services if s["service_id"] == "SVC_LIBRARY")
    assert lib["name"] == "Кітапхана" and lib["ask"] == "Library"   # asked for again in English words
    assert re.search(r"ашық|жабық|ашылады|үзіліс", lib["status"])
    # an error message too
    assert me.put("/api/favourites/Z999").json()["detail"] == "Бұл аудитория анықтамалықта жоқ."
    bad = me.post("/api/schedule", json={"subject": "", "day": 0, "start": "09:00", "end": "09:50", "room": "D103"})
    assert bad.json()["detail"]["message"] == "Пәнді енгізіңіз."


def test_us21_fail_the_language_resets_on_every_page_load():
    """The choice is a cookie the server reads on every request; no page sets it back."""
    c = TestClient(app, cookies={i18n.LANG_COOKIE: "ru"})
    c.post("/api/auth/guest")
    for path in ("/", "/events", "/", "/events"):
        assert '<html lang="ru">' in c.get(path).text
    for name in PAGES.values():
        assert "sdu-lang" not in (STATIC / name).read_text()


def test_us21_an_unknown_language_is_english():
    c = TestClient(app, cookies={i18n.LANG_COOKIE: "fr"})
    c.post("/api/auth/guest")
    assert '<html lang="en">' in c.get("/").text


def test_us21_the_page_text_is_put_in_place_on_the_server_not_flashed_in_english():
    out = translate_html('<html lang="en"><head><title>Your week</title></head><body>'
                         '<p>Where do you need to be?</p><input placeholder="Room, hall, office or block">'
                         '<script>var x = "Where do you need to be?";</script></body></html>', "ru")
    assert "<title>Ваша неделя</title>" in out and "<p>Куда вам нужно?</p>" in out
    assert 'placeholder="Аудитория, зал, офис или блок"' in out
    assert 'var x = "Where do you need to be?";' in out, "a script is left alone"


def test_us21_counted_texts_take_the_language_s_forms():
    one, other = "{n} room, booked for classes", "{n} rooms, booked for classes"
    with i18n.use("ru"):
        assert [i18n.tn(n, one, other).split(",")[0] for n in (1, 3, 5, 21)] == [
            "1 аудитория", "3 аудитории", "5 аудиторий", "21 аудитория"]
    with i18n.use("kk"):
        assert i18n.tn(5, one, other).startswith("5 аудитория")
    assert i18n.tn(1, one, other).startswith("1 room,") and i18n.tn(2, one, other).startswith("2 rooms,")
    # the same rule in the browser (static/i18n.js)
    assert "n % 10 >= 2 && n % 10 <= 4" in I18N_JS


# ------------------------------------------------------------------ US22
REGRESSIONS = {"en": en_questions.REGRESSION, "ru": ru_questions.REGRESSION, "kk": kk_questions.REGRESSION}


def test_us22_task_a_regression_list_per_language_asks_the_same_rooms():
    rooms = {lang: [code for _, code in items] for lang, items in REGRESSIONS.items()}
    assert rooms["en"] == rooms["ru"] == rooms["kk"] and len(rooms["en"]) >= 10


@pytest.mark.parametrize("lang, question, code",
                         [(lang, q, code) for lang, items in REGRESSIONS.items() for q, code in items])
def test_us22_pass_the_same_question_in_all_three_languages_reaches_the_same_room(lang, question, code):
    answer = index.search(question)
    assert (answer.get("map") or {}).get("code") == code, (question, answer["kind"], answer.get("title"))
    assert answer["lang"] == lang


def test_us22_scenario_1_a_kazakh_question_is_answered_in_kazakh(me):
    answer = in_lang(me, "kk").get("/api/search", params={"q": "F204 аудиториясы қайда?"}).json()
    assert answer["map"]["code"] == "F204" and answer["lang"] == "kk"
    assert answer["summary"] == "F204 — 2-қабатта, F блогы — Инженерия және жаратылыстану ғылымдары факультеті."
    assert all(not re.search(r"\b(?:floor|Block|wing|door)\b", step) for step in answer["steps"])


def test_us22_scenario_2_a_russian_question_is_answered_in_russian(me):
    answer = in_lang(me, "ru").get("/api/search", params={"q": "Где находится D103?"}).json()
    assert answer["map"]["code"] == "D103" and answer["lang"] == "ru"
    assert answer["summary"].startswith("D103 — на 1-м этаже")
    assert all(re.search(r"[а-яё]", step) for step in answer["steps"])


def test_us22_fail_a_kazakh_question_with_a_valid_room_code_is_understood():
    for question in ("D103 қайда?", "Д103 қайда?", "D103 бөлмесі қай жерде?", "D103-ке қалай барамын?"):
        answer = index.search(question)
        assert answer["kind"] == "room" and answer["map"]["code"] == "D103", question
        assert answer["lang"] == "kk"


def test_us22_fail_a_russian_question_is_not_answered_in_english():
    for question in ("Где G215?", "Как пройти в библиотеку?", "Где туалет в блоке F?", "Из D103 в F204"):
        answer = index.search(question)
        assert answer["lang"] == "ru"
        text = " ".join([answer["title"], answer.get("summary", "")] + answer.get("steps", [])
                        + (answer.get("directions") or {}).get("steps", []))
        assert not re.search(r"\b(?:is on floor|Follow|Turn|the central corridor|door on your)\b", text), question


def test_us22_a_kazakh_route_says_its_way_in_kazakh():
    answer = index.search("D103-тен F204-ке қалай барамын?")
    route = answer["directions"]
    assert route["from"]["code"] == "D103" and route["to"]["code"] == "F204"
    assert route["summary"] == "Бағыт: D103 → F204, 1-қабаттан 2-қабатқа."
    assert all(re.search(r"[әіңғүұқөһ]", step) for step in route["steps"])
    # the way to a place in words: "to the library", "from the library to the cafeteria"
    assert index.search("Кітапханаға қалай барамын?")["directions"]["to"]["code"] == "LIBRARY"
    trip = index.search("Кітапханадан асханаға қалай барамын?")["directions"]
    assert (trip["from"]["code"], trip["to"]["code"]) == ("LIBRARY", "CAFETERIA")


def test_us22_kazakh_blocks_floors_kinds_and_the_next_class():
    assert index.search("G блогындағы дәретхана")["map"]["code"] == "RESTROOM-G"
    labs = index.search("F блогындағы зертханалар")
    assert labs["kind"] == "list" and {r["building_id"] for r in labs["results"]} == {"F"}
    assert index.search("Келесі сабағым қайда?")["kind"] == "needs_account"     # a visitor's
    assert index.search("Жатақханаға қалай барамын?")["map"]["code"] == "STUDENT-HOUSE"


def test_us22_a_question_with_no_language_of_its_own_takes_the_interface_s(me):
    in_lang(me, "kk")
    assert me.get("/api/search", params={"q": "D103"}).json()["lang"] == "kk"
    assert me.get("/api/search", params={"q": "Where is D103?"}).json()["lang"] == "en"
    in_lang(me, "en")
    assert me.get("/api/search", params={"q": "Д217"}).json()["lang"] == "en"


def test_us22_the_way_there_is_in_the_language_of_the_question(me):
    in_lang(me, "en")
    route = me.get("/api/route", params={"to": "F204", "lang": "kk"}).json()
    assert route["summary"].startswith("Бағыт: басты кіреберіс → F204")
    assert "data-lang" in APP_JS and "&lang=" in APP_JS


def test_us22_constraint_pattern_lists_per_language_no_translation_service():
    folder = BASE_DIR / "app" / "questions"
    assert {p.name for p in folder.glob("*.py")} == {"__init__.py", "en.py", "ru.py", "kk.py"}
    for p in folder.glob("*.py"):
        assert not re.search(r"urllib|requests|httpx|translate", p.read_text().replace("translation service", "")), p


def test_us22_deferred_other_languages_are_not_parsed_as_kazakh_or_russian():
    assert i18n.detect("Wo ist D103?") == "en"      # a Latin question goes to the English parser
    assert i18n.detect("D103") is None and i18n.detect("Red Hall") is None


# ------------------------------------------------------------------ US23
def test_us23_scenario_1_history_is_kept_and_a_press_repeats_it(me):
    for q in ("D103", "Where is the library?", "F204", "D103"):
        assert me.get("/api/search", params={"q": q}).status_code == 200
    history = [h["query"] for h in me.get("/api/history").json()["history"]]
    assert history == ["D103", "F204", "Where is the library?"], "newest first, asked again moves up"
    # the page lists them, and a press asks again
    assert 'id="mine-recent-list"' in (STATIC / "index.html").read_text()
    assert 'class="recent" data-ask="${esc(h.query)}"' in APP_JS


def test_us23_only_the_latest_ten_are_kept(me):
    for n in range(1, 13):
        me.get("/api/search", params={"q": f"G{200 + n}"})
    history = [h["query"] for h in me.get("/api/history").json()["history"]]
    assert len(history) == 10 and history[0] == "G212" and "G201" not in history


def test_us23_a_press_on_the_plan_is_not_a_search_to_keep(me):
    me.get("/api/search", params={"q": "H304", "record": "0"})
    assert "H304" not in [h["query"] for h in me.get("/api/history").json()["history"]]
    assert "ask(room.ask || room.code, false)" in APP_JS


def test_us23_history_can_be_cleared(me):
    me.get("/api/search", params={"q": "D103"})
    assert me.delete("/api/history").json() == {"ok": True}
    assert me.get("/api/history").json()["history"] == []


def test_us23_fail_one_user_never_sees_another_s_history_or_stars(me, them):
    me.get("/api/search", params={"q": "My own question about E207"})
    me.put("/api/favourites/E207")
    assert "My own question about E207" not in [h["query"] for h in them.get("/api/history").json()["history"]]
    assert "E207" not in [f["code"] for f in them.get("/api/favourites").json()["favourites"]]
    assert them.delete("/api/favourites/E207").status_code == 404
    assert "E207" in [f["code"] for f in me.get("/api/favourites").json()["favourites"]]


def test_us23_scenario_2_a_visitor_keeps_nothing(visitor):
    def rows():
        if users.backend != "sqlite":
            pytest.skip("counted in the SQLite store")
        with sqlite3.connect(users.path) as conn:
            return conn.execute("SELECT COUNT(*) FROM search_history").fetchone()[0], \
                conn.execute("SELECT COUNT(*) FROM favourites").fetchone()[0]
    before = rows()
    for q in ("D103", "Where is the library?", "F204"):
        assert visitor.get("/api/search", params={"q": q}).status_code == 200
    assert rows() == before, "nothing written to the history table"
    assert visitor.get("/api/history").status_code == 403
    assert visitor.put("/api/favourites/D103").status_code == 403
    assert rows() == before
    # and the page shows no list: it is only filled for an account
    assert "if (!visitor) loadMine();" in APP_JS


def test_us23_pass_a_starred_room_persists_across_logins_and_reopens_with_one_tap(counter):
    number = next(counter)
    first = someone(number)
    star = first.put("/api/favourites/hall%20a1").json()       # its hall name is enough
    assert star == {"code": "D117", "label": "D117", "ask": "D117", "where": "Floor 1 · Block D"}
    first.post("/api/auth/logout")
    again = someone(number)                                    # signs in to the same account
    favourites = again.get("/api/favourites").json()["favourites"]
    assert [f["code"] for f in favourites] == ["D117"]
    # one tap asks for it again, and lands on that room
    assert index.search(favourites[0]["ask"])["map"]["code"] == "D117"
    assert 'data-ask="${esc(f.ask)}"' in APP_JS


def test_us23_fail_a_starred_room_can_be_unstarred(me):
    assert me.put("/api/favourites/Library").status_code == 200
    assert "LIBRARY" in [f["code"] for f in me.get("/api/favourites").json()["favourites"]]
    assert me.delete("/api/favourites/LIBRARY").json() == {"ok": True}
    assert me.get("/api/favourites").json()["favourites"] == []
    # on the card (the star again) and in the list (its cross)
    assert "data-star=" in APP_JS and "data-unstar=" in APP_JS and 'method: on ? "DELETE" : "PUT"' in APP_JS


def test_us23_only_rooms_of_the_directory_are_starred_once_each(me):
    assert me.put("/api/favourites/Z999").status_code == 404
    me.put("/api/favourites/D103")
    me.put("/api/favourites/d103")
    assert [f["code"] for f in me.get("/api/favourites").json()["favourites"]] == ["D103"]


def test_us23_starred_rooms_are_named_in_the_interface_language(me):
    me.put("/api/favourites/Library")
    in_lang(me, "kk")
    fav = me.get("/api/favourites").json()["favourites"][0]
    assert fav["label"] == "Кітапхана" and fav["ask"] == "Library" and fav["where"] == "1-қабат · B блогы"


# ------------------------------------------------------------------ US24
def test_us24_constraint_plain_css_no_ui_framework():
    for name in PAGES.values():
        html = (STATIC / name).read_text()
        assert not re.search(r"bootstrap|tailwind|bulma|foundation\.css|materialize", html, re.I), name
        assert 'name="viewport" content="width=device-width, initial-scale=1' in html, name
    requirements = (BASE_DIR / "requirements.txt").read_text().lower()
    assert "bootstrap" not in requirements


def test_us24_task_controls_are_a_finger_s_size_on_a_phone():
    phone = STYLES[STYLES.index("/* US24: on a phone every control"):]
    assert "@media (max-width: 767px)" in phone
    assert re.search(r"\.chip, \.fav-x, \.mine-head \.btn-text \{ min-height: 44px; \}", phone)
    assert ".btn-line, .btn-text, .theme-opt { min-height: 44px; }" in phone


def test_us24_task_long_words_never_push_a_card_past_the_screen():
    assert ".route > *, .trip > *, .trip-from > *, .card > *, .listing > *, .prompt > * { min-width: 0; }" in STYLES
    assert "overflow-wrap: anywhere" in STYLES


def test_us24_pass_the_plan_fills_the_width_and_pans_and_zooms_on_touch():
    # the plan under the bar on a phone, the answers a sheet over it (since Sprint 3)
    assert "position: absolute; left: 0; right: 0; bottom: 0; top: var(--bar-h);" in STYLES
    assert re.search(r"pointers?\.size === 2|touches\.length === 2|pinch", APP_JS, re.I)
    assert "viewBox" in APP_JS
