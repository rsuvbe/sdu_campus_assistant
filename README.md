# SDU Campus Assistant

AI campus navigation and smart services assistant for SDU University.
**Sprint 1, US1 — Conversational Location Search.** Ask where a room or a
service is, get step-by-step directions, and watch the room light up on a
floor plan that was redrawn from the university's own evacuation sheets.

- Backend: **FastAPI** + SQLite (`data/campus.db`, read-only)
- Frontend: plain HTML/CSS/JS in `static/`, no build step
- Data: 268 rooms and places, blocks A–I, 3 floors, digitised from the fire evacuation plans
  and the university's colour campus map
- Accounts: SDU addresses (nine digits + `@sdu.edu.kz`); visitors come in without one

---

## Sprints 2 and 3

Checked story by story against the story sheet in `tests/test_sprints_2_3.py`:
every responsibility, QA scenario and (Fail) test script of US5 to US12, plus the
password change US4 carried over from Sprint 1.

| Story | What it is now |
|---|---|
| US5 Room and Facility Directory | `data/campus.sql` is the versioned source (schema and data); `tools/build_db.py` rebuilds `campus.db` from it and fails loudly on a duplicate or a dangling row; `--dump` writes it back after an edit, `--check` says whether the two match. Room numbers are unique in the database itself, and every room has a `purpose` |
| US6 Search by Room Code | one exact result with block, floor and purpose; an unknown code says so and explains the code format |
| US7 Search by Name and Purpose | "laboratory", "lecture hall", "labs in Block F": every room whose purpose or name matches, closest first, as a list with code, block and floor; case-insensitive |
| US8 Plain-Language Questions | ten question forms reach the room; with two codes the one asked about wins ("I'm in D101, where is D105?"); "room 204" names its blocks and floor; an unclear question gets examples |
| US9 Floor Plan Viewer | three continuous vector floors, blocks in corridor order, no two rooms overlapping (measured) |
| US10 Highlight the Found Room | switches floor, highlights, centres, clears the previous highlight |
| US11 Floor Switching, Zoom and Pan | floors switch in place keeping the zoom; zoom bounded; drag clamped so the plan stays in view; two-finger pinch on touch |
| US12 Lecture Halls by Name | A1 to D2 answer by name with their code, drawn as traced circles, the highlight covering the hall |
| US4 (carried over) | `/profile`: name, address, student ID, change password (current password required, rules enforced, other devices signed out), sign out |

**What the data still needs from the university:** 115 rooms are on the plans
with no recorded use, so their purpose is "Room"; Block C's floor-3 rooms are
drawn on the sheet without numbers and are not in the directory until they are
given.

## Campus offices — October 2026

The university's own list of offices, their rooms and hours:

| Office | Where | Hours |
|---|---|---|
| Library | B, foyer | Mon–Fri 08:30–17:30, no lunch break |
| Student Center | D109 | Mon–Fri 08:30–17:30, lunch 12:30–13:30 |
| Advising Desk | corridor west wall, across from D109 | Mon–Fri 08:30–17:30, lunch 12:30–13:30 |
| Moodle help | F105 | — |
| Ay Market | the shop beside the food court, F, floor 1 | Mon–Fri 08:00–20:00, Sat–Sun 08:00–18:00 |
| Wardrobe | C, lobby | Mon–Sat 08:30–20:30 |
| Table tennis | beside the food court, F, floor 1 | Mon–Sat 08:30–20:30 |
| Extension Center | F109, F110 | Mon–Fri 08:30–17:30 |
| School of Information Technologies and Applied Mathematics — dean's office | F212, F213 | Mon–Fri 08:30–17:30; written applications 10:00–11:00 and 14:00–15:00 |
| School of Social Sciences, Business and Law — dean's office | D212, D213 | Mon–Fri 08:30–17:30 |
| Center for Multidisciplinary Education — dean's office | H210 | Mon–Fri 08:30–17:30 |
| Strategic Development Department | I214 | — |
| Inclusive Education Office | I113 | — |
| Educational Methodical Center | H107 | — |

- A lunch break is two opening intervals on one day; the status says "Open until
  12:30, back at 13:30 after lunch" and "Lunch break, back at 13:30".
- An office in two rooms (`service_rooms`) is routed to the first and lights up
  both; asking for the second room names the office among its facts.
- On the plan, a numbered room that holds an office is tinted and, where the name
  fits between its walls, labelled with it ("Student Center"); otherwise the name
  is on hover. The directory board lists every office with hours, open ones first,
  folded after six.
