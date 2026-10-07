"""
Accounts for the campus assistant.

Only SDU students and staff get in: the login is the university address, which
is exactly nine digits and the university domain (240103048@sdu.edu.kz), and
the password has to pass the usual strength rules. Both checks run here, on
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
RESET_MINUTES = 30
RESET_COOLDOWN_SECONDS = 60   # one link a minute per account, so the form cannot flood an inbox

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
]


class _Postgres:
    """A Postgres connection that takes the store's SQLite-style queries."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql.replace("?", "%s"), params)


class UserStore:
    """Users, sessions and reset links: in SQLite, or in Postgres when given a URL."""

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
            return
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._migrate(conn)
            conn.executescript(SQLITE_SCHEMA)

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

    @staticmethod
    def _public(row) -> dict:
        return {"user_id": row["user_id"], "email": row["email"],
                "student_id": row["student_id"], "full_name": row["full_name"],
                "role": ROLE_MEMBER}


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
