"""
SDU Campus Assistant — FastAPI entry point.

Run locally:   uvicorn app.main:app --reload
Then open:     http://127.0.0.1:8000        (the web app)
               http://127.0.0.1:8000/docs   (interactive API docs)

Everything except the sign-in page, the static files and /api/health needs a
signed-in SDU account; see app/auth.py for the rules.
"""
import functools
import hashlib
import os
import re
import time
from datetime import date, timedelta
from urllib.parse import quote
from pathlib import Path

import logging

from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import (GUEST, MAX_CLASSES, RESET_MINUTES, ROLE_VISITOR, SESSION_COOKIE, AuthError, UserStore,
                   clean_class, clean_event, database_url, default_db_path, normalise_email, seed_account)
from .ics import timetable_calendar
from .engine import CampusIndex, campus_now
from .floorplan import CampusMap
from .routing import Router
from .mailer import mail_configured, send_reset_link
from .news import NewsFeed, fetch_picture
from .sdulife import SduLifeSync, fetch_poster

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CAMPUS_DB", BASE_DIR / "data" / "campus.db"))
STATIC_DIR = BASE_DIR / "static"
SECURE_COOKIES = os.environ.get("CAMPUS_SECURE_COOKIES", "").lower() in ("1", "true", "yes")
# Where the site lives, for links that leave it (the password reset email).
# Taken from the configuration and never from the request, whose Host header the
# caller controls — otherwise anyone could have a reset link mailed out that
# points at their own server.
# On Vercel the production address is known without being configured.
PUBLIC_URL = (os.environ.get("CAMPUS_PUBLIC_URL")
              or (f"https://{os.environ['VERCEL_PROJECT_PRODUCTION_URL']}"
                  if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") else "")).rstrip("/")
RESET_SENT = (f"If an account exists for that address, a link to choose a new password is on "
              f"its way. It works once, for {RESET_MINUTES} minutes.")

index = CampusIndex.load(DB_PATH)
campus_map = CampusMap(index)
index.attach_map(campus_map)
router = Router(index, campus_map)
index.attach_router(router)
users = UserStore(default_db_path(BASE_DIR), database_url())
seeded = seed_account(users, os.environ.get("CAMPUS_SEED_ACCOUNT", ""),
                      os.environ.get("CAMPUS_SEED_NAME"))

app = FastAPI(
    title="SDU Campus Assistant API",
    description="US1 — Conversational Location Search over SDU's digitised evacuation plans.",
    version="2.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                   allow_headers=["*"])


def current_user(request: Request) -> dict:
    """Whoever is signed in — an SDU account or a visitor — or 401.

    US1 is written for students, staff and visitors alike, so everything it
    covers is behind this and not behind an account.
    """
    user = users.session_user(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Open the campus assistant to continue.")
    return user


def require_account(user: dict = Depends(current_user)) -> dict:
    """For anything personal a visitor session cannot hold: a timetable, a saved
    route, a reminder."""
    if user["role"] == ROLE_VISITOR:
        raise HTTPException(status_code=403,
                            detail="Sign in with your SDU account to use this.")
    return user


# Who may add, change and delete campus events: the accounts named in
# CAMPUS_ADMINS, comma-separated SDU addresses. Nobody, when it is unset.
ADMINS = {e.strip().lower() for e in os.environ.get("CAMPUS_ADMINS", "").split(",") if e.strip()}


def is_admin(user: dict | None) -> bool:
    return bool(user and user.get("email") and user["email"].lower() in ADMINS)


def require_admin(user: dict = Depends(require_account)) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only the site's administrators can change events.")
    return user


# The events an administrator added, read once a minute at most: every search
# looks at their titles, and a database round trip per question would be wasted.
# A change made on this server empties it at once; on another, within a minute.
_added_cache: dict = {"at": 0.0, "rows": None}
ADDED_FRESH = 60.0


def added_events() -> list[dict]:
    if _added_cache["rows"] is None or time.monotonic() - _added_cache["at"] > ADDED_FRESH:
        _added_cache["rows"] = users.campus_events()
        _added_cache["at"] = time.monotonic()
    return _added_cache["rows"]


def _events_changed() -> None:
    _added_cache["rows"] = None


news_feed = NewsFeed()


def _room_of(place: str) -> str | None:
    room = index.event_place(place).get("room")
    return room["room_number"] if room else None


# SDU Life's events, copied into campus_events at most every half hour when the
# events page asks (app/sdulife.py). SDULIFE_SYNC=0 turns it off (the tests do).
sdulife = SduLifeSync(users, room_of=_room_of) \
    if os.environ.get("SDULIFE_SYNC", "1").lower() not in ("0", "false", "no") else None


def _sync_sdulife(force: bool = False) -> None:
    if sdulife and sdulife.refresh(force=force):
        _events_changed()


def _set_session(response: Response, user: dict | None) -> None:
    # a cookie for this browser session only: closing the browser ends the visit,
    # and the next one starts at the sign-in page (the server still lets a
    # session lapse after SESSION_DAYS)
    token, _ = users.start_session(user)
    response.set_cookie(SESSION_COOKIE, token, httponly=True,
                        samesite="lax", secure=SECURE_COOKIES, path="/")


# ------------------------------------------------------------------ accounts
@app.post("/api/auth/register", tags=["accounts"])
def register(response: Response, email: str = Body(..., embed=True),
             password: str = Body(..., embed=True),
             full_name: str = Body("", embed=True)):
    """Create an account: full name, 9 digits + @sdu.edu.kz, a strong password."""
    try:
        user = users.register(email, password, full_name)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    _set_session(response, user)
    return {"user": user}


@app.post("/api/auth/login", tags=["accounts"])
def login(response: Response, email: str = Body(..., embed=True),
          password: str = Body(..., embed=True)):
    try:
        user = users.authenticate(email, password)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    _set_session(response, user)
    return {"user": user}


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _reset_on_screen(request: Request) -> bool:
    """Whether a reset link may be shown on the page instead of mailed.

    Only on a developer's own machine with no mail server: the request comes
    from this computer, to this computer, and the site has no public address.
    A deployed site sets CAMPUS_PUBLIC_URL (and a mail server), so this is
    never true there, whatever a client claims about itself.
    """
    if mail_configured() or PUBLIC_URL:
        return False
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    return bool(request.client) and request.client.host in LOOPBACK and host in LOOPBACK


@app.post("/api/auth/forgot", tags=["accounts"])
def forgot_password(request: Request, background: BackgroundTasks,
                    email: str = Body(..., embed=True)):
    """Send a one-time link for choosing a new password.

    `delivery` says how the link travels:
      * "email": mailed to the address. The answer is the same whether or not
        the address has an account, and the mail goes out after the answer, so
        neither the text nor the timing says who is registered.
      * "screen": a developer's machine with no mail server (see
        _reset_on_screen): the link comes back in `reset_url` so the flow can
        be used end to end without a mail server.
      * "unavailable": a deployed site with no mail server. Nothing is sent and
        the page says so, rather than promising a letter that never comes.
    """
    try:
        email = normalise_email(email)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})

    if _reset_on_screen(request):
        issued = users.request_reset(email)
        if not issued:
            return {"ok": True, "delivery": "screen", "reset_url": None,
                    "message": "There's no account for that address, or a link was made for it under a "
                               "minute ago. Check the address, or wait a moment and ask again."}
        _, token = issued
        return {"ok": True, "delivery": "screen", "reset_url": f"/login?mode=reset#reset={token}",
                "message": "No mail server is set up on this computer, so the reset link is right here. "
                           f"It works once, for {RESET_MINUTES} minutes."}

    if not mail_configured() or not PUBLIC_URL:
        logging.getLogger("campus.mail").error(
            "Password reset requested, but mail is not set up: set CAMPUS_BREVO_API_KEY (or "
            "CAMPUS_SMTP_HOST) and CAMPUS_PUBLIC_URL.")
        return {"ok": False, "delivery": "unavailable",
                "message": "Password reset by e-mail isn't switched on for this site yet. "
                           "Ask the site's administrator to reset your password."}

    issued = users.request_reset(email)
    if issued:
        user, token = issued
        # the token rides in the fragment, which browsers never send to a server
        background.add_task(send_reset_link, user["email"], f"{PUBLIC_URL}/login?mode=reset#reset={token}",
                            RESET_MINUTES)
    return {"ok": True, "delivery": "email", "message": RESET_SENT}


@app.post("/api/auth/reset", tags=["accounts"])
def reset_password(response: Response, token: str = Body(..., embed=True),
                   password: str = Body(..., embed=True)):
    """Spend a reset link on a new password, end every other session, sign in."""
    try:
        user = users.reset_password(token, password)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    _set_session(response, user)
    return {"user": user}


@app.post("/api/profile/password", tags=["accounts"])
def change_password(request: Request, current_password: str = Body("", embed=True),
                    new_password: str = Body("", embed=True),
                    user: dict = Depends(require_account)):
    """Change the password from the profile: the current password is required.
    Other devices are signed out; this one stays signed in."""
    try:
        users.change_password(user["user_id"], current_password, new_password,
                              keep_token=request.cookies.get(SESSION_COOKIE))
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    return {"ok": True, "message": "Your password is changed. Other devices have been signed out."}


@app.post("/api/auth/guest", tags=["accounts"])
def guest(response: Response):
    """Come in as a visitor, without an account.

    A visitor has no university address, so US1 — finding a room, reading the
    map, checking opening hours — is open to them. Anything added later that
    belongs to a person goes behind require_account().
    """
    _set_session(response, None)
    return {"user": dict(GUEST)}


@app.post("/api/auth/logout", tags=["accounts"])
def logout(request: Request, response: Response):
    users.end_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me", tags=["accounts"])
def me(user: dict = Depends(current_user)):
    return {"user": {**user, "admin": is_admin(user)}}


# ---------------------------------------------------------------------- data
@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", **index.stats()}


@app.get("/api/stats", tags=["meta"])
def stats(user: dict = Depends(current_user)):
    return index.stats()


@app.get("/api/search", tags=["US1 search"])
def search(q: str = Query(..., min_length=1, max_length=200,
                          description="Free-form question, e.g. 'Where is D103?'"),
           context: str | None = Query(None, max_length=8,
                                       description="The `context` of the previous answer, so a "
                                                   "follow-up like 'Engineering' resolves '204'"),
           user: dict = Depends(current_user)):
    """Answer a free-form question about a room, a block, a campus service or the
    asker's own next class."""
    timetable = None if user["role"] == ROLE_VISITOR else (lambda: users.classes(user["user_id"]))
    return index.search(q, context=context, timetable=timetable, events=added_events)


@app.get("/api/route", tags=["directions"])
def route(to: str = Query(..., min_length=1, max_length=200,
                          description="Where to: a room code, a hall name or a service, e.g. 'F204'"),
          frm: str | None = Query(None, alias="from", max_length=200,
                                  description="Where from: any room, a named place or an exit. "
                                              "Left out, the route starts at the main entrance."),
          via: str | None = Query(None, max_length=120,
                                  description="To a building of the grounds: the door of floor 1 to "
                                              "go out by, one of the route's `alternatives`."),
          user: dict = Depends(current_user)):
    """Step-by-step walking directions between two places, drawn on the plans too."""
    return index.directions(to, frm, via)


@app.get("/api/map", tags=["map"])
def vector_map(user: dict = Depends(current_user)):
    """The three floors as vector geometry, one merged drawing per floor, all in
    one frame with the campus grounds round the main building (`grounds`)."""
    return {"floors": campus_map.floor_list(), "grounds": campus_map.grounds()}


@app.get("/api/sheets", tags=["map"])
def sheets(user: dict = Depends(current_user)):
    """The original evacuation sheets with the rooms drawn on them."""
    return index.sheet_list()


@app.get("/api/services", tags=["services"])
def services(user: dict = Depends(current_user)):
    """Campus services with an open/closed status computed in Almaty time."""
    return index.service_list()


# ----------------------------------------------------------------- timetable
class ClassForm(BaseModel):
    subject: str = ""
    day: int = -1          # 0=Mon .. 6=Sun
    start: str = ""        # 'HH:MM', campus time
    end: str = ""
    room: str = ""         # a room of the directory: its code, hall name or alias


def _class_fields(form: ClassForm) -> tuple[dict, str]:
    """The checked fields of a class and its room's number, or 400. US17: a room
    that is not in the directory is refused, whatever the class is."""
    try:
        fields = clean_class(form.subject, form.day, form.start, form.end)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    room = index.directory_room(form.room)
    if not room:
        raise HTTPException(status_code=400, detail={
            "field": "room", "message": "Choose a room from the list, like D103 or Hall A1."})
    return fields, room["room_number"]


NOT_YOURS = HTTPException(status_code=404, detail="That class isn't in your timetable.")


@app.get("/api/rooms", tags=["timetable"])
def rooms(user: dict = Depends(require_account)):
    """The room directory, for the picker on the timetable form."""
    return index.room_list()


@app.get("/api/schedule", tags=["timetable"])
def schedule(user: dict = Depends(require_account)):
    """Your own week. No request here can name another account."""
    return {"classes": [index.class_payload(c) for c in users.classes(user["user_id"])]}


@app.post("/api/schedule", tags=["timetable"])
def add_class(form: ClassForm, user: dict = Depends(require_account)):
    fields, room = _class_fields(form)
    try:
        return index.class_payload(users.add_class(user["user_id"], fields, room))
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})


