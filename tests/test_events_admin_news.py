"""
Campus events added by an administrator (US26), and SDU University's own news
read from sdu.edu.kz.

The university publishes no events a program can read: its events page is
empty and the home page's "upcoming events" are pictures. Its news is an RSS
feed, shown as news with the day it was published. Events with a time and a
room are added by the accounts named in CAMPUS_ADMINS.

Nothing here goes to the network: the feed is a document written below.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.auth import AuthError, clean_event
from app.main import app, index
from app.news import FRESH, RETRY, FeedError, NewsFeed, parse_feed

PASSWORD = "Campus#2026"
ADMIN = "240104001@sdu.edu.kz"
EVENT = {"title": "Robotics Club Demo", "description": "Robots on show, all welcome.",
         "room": "F202", "starts": "2030-11-20T15:00", "ends": "2030-11-20T17:00",
         "link": "https://sdu.edu.kz/en/robotics/"}

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>SDU University</title>
<item>
  <title>Open Day 2026 Held at SDU University</title>
  <link>https://sdu.edu.kz/en/open-day-2026-held-at-sdu-university/</link>
  <pubDate>Tue, 03 Nov 2026 11:48:37 +0000</pubDate>
  <description><![CDATA[<p>Open Day 2026 Held at SDU University SDU University hosted Open Day 2026 for prospective students &amp; their parents.</p> [&#8230;]]]></description>
  <content:encoded><![CDATA[<img src="https://elsewhere.example/x.jpg"><img src="https://sdu.edu.kz/wp-content/uploads/2026/11/open-day.jpeg" alt="">]]></content:encoded>
</item>
<item>
  <title>SDU University Participates in Profit Education Day 2026</title>
  <link>https://sdu.edu.kz/en/profit-education-day-2026/</link>
  <pubDate>Fri, 06 Nov 2026 12:24:10 +0000</pubDate>
  <description><![CDATA[""" + ("Representatives took part in a long day of talks. " * 12).encode() + b"""]]></description>
</item>
<item>
  <title>A story that points away</title>
  <link>https://elsewhere.example/story/</link>
  <pubDate>Sat, 07 Nov 2026 10:00:00 +0000</pubDate>
  <description>Not ours.</description>
</item>
</channel></rss>"""


def account(number: int) -> TestClient:
    c = TestClient(app)
    res = c.post("/api/auth/register", json={"email": f"24010{number:04d}@sdu.edu.kz",
                                             "password": PASSWORD, "full_name": "Aidana Serikova"})
    if res.status_code != 200:
        res = c.post("/api/auth/login", json={"email": f"24010{number:04d}@sdu.edu.kz", "password": PASSWORD})
    assert res.status_code == 200, res.text
    return c


@pytest.fixture()
def admins(monkeypatch):
    monkeypatch.setattr(main, "ADMINS", {ADMIN})
    main._events_changed()
    yield
    for row in main.users.campus_events():
        main.users.delete_event(row["event_id"])
    main._events_changed()


@pytest.fixture()
def admin(admins):
    return account(4001)


@pytest.fixture()
def student(admins):
    return account(4002)


# ------------------------------------------------------------------- news
def test_the_feed_is_read_into_news_newest_first():
    items = parse_feed(FEED)
    assert [i["title"] for i in items] == ["SDU University Participates in Profit Education Day 2026",
                                           "Open Day 2026 Held at SDU University"]
    open_day = items[1]
    # published 11:48 UTC is 16:48 on campus (UTC+5)
    assert open_day["published"] == "2026-11-03 16:48" and open_day["date"] == "3 November 2026"
    # the repeated title and WordPress's [...] are gone, the entity is read
    assert open_day["excerpt"] == "SDU University hosted Open Day 2026 for prospective students & their parents."
    # a picture from anywhere but sdu.edu.kz is passed over
    assert open_day["image"] == "https://sdu.edu.kz/wp-content/uploads/2026/11/open-day.jpeg"
    assert items[0]["image"] is None


def test_a_long_excerpt_is_cut_at_a_word():
    excerpt = parse_feed(FEED)[0]["excerpt"]
    assert len(excerpt) <= 221 and excerpt.endswith("…") and not excerpt[:-1].endswith(" ")


def test_a_story_that_links_off_the_university_site_is_left_out():
    assert all(i["link"].startswith("https://sdu.edu.kz/") for i in parse_feed(FEED))


