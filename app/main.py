"""
SDU Campus Assistant — FastAPI entry point.

Run locally:   uvicorn app.main:app --reload
Then open:     http://127.0.0.1:8000        (the web app)
               http://127.0.0.1:8000/docs   (interactive API docs)

Everything except the sign-in page, the static files and /api/health needs a
signed-in SDU account; see app/auth.py for the rules.
"""
import os
from pathlib import Path

import logging

from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (GUEST, RESET_MINUTES, ROLE_VISITOR, SESSION_COOKIE, AuthError, UserStore,
                   default_db_path, normalise_email, seed_account)
from .engine import CampusIndex
from .floorplan import CampusMap
from .mailer import mail_configured, send_reset_link

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CAMPUS_DB", BASE_DIR / "data" / "campus.db"))
STATIC_DIR = BASE_DIR / "static"
SECURE_COOKIES = os.environ.get("CAMPUS_SECURE_COOKIES", "").lower() in ("1", "true", "yes")
# Where the site lives, for links that leave it (the password reset email).
# Taken from the configuration and never from the request, whose Host header the
# caller controls — otherwise anyone could have a reset link mailed out that
# points at their own server.
PUBLIC_URL = os.environ.get("CAMPUS_PUBLIC_URL", "").rstrip("/")
RESET_SENT = (f"If an account exists for that address, a link to choose a new password is on "
              f"its way. It works once, for {RESET_MINUTES} minutes.")

index = CampusIndex.load(DB_PATH)
campus_map = CampusMap(index)
index.attach_map(campus_map)
users = UserStore(default_db_path(BASE_DIR))
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
    """For anything personal a visitor session cannot hold — a saved route, a
    timetable, a reminder. Nothing in US1 needs it; US2 and later will."""
    if user["role"] == ROLE_VISITOR:
        raise HTTPException(status_code=403,
                            detail="Sign in with your SDU account to use this.")
    return user


def _set_session(response: Response, user: dict | None) -> None:
    token, max_age = users.start_session(user)
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True,
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
            "Password reset requested, but mail is not set up: set CAMPUS_SMTP_HOST and CAMPUS_PUBLIC_URL.")
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
    return {"user": user}


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
    """Answer a free-form question about a room, a block or a campus service."""
    return index.search(q, context=context)


@app.get("/api/map", tags=["map"])
def vector_map(user: dict = Depends(current_user)):
    """The three floors as vector geometry: one merged drawing per floor."""
    return {"floors": campus_map.floor_list()}


@app.get("/api/sheets", tags=["map"])
def sheets(user: dict = Depends(current_user)):
    """The original evacuation sheets with the rooms drawn on them."""
    return index.sheet_list()


@app.get("/api/services", tags=["services"])
def services(user: dict = Depends(current_user)):
    """Campus services with an open/closed status computed in Almaty time."""
    return index.service_list()


# ---------------------------------------------------------------------- site
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# The pages name their scripts and styles with a version (app.js?v=44), so a
# browser must ask again for the page itself to pick up a new release.
PAGE_HEADERS = {"Cache-Control": "no-cache"}


@app.get("/", include_in_schema=False)
def home(request: Request):
    if not users.session_user(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html", headers=PAGE_HEADERS)


@app.get("/profile", include_in_schema=False)
def profile_page(request: Request):
    if not users.session_user(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "profile.html", headers=PAGE_HEADERS)


@app.get("/login", include_in_schema=False)
def login_page(request: Request, mode: str | None = None):
    # a reset link opens the form even in a browser that is already signed in
    if mode != "reset" and users.session_user(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "auth.html", headers=PAGE_HEADERS)