@app.get("/api/schedule/{class_id}", tags=["timetable"])
def get_class(class_id: int, user: dict = Depends(require_account)):
    entry = users.get_class(user["user_id"], class_id)
    if not entry:
        raise NOT_YOURS
    return index.class_payload(entry)


@app.put("/api/schedule/{class_id}", tags=["timetable"])
def edit_class(class_id: int, form: ClassForm, user: dict = Depends(require_account)):
    fields, room = _class_fields(form)
    entry = users.update_class(user["user_id"], class_id, fields, room)
    if not entry:
        raise NOT_YOURS
    return index.class_payload(entry)


@app.delete("/api/schedule/{class_id}", tags=["timetable"])
def delete_class(class_id: int, user: dict = Depends(require_account)):
    if not users.delete_class(user["user_id"], class_id):
        raise NOT_YOURS
    return {"ok": True}


class ReadRoom(BaseModel):
    room: str = Field("", max_length=200)


@app.post("/api/schedule/rooms", tags=["timetable"])
def read_rooms(rooms: list[ReadRoom] = Body(..., max_length=MAX_CLASSES),
               user: dict = Depends(require_account)):
    """The rooms of a timetable read off a screenshot, matched to the directory
    with the OCR's look-alike characters put right ("11301" is I301). A room that
    matches nothing (an online class, "VR 93") comes back as not in the
    directory: the preview asks for one from the list before it can be saved."""
    return [{"read": item.room, **index.read_room(item.room, 40)} for item in rooms]


