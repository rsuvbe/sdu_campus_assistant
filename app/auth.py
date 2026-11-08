"""
Accounts for the campus assistant.

Only SDU students and staff get in: the login is the university address. A
student's is their nine-digit number and the university domain
(240103048@sdu.edu.kz); a member of staff's is their name and surname in Latin
letters (aidana.serikova@sdu.edu.kz), and that account has the staff role. The
password has to pass the usual strength rules. Both checks run here, on
the server, so the browser form is a convenience and not the gate.

Storage is a database of its own — campus.db stays read-only. Locally that is a
small SQLite file (data/users.db); a deployment with DATABASE_URL set keeps the
accounts in Postgres instead, because serverless and free hosting wipe their
disks. Passwords are kept as PBKDF2-HMAC-SHA256 hashes with a per-user
salt, and a session is a random token whose SHA-256 is what the table holds,
so a copy of the database cannot be replayed as a login.

A forgotten password is reset through a one-time link: a random token whose
SHA-256 is stored, valid for RESET_MINUTES, spent on first use. Asking for one
answers the same way whether or not the address has an account, so the form
cannot be used to find out who is registered; a successful reset signs the
account out everywhere.

A person's weekly classes (US17) live here too, keyed by the account, so a
timetable goes wherever the account goes and goes away with it. Every read and
write of one takes the user id, so nobody reaches a class that isn't theirs.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

EMAIL_RE = re.compile(r"^(\d{9})@sdu\.edu\.kz$", re.IGNORECASE)          # a student's
STAFF_RE = re.compile(r"^([a-z]+(?:-[a-z]+)*)\.([a-z]+(?:-[a-z]+)*)@sdu\.edu\.kz$", re.IGNORECASE)

# US1 is written for students, staff AND visitors. A visitor has no university
# address, so they get a session without an account: same door, no sign-up.
# Everything US1 offers — search, the map, opening hours — is open to them;
# anything added later that is personal (a saved route, a timetable) should ask
# for an account through require_account() in app/main.py.
ROLE_MEMBER = "student"
ROLE_STAFF = "staff"
ROLE_VISITOR = "visitor"
GUEST = {"user_id": None, "email": None, "student_id": None,
         "full_name": None, "role": ROLE_VISITOR}
SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\""
MIN_PASSWORD = 8
MAX_PASSWORD = 72
SESSION_DAYS = 14
SESSION_COOKIE = "sdu_session"
PBKDF2_ROUNDS = 240_000
RESET_MINUTES = 30
RESET_COOLDOWN_SECONDS = 60   # one link a minute per account, so the form cannot flood an inbox

# Passwords that pass the character rules but are still the first thing anyone
# would try against a student portal.
BANNED_PASSWORDS = {
    "password1!", "password123!", "qwerty123!", "abcd1234!", "admin123!",
    "sdu12345!", "student1!", "welcome1!", "passw0rd!", "letmein1!",
}

MAX_SUBJECT = 80
MAX_CLASSES = 60              # more than any timetable, so the table cannot be flooded
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

EMAIL_HINT = ("Use your SDU address: your student number (240103048@sdu.edu.kz), "
              "or for staff your name and surname (aidana.serikova@sdu.edu.kz).")


class AuthError(Exception):
    """A sign-up or sign-in the server refuses, with a message for the form."""

    def __init__(self, message: str, field: str = "email") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def normalise_email(raw: str) -> str:
    """Return the canonical address, or raise AuthError if it isn't an SDU one."""
    email = (raw or "").strip().lower()
    if not email:
        raise AuthError("Enter your university email.", "email")
    if " " in email:
        raise AuthError("An email address cannot contain spaces.", "email")
    if not EMAIL_RE.match(email) and not STAFF_RE.match(email):
        raise AuthError(EMAIL_HINT, "email")
    return email


def role_of(email: str) -> str:
    """Staff sign in with name.surname@sdu.edu.kz, students with their number."""
    return ROLE_STAFF if STAFF_RE.match(email or "") else ROLE_MEMBER


# A name as people write it: letters of any script (Kazakh and Russian included),
# with spaces, hyphens and apostrophes between them. At least two letters.
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '’\-][^\W\d_]+)*$")
MAX_NAME = 80


