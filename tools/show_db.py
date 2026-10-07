"""
For a demo: it shows that a sign-up really lands in data/users.db, that the
password is stored as a PBKDF2 hash and never as text, and that a live login
has a session row whose token is kept only as a SHA-256 digest.

    python3 tools/show_db.py
    python3 tools/show_db.py --full   # whole hashes instead of a prefix
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "users.db"


def table(rows: list[tuple], headers: list[str]) -> str:
    rows = [tuple("" if v is None else str(v) for v in r) for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    rule = "  ".join("-" * w for w in widths)
    body = ["  ".join(v.ljust(w) for v, w in zip(r, widths)) for r in rows]
    return "\n".join([line, rule, *body]) if rows else "\n".join([line, rule, "(empty)"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="do not shorten hashes")
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"{DB} does not exist yet — sign up once and run this again.")

    cut = (lambda s: s) if args.full else (lambda s: s[:38] + "..." if s and len(s) > 41 else s)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    print(f"database: {DB}  ({DB.stat().st_size / 1024:.1f} KB)\n")

    print("tables")
    print(table(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name").fetchall(), ["name"]))

    print("\nusers — one row per registered SDU account")
    users = [(r[0], r[1], r[2], r[3], cut(r[4]), r[5]) for r in conn.execute(
        "SELECT user_id, email, student_id, full_name, password_hash, created_at"
        " FROM users ORDER BY user_id")]
    print(table(users, ["id", "email", "student_id", "full_name",
                        "password_hash (PBKDF2, salted)", "created_at"]))

    print("\nsessions — one row per live login; user_id NULL means a visitor")
    sessions = [(cut(r[0]), r[1], r[2], r[3], r[4]) for r in conn.execute(
        "SELECT s.token_hash, s.user_id, u.email, s.created_at, s.expires_at"
        " FROM sessions s LEFT JOIN users u ON u.user_id = s.user_id"
        " ORDER BY s.created_at")]
    print(table(sessions, ["token_hash (SHA-256)", "user_id", "email",
                           "created_at", "expires_at"]))

    plain = conn.execute(
        "SELECT COUNT(*) FROM users WHERE password_hash NOT LIKE 'pbkdf2_sha256$%'"
    ).fetchone()[0]
    print(f"\n{len(users)} account(s), {len(sessions)} live session(s).")
    print("every password is a PBKDF2-HMAC-SHA256 hash — no plain text in the table"
          if plain == 0 else f"WARNING: {plain} row(s) are not PBKDF2 hashes")


if __name__ == "__main__":
    main()