class ImportForm(BaseModel):
    classes: list[ClassForm] = Field(..., max_length=MAX_CLASSES)
    replace: bool = True   # in place of the timetable there was, or added to it


@app.post("/api/schedule/import", tags=["timetable"])
def import_classes(form: ImportForm, user: dict = Depends(require_account)):
    """A whole week at once, as checked on the import preview. Every class is
    checked first; one that is wrong stops the import, naming its row."""
    if not form.classes:
        raise HTTPException(status_code=400, detail={"field": "classes", "message": "There are no classes to save."})
    entries = []
    for row, entry in enumerate(form.classes):
        try:
            entries.append(_class_fields(entry))
        except HTTPException as err:
            raise HTTPException(status_code=400, detail={**err.detail, "row": row})
    try:
        saved = users.import_classes(user["user_id"], entries, form.replace)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    return {"classes": [index.class_payload(c) for c in saved]}


@app.get("/api/schedule.ics", tags=["timetable"])
def schedule_calendar(request: Request,
                      lead: int = Query(10, ge=0, le=120,
                                        description="Minutes before a class its reminder goes off"),
                      user: dict = Depends(require_account)):
    """The week as a calendar file: every class repeats weekly in campus time,
    with a reminder `lead` minutes before and a link to the way there. A phone's
    calendar then reminds even with the site closed."""
    site = PUBLIC_URL or str(request.base_url).rstrip("/")
    body = timetable_calendar([index.class_payload(c) for c in users.classes(user["user_id"])],
                              site, lead, user["user_id"])
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="sdu-timetable.ics"',
                             "Cache-Control": "no-store"})