def normalise_name(raw: str | None) -> str:
    """The full name, tidied, or AuthError if it is missing or not a name."""
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not name:
        raise AuthError("Enter your full name.", "full_name")
    if len(name) > MAX_NAME:
        raise AuthError(f"A name can be at most {MAX_NAME} characters.", "full_name")
    if len(re.sub(r"[^\w]|\d|_", "", name)) < 2 or not NAME_RE.match(name):
        raise AuthError("Use letters only, as your name is written: Aidana Serikova.", "full_name")
    return name


def clean_class(subject: str, day: int, start: str, end: str) -> dict:
    """The fields of a class, tidied, or AuthError naming the one that is wrong.
    Whether its room exists is for the caller, who has the directory."""
    subject = re.sub(r"\s+", " ", (subject or "").strip())
    if not subject:
        raise AuthError("Enter the subject.", "subject")
    if len(subject) > MAX_SUBJECT:
        raise AuthError(f"A subject can be at most {MAX_SUBJECT} characters.", "subject")
    if day not in range(7):
        raise AuthError("Choose the day of the week.", "day")
    if not TIME_RE.match(start or ""):
        raise AuthError("Enter when the class starts, like 09:00.", "start")
    if not TIME_RE.match(end or ""):
        raise AuthError("Enter when the class ends, like 09:50.", "end")
    if end <= start:
        raise AuthError("A class has to end after it starts.", "end")
    return {"subject": subject, "day": day, "start": start, "end": end}


MAX_EVENT_TITLE = 120
MAX_EVENT_TEXT = 1000
MAX_EVENT_PLACE = 120
EVENT_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})$")
LINK_RE = re.compile(r"^https?://[^\s\"'<>]{1,300}$")


def clean_event(title: str, description: str, place: str, starts: str, ends: str, link: str) -> dict:
    """The fields of an event, tidied, or AuthError naming the one that is wrong.
    Times come from a date-and-time field ('2026-11-14T14:00') and are kept as
    campus time, 'YYYY-MM-DD HH:MM'. Whether its room exists is for the caller."""
    title = re.sub(r"\s+", " ", (title or "").strip())
    description = re.sub(r"[ \t]+", " ", (description or "").strip())
    place = re.sub(r"\s+", " ", (place or "").strip())
    link = (link or "").strip()
    if not title:
        raise AuthError("Give the event a title.", "title")
    if len(title) > MAX_EVENT_TITLE:
        raise AuthError(f"A title can be at most {MAX_EVENT_TITLE} characters.", "title")
    if len(description) > MAX_EVENT_TEXT:
        raise AuthError(f"A description can be at most {MAX_EVENT_TEXT} characters.", "description")
    if len(place) > MAX_EVENT_PLACE:
        raise AuthError(f"A place can be at most {MAX_EVENT_PLACE} characters.", "place")
    times = []
    for value, field, word in ((starts, "starts", "starts"), (ends, "ends", "ends")):
        m = EVENT_TIME_RE.match((value or "").strip())
        try:
            if not m:
                raise ValueError
            datetime.fromisoformat(f"{m[1]}T{m[2]}")
        except ValueError:
            raise AuthError(f"Give the day and time it {word}.", field) from None
        times.append(f"{m[1]} {m[2]}")
    if times[1] <= times[0]:
        raise AuthError("An event has to end after it starts.", "ends")
    if link and not LINK_RE.match(link):
        raise AuthError("The link has to be a web address, starting with https://", "link")
    return {"title": title, "description": description, "place": place,
            "starts_at": times[0], "ends_at": times[1], "link": link or None}


def search_text(title: str, description: str) -> str:
    return f"{title}\n{description}".casefold()


def student_id(email: str) -> str:
    match = EMAIL_RE.match(email)
    return match.group(1) if match else ""


