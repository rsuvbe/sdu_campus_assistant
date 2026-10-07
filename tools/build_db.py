"""
Rebuild data/campus.db from data/campus.sql, the versioned source of the campus.

    python3 tools/build_db.py          # campus.sql -> campus.db
    python3 tools/build_db.py --dump   # campus.db  -> campus.sql (after editing the database)
    python3 tools/build_db.py --check  # exit 1 if the two have drifted apart

The rebuild runs every statement and fails loudly on the first problem: a duplicate room number (the UNIQUE index on rooms.room_number),
an alias, service or floor pointing at a row that is not there, or a file that
does not parse. The old database is only replaced once the new one is complete
and passes SQLite's integrity check, so a failed rebuild leaves it untouched.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "campus.db"
SQL = ROOT / "data" / "campus.sql"

HEADER = ("-- SDU Campus Assistant: the campus directory, schema and data.\n"
          "-- This file is the source; data/campus.db is built from it by tools/build_db.py.\n"
          "-- After editing the database, run `python3 tools/build_db.py --dump` and commit both.\n")


def dump(db: Path = DB) -> str:
    """The database as SQL text, in a stable order."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return HEADER + "\n".join(conn.iterdump()) + "\n"
    finally:
        conn.close()


def build(sql_text: str, target: Path) -> None:
    """Create a fresh database at `target` from SQL text; raise on any problem."""
    if target.exists():
        target.unlink()
    conn = sqlite3.connect(target)
    try:
        # tables come in alphabetical order (aliases before the rows they name), so
        # references are checked once everything is in, by foreign_key_check below
        conn.execute("PRAGMA foreign_keys = OFF")
        body = "\n".join(l for l in sql_text.splitlines() if not l.startswith("--"))
        # iterdump wraps everything in one transaction; run it statement by statement
        # so the first failing statement is the one reported
        for statement in _statements(body):
            if statement.upper() in ("BEGIN TRANSACTION;", "COMMIT;"):
                continue
            try:
                conn.execute(statement)
            except sqlite3.Error as err:
                raise SystemExit(f"campus.sql: {err}\n  in: {statement[:200]}") from None
        conn.commit()
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise SystemExit(f"campus.sql: rows pointing at nothing: {problems[:5]}")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("campus.sql: the built database fails SQLite's integrity check")
    finally:
        conn.close()


def _statements(body: str):
    buf = ""
    for line in body.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            yield buf.strip()
            buf = ""
    if buf.strip():
        raise SystemExit(f"campus.sql: unfinished statement at the end: {buf.strip()[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", action="store_true", help="write campus.sql from campus.db")
    ap.add_argument("--check", action="store_true", help="fail if campus.sql and campus.db differ")
    args = ap.parse_args()

    if args.dump:
        SQL.write_text(dump())
        print(f"wrote {SQL.relative_to(ROOT)} from {DB.relative_to(ROOT)}")
        return
    if args.check:
        same = SQL.exists() and SQL.read_text() == dump()
        print("campus.sql and campus.db match" if same else
              "campus.sql and campus.db differ: run tools/build_db.py --dump (or rebuild)")
        sys.exit(0 if same else 1)

    fd, tmp = tempfile.mkstemp(suffix=".db", dir=DB.parent)
    os.close(fd)
    tmp = Path(tmp)
    try:
        build(SQL.read_text(), tmp)
        os.replace(tmp, DB)
    finally:
        if tmp.exists():
            tmp.unlink()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rooms = conn.execute("SELECT count(*) FROM rooms").fetchone()[0]
    conn.close()
    print(f"built {DB.relative_to(ROOT)} from {SQL.relative_to(ROOT)}: {rooms} rooms")


if __name__ == "__main__":
    main()
