# SDU Campus Assistant

AI campus navigation and smart services assistant for SDU University.
Ask where a room or a service is, see it light up on a floor plan redrawn
from the university's own evacuation sheets, and get walking directions to it
from the main entrance or from any other room. A services page lists what the
campus offers and what is open right now.

- Backend: **FastAPI** + SQLite (`data/campus.db`, read-only)
- Frontend: plain HTML/CSS/JS in `static/`, no build step
- Data: 268 rooms and places, blocks A–I, 3 floors, digitised from the fire evacuation plans
  and the university's colour campus map
- Accounts: SDU addresses — a student's nine-digit number (`240103048@sdu.edu.kz`) or a
  member of staff's `name.surname@sdu.edu.kz`, with the staff role; visitors come in without one

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

## Sprint 4 — Directions and campus services

Checked story by story against the story sheet in `tests/test_sprint_4.py`:
every responsibility, QA scenario and (Pass)/(Fail) test script of US13 to US16,
and the maintenance tasks a program can check.

| Story | What it is now |
|---|---|
| US13 Text Directions Between Two Rooms | `app/routing.py` builds a corridor graph from the plan geometry and walks it with Dijkstra. The steps name the corridor, the block, the turn, the side and the stairs ("Turn left into the Block F wing: F204 is the fourth door on your left, just after F202 and F203"), say every floor change ("take the stairwell there up to floor 2"), and count doors from the way you actually come in. Questions such as "from G108 to F204", "how do I get to Red Hall from D217", "I'm in D101, where is D105?", "из D101 в F204" and "nearest restroom to G101" get the walk. A walk between two doors on the Block B foyer stays in the foyer instead of going back out to the central corridor. The route is drawn on the plan floor by floor: one line from the wall of the room it starts in to the wall of the room it ends in, corners rounded, arrowheads pointing the way, and a tag at each staircase on the plan's own stairs mark, framed with the line |
| US14 Directions from the Main Entrance | every answer that is on the plan has a **How do I get there?** button. The route starts at the main entrance, and its first step names it. "Starting from" can be changed to any room, a named place or another entrance, and the route is worked out again and replaces the old one. No device location is ever asked for |
| US15 Campus Services Directory | the services page lists every service by category (Food and shops, Library and study, Health, Student services, Dean's offices, Offices, Facilities), with chips to show one category. Each row gives the room, block and floor (for restrooms, the blocks and floors they are in) and whether it is open now. A row opens the service on the plan with its room lit. The laboratory rooms, study spaces and lecture halls are listed as well |
| US16 Opening Hours and Open-Now Status | weekday hours (lunch breaks included) live in `service_hours`. The status is computed in campus time, Asia/Almaty, UTC+5, even when the server clock runs on UTC; the zone comes from the bundled `tzdata` package so outdated system time-zone files cannot shift it by an hour. An open service shows its closing time, a closed one its next opening time, and a service with no hours on file is never shown as open. |

**Staircases.** Floors are joined only by staircases that are drawn on the
evacuation sheets. Seven were added to `campus.sql` from the sheets: the main
lobby staircase (floors 1–2) and the floor-1 foot of the stairwell at the far end
of the Block D to H wings, which `campus.db` already had on floors 2 and 3.
Two more come up inside the 3rd-floor Red Canteen, west of the corridor at
Block F: the north Red Canteen staircase, from the hall over the food court on
floor 2 (the way up from floor 2), and the Red Canteen staircase, which runs
from beside the table tennis on floor 1 straight to floor 3 with no way off at
floor 2. The floor-2 hall is drawn on its plan from the sheet, with the passage
along its top that leads to it from the corridor. A place asked for by its floor ("Red Canteen
3rd floor") is routed to that one, not to the nearer place of the same name.

**Places that share a name.** Four halls are called Study Space, five rooms
Restroom, four Staff restroom, and two Red Canteen. Asked for by that name, every
one of them is listed (and lit on the plan), each told apart wherever it is
named: Study Space 1 to 4 (numbered from the lobby end, "No. 2" on the plan, and
found however the number is written: "study space 4", "No. 4", "№4", "fourth"),
Restroom, Block D, and the canteens by their floor. A block or a floor in the
question narrows the list ("toilet in block G", "red canteen on the 3rd floor"),
and a route from a start goes to the nearest. A word that is part of other
places' names lists them too: "canteen" is the Cafeteria and both Red Canteens.

**Still to do by hand (US13, Verified):** walk three of the generated routes on
campus and check each step. A program cannot do this, so it is left for the
team.

**What the data still needs from the university:** 115 rooms are on the plans
with no recorded use, so their purpose is "Room"; Block C's floor-3 rooms are
drawn on the sheet without numbers and are not in the directory until they are
given.

## Sprint 5 — Timetable and campus events

Checked story by story against the story sheet in `tests/test_sprint_5.py`:
every responsibility, QA scenario and (Pass)/(Fail) test script of US17 to US20,
and the maintenance tasks a program can check.

| Story | What it is now |
|---|---|
| US17 Manual Class Schedule Entry | **Your timetable** on the profile: subject, day, start and end, and a room picked from the directory. Classes are added, edited and deleted through `/api/schedule`. A class lives in the `classes` table next to its account (Postgres on the live site, so it outlives a deploy), and every query carries the user id: another account's class answers 404 with nothing in it, to read, change or delete alike. A room that isn't in the directory is refused on the server; `A1`, `д217` and `Red Hall` are understood. There is no import from the student portal, as the story says |
| US18 Where Is My Next Class | "Where is my next class?", "next lecture" or "следующая пара" pick the next class that hasn't started from the asker's own week, in campus time, across the end of the week too. The answer is the room's usual card with the class, the day and the time on top, and **How do I get there?** A class that has begun is never the next one: it is named as the one on now. If the next class is today and an earlier one has been, the walk starts from that room; the start can still be changed. A visitor gets an explanation and a link to sign in, and an account with an empty timetable a link to fill it |
| US19 Campus Event List | The `events` table in `campus.db` holds the title, description, place, room, start and end. **Campus events** is a page of its own, `/events`, linked from the main page. It lists the ones that haven't ended, soonest first, with place and time. A row opens the map and asks about the event: its room lights up on the plan and the title heads the card. A place that isn't on the plans says so |
| US20 Event Search and Date Filter | A search box, Today / This week / This month, and two dates. Each change asks `/api/events`, which runs a query on the events table: every word must be in the title or description (Cyrillic ignores case too), and an event has to overlap the dates. The match count is shown, and an empty result says so and offers to clear the filters |

**The events table is empty.** We have no list from the university and nothing
is made up, so the page says no events have been added yet; the story sheet's
"seed it with sample events" was dropped on purpose. The tests run on rows of
their own in a copy of the database. An event goes in as a row in
`data/campus.sql`, then `python3 tools/build_db.py`.

## Events and SDU news — November 2026

SDU University publishes no events a program can read: sdu.edu.kz's events
page is empty, and the "upcoming events" on its home page are pictures. Its
news is a WordPress RSS feed. So the events page now has two parts:

| What | How it works |
|---|---|
| **Campus events, added by administrators** | The accounts in `CAMPUS_ADMINS` see **Add an event** on `/events`, and **Edit** and **Delete** on the events they added: title, description, start and end, a room from the directory (its name becomes the place) or a place in words, and a link to the announcement. They live in the accounts database (`campus_events`, Postgres on the live site) next to the ones shipped in `campus.db`, and are searched and filtered by date with the same database query (US20), listed and found by title on the map exactly like them. This is not US26 (the admin page for rooms and services, Sprint 7): it is only what US19's list needs to hold real events |
| **News from SDU** | Under the events, the ten latest stories from `https://sdu.edu.kz/en/feed/`: picture, the day it was published, title and a short excerpt, each linking to the story. The feed is read at most every 30 minutes per server; when the site can't be reached the last copy stays, marked stale. Only links and pictures on sdu.edu.kz are kept. A news date is the day a story was published, never shown as an event's date |
| **From a story to an event** | An administrator can press **Make it an event** on a story: the form starts with its title, excerpt and link, and the day, time and room are filled in by hand, since the story doesn't give them |

## The timetable page — November 2026

The timetable left the profile for a page of its own, **`/schedule`** (linked
from the main page and the profile).

| What | How it works |
|---|---|
| **The week as the portal draws it** | Days across (Mo–Sa, Su when a class is on it), the portal's hours down (08:30–09:20 … 21:30–22:20, stretched for a class outside them). A class is a card over its hours with the course, its group and the room; today's column is tinted with a line at the current minute, and the next class is lit. A press on an empty hour adds a class there; a press on a class opens it: the way there, edit, delete. Above the grid, the next class and **How do I get there**. On a phone the grid scrolls sideways under a sticky hour column |
| **Import from a screenshot** | A screenshot of the portal's *Course Schedule* is dropped, pasted or picked. It is read **in the browser** (`static/schedule-ocr.js` with tesseract.js from jsdelivr; the picture is never uploaded): the table is found by the portal's yellow lines, the icons are wiped out, the picture is enlarged by a whole factor and read; each word goes to its day and hour, an hour the OCR misread is put right from the others (they are an hour apart), the two hours of a long class become one, and a course code read short in one cell is put right by the same course elsewhere. The server then matches the rooms (`/api/schedule/rooms`), putting right the look-alikes the house icon leaves ("11301" → I301, "S110" → I110). Everything is shown for checking before it is saved, in place of the week or added to it. A room that is not in the directory ("VR 93", an online class) is held back unticked: US17 lets no class be saved without a room from the directory, so one has to be chosen from the list or the class left out. This is not the portal integration US17 leaves out: nothing is fetched from the portal, the student brings a picture of their own week |
| **Reminders** | **Turn on reminders** on the page: a few minutes before each class (5, 10, 15 or 30) every open page of the site shows a note with the room and **How do I get there**, and a system notification through a service worker (`/sw.js`) when allowed. The way there is "How do I get to my next class?", so it starts from the class before. **Add to my calendar** downloads `/api/schedule.ics`: the phone's calendar reminds even with the site closed |
| **Back after signing in** | A link into the site (a reminder, the calendar's way there) opened in a new visit goes through the sign-in page and comes back with its question: `/login?next=…`, a path on this site only |

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
- Every service's hours are the ones it keeps (`services.hours_confirmed`).

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
apostrophes; required), a university address — a student's nine digits and
`@sdu.edu.kz`, e.g. `240103048@sdu.edu.kz`, or a member of staff's name and
surname in Latin letters, e.g. `aidana.serikova@sdu.edu.kz`, which gives the
account the staff role — and a password that has an uppercase letter, a
lowercase letter, a digit, a special character, at least 8 characters, no
spaces, no student ID or name inside it, and nothing from the common-password list.
Both checks run on the server (`app/auth.py`); the form only makes them
quicker to see.

US1 is written for students, staff **and visitors**, and a visitor has no
university address to sign up with. So the sign-in page also has *Continue as a
visitor*: a session with no account behind it, which gets everything US1
covers — search, the map, opening hours, the events. What belongs to a person
(the timetable, and later a saved route or a reminder) goes behind
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
│   ├── engine.py      # search, service hours, the services page, next class, events
│   ├── routing.py     # the corridor graph and walking directions (US13, US14)
│   ├── floorplan.py   # the redrawn vector floor plans
│   ├── auth.py        # SDU accounts, password rules, sessions, password reset, timetables
│   └── mailer.py      # the password-reset email (SMTP, or the log in development)
├── data/
│   ├── campus.sql     # the campus, schema and data: the versioned source
│   ├── campus.db      # built from campus.sql by tools/build_db.py (read-only for the app)
│   ├── users.db       # accounts and timetables, created on first run, git-ignored
│   └── schema.sql     # exact schema of campus.db
├── static/
│   ├── index.html     # the app
│   ├── auth.html      # sign in / create account
│   ├── events.html    # the campus events page
│   ├── app.js         # conversation + SVG map renderer
│   ├── events.js      # the events list, search and dates
│   ├── auth.js        # the sign-in form
│   ├── styles.css, auth.css
│   ├── img/           # the SDU mark, the full lockup and the favicon
│   └── plans/         # the original sheets, the wider floor-1 print, the colour map
├── tests/             # 645 tests: every sprint's story sheet, the data, accounts, the map, the routes
├── requirements.txt
├── render.yaml        # one-click deploy on Render
└── Dockerfile         # Railway or any Docker host
```

---

## Running it locally

Python 3.14.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>. You will land on the sign-in page — create
an account with any nine-digit SDU address, for example `240103048@sdu.edu.kz`
(or a staff one, `aidana.serikova@sdu.edu.kz`)
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

645 tests. `tests/test_sprint_5.py` checks US17–US20, `tests/test_sprint_4.py` US13–US16,
`tests/test_sprints_2_3.py`
US4–US12 and `tests/test_us1_acceptance.py` checks US1, each line by line against
the story sheet. The US1 checks:

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
| `GET /api/route?to=...&from=...` | Walking directions (US13, US14): ordered `steps` with the floor each one is on, the route in brief (`signs`), the line to draw on each floor (`legs`) and the staircases (`stairs`). `to` and `from` take anything the search understands; leave out `from` and the route starts at the main entrance. A place it can't find gives `kind: "route_error"` and suggestions |
| `GET /api/services` | The services page: each service with its category group, location and an open/closed status in Almaty time, then the kinds of room there are many of |
| `GET /api/events?q=...&from=...&to=...` | Upcoming events, soonest first (US19, US20): words to find, and a period in campus dates, both days included. Also gives the match count, the total, and today, this week and this month as dates |
| `POST /api/events` | Add an event (administrators only): `title`, `description`, `starts`, `ends` ('2026-11-14T14:00', campus time), `room` from the directory or `place` in words, `link` |
| `PUT` / `DELETE /api/events/{id}` | Change or remove an event an administrator added (`a12`); one shipped in `campus.db` answers 404 |
| `GET /api/news` | The latest news from sdu.edu.kz's RSS feed, newest first, kept for half an hour; `stale` when the site couldn't be reached |
| `GET /api/schedule` | Your own timetable (accounts only; a visitor gets 403) |
| `POST /api/schedule` | Add a class: `subject`, `day` (0 = Monday), `start`, `end`, `room`; a room that is not in the directory is refused (US17) |
| `POST /api/schedule/rooms` | Rooms read off a screenshot, matched to the directory with the OCR's look-alikes put right ("11301" is I301) |
| `POST /api/schedule/import` | A whole week at once: `classes`, and `replace` (default) or add. All of it or nothing; a wrong class names its `row` |
| `GET /api/schedule.ics?lead=10` | Your week as a calendar file: weekly events in UTC, a reminder `lead` minutes before, a link to the way there |
| `GET` / `PUT` / `DELETE /api/schedule/{id}` | One of your classes; somebody else's answers 404 |
| `GET /api/rooms` | The room directory for the timetable's picker (accounts only) |
| `GET /api/health` | Liveness check (the only open data endpoint) |

Everything except `/api/health`, `/api/auth/*`, `/login` and `/static/*` needs
a session cookie; without one the API answers `401` and `/` redirects to
`/login`.

`/api/search` answer kinds: `room`, `block` (a faculty or a whole block),
`service`, `event` (an event at a place that isn't on the plans; one in a room
comes as `room`, with an `occasion`, as does the next class), `needs_account`
(the next class without a timetable, or a pointer to the events: it carries a
`link`), `ambiguous` (e.g. "204" exists in five blocks — the answer carries a
`context` for the next turn), `not_found` and `no_match`. A question that names a
start and a destination, or asks for the way ("how do I get to G215"), also
carries `directions`, in the same shape as `/api/route`.

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

### Walking routes (US13, US14)

The route graph is built at start-up (about 0.4 s) from the same geometry that
draws the plans, so the route and the drawing always agree:

- the **central corridor** is a chain of points down its middle, one where every
  room, wing and open area joins it;
- every **wing corridor** is a chain from the central corridor to the far end
  of the wing, and each wing room's door is on it, level with the room;
- the rooms **along the central corridor** open straight onto it;
- the **west side** (the round halls, the food court), the **lobby** and the
  **Block B foyer** are open floor. Each place there is joined to the corridor
  by the shortest walk that goes round every room in the way: a visibility
  graph over the rooms' corners, checked against the building's outline;
- floors are joined only by the **staircases on the sheets** (see Sprint 4);
- a room is a destination, never a corridor: no route walks through one.

`tests/test_sprint_4.py` checks every edge of the graph against every room
outline, so no route can pass through a wall or a closed room.

The steps are written from the walker's point of view. Turns come from the angle
between one stretch and the next ("turn right into the central corridor"), and
sides come from which side of the walking direction a door is on. Doors are
counted from where you enter, so coming down the wing-end stairwell counts from
that end. The last step uses the same door order and "directly across" as the
room's own answer.

## Honest limitations

- **Block I** is not digitised. Its classroom wings are copied from the east
  half of the Block H layout (`source = 'approximated_from_H'` in the database)
  and the rooms west of its corridor are placed from a sketch of the floors
  (`source = 'sketch'`); I110/I111, I211/I212 and I310/I311 are each one
  lecture hall answering to both numbers. The answer says the position is a
  guess and the map draws Block I with dashed outlines.
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
  and the Medcenter, Moodle help and the Educational Methodical Center have none on
  file — the app says so rather than guessing.
- **Block I's two offices are left out.** The university names the Strategic
  Development Department (I214) and the Inclusive Education Office (I113) in
  Block I, which has no plan; neither the rooms nor the offices are listed.
- **One colour-map reading is an inference.** The table-tennis corner's edges are
  read off a schematic. Red Canteen's seating runs past the top of the sheet,
  where nothing is drawn, so its outline stops at the sheet edge.
- **The colour map covers floor 1 only.** Restrooms and the other places it
  marks are not repeated on floors 2 and 3 until a source shows them there.
- **Only the staircases on the sheets are routed.** The sheets also show
  narrower stairs beside the central corridor and a stairwell by the wardrobe,
  but not clearly enough to tell which floors each one joins, so routes don't
  use them. There is no lift data, so step-free routes (US25) are not offered
  yet. Block I has no plan and so no staircase: its upper floors are reached
  along the corridor from Block H's stairwell.
- **Routes are walks on the drawing.** Doors are placed where each room meets
  its corridor, not surveyed, and the open floor west of the corridor is walked
  in straight lines between rooms. Distances are never quoted, because the
  sheets have no scale.
- **Events are added by hand.** The university's site has no events feed, so
  an administrator adds each one (`CAMPUS_ADMINS`); the news from sdu.edu.kz is
  shown as news, by the day it was published, and is not turned into events on
  its own. A change made on one server instance reaches the others' searches
  within a minute.
- **The timetable knows one week.** It repeats for ever: no term dates, no odd
  and even weeks, no holidays. A class during a break still counts as next, and
  the calendar file repeats with no end date.
- **The site reminds only while it is open.** A page in some tab is enough, but
  with the browser closed only the calendar file reminds; there is no push
  server. iPhones show the site's notifications only once it is added to the
  home screen; the note on the page shows anyway. The calendar file is a copy:
  after a change to the week it has to be added again.
- **The screenshot reader knows one template:** the portal's *Course Schedule*
  table as the browser shows it. A photo of a screen, a cropped or a
  Russian-language table reads worse or not at all; the preview is there to put
  it right.
- **Block B's letter** comes from the room label B114. The sheet does not say
  which block the Library and Red Hall belong to; they are filed under Block B
  because they share its foyer.
- Answers are in English. Questions are understood in English and Russian;
  full multilingual answers are planned for US6.
- **Free hosting has no persistent disk.** Serverless functions and Render's
  free plan wipe their filesystem, so accounts must not live in `users.db`
  there. The live site keeps them in Postgres (`DATABASE_URL`, see Deployment).

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

### Vercel + Neon + Brevo (the live site)

The site runs at <https://sdu-campus-assistant.vercel.app>: FastAPI as one
Vercel Function in Frankfurt (`vercel.json`), accounts in a Neon Postgres
database, password-reset mail through Brevo's HTTP API. All three are free.

1. **Vercel.** `npx vercel login`, then `npx vercel deploy --prod` from the
   project folder. `app/main.py` is found by itself; `.vercelignore` keeps the
   tests, the reports and the local `users.db` out of the bundle.
2. **Neon.** In the Vercel project: **Storage → Create Database → Neon**, region
   Frankfurt, **Connect** to the project. That adds `DATABASE_URL`; the tables
   are created on the first start.
3. **Brevo.** Verify a sender (**Settings → Senders**), create an API key
   (**SMTP & API → API Keys**), and add `CAMPUS_BREVO_API_KEY` (sensitive) and
   `CAMPUS_MAIL_FROM` (the verified sender) to the Vercel project.
4. Redeploy. `CAMPUS_PUBLIC_URL` and `CAMPUS_SECURE_COOKIES=true` are set on the
   project; reset links point at the public address.

Why not free Render: it blocks the SMTP ports and wipes the disk whenever the
service sleeps, so neither accounts nor reset mail survive there.

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
| `DATABASE_URL` | unset | Postgres for accounts, sessions and reset links (also read as `CAMPUS_DATABASE_URL` or `POSTGRES_URL`); unset uses SQLite |
| `CAMPUS_USERS_DB` | `data/users.db` | The SQLite file when there is no `DATABASE_URL` (`/tmp/users.db` on Vercel) |
| `CAMPUS_SECURE_COOKIES` | off | Set to `true` when serving over HTTPS |
| `CAMPUS_ADMINS` | unset | Comma-separated SDU addresses of the accounts that may add, change and delete events; nobody when unset |
| `CAMPUS_SEED_ACCOUNT` | unset | `<email>:<password>` — one account recreated at every start, so a shared link keeps working on hosting with no persistent disk |
| `CAMPUS_SEED_NAME` | `SDU Student` | The full name for that account (every account has one) |
| `CAMPUS_PUBLIC_URL` | unset | The site's address, e.g. `https://sdu-campus-assistant.vercel.app` — reset links are built from it; on Vercel it defaults to the production address |
| `CAMPUS_BREVO_API_KEY` | unset | Brevo API key: the reset email goes over HTTPS through Brevo |
| `CAMPUS_SMTP_HOST` | unset | SMTP server, used when there is no Brevo key; with neither the link goes to the log |
| `CAMPUS_SMTP_PORT` | `587` | STARTTLS; `465` for implicit TLS |
| `CAMPUS_SMTP_USER` / `CAMPUS_SMTP_PASSWORD` | unset | SMTP login |
| `CAMPUS_MAIL_FROM` | `CAMPUS_SMTP_USER` | Sender address; with Brevo, a sender verified in the account |
