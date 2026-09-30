# SDU Campus Assistant

AI campus navigation and smart services assistant for SDU University.
**Sprint 1, US1 — Conversational Location Search.** Ask where a room or a
service is, get step-by-step directions, and watch the room light up on a
floor plan that was redrawn from the university's own evacuation sheets.

- Backend: **FastAPI** + SQLite (`data/campus.db`, read-only)
- Frontend: plain HTML/CSS/JS in `static/`, no build step
- Data: 237 rooms, blocks C–I, 3 floors, digitised from the fire evacuation plans
- Accounts: SDU addresses only (nine digits + `@sdu.edu.kz`)

---

## What is new in this version

**1. A real vector map instead of the photographed sheets.**
Each floor used to be two photographs — a "front" sheet with blocks C–E and a
"back" sheet with F–H — both covered in fire symbols, evacuation arrows and a
Kazakh title block. `app/floorplan.py` now rebuilds every floor as a single
continuous drawing:

- the two sheets are merged. Their x axes are aligned on the central corridor
  and the back sheet is pushed down by the real block-to-block pitch, so the
  corridor runs unbroken from the lobby all the way to Block H;
- every room is a polygon whose centre is its surveyed position in
  `campus.db` and whose size comes from the gap to its neighbours in the same
  row, so door order, row side, wing slope and adjacency match the plans;
- narrow rooms get the vertical label the printed plans use for them, and the
  small rooms that form a strip along the outer west wall are drawn flush
  against it;
- the eight round lecture halls — the "barrels" the campus calls A1, A2, B1,
  B2, C1, C2, D1 and D2 — are drawn as circles traced from the sheets, because
  their database coordinate is the label on the rim rather than the middle of
  the hall. Search answers to the hall name as well as to the room code;
- the corridor, the wing corridors, the lecture-hall "barrels" and the lobby
  are drawn as one building envelope, and the fire equipment, arrows and title
  blocks are simply not drawn.

Block I has no sheet of its own. It continues the same corridor one block below
Block H and repeats its layout, minus the west-side rooms that the annex does
not have (H109–H111 and H212–H214 have no I counterpart), drawn with dashed
outlines and a note in the answer.

**2. SDU colours.** Navy `#2F345C` and peach `#E89A64` come off the university
mark, which the header and the sign-in page now carry. The drawing itself sits
on its own set of tokens (`--map-bg`, `--map-slab`, `--map-room`, `--map-wall`,
`--map-ink`) and is kept a shade darker than the page, so a floor full of rooms
reads as a drawing instead of glaring white with labels lost in it.

**3. Accounts.** The map is behind a sign-in page. An account needs a
university address — exactly nine digits and `@sdu.edu.kz`, e.g.
`240103048@sdu.edu.kz` — and a password that has an uppercase letter, a
lowercase letter, a digit, a special character, at least 8 characters, no
spaces, no student ID inside it, and nothing from the common-password list.
Both checks run on the server (`app/auth.py`); the form only makes them
quicker to see.

---

## Layout

```
sdu-campus-assistant/
├── app/
│   ├── main.py        # FastAPI: API, accounts, the site
│   ├── engine.py      # search, directions, service hours
│   ├── floorplan.py   # the redrawn vector floor plans
│   └── auth.py        # SDU accounts, password rules, sessions
├── data/
│   ├── campus.db      # source of truth (read-only)
│   ├── users.db       # accounts, created on first run, git-ignored
│   └── schema.sql     # exact schema of campus.db
├── static/
│   ├── index.html     # the app
│   ├── auth.html      # sign in / create account
│   ├── app.js         # conversation + SVG map renderer
│   ├── auth.js        # the sign-in form
│   ├── styles.css, auth.css
│   ├── img/           # the SDU mark, the full lockup and the favicon
│   └── plans/         # the six original sheets, kept for reference
├── tests/             # 94 tests: the data, US1 acceptance, accounts, the map
├── requirements.txt
├── render.yaml        # one-click deploy on Render
└── Dockerfile         # Railway or any Docker host
```