@pytest.mark.parametrize("body", [
    b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaa">]><rss><channel></channel></rss>',
    b"<rss><channel><item><title>broken",
    b"<html><body>Not a feed</body></html>",
])
def test_a_feed_that_is_not_a_plain_rss_document_is_refused(body):
    with pytest.raises(FeedError):
        parse_feed(body)


def test_the_feed_is_asked_again_only_when_it_has_gone_stale():
    calls, now = [], [1000.0]

    def fetch():
        calls.append(now[0])
        return FEED

    feed = NewsFeed(fetch=fetch, clock=lambda: now[0])
    assert len(feed.latest()["items"]) == 2 and len(calls) == 1
    now[0] += FRESH - 1
    feed.latest()
    assert len(calls) == 1
    now[0] += 2
    feed.latest()
    assert len(calls) == 2


def test_when_the_site_cannot_be_reached_the_last_news_is_kept_and_marked_stale():
    now, fail = [0.0], [False]

    def fetch():
        if fail[0]:
            raise OSError("unreachable")
        return FEED

    feed = NewsFeed(fetch=fetch, clock=lambda: now[0])
    assert feed.latest()["stale"] is False
    fail[0], now[0] = True, FRESH + 1
    page = feed.latest()
    assert page["stale"] is True and len(page["items"]) == 2
    # and it waits before trying again
    fail[0], now[0] = False, now[0] + RETRY - 1
    assert feed.latest()["stale"] is True
    now[0] += 2
    assert feed.latest()["stale"] is False


def test_news_with_nothing_fetched_yet_is_an_empty_stale_list():
    def fetch():
        raise OSError("unreachable")

    page = NewsFeed(fetch=fetch).latest()
    assert page == {"items": [], "source": "https://sdu.edu.kz/en/", "fetched_at": None, "stale": True}


def test_anyone_inside_can_read_the_news(monkeypatch):
    monkeypatch.setattr(main, "news_feed", NewsFeed(fetch=lambda: FEED))
    visitor = TestClient(app)
    assert visitor.get("/api/news").status_code == 401
    visitor.post("/api/auth/guest")
    page = visitor.get("/api/news").json()
    assert [i["link"] for i in page["items"]][-1] == "https://sdu.edu.kz/en/open-day-2026-held-at-sdu-university/"


# --------------------------------------------------------- who is an admin
def test_only_the_accounts_named_as_administrators_are_told_they_are(admin, student):
    assert admin.get("/api/auth/me").json()["user"]["admin"] is True
    assert student.get("/api/auth/me").json()["user"]["admin"] is False


def test_nobody_is_an_administrator_when_none_is_named(monkeypatch):
    monkeypatch.setattr(main, "ADMINS", set())
    me = account(4003)
    assert me.get("/api/auth/me").json()["user"]["admin"] is False
    assert me.post("/api/events", json=EVENT).status_code == 403


def test_a_student_and_a_visitor_cannot_change_events(student):
    assert student.post("/api/events", json=EVENT).status_code == 403
    assert student.put("/api/events/a1", json=EVENT).status_code == 403
    assert student.delete("/api/events/a1").status_code == 403
    visitor = TestClient(app)
    visitor.post("/api/auth/guest")
    assert visitor.post("/api/events", json=EVENT).status_code == 403


# ------------------------------------------------------- adding an event
def test_an_added_event_is_listed_for_everyone_with_its_room(admin, student):
    added = admin.post("/api/events", json=EVENT).json()
    assert added["event_id"].startswith("a") and added["editable"] is True
    assert (added["place"], added["room"], added["where"]) == ("F202", "F202", "Floor 2 · Block F")
    assert added["link"] == "https://sdu.edu.kz/en/robotics/"
    listed = student.get("/api/events").json()
    assert [e["title"] for e in listed["events"]] == ["Robotics Club Demo"] and listed["total"] == 1


def test_an_added_event_is_searched_and_filtered_like_any_other(admin, student):
    admin.post("/api/events", json=EVENT)
    admin.post("/api/events", json={**EVENT, "title": "Чемпионат по шахматам", "description": "Шахматы",
                                     "starts": "2030-12-05T10:00", "ends": "2030-12-05T12:00"})
    assert [e["title"] for e in student.get("/api/events?q=ROBOT").json()["events"]] == ["Robotics Club Demo"]
    assert [e["title"] for e in student.get("/api/events?q=шахмат").json()["events"]] == ["Чемпионат по шахматам"]
    december = student.get("/api/events?from=2030-12-01&to=2030-12-31").json()
    assert [e["title"] for e in december["events"]] == ["Чемпионат по шахматам"]
    assert december["total"] == 2


