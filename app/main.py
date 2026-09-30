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

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (GUEST, ROLE_VISITOR, SESSION_COOKIE, AuthError, UserStore,
                   default_db_path, seed_account)
from .engine import CampusIndex
from .floorplan import CampusMap

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CAMPUS_DB", BASE_DIR / "data" / "campus.db"))
STATIC_DIR = BASE_DIR / "static"
SECURE_COOKIES = os.environ.get("CAMPUS_SECURE_COOKIES", "").lower() in ("1", "true", "yes")

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
             full_name: str | None = Body(None, embed=True)):
    """Create an account. The email must be 9 digits + @sdu.edu.kz."""
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


@app.get("/", include_in_schema=False)
def home(request: Request):
    if not users.session_user(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if users.session_user(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "auth.html")
