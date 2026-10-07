-- Schema of data/campus.db. The full database, schema and data, is data/campus.sql;
-- tools/build_db.py rebuilds campus.db from it.

CREATE TABLE plan_sheets (
    sheet_id     TEXT PRIMARY KEY,
    floor_number INTEGER NOT NULL,
    section      TEXT,              -- 'front' (C/D/E) | 'back' (F/G/H) | NULL if whole-floor
    image_path   TEXT,
    width_px     INTEGER,
    height_px    INTEGER
);

CREATE TABLE buildings (
    building_id TEXT PRIMARY KEY,   -- physical block letter: C, D, E, F, G, H, I ...
    name        TEXT,
    lat         REAL,
    lon         REAL
);

CREATE TABLE building_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id TEXT NOT NULL REFERENCES buildings(building_id) ON DELETE CASCADE,
    alias       TEXT NOT NULL
);

CREATE TABLE floors (
    floor_id     TEXT PRIMARY KEY,          -- e.g. 'D-1' (block D, floor 1)
    building_id  TEXT NOT NULL REFERENCES buildings(building_id) ON DELETE CASCADE,
    floor_number INTEGER NOT NULL,
    sheet_id     TEXT REFERENCES plan_sheets(sheet_id)   -- which physical sheet its rooms are drawn on
);

CREATE TABLE landmarks (
    landmark_id TEXT PRIMARY KEY,
    floor_id    TEXT NOT NULL REFERENCES floors(floor_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    type        TEXT,               -- exit / amenity / elevator / stairs / entrance
    x           REAL NOT NULL,
    y           REAL NOT NULL
);

CREATE TABLE rooms (
    room_id             TEXT PRIMARY KEY,
    floor_id            TEXT NOT NULL REFERENCES floors(floor_id) ON DELETE CASCADE,
    room_number         TEXT NOT NULL,
    name                TEXT,
    type                TEXT,       -- CLASS / LAB / HALL / SPEC / SPORT / FREEDOM / unknown
    department          TEXT,       -- BINA from Reports.xlsx where matched (ECO/ENG/LAW/PHIL/MAIN/...), else NULL
    source              TEXT NOT NULL DEFAULT 'fire_plan',  -- 'fire_plan' | 'reports_xlsx' | 'both'
    x                   REAL NOT NULL,
    y                   REAL NOT NULL,
    nearest_landmark_id TEXT REFERENCES landmarks(landmark_id),
    step_free           INTEGER NOT NULL DEFAULT 1,
    accessibility_notes TEXT
, entry_node_id TEXT REFERENCES nav_nodes(node_id), purpose TEXT);
-- purpose: what the room is for, in words, searched by US7 ("Laboratory room", "Lecture hall",
-- "Dean's office"). Every room has one; "Room" where no source says more.

CREATE TABLE room_aliases (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    alias   TEXT NOT NULL
);

CREATE TABLE nav_nodes (
    node_id   TEXT PRIMARY KEY,
    floor_id  TEXT NOT NULL REFERENCES floors(floor_id) ON DELETE CASCADE,
    type      TEXT NOT NULL,      -- corridor_junction / door / stairs / elevator / entrance / exit
    x         REAL NOT NULL,
    y         REAL NOT NULL,
    step_free INTEGER NOT NULL DEFAULT 1   -- reused by US5 accessible routing too
);

CREATE TABLE nav_edges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id  TEXT NOT NULL REFERENCES nav_nodes(node_id) ON DELETE CASCADE,
    to_node_id    TEXT NOT NULL REFERENCES nav_nodes(node_id) ON DELETE CASCADE,
    distance_m    REAL,                     -- pixel distance * scale_meters_per_pixel
    step_free     INTEGER NOT NULL DEFAULT 1,
    bidirectional INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE services (
    service_id           TEXT PRIMARY KEY,
    room_id              TEXT REFERENCES rooms(room_id),
    landmark_id          TEXT REFERENCES landmarks(landmark_id),
    name                 TEXT NOT NULL,
    category             TEXT,                 -- library / cafeteria / computer_lab / health_center / print_center ...
    capacity             INTEGER,
    occupancy_status     TEXT NOT NULL DEFAULT 'unknown',  -- open / full / unknown -- MOCK, not schedule-derived
    occupancy_source     TEXT NOT NULL DEFAULT 'mock',      -- 'mock' | 'facilities_api'
    occupancy_updated_at TEXT
, short_name TEXT, notes TEXT, hours_confirmed INTEGER NOT NULL DEFAULT 0);
-- short_name: a few words for the map label; notes: one line of extra information
-- (an application window); hours_confirmed: 1 when the hours come from the university

-- Further rooms a service occupies besides services.room_id (Extension Center: F109 + F110).
CREATE TABLE service_rooms (
    service_id TEXT NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    room_id    TEXT NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    PRIMARY KEY (service_id, room_id)
);

CREATE TABLE service_hours (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id  TEXT NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL,     -- 0=Mon .. 6=Sun; two rows on one day = a lunch break between them
    open_time   TEXT,                -- 'HH:MM'
    close_time  TEXT
);

CREATE TABLE sheet_geometry (
    sheet_id    TEXT PRIMARY KEY REFERENCES plan_sheets(sheet_id),
    west_max_x  REAL NOT NULL,
    wing_min_x  REAL NOT NULL
);

CREATE TABLE service_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    alias TEXT NOT NULL
);

CREATE INDEX idx_building_aliases_alias ON building_aliases(alias);

CREATE INDEX idx_floors_building ON floors(building_id);

CREATE INDEX idx_floors_sheet ON floors(sheet_id);

CREATE INDEX idx_landmarks_floor ON landmarks(floor_id);

CREATE INDEX idx_rooms_floor ON rooms(floor_id);

CREATE UNIQUE INDEX idx_rooms_room_number ON rooms(room_number);   -- one number, one room

CREATE INDEX idx_room_aliases_alias ON room_aliases(alias);

CREATE INDEX idx_nav_nodes_floor ON nav_nodes(floor_id);

CREATE INDEX idx_nav_edges_from ON nav_edges(from_node_id);

CREATE INDEX idx_nav_edges_to   ON nav_edges(to_node_id);

CREATE INDEX idx_service_hours_service ON service_hours(service_id);