- The three schools' offices are their dean's offices. "Where is the dean's
  office?" / "Где деканат?" answers with the three to choose from; naming the
  school, its block or its faculty ("деканат юридического", "dean's office in
  Block F") goes straight to it. The old generic "Dean's Office", which had no
  room and guessed hours, is gone.
- Hours from this list are marked exact (`services.hours_confirmed`); the
  cafeteria's remain approximate and say so.

## Plan update — October 2026

Four new photographs of the evacuation sheets were read into the map. Three
are reprints of sheets already in `static/plans/` with more labels on them
(pixel-identical otherwise, so their coordinates carry straight over); the
fourth is a wider print of floor 1 that shows what the old front sheet cut off.

| Sheet | What it added |
|---|---|
| floor 1, wider print (`floor1_north.jpg`) | **Block B** north of the lobby: B114, the **Library** and **Red Hall** along a foyer running east, with an exit at each end |
| floor 1, back | **Red Canteen**, **Red Coffee**, **Doner House** and the **Cafeteria** on the Block F west side; three exits that had no landmark (west by Doner House, between F and G, end of the H wing) |
| floor 3, back | **G318–G322** in the slanted west wing of Block G; the **Red Canteen** upper hall in Block F |
| floor 3, front | the four round halls above A1–D1 are **Study Spaces** |

- The Library and the Cafeteria now have a room, so asking for them gives a
  route and a pin on the plan, not just the opening hours. Red Canteen, Red
  Coffee and Doner House are new services ("where can I get coffee?",
  "где донер").
- Places are found by their name: "Where is Red Hall?". A name several rooms
  share ("study space") shows the first one from the lobby, lights up the
  rest and offers each one ("Study Space 3").
- Block B does not hang off the central corridor, so its directions count the
  doors along the foyer instead, and room codes now start at B (`B114`, `Б114`).
- Rooms the row logic cannot shape — an irregular hall, a slanted wing, all of
  Block B — are drawn from outlines traced on their sheet (`OUTLINES` in
  `app/floorplan.py`). Block B was traced on the wider print and carried onto
  the front sheet's pixels with an affine fit on nine shared points (worst
  error 6 px).

### Second pass: the colour campus map

The university's colour map of floor 1 (`plans/floor1_colour.jpg`, drawn upside
down relative to ours) says what the rooms *are*: every icon and block colour
was matched to a room traced on the evacuation sheets.

- **Red Hall is Block A** (coral), a block of its own at the end of the Block B
  foyer; the Library, B114, a restroom and **Administration** (the org-chart
  icon) are Block B.
- **The Library includes its north exit**: the evacuation path runs down the
  passage on its east side to that exit, so the passage is drawn as Library.
- **Information desk** and **wardrobe** in the lobby; **restrooms** at the mouth
  of every wing on floor 1 (public on the classroom side, staff on the slanted
  side), plus Block B's; **Student Support** is D109; the **Medcenter** as before.
- **The food court is the size the map shows**: the dining hall (fork and
  knife) is the whole hall in Block F — that is the Cafeteria now — the seating
  is Red Canteen, the coffee bar Red Coffee. The shop beside it is
  **Ay Market**, next to the **table tennis** corner.
- **G115 and G114 were each on the wrong room.** Their points sat one room along
  from their printed labels; they now sit on their labels, and G114–G116 and
  G112–G113 are drawn with their real rotated outlines.
- Restrooms sit in the corridor column at each wing mouth, drawn like the other
  corridor rooms. The two rows south of the Block B foyer are drawn plain, the
  rest of them unnamed; floors 2 and 3 are drawn from their rooms alone, as
  before.
- Restrooms: "Where is the toilet?" shows the first one from the lobby and lists
  the rest; "туалет в блоке F" or "toilet in block G" picks that block's.

### Forgot password

The sign-in page has **Forgot password?**: enter the SDU address and a one-time
link is emailed; it opens a form for a new password and signs you in.

- the answer is the same whether or not the address has an account, and the
  mail is sent after it, so the form does not reveal who is registered;
- the token is random, stored only as a SHA-256 hash, works once, for 30
  minutes, and at most one is issued per minute per account;
- it travels in the link's `#fragment`, which browsers never send to a server,
  and is wiped from the address bar as soon as the page reads it;
- a reset signs the account out everywhere else;
- the link is built from `CAMPUS_PUBLIC_URL`, never from the request's Host
  header, so nobody can get a reset mailed out that points at their own server.

Without SMTP settings the link is written to the server log instead of mailed,
which is how to use it on a laptop.

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

**3. Accounts, and a door for visitors.** The map is behind a sign-in page. An
account needs a full name (letters of any alphabet, with spaces, hyphens or
apostrophes; required), a university address — exactly nine digits and `@sdu.edu.kz`,
e.g. `240103048@sdu.edu.kz` — and a password that has an uppercase letter, a
lowercase letter, a digit, a special character, at least 8 characters, no
spaces, no student ID inside it, and nothing from the common-password list.
Both checks run on the server (`app/auth.py`); the form only makes them
quicker to see.

