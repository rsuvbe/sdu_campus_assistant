"""
Accounts for the campus assistant.

Only SDU students and staff get in: the login is the university address, which
is exactly nine digits and the university domain (240103048@sdu.edu.kz), and
the password has to pass the usual strength rules. Both checks run here, on
the server, so the browser form is a convenience and not the gate.

Storage is a small SQLite file of its own (data/users.db) — campus.db stays
read-only. Passwords are kept as PBKDF2-HMAC-SHA256 hashes with a per-user
salt, and a session is a random token whose SHA-256 is what the table holds,
so a copy of the database cannot be replayed as a login.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

EMAIL_RE = re.compile(r"^(\d{9})@sdu\.edu\.kz$", re.IGNORECASE)

# US1 is written for students, staff AND visitors. A visitor has no university
# address, so they get a session without an account: same door, no sign-up.
# Everything US1 offers — search, the map, opening hours — is open to them;
# anything added later that is personal (a saved route, a timetable) should ask
# for an account through require_account() in app/main.py.
ROLE_MEMBER = "student"
ROLE_VISITOR = "visitor"
GUEST = {"user_id": None, "email": None, "student_id": None,
         "full_name": None, "role": ROLE_VISITOR}
SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\""
MIN_PASSWORD = 8
MAX_PASSWORD = 72
SESSION_DAYS = 14
SESSION_COOKIE = "sdu_session"
PBKDF2_ROUNDS = 240_000

# Passwords that pass the character rules but are still the first thing anyone
# would try against a student portal.
BANNED_PASSWORDS = {
    "password1!", "password123!", "qwerty123!", "abcd1234!", "admin123!",
    "sdu12345!", "student1!", "welcome1!", "passw0rd!", "letmein1!",
}

EMAIL_HINT = ("Use your SDU address: nine digits and @sdu.edu.kz, "
              "for example 240103048@sdu.edu.kz.")


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
    if not EMAIL_RE.match(email):
        raise AuthError(EMAIL_HINT, "email")
    return email


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


class UserStore:
    """Users and sessions in their own SQLite file."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._migrate(conn)
            conn.executescript("""
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
            """)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Visitor sessions have no user, so user_id had to stop being NOT NULL.

        SQLite cannot relax a column in place, and a session is disposable, so
        the table is simply rebuilt — everyone signs in again once.
        """
        columns = {r["name"]: r for r in conn.execute("PRAGMA table_info(sessions)")}
        if columns and columns["user_id"]["notnull"]:
            conn.execute("DROP TABLE sessions")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------- accounts
    def register(self, email: str, password: str, full_name: str | None = None) -> dict:
        email = normalise_email(email)
        validate_password(password, email)
        name = (full_name or "").strip()[:80] or None
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

    @staticmethod
    def _public(row: sqlite3.Row) -> dict:
        return {"user_id": row["user_id"], "email": row["email"],
                "student_id": row["student_id"], "full_name": row["full_name"],
                "role": ROLE_MEMBER}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_db_path(base_dir: Path) -> Path:
    return Path(os.environ.get("CAMPUS_USERS_DB", base_dir / "data" / "users.db"))


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
            store.register(email, password, full_name)
        return email
    except AuthError as err:
        logging.getLogger(__name__).warning("CAMPUS_SEED_ACCOUNT ignored: %s", err.message)
        return None