# -------------------------------------------------------------------- events
def _event_date(value: str | None, field: str) -> date | None:
    """A campus date from the query string, 'YYYY-MM-DD', or 400."""
    if not value:
        return None
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(value)
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail={
            "field": field, "message": f"Give the {'first' if field == 'from' else 'last'} day as year-month-day, like 2026-11-14."})


@app.get("/api/events", tags=["events"])
def events(q: str | None = Query(None, max_length=200,
                                 description="Words to find in an event's title or description"),
           frm: str | None = Query(None, alias="from",
                                   description="First day of the period, YYYY-MM-DD, campus time"),
           to: str | None = Query(None,
                                  description="Last day of the period, YYYY-MM-DD, included"),
           user: dict = Depends(current_user)):
    """Upcoming campus events, soonest first. A visitor may read them. Those of
    SDU Life are copied in first, when the last copy is half an hour old."""
    start, end = _event_date(frm, "from"), _event_date(to, "to")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail={
            "field": "to", "message": "The last day can't be before the first."})
    # the same query, run on the events an administrator added (US20)
    stamp = campus_now().strftime("%Y-%m-%d %H:%M")
    _sync_sdulife()
    added = users.campus_events(after=stamp, words=(q or "").split(),
                                start=f"{start:%Y-%m-%d} 00:00" if start else None,
                                end=f"{end + timedelta(days=1):%Y-%m-%d} 00:00" if end else None)
    result = index.events(q, start, end, added=added, added_total=users.count_events(stamp))
    result["sources"] = [sdulife.status()] if sdulife else []
    return result