---

## Running it locally

Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>. You will land on the sign-in page — create
an account with any nine-digit SDU address, for example `240103048@sdu.edu.kz`
and a password such as `Campus#2026`. The interactive API docs are at
<http://127.0.0.1:8000/docs>.

Accounts live in `data/users.db`, which is git-ignored and created on first
run. To skip the sign-up form every time you wipe it, let the app make the
account for you:

```bash
CAMPUS_SEED_ACCOUNT="240103048@sdu.edu.kz:Campus#2026" uvicorn app.main:app --reload
```

## Changing the data

`data/campus.db` is the source of truth: rooms, their coordinates on the
evacuation sheets, the aliases they answer to, and the services. Nothing about
the map is hard-coded — moving a room in the database moves it on the drawing.

There is no migration tool; edit it with Python's `sqlite3`, or with a GUI such
as DB Browser for SQLite. Two rules:

- turn foreign keys on (`PRAGMA foreign_keys = ON`) before deleting anything,
  because SQLite ignores them otherwise;
- run `pytest` afterwards. `tests/test_data.py` fails on an alias, a service or
  a floor left pointing at a room that is gone, and `tests/test_map.py` fails if
  a room stops being drawn or two rooms end up on top of each other.

A room only becomes searchable once it has an alias equal to its own number, so
add both rows together:

```python
import sqlite3
conn = sqlite3.connect("data/campus.db")
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("INSERT INTO rooms (room_id, floor_id, room_number, name, type, x, y)"
             " VALUES ('D-1-D130', 'D-1', 'D130', 'D130', 'CLASS', 215, 760)")
conn.execute("INSERT INTO room_aliases (room_id, alias) VALUES ('D-1-D130', 'd130')")
conn.commit()
```

## Tests

```bash
pytest -v
```

94 tests, including both `US1QATest` scenarios:

| US1 acceptance criterion | Test |
|---|---|
| 5 natural-language questions return the right block and floor in under 5 s | `test_scenario1_correct_building_and_floor` (English and Russian, including a Cyrillic lookalike room code) |
| A room that does not exist gives a clear "not found" plus real nearby rooms | `test_scenario2_not_found_with_suggestions` |
| Every room in the database is drawn exactly once on the map | `test_every_room_in_the_database_is_drawn_exactly_once` |
| Only nine-digit SDU addresses with strong passwords can register | `test_everything_else_is_refused`, `test_weak_passwords_are_named_rule_by_rule` |
| The app is unreachable without an account | `test_the_app_is_closed_without_an_account` |
| Nothing in the database points at a row that is gone | `test_nothing_is_left_dangling` |
| Each of the eight barrels is a circle and answers to its A1–D2 name | `test_every_barrel_is_drawn_as_a_circle_and_answers_to_its_name` |

Real answer time is around 0.1–1 ms.

---

## API

| Method | What it does |
|---|---|
| `POST /api/auth/register` | Create an account (9 digits + `@sdu.edu.kz`, strong password) |
| `POST /api/auth/login` / `logout` | Start or end a session |
| `GET /api/auth/me` | The signed-in account |
| `GET /api/search?q=Where is D103?` | The US1 endpoint: directions, map position, suggestions. Also answers to hall names such as `A1` |
| `GET /api/map` | All three floors as vector geometry |
| `GET /api/sheets` | The original evacuation sheets, for reference |
| `GET /api/services` | Services with an open/closed status in Almaty time |
| `GET /api/health` | Liveness check (the only open data endpoint) |

Everything except `/api/health`, `/api/auth/*`, `/login` and `/static/*` needs
a session cookie; without one the API answers `401` and `/` redirects to
`/login`.

`/api/search` answer kinds: `room`, `service`, `not_found`, `ambiguous`
(e.g. "204" exists in five blocks) and `no_match`.

---

## How the directions are derived