def test_an_added_event_is_found_by_its_title_and_lit_on_the_plan(admin, student):
    admin.post("/api/events", json=EVENT)
    answer = student.get("/api/search", params={"q": "Robotics Club Demo"}).json()
    assert answer["occasion"]["label"] == "Event" and answer["map"]["code"] == "F202"


def test_a_place_off_the_plans_is_said_in_words(admin):
    added = admin.post("/api/events", json={**EVENT, "room": "", "place": "Sports ground"}).json()
    assert (added["place"], added["room"], added["where"]) == ("Sports ground", None, None)
    res = admin.post("/api/events", json={**EVENT, "room": "", "place": ""})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "place"


def test_a_hall_is_named_as_people_call_it(admin):
    assert admin.post("/api/events", json={**EVENT, "room": "A1"}).json()["place"] == "Hall A1 (D117)"


@pytest.mark.parametrize("change, field", [
    ({"title": "  "}, "title"),
    ({"starts": "tomorrow"}, "starts"),
    ({"ends": "2030-11-20T14:00"}, "ends"),
    ({"ends": "2030-02-30T14:00"}, "ends"),
    ({"room": "Z999"}, "room"),
    ({"link": "javascript:alert(1)"}, "link"),
    ({"title": "x" * 121}, "title"),
])
def test_a_wrong_event_is_refused_naming_the_field(admin, change, field):
    res = admin.post("/api/events", json={**EVENT, **change})
    assert res.status_code == 400 and res.json()["detail"]["field"] == field


def test_an_event_is_edited_and_deleted_and_every_page_sees_it_at_once(admin, student):
    added = admin.post("/api/events", json=EVENT).json()
    student.get("/api/search", params={"q": "Robotics Club Demo"})        # read into the cache
    edited = admin.put(f"/api/events/{added['event_id']}", json={**EVENT, "title": "Robotics Night"}).json()
    assert edited["title"] == "Robotics Night"
    assert student.get("/api/search", params={"q": "Robotics Night"}).json()["occasion"]["title"] == "Robotics Night"
    assert admin.delete(f"/api/events/{added['event_id']}").json() == {"ok": True}
    assert student.get("/api/events").json()["total"] == 0
    assert admin.delete(f"/api/events/{added['event_id']}").status_code == 404


def test_an_event_shipped_in_the_campus_database_is_not_changed_through_the_site(admin):
    assert admin.put("/api/events/E1", json=EVENT).status_code == 404
    assert admin.delete("/api/events/E1").status_code == 404


def test_a_past_added_event_is_no_longer_listed(admin, student):
    admin.post("/api/events", json={**EVENT, "starts": "2020-01-01T10:00", "ends": "2020-01-01T12:00"})
    assert student.get("/api/events").json()["total"] == 0


def test_the_engine_holds_added_events_to_the_same_rules():
    row = {"event_id": 7, "title": "Late talk", "description": "", "place": "D103", "room_number": "D103",
           "starts_at": "2030-01-10 18:00", "ends_at": "2030-01-10 19:00", "link": None}
    page = index.events(now=datetime(2030, 1, 10, 18, 30), added=[row])
    assert page["events"][0]["event_id"] == "a7" and page["events"][0]["on_now"] is True
    assert index.events(now=datetime(2030, 1, 10, 19, 0), added=[row])["total"] == 0


def test_clean_event_keeps_campus_time_as_given():
    fields = clean_event(" Talk ", "", "D103", "2030-01-10T18:00", "2030-01-10 19:30", "")
    assert (fields["title"], fields["starts_at"], fields["ends_at"], fields["link"]) == (
        "Talk", "2030-01-10 18:00", "2030-01-10 19:30", None)
    with pytest.raises(AuthError):
        clean_event("Talk", "x" * 1001, "D103", "2030-01-10T18:00", "2030-01-10T19:00", "")


# ------------------------------------------------------------- the page
def test_the_events_page_shows_the_news_and_the_administrators_tools():
    html = (main.STATIC_DIR / "events.html").read_text()
    js = (main.STATIC_DIR / "events.js").read_text()
    assert 'id="news-list"' in html and 'id="ev-dialog"' in html and 'id="ev-add"' in html
    assert "/api/news" in js and 'rel="noopener noreferrer"' in js
    # the tools come only when the server says this account is an administrator
    assert "admin = !!(await res.json()).user.admin" in js