class EventForm(BaseModel):
    title: str = ""
    description: str = ""
    place: str = ""        # in words; may be left out when a room is given
    room: str = ""         # a room of the directory, or nothing for a place off the plans
    starts: str = ""       # '2026-11-14T14:00', campus time
    ends: str = ""
    link: str = ""         # the announcement, e.g. on sdu.edu.kz


def _event_fields(form: EventForm) -> tuple[dict, str | None]:
    """The checked fields of an event and its room's number (None off the plans), or 400."""
    room = None
    if form.room.strip():
        room = index.directory_room(form.room)
        if not room:
            raise HTTPException(status_code=400, detail={
                "field": "room", "message": "Choose a room from the list, or leave it empty for a place off the plans."})
    place = form.place.strip() or (index.class_room(room) if room else "")
    if not place:
        raise HTTPException(status_code=400, detail={"field": "place", "message": "Say where it is, or choose a room."})
    try:
        fields = clean_event(form.title, form.description, place, form.starts, form.ends, form.link)
    except AuthError as err:
        raise HTTPException(status_code=400, detail={"field": err.field, "message": err.message})
    return fields, room["room_number"] if room else None


def _event_id(event_id: str) -> int:
    """'a12' is the event with id 12 in the accounts database; any other id is
    one shipped in campus.db, which is changed there and not here."""
    match = re.fullmatch(r"a(\d{1,18})", event_id)
    if not match:
        raise HTTPException(status_code=404, detail="That event can't be changed here.")
    return int(match[1])


def _added_id(event_id: str) -> int:
    """An event an administrator added. One copied from SDU Life has its title
    and description changed on SDU Life (409); only its place and times are
    corrected here."""
    number = _event_id(event_id)
    if users.event_source(number):
        raise HTTPException(status_code=409, detail="This event comes from SDU Life; change it there.")
    return number


def _event_out(row: dict) -> dict:
    return index.event_payload(index.added_event(row), campus_now().strftime("%Y-%m-%d %H:%M"))


@app.post("/api/events", tags=["events"])
def add_event(form: EventForm, user: dict = Depends(require_admin)):
    """An administrator adds an event, so the list of US19 has real ones in it."""
    fields, room = _event_fields(form)
    row = users.add_event(fields, room, user["user_id"])
    _events_changed()
    return _event_out(row)