US1 is written for students, staff **and visitors**, and a visitor has no
university address to sign up with. So the sign-in page also has *Continue as a
visitor*: a session with no account behind it, which gets everything US1
covers — search, the map, opening hours. Anything added later that belongs to a
person (a saved route, a timetable, a reminder) goes behind
`require_account()` in `app/main.py`, which answers a visitor with 403.

| Who | How they get in | What they can reach |
|---|---|---|
| Student | 9-digit SDU address + password | everything |
| Visitor | *Continue as a visitor* | everything in US1; `require_account()` refuses the rest |
| Staff | **not yet** — see "Honest limitations" | — |

---

## Layout

```
sdu-campus-assistant/
├── app/
│   ├── main.py        # FastAPI: API, accounts, the site
│   ├── engine.py      # search, directions, service hours
│   ├── floorplan.py   # the redrawn vector floor plans
│   ├── auth.py        # SDU accounts, password rules, sessions, password reset
│   └── mailer.py      # the password-reset email (SMTP, or the log in development)
├── data/
│   ├── campus.sql     # the campus, schema and data: the versioned source
│   ├── campus.db      # built from campus.sql by tools/build_db.py (read-only for the app)
│   ├── users.db       # accounts, created on first run, git-ignored
│   └── schema.sql     # exact schema of campus.db
├── static/
│   ├── index.html     # the app
│   ├── auth.html      # sign in / create account
│   ├── app.js         # conversation + SVG map renderer
│   ├── auth.js        # the sign-in form
│   ├── styles.css, auth.css
│   ├── img/           # the SDU mark, the full lockup and the favicon
│   └── plans/         # the original sheets, the wider floor-1 print, the colour map
├── tests/             # 180 tests: US1 clause by clause, the data, accounts, the map
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
- write the change back to the versioned source with
  `python3 tools/build_db.py --dump` (the test suite fails while `campus.sql`
  and `campus.db` differ), and commit both;
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

180 tests. `tests/test_us1_acceptance.py` walks the story sheet clause by clause:

| US1 clause | Test |
|---|---|
| QA scenario 1, verbatim: "Where is room 204 in the Engineering building?" returns building, floor and landmark | `test_qa_scenario_1_returns_building_floor_and_landmark` |
| QA scenario 1: answered within 5 seconds | `test_qa_scenario_1_is_answered_well_inside_five_seconds` |
| QA scenario 2: a room that does not exist gives "not found" plus real nearby rooms | `test_qa_scenario_2_says_not_found_and_suggests_real_rooms` |
| Parses **room numbers** | `test_room_queries_are_understood` (English, Russian, Cyrillic lookalikes, hall names) |
| Parses **department names** | `test_department_and_building_names_are_understood` |
| Parses **facility types** | `test_facility_types_are_understood` |
| Works across **single and multi-turn** conversations | `test_a_number_alone_asks_which_block_and_remembers_the_question`, `test_the_follow_up_turn_resolves_the_earlier_number` |
| Returns building, floor and nearest landmark on every match | `test_every_room_answer_names_building_floor_and_a_landmark` |
| Never reports a valid room as missing (test script: Fail) | `test_no_existing_room_is_ever_reported_as_missing` |
| Never returns the wrong building (test script: Fail) | `test_no_room_is_ever_put_in_the_wrong_building` |
| Reads the campus data read-only (constraint) | `test_the_campus_database_is_opened_read_only` |
| Five plain-language questions return the right block and floor | `test_scenario1_correct_building_and_floor` |

Beyond US1: every room is drawn exactly once on the map
(`test_every_room_in_the_database_is_drawn_exactly_once`), only nine-digit SDU
addresses with strong passwords can register (`test_everything_else_is_refused`),
the app is unreachable without an account
(`test_the_app_is_closed_without_an_account`), and nothing in the database
points at a row that is gone (`test_nothing_is_left_dangling`).

Real answer time is around 0.1–1 ms.

---

## API

| Method | What it does |
|---|---|
| `POST /api/auth/register` | Create an account (9 digits + `@sdu.edu.kz`, strong password) |
| `POST /api/auth/login` / `logout` | Start or end a session |
| `POST /api/auth/forgot` | Mail a one-time password-reset link (same answer for every address) |
| `POST /api/auth/reset` | Spend the link's token on a new password; signs in, ends other sessions |
| `POST /api/profile/password` | Change the password: current password required; other sessions end (accounts only) |
| `POST /api/auth/guest` | Come in as a visitor, without an account |
| `GET /api/auth/me` | The signed-in account |
| `GET /api/search?q=...&context=...` | The US1 endpoint: directions, map position, suggestions. Understands room codes, hall names (`A1`), faculties (`Business School`), blocks (`Block D`) and services. `context` carries the room number a previous answer asked about, which is what makes a follow-up like "Engineering" resolve "204" |
| `GET /api/map` | All three floors as vector geometry |
| `GET /api/sheets` | The original evacuation sheets, for reference |
| `GET /api/services` | Services with an open/closed status in Almaty time |
| `GET /api/health` | Liveness check (the only open data endpoint) |

Everything except `/api/health`, `/api/auth/*`, `/login` and `/static/*` needs
a session cookie; without one the API answers `401` and `/` redirects to
`/login`.

`/api/search` answer kinds: `room`, `block` (a faculty or a whole block),
`service`, `ambiguous` (e.g. "204" exists in five blocks — the answer carries a
`context` for the next turn), `not_found` and `no_match`.

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
- landmarks are the exits on floor 1 and the wing-end stairwells on floors 2–3;
  where none is close enough, the answer falls back to what is recognisable
  around the room — the round lecture hall beside it, the central corridor, or
  the mouth of its wing — so every answer names a landmark;
- a question that names a faculty or a block but no room ("Where is the Business
  School?") is answered with the block, the floors it covers and the rooms it
  starts at;
- a bare number that exists in several blocks is answered with a question, and
  the next turn settles it: "204" then "Engineering" gives F204. The pending
  number travels in the answer's `context`, so the conversation state lives in
  the browser tab rather than on the server.

## Honest limitations

- **Block I** is not digitised. Its rooms are copied from the east half of the
  Block H layout (`source = 'approximated_from_H'` in the database); the answer
  says so and the map draws it with dashed outlines.
- **The vector plan is a redrawing, not a survey.** Room positions, door
  order, row sides and adjacency come straight from the digitised sheets;
  wall thicknesses and room depths are regularised so the drawing stays
  readable. The original photographs are still served under `/static/plans/`.
- **Default hours.** Every service the university gave no hours for (the
  Medcenter, the cafés, Moodle help, the offices, the information desk,
  restrooms and the rest) is open 08:30–17:30, Monday to Saturday,
  and says its hours are approximate. On a Sunday only Ay Market is open
  (08:00–18:00), as the university's list says.
- **Office days are assumed.** The list gives "8:30–17:30" without days; offices
  are taken as Monday to Friday. The cafeteria's hours are still approximate,
  and the Medcenter, Moodle help, the Strategic Development Department, the
  Inclusive Education Office and the Educational Methodical Center have none on
  file — the app says so rather than guessing.
- **I113 and I214 are approximate.** Block I has no plan; the two rooms the
  university names on its west side are drawn where Block H has H111 and H214,
  dashed like the rest of Block I.
- **One colour-map reading is an inference.** The table-tennis corner's edges are
  read off a schematic. Red Canteen's seating runs past the top of the sheet,
  where nothing is drawn, so its outline stops at the sheet edge.
- **The colour map covers floor 1 only.** Restrooms and the other places it
  marks are not repeated on floors 2 and 3 until a source shows them there.
- The **dean's offices are not tied to rooms** yet, so they show a status but
  no route. The Library, Cafeteria, Medcenter, Red Canteen, Red Coffee and
  Doner House are tied to rooms and appear on the plan; the last three have no
  opening hours on file and say so.
- **Block B's letter** comes from the room label B114. The sheet does not say
  which block the Library and Red Hall belong to; they are filed under Block B
  because they share its foyer.
- Answers are in English. Questions are understood in English and Russian;
  full multilingual answers are planned for US6.
- **Staff cannot register yet.** The sign-up rule is exactly nine digits plus
  `@sdu.edu.kz`, which is a student number. A lecturer's address is usually a
  name (`aidana.serikova@sdu.edu.kz`) and is refused. Either widen the rule to
  any `@sdu.edu.kz` address and give those accounts a staff role, or leave
  staff on the visitor door until US2 needs to tell the two apart.
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
| `CAMPUS_SEED_NAME` | `SDU Student` | The full name for that account (every account has one) |
| `CAMPUS_PUBLIC_URL` | unset | The site's address, e.g. `https://sdu-campus-assistant.onrender.com` — reset links are built from it; required once mail is configured |
| `CAMPUS_SMTP_HOST` | unset | SMTP server for the reset email; unset writes the link to the log instead |
| `CAMPUS_SMTP_PORT` | `587` | STARTTLS; `465` for implicit TLS |
| `CAMPUS_SMTP_USER` / `CAMPUS_SMTP_PASSWORD` | unset | SMTP login |
| `CAMPUS_MAIL_FROM` | `CAMPUS_SMTP_USER` | Sender address |

---

## Next: Sprint 2

- **US2 Navigation.** A corridor graph (`nav_nodes` / `nav_edges` are already
  in the schema) and a real route drawn on the vector plan.
- **US3 Smart Recommendations.** Tie services to rooms, add exact hours, and
  suggest a place to work during a gap in the timetable.