Nothing is invented — every sentence comes out of the plan geometry:

- each sheet has a central corridor running top to bottom with classroom wings
  branching east; the boundaries live in the `sheet_geometry` table;
- inside a wing the rooms fall into two rows. Walking into the wing, the upper
  row on the plan is on your **left** and the lower row on your **right**;
- "the third door, just after D101 and D102" is the door order along the wing,
  counted from the central corridor;
- "directly across the corridor is D107" is the room in the other row at the
  closest position;
- landmarks are the exits on floor 1 and the wing-end stairwells on floors 2–3.

## Honest limitations

- **Block I** is not digitised. Its rooms are copied from the east half of the
  Block H layout (`source = 'approximated_from_H'` in the database); the answer
  says so and the map draws it with dashed outlines.
- **The vector plan is a redrawing, not a survey.** Room positions, door
  order, row sides and adjacency come straight from the digitised sheets;
  wall thicknesses and room depths are regularised so the drawing stays
  readable. The original photographs are still served under `/static/plans/`.
- **Opening hours** for the library, cafeteria and dean's offices are
  approximate (Mon–Fri). The Medcenter has none on file, and the app says so
  rather than guessing.
- The library, cafeteria and dean's offices are **not tied to rooms** yet, so
  they show a status but no route. The Medcenter is tied to a room and appears
  on the plan.
- Answers are in English. Questions are understood in English and Russian;
  full multilingual answers are planned for US6.
- **Free hosting has no persistent disk.** On Render's free plan the filesystem
  is wiped every time the service restarts, which includes waking from sleep —
  so accounts created through the sign-up form do not last. Set
  `CAMPUS_SEED_ACCOUNT` to keep one account alive across restarts, or pay for
  an instance with a disk and point `CAMPUS_USERS_DB` at it.

---

## Deployment

### Put it on GitHub

```bash
git init
git add .
git commit -m "SDU Campus Assistant"
git branch -M main
git remote add origin https://github.com/<your-account>/sdu-campus-assistant.git
git push -u origin main
```

`data/campus.db` is part of the repository — the app reads the campus from it,
so it has to be committed. `data/users.db` is ignored: accounts belong to each
deployment, not to the source.

### Render (free)

1. On <https://render.com>, sign in with GitHub.
2. **New → Blueprint**, pick the repository. Render reads `render.yaml` by
   itself and asks for `CAMPUS_SEED_ACCOUNT` — give it
   `<email>:<password>`, e.g. `240103048@sdu.edu.kz:Campus#2026`. That account
   is recreated on every start, so the link keeps working; anyone else can
   still sign up for their own.
3. In two or three minutes you get a URL like
   `https://sdu-campus-assistant.onrender.com`. Every `git push` redeploys it.

> Before a demo: the free plan sleeps after 15 minutes idle and the first
> request then takes 30–50 seconds. Open the link a couple of minutes early.

### Railway or any Docker host

**New Project → Deploy from GitHub repo**; the `Dockerfile` is picked up
automatically (Settings → Networking → Generate Domain).

```bash
docker build -t sdu-campus .
docker run -p 8000:8000 sdu-campus
```

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `CAMPUS_DB` | `data/campus.db` | The read-only campus database |
| `CAMPUS_USERS_DB` | `data/users.db` | Where accounts and sessions are stored |
| `CAMPUS_SECURE_COOKIES` | off | Set to `true` when serving over HTTPS |
| `CAMPUS_SEED_ACCOUNT` | unset | `<email>:<password>` — one account recreated at every start, so a shared link keeps working on hosting with no persistent disk |
| `CAMPUS_SEED_NAME` | unset | The display name for that account |

---

## Next: Sprint 2

- **US2 Navigation.** A corridor graph (`nav_nodes` / `nav_edges` are already
  in the schema) and a real route drawn on the vector plan.
- **US3 Smart Recommendations.** Tie services to rooms, add exact hours, and
  suggest a place to work during a gap in the timetable.