@app.put("/api/events/{event_id}", tags=["events"])
def edit_event(event_id: str, form: EventForm, user: dict = Depends(require_admin)):
    """An event an administrator added is changed whole. One copied from SDU Life
    gets the place, room and times from its poster; its title, description and
    link stay SDU Life's, and later copies keep the correction."""
    number = _event_id(event_id)
    fields, room = _event_fields(form)
    if users.event_source(number):
        row = users.correct_event(number, fields["place"], room, fields["starts_at"], fields["ends_at"])
    else:
        row = users.update_event(number, fields, room)
    if not row:
        raise HTTPException(status_code=404, detail="That event isn't there any more.")
    _events_changed()
    return _event_out(row)


@app.delete("/api/events/{event_id}", tags=["events"])
def delete_event(event_id: str, user: dict = Depends(require_admin)):
    if not users.delete_event(_added_id(event_id)):
        raise HTTPException(status_code=404, detail="That event isn't there any more.")
    _events_changed()
    return {"ok": True}


@app.get("/api/events/{event_id}/poster", tags=["events"])
def event_poster(event_id: str, user: dict = Depends(require_admin)):
    """The poster of an event copied from SDU Life, passed through this site so
    the administrator's browser may read the place and the time off it."""
    image = users.event_image(_event_id(event_id))
    if not image:
        raise HTTPException(status_code=404, detail="This event has no poster.")
    try:
        body, kind = fetch_poster(image)
    except Exception:                      # noqa: BLE001 — unreachable, too big, not a picture
        raise HTTPException(status_code=502, detail="SDU Life's poster couldn't be fetched just now.") from None
    return Response(body, media_type=kind, headers={"Cache-Control": "private, max-age=86400",
                                                    "X-Content-Type-Options": "nosniff"})


@app.delete("/api/events/{event_id}/correction", tags=["events"])
def uncorrect_event(event_id: str, user: dict = Depends(require_admin)):
    """Drop a correction: the event takes SDU Life's place and times again, now."""
    if not users.uncorrect_event(_event_id(event_id)):
        raise HTTPException(status_code=404, detail="That event has no correction to undo.")
    _sync_sdulife(force=True)
    _events_changed()
    return {"ok": True}


@app.post("/api/events/sync", tags=["events"])
def sync_events(user: dict = Depends(require_admin)):
    """An administrator copies SDU Life's events now, without waiting for the half hour."""
    if not sdulife:
        raise HTTPException(status_code=404, detail="Copying from SDU Life is turned off on this server.")
    _sync_sdulife(force=True)
    if sdulife.ok is False:
        raise HTTPException(status_code=502, detail="SDU Life couldn't be read just now. Try again later.")
    return sdulife.status()


@app.get("/api/news/picture", tags=["events"])
def news_picture(src: str = Query(..., max_length=400)):
    """A news story's picture, passed through this site from sdu.edu.kz's uploads
    (nothing else is fetched). The pictures are public and never change under
    their name, so the browser and Vercel's edge keep them for a week."""
    try:
        body, kind = fetch_picture(src)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not a picture of sdu.edu.kz.") from None
    except Exception:                      # noqa: BLE001 — unreachable or too slow
        raise HTTPException(status_code=502, detail="sdu.edu.kz couldn't be reached just now.") from None
    return Response(body, media_type=kind, headers={
        "Cache-Control": "public, max-age=604800, s-maxage=604800, stale-while-revalidate=86400",
        "X-Content-Type-Options": "nosniff"})


@app.get("/api/news", tags=["events"])
def news(user: dict = Depends(current_user)):
    """The latest news from sdu.edu.kz, read from its RSS feed and kept for half
    an hour. News carries the day it was published, not the day of an event."""
    return news_feed.latest()


# ---------------------------------------------------------------------- site
def content_tag(path: Path) -> str:
    """An ETag made of what the file holds. Vercel stamps every file of a
    deployment with the same date, so the usual tag (its date and size) stayed
    the same when a page changed only in its digits ("app.js?v=93" to "v=94"):
    the browser was told its old page was still good."""
    stat = path.stat()
    return _content_tag(str(path), stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=256)
def _content_tag(path: str, mtime_ns: int, size: int) -> str:
    return '"' + hashlib.sha256(Path(path).read_bytes()).hexdigest()[:32] + '"'


