"""
The database itself: campus.db is the source of truth, so nothing in it may
point at a row that is no longer there.

Rooms get added and removed as the plans are re-read, and SQLite only enforces
foreign keys when a connection asks it to — these tests are what keeps an edit
from quietly leaving an alias, a service or a whole floor pointing at nothing.
"""
import sqlite3

import pytest

from app.main import DB_PATH, index


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def rows(db, sql):
    return [tuple(r) for r in db.execute(sql)]


# ------------------------------------------------------------------ the file
def test_the_file_is_not_corrupt(db):
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_no_foreign_key_points_at_a_missing_row(db):
    assert rows(db, "PRAGMA foreign_key_check") == []


# ---------------------------------------------------------------- the rooms
@pytest.mark.parametrize("what, sql", [
    ("an alias without a room",
     "SELECT alias FROM room_aliases WHERE room_id NOT IN (SELECT room_id FROM rooms)"),
    ("a room on a floor that does not exist",
     "SELECT room_id FROM rooms WHERE floor_id NOT IN (SELECT floor_id FROM floors)"),
    ("a room pointing at a landmark that does not exist",
     "SELECT room_id FROM rooms WHERE nearest_landmark_id IS NOT NULL"
     " AND nearest_landmark_id NOT IN (SELECT landmark_id FROM landmarks)"),
    ("a floor drawn on a sheet that does not exist",
     "SELECT floor_id FROM floors WHERE sheet_id IS NOT NULL"
     " AND sheet_id NOT IN (SELECT sheet_id FROM plan_sheets)"),
    ("a floor with no rooms left on it",
     "SELECT floor_id FROM floors f WHERE NOT EXISTS"
     " (SELECT 1 FROM rooms r WHERE r.floor_id = f.floor_id)"),
    ("geometry for a sheet that does not exist",
     "SELECT sheet_id FROM sheet_geometry WHERE sheet_id NOT IN (SELECT sheet_id FROM plan_sheets)"),
    ("a service in a room that does not exist",
     "SELECT service_id FROM services WHERE room_id IS NOT NULL"
     " AND room_id NOT IN (SELECT room_id FROM rooms)"),
    ("opening hours for a service that does not exist",
     "SELECT id FROM service_hours WHERE service_id NOT IN (SELECT service_id FROM services)"),
])
def test_nothing_is_left_dangling(db, what, sql):
    assert rows(db, sql) == [], f"campus.db has {what}"


def test_room_numbers_and_aliases_are_unique(db):
    assert rows(db, "SELECT room_number FROM rooms GROUP BY room_number HAVING count(*) > 1") == []
    assert rows(db, "SELECT lower(alias) FROM room_aliases"
                    " GROUP BY lower(alias) HAVING count(*) > 1") == []


def test_every_room_can_be_found_by_its_own_number(db):
    missing = rows(db, "SELECT room_number FROM rooms r WHERE NOT EXISTS"
                       " (SELECT 1 FROM room_aliases a WHERE a.room_id = r.room_id"
                       "  AND lower(a.alias) = lower(r.room_number))")
    assert missing == [], "a room with no alias of its own cannot be searched for"


def test_the_engine_loads_every_room_in_the_file(db):
    assert len(index.rooms) == db.execute("SELECT count(*) FROM rooms").fetchone()[0]
    # a room that houses a service (Library, Cafeteria, Medcenter) answers as
    # that service, which still carries the room, the floor and the route
    for room in index.rooms:
        expected = "service" if index.hosted_service(room) else "room"
        assert index.search(room["room_number"])["kind"] == expected, room["room_number"]


def test_the_schema_file_still_matches_the_database(db):
    """data/schema.sql is documentation — it has to describe the real tables."""
    from app.main import BASE_DIR
    documented = (BASE_DIR / "data" / "schema.sql").read_text()
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"
                            " AND name NOT LIKE 'sqlite_%'"):
        assert f"CREATE TABLE {name}" in documented, f"{name} is missing from schema.sql"
