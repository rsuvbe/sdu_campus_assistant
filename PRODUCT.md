# SDU Campus Assistant

## Product
A conversational wayfinding assistant for SDU University (Kaskelen, Almaty region). A person
asks where a room, a block, a faculty or a campus service is — by room code ("D103", "Д217"),
hall name ("A1"), faculty, or in their own words in English or Russian — and gets the building,
floor, a door-by-door route and a nearest landmark, with the room lit up on a vector floor plan
redrawn from the university's own evacuation sheets.

## Users and scene
- Students (first-years above all) and staff, plus visitors without an account.
- Used equally on phones while walking the central corridor and on laptops/desktops.
- Indoors, daytime, fluorescent light; quick, task-first sessions.

## Mechanism
One central corridor runs from the lobby past every block (C to I); blocks A and B sit off the
lobby foyer. Every answer is derived from plan geometry: door order along a wing, which side,
what is opposite, the nearest exit or stairwell. Nothing is invented.

## Capabilities (must be preserved)
- Search: rooms, round lecture halls (A1–D2), faculties/blocks, services; multi-turn follow-up
  for ambiguous numbers; "not found" with real suggestions.
- Floor plan: 3 floors, pan/zoom, floor and block switching, tap a room to ask about it.
- Services strip with open/closed status in Almaty time.
- Accounts: SDU address (9 digits + @sdu.edu.kz), visitor entry, forgot/reset password.

## Brand commitments
- SDU navy #2F345C and peach #E89A64 come off the university mark; the SDU logo files in
  static/img are the only logo assets.
- Exit/stairs are signal green, as on the evacuation plans.

## Platform
web (FastAPI + static HTML/CSS/JS, no build step). Interface language: English; questions
understood in English and Russian.