def tagged_file(request: Request, path: Path, headers: dict, media_type: str | None = None) -> Response:
    """A file with the ETag of its content; 304 when the browser already has it."""
    tag = content_tag(path)
    headers = {**headers, "ETag": tag}
    if tag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    # its size and type are set now (not when sent), so the date can be taken out
    response = FileResponse(path, media_type=media_type, headers=headers, stat_result=os.stat(path))
    if "last-modified" in response.headers:    # the deployment's one date: says nothing
        del response.headers["last-modified"]
    return response


class CachedStatic(StaticFiles):
    """Static files the CDN and the browser keep, so a page opens without asking
    the server for each of them again. A script or a stylesheet the pages name
    with a version (app.js?v=44) never changes under that name: kept for a year.
    Anything else (the logo, the plans) for an hour in the browser and a day at
    the edge. Vercel empties its edge cache on every deploy."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            # the content's tag, not the deployment's one date and the size (content_tag)
            full, _ = self.lookup_path(path)
            if full:
                tag = content_tag(Path(full))
                asked = dict(scope.get("headers") or []).get(b"if-none-match", b"").decode()
                if tag in [t.strip() for t in asked.split(",")]:
                    response = Response(status_code=304)
                elif response.status_code == 304:      # the old kind of tag matched: send it again
                    response = FileResponse(full)
                response.headers["ETag"] = tag
                if "last-modified" in response.headers:
                    del response.headers["last-modified"]
        if response.status_code in (200, 304):
            versioned = b"v=" in scope.get("query_string", b"")
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, s-maxage=31536000, immutable" if versioned
                else "public, max-age=3600, s-maxage=86400")
        return response


app.mount("/static", CachedStatic(directory=STATIC_DIR), name="static")

# The pages name their scripts and styles with a version (app.js?v=44), so a
# browser must ask again for the page itself to pick up a new release.
PAGE_HEADERS = {"Cache-Control": "no-cache"}


def safe_next(path: str | None) -> str:
    """Where to go after signing in: a path on this site and nothing else. A
    browser reads "//elsewhere" and "/\\elsewhere" as another site, and drops tabs
    and line breaks first ("/<tab>/elsewhere"), so a backslash, a space or a
    control character anywhere sends it to the map instead; so does the sign-in
    page itself."""
    if (path and path.startswith("/") and not path.startswith("//")
            and not re.search(r"[\x00-\x20\x7f\\]", path) and not re.match(r"/login\b", path)):
        return path
    return "/"


def _page(request: Request, name: str):
    """A page behind the door: the file, or the sign-in page, which brings the
    visitor back here (with its question, /?ask=...) once they are in."""
    if not users.session_user(request.cookies.get(SESSION_COOKIE)):
        here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        target = "/login" if here == "/" else f"/login?next={quote(here, safe='')}"
        return RedirectResponse(target, status_code=303)
    return tagged_file(request, STATIC_DIR / name, PAGE_HEADERS)


@app.get("/", include_in_schema=False)
def home(request: Request):
    return _page(request, "index.html")


@app.get("/profile", include_in_schema=False)
def profile_page(request: Request):
    return _page(request, "profile.html")


@app.get("/events", include_in_schema=False)
def events_page(request: Request):
    return _page(request, "events.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker(request: Request):
    """The reminders' service worker (static/sw.js), served from the root so it
    may show notifications for every page of the site."""
    return tagged_file(request, STATIC_DIR / "sw.js", {"Cache-Control": "no-cache"}, "text/javascript")


@app.get("/schedule", include_in_schema=False)
def schedule_page(request: Request):
    return _page(request, "schedule.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request, mode: str | None = None, next: str | None = None):
    # a reset link opens the form even in a browser that is already signed in, and
    # a visitor comes here to sign in, so only an account is sent on to the map
    user = users.session_user(request.cookies.get(SESSION_COOKIE))
    if mode != "reset" and user and user["role"] != ROLE_VISITOR:
        return RedirectResponse(safe_next(next), status_code=303)
    return tagged_file(request, STATIC_DIR / "auth.html", PAGE_HEADERS)