def password_problems(password: str, email: str = "") -> list[str]:
    """Every rule the password breaks, in the order they are shown on the form."""
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"at least {MIN_PASSWORD} characters")
    if len(password) > MAX_PASSWORD:
        problems.append(f"no more than {MAX_PASSWORD} characters")
    if not any(c.isupper() for c in password):
        problems.append("an uppercase letter")
    if not any(c.islower() for c in password):
        problems.append("a lowercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if not any(c in SPECIALS for c in password):
        problems.append("a special character")
    if any(c.isspace() for c in password):
        problems.append("no spaces")
    sid = student_id(email)
    if sid and sid in password:
        problems.append("something other than your student ID")
    staff = STAFF_RE.match(email or "")
    if staff and any(len(part) >= 3 and part.lower() in password.lower()
                     for part in re.split(r"[.-]", staff.group(1) + "." + staff.group(2))):
        problems.append("something other than your name")
    if password.lower() in BANNED_PASSWORDS:
        problems.append("a password that isn't on the common-password list")
    return problems


def validate_password(password: str, email: str = "") -> None:
    problems = password_problems(password, email)
    if problems:
        raise AuthError("Your password needs " + ", ".join(problems) + ".", "password")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(digest.hex(), digest_hex)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# The same tables in both dialects: SQLite numbers rows with AUTOINCREMENT,
# Postgres with an identity column. Times are ISO strings in both, so every
# comparison the queries make is the same string comparison.
SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT NOT NULL UNIQUE,
        student_id    TEXT NOT NULL,
        full_name     TEXT,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        -- NULL for a visitor, who is signed in without an account
        user_id    INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS password_resets (
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS classes (
        class_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        subject     TEXT NOT NULL,
        day_of_week INTEGER NOT NULL,   -- 0=Mon .. 6=Sun, as in service_hours
        start_time  TEXT NOT NULL,      -- 'HH:MM', campus time
        end_time    TEXT NOT NULL,
        room_number TEXT NOT NULL       -- rooms.room_number in campus.db
    );
    CREATE INDEX IF NOT EXISTS idx_classes_user ON classes(user_id);
    -- events an administrator adds, for the list of US19; the ones shipped in campus.db stay there
    CREATE TABLE IF NOT EXISTS campus_events (
        event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        description TEXT NOT NULL,
        place       TEXT NOT NULL,      -- in words, as the event is announced
        room_number TEXT,               -- rooms.room_number in campus.db; NULL: not on the plans
        starts_at   TEXT NOT NULL,      -- 'YYYY-MM-DD HH:MM', campus time
        ends_at     TEXT NOT NULL,
        link        TEXT,               -- the announcement on sdu.edu.kz, if any
        created_by  INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
        created_at  TEXT NOT NULL,
        -- the title and description case-folded, so a word search is one query in
        -- both databases, Cyrillic included, whatever the server's locale
        search_text TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_campus_events_ends ON campus_events(ends_at);
"""
POSTGRES_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        user_id       BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        email         TEXT NOT NULL UNIQUE,
        student_id    TEXT NOT NULL,
        full_name     TEXT,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id    BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS password_resets (
        token_hash TEXT PRIMARY KEY,
        user_id    BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS classes (
        class_id    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        subject     TEXT NOT NULL,
        day_of_week INTEGER NOT NULL,
        start_time  TEXT NOT NULL,
        end_time    TEXT NOT NULL,
        room_number TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_classes_user ON classes(user_id)",
    """CREATE TABLE IF NOT EXISTS campus_events (
        event_id    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        title       TEXT NOT NULL,
        description TEXT NOT NULL,
        place       TEXT NOT NULL,
        room_number TEXT,
        starts_at   TEXT NOT NULL,
        ends_at     TEXT NOT NULL,
        link        TEXT,
        created_by  BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
        created_at  TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_campus_events_ends ON campus_events(ends_at)",
    # added after the table first went live; a table made since has it already
    "ALTER TABLE campus_events ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT ''",
]


CLASS_FIELDS = ('class_id, subject, day_of_week AS day, start_time AS start, '
                'end_time AS "end", room_number AS room')


class _Postgres:
    """A Postgres connection that takes the store's SQLite-style queries."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql.replace("?", "%s"), params)


class UserStore:
    """Users, sessions, reset links and timetables: in SQLite, or in Postgres
    when given a URL."""

    def __init__(self, db_path: str | Path | None = None, database_url: str | None = None) -> None:
        self._pool = None
        if database_url:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            # prepare_threshold=None: a pooled endpoint (PgBouncer, Neon's pooler)
            # cannot keep prepared statements between transactions
            self._pool = ConnectionPool(
                database_url, min_size=1, max_size=4, open=True,
                kwargs={"row_factory": dict_row, "prepare_threshold": None},
                check=ConnectionPool.check_connection)
            with self._connect() as conn:
                # every cold start runs this; the lock keeps two of them from
                # creating the same table at the same moment
                conn.execute("SELECT pg_advisory_xact_lock(4207)")
                for statement in POSTGRES_SCHEMA:
                    conn.execute(statement)
                self._fill_search_text(conn)
            return
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._migrate(conn)
            conn.executescript(SQLITE_SCHEMA)
            if "search_text" not in {r["name"] for r in conn.execute("PRAGMA table_info(campus_events)")}:
                conn.execute("ALTER TABLE campus_events ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
            self._fill_search_text(conn)

    @staticmethod
    def _fill_search_text(conn) -> None:
        """Events saved before search_text existed get theirs."""
        for row in conn.execute("SELECT event_id, title, description FROM campus_events"
                                " WHERE search_text = ''").fetchall():
            conn.execute("UPDATE campus_events SET search_text = ? WHERE event_id = ?",
                         (search_text(row["title"], row["description"]), row["event_id"]))

    @property
    def backend(self) -> str:
        return "postgres" if self._pool else "sqlite"

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Visitor sessions have no user, so user_id had to stop being NOT NULL.

        SQLite cannot relax a column in place, and a session is disposable, so
        the table is simply rebuilt — everyone signs in again once.
        """
        columns = {r["name"]: r for r in conn.execute("PRAGMA table_info(sessions)")}
        if columns and columns["user_id"]["notnull"]:
            conn.execute("DROP TABLE sessions")

    @contextmanager
    def _connect(self) -> Iterator:
        """One transaction: committed when the block ends, rolled back on an error."""
        if self._pool:
            with self._pool.connection() as conn:
                yield _Postgres(conn)
            return
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------- accounts
    def register(self, email: str, password: str, full_name: str | None) -> dict:
        name = normalise_name(full_name)
        email = normalise_email(email)
        validate_password(password, email)
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AuthError("That account already exists — sign in instead.", "email")
            conn.execute(
                "INSERT INTO users (email, student_id, full_name, password_hash, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (email, student_id(email), name, hash_password(password), _now().isoformat()))
        return self.authenticate(email, password)

    def authenticate(self, email: str, password: str) -> dict:
        try:
            email = normalise_email(email)
        except AuthError:
            raise AuthError(EMAIL_HINT, "email") from None
        if not password:
            raise AuthError("Enter your password.", "password")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise AuthError("Email or password is wrong.", "password")
        return self._public(row)

    # ------------------------------------------------------ password change
    def change_password(self, user_id: int, current: str, new: str,
                        keep_token: str | None = None) -> dict:
        """Change a signed-in account's password. The current one has to be given
        and right; the new one passes the usual rules and differs from it. Every
        other session of the account ends, the one making the change stays."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                raise AuthError("This account no longer exists.", "current_password")
            if not current or not verify_password(current, row["password_hash"]):
                raise AuthError("Your current password is not right.", "current_password")
            try:
                validate_password(new, row["email"])
            except AuthError as err:
                raise AuthError(err.message, "new_password") from None
            if verify_password(new, row["password_hash"]):
                raise AuthError("Choose a password different from the current one.", "new_password")
            conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?",
                         (hash_password(new), user_id))
            conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                         (user_id, _token_hash(keep_token) if keep_token else ""))
        return self._public(row)

    # ------------------------------------------------------- password reset
    def request_reset(self, email: str) -> tuple[dict, str] | None:
        """A one-time reset token for the account, or None when there is no such
        account (or one was issued under a minute ago). The caller answers the
        same way in every case and only mails the token when there is one."""
        email = normalise_email(email)
        now = _now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                return None
            recent = conn.execute(
                "SELECT 1 FROM password_resets WHERE user_id = ? AND created_at > ?",
                (row["user_id"], (now - timedelta(seconds=RESET_COOLDOWN_SECONDS)).isoformat())).fetchone()
            if recent:
                return None
            token = secrets.token_urlsafe(32)
            # a new link replaces any older one
            conn.execute("DELETE FROM password_resets WHERE user_id = ? OR expires_at < ?",
                         (row["user_id"], now.isoformat()))
            conn.execute("INSERT INTO password_resets (token_hash, user_id, created_at, expires_at)"
                         " VALUES (?, ?, ?, ?)",
                         (_token_hash(token), row["user_id"], now.isoformat(),
                          (now + timedelta(minutes=RESET_MINUTES)).isoformat()))
        return self._public(row), token

    def reset_password(self, token: str, password: str) -> dict:
        """Spend a reset token on a new password. Every session of the account
        ends, so whoever knew the old password is signed out too."""
        expired = AuthError("This reset link has expired or has already been used. "
                            "Ask for a new one.", "token")
        if not token:
            raise expired
        with self._connect() as conn:
            row = conn.execute(
                "SELECT u.* FROM password_resets r JOIN users u ON u.user_id = r.user_id"
                " WHERE r.token_hash = ? AND r.expires_at > ?",
                (_token_hash(token), _now().isoformat())).fetchone()
            if not row:
                raise expired
            validate_password(password, row["email"])
            if verify_password(password, row["password_hash"]):
                raise AuthError("Choose a password you haven't used for this account.", "password")
            conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?",
                         (hash_password(password), row["user_id"]))
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (row["user_id"],))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
        return self._public(row)

    # ------------------------------------------------------------- sessions
    def start_session(self, user: dict | None = None) -> tuple[str, int]:
        """Open a session. Without a user it is a visitor's session."""
        token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=SESSION_DAYS)
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
            conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at)"
                         " VALUES (?, ?, ?, ?)",
                         (_token_hash(token), user["user_id"] if user else None,
                          _now().isoformat(), expires.isoformat()))
        return token, SESSION_DAYS * 24 * 3600

    def exists(self, email: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() is not None

    def session_user(self, token: str | None) -> dict | None:
        """Who is on the other end: an account, a visitor, or nobody."""
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT s.user_id, u.email, u.student_id, u.full_name"
                " FROM sessions s LEFT JOIN users u ON u.user_id = s.user_id"
                " WHERE s.token_hash = ? AND s.expires_at > ?",
                (_token_hash(token), _now().isoformat())).fetchone()
        if not row:
            return None
        return dict(GUEST) if row["user_id"] is None else self._public(row)

    def end_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ------------------------------------------------------------ timetable
    def classes(self, user_id: int) -> list[dict]:
        """One account's week, Monday morning first."""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {CLASS_FIELDS} FROM classes WHERE user_id = ?"
                                " ORDER BY day_of_week, start_time, class_id", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_class(self, user_id: int, class_id: int) -> dict | None:
        """A class of this account's; somebody else's is the same as none at all."""
        with self._connect() as conn:
            row = conn.execute(f"SELECT {CLASS_FIELDS} FROM classes WHERE class_id = ? AND user_id = ?",
                               (class_id, user_id)).fetchone()
        return dict(row) if row else None

    def add_class(self, user_id: int, fields: dict, room_number: str) -> dict:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM classes WHERE user_id = ?", (user_id,)).fetchone()
            if count["n"] >= MAX_CLASSES:
                raise AuthError(f"A timetable can hold at most {MAX_CLASSES} classes.", "subject")
            row = conn.execute(
                "INSERT INTO classes (user_id, subject, day_of_week, start_time, end_time, room_number)"
                f" VALUES (?, ?, ?, ?, ?, ?) RETURNING {CLASS_FIELDS}",
                (user_id, fields["subject"], fields["day"], fields["start"], fields["end"],
                 room_number)).fetchone()
        return dict(row)

    def update_class(self, user_id: int, class_id: int, fields: dict, room_number: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE classes SET subject = ?, day_of_week = ?, start_time = ?, end_time = ?,"
                f" room_number = ? WHERE class_id = ? AND user_id = ? RETURNING {CLASS_FIELDS}",
                (fields["subject"], fields["day"], fields["start"], fields["end"], room_number,
                 class_id, user_id)).fetchone()
        return dict(row) if row else None

    def import_classes(self, user_id: int, entries: list[tuple[dict, str]], replace: bool) -> list[dict]:
        """A week read off a screenshot, saved in one go: in place of the
        timetable there was, or after it. All of it or nothing."""
        with self._connect() as conn:
            if replace:
                conn.execute("DELETE FROM classes WHERE user_id = ?", (user_id,))
            count = conn.execute("SELECT COUNT(*) AS n FROM classes WHERE user_id = ?", (user_id,)).fetchone()
            if count["n"] + len(entries) > MAX_CLASSES:
                raise AuthError(f"A timetable can hold at most {MAX_CLASSES} classes.", "classes")
            for fields, room_number in entries:
                conn.execute(
                    "INSERT INTO classes (user_id, subject, day_of_week, start_time, end_time, room_number)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, fields["subject"], fields["day"], fields["start"], fields["end"], room_number))
        return self.classes(user_id)

    # ---------------------------------------------------------------- events
    EVENT_FIELDS = "event_id, title, description, place, room_number, starts_at, ends_at, link"

    def campus_events(self, after: str | None = None, words: list[str] | tuple = (),
                      start: str | None = None, end: str | None = None) -> list[dict]:
        """The events an administrator added, soonest first, as one query (US20):
        with `after` ('YYYY-MM-DD HH:MM') only those that end after it; every one
        of `words` in the title or the description, any case; and only those that
        overlap `start`..`end` (campus times; `end` is the moment after the last day)."""
        where, args = [], []
        if after:
            where.append("ends_at > ?")
            args.append(after)
        find = "strpos(search_text, ?) > 0" if self._pool else "instr(search_text, ?) > 0"
        for word in words:
            where.append(find)
            args.append(word.casefold())
        if start:
            where.append("ends_at > ?")
            args.append(start)
        if end:
            where.append("starts_at < ?")
            args.append(end)
        sql = f"SELECT {self.EVENT_FIELDS} FROM campus_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY starts_at, title", tuple(args)).fetchall()
        return [dict(r) for r in rows]

    def count_events(self, after: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM campus_events WHERE ends_at > ?", (after,)).fetchone()
        return row["n"]

    def add_event(self, fields: dict, room_number: str | None, user_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO campus_events (title, description, place, room_number, starts_at, ends_at, link,"
                f" created_by, created_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                f" RETURNING {self.EVENT_FIELDS}",
                (fields["title"], fields["description"], fields["place"], room_number, fields["starts_at"],
                 fields["ends_at"], fields["link"], user_id, _now().isoformat(),
                 search_text(fields["title"], fields["description"]))).fetchone()
        return dict(row)

    def update_event(self, event_id: int, fields: dict, room_number: str | None) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE campus_events SET title = ?, description = ?, place = ?, room_number = ?,"
                " starts_at = ?, ends_at = ?, link = ?, search_text = ?"
                f" WHERE event_id = ? RETURNING {self.EVENT_FIELDS}",
                (fields["title"], fields["description"], fields["place"], room_number, fields["starts_at"],
                 fields["ends_at"], fields["link"], search_text(fields["title"], fields["description"]),
                 event_id)).fetchone()
        return dict(row) if row else None

    def delete_event(self, event_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("DELETE FROM campus_events WHERE event_id = ? RETURNING event_id",
                               (event_id,)).fetchone()
        return row is not None

    def delete_class(self, user_id: int, class_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("DELETE FROM classes WHERE class_id = ? AND user_id = ?"
                               " RETURNING class_id", (class_id, user_id)).fetchone()
        return row is not None

    @staticmethod
    def _public(row) -> dict:
        return {"user_id": row["user_id"], "email": row["email"],
                "student_id": row["student_id"], "full_name": row["full_name"],
                "role": role_of(row["email"])}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_db_path(base_dir: Path) -> Path:
    if os.environ.get("CAMPUS_USERS_DB"):
        return Path(os.environ["CAMPUS_USERS_DB"])
    if os.environ.get("VERCEL"):
        # the deployment's own files are read-only; /tmp is the one writable
        # place, and it does not outlive the instance — set DATABASE_URL
        return Path("/tmp/users.db")
    return base_dir / "data" / "users.db"


def database_url() -> str | None:
    """The Postgres the accounts live in on a deployment, if one is attached.
    Vercel's Neon integration and most hosts name it one of these."""
    for key in ("CAMPUS_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"):
        if os.environ.get(key):
            return os.environ[key]
    return None


def seed_account(store: UserStore, spec: str, full_name: str | None = None) -> str | None:
    """Make sure one fixed account exists, and return its address.

    Free hosting plans have no persistent disk: the filesystem is wiped every
    time the service restarts, which on a free plan happens whenever it wakes
    from sleep. Accounts created through the sign-up form would disappear with
    it, and a link shared with someone would stop letting them back in. Setting
    CAMPUS_SEED_ACCOUNT to "<email>:<password>" keeps one account alive across
    restarts; everything else about it is an ordinary account.

    A spec that breaks the email or password rules is reported and ignored
    rather than taking the whole deployment down.
    """
    email, _, password = (spec or "").partition(":")
    if not email or not password:
        return None
    try:
        email = normalise_email(email)
        if not store.exists(email):
            # every account has a name; the seeded one gets a plain one unless
            # CAMPUS_SEED_NAME gives it a real one
            store.register(email, password, full_name or "SDU Student")
        return email
    except AuthError as err:
        logging.getLogger(__name__).warning("CAMPUS_SEED_ACCOUNT ignored: %s", err.message)
        return None
