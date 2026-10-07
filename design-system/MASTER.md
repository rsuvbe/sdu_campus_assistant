# SDU Campus Assistant — Design System (MASTER)

**Direction: The Student Card.** A wayfinding assistant that issues you a destination card.
SDU's own card is the design language: a navy band, white card stock, the peach stripe under
the band, labelled fields in small capitals, and a portrait slot that holds the room's corner
of the floor plan. Mode: *Operate* — the layout and controls are standard; the world lends
type, palette, density and one signature move.

Source of truth for values: `static/styles.css :root` (tokens, app) and `static/auth.css`
(sign-in, profile). This file explains them; when they disagree, the CSS wins and this file
is updated.

---

## 1. Principles

1. **Search first.** The question field is the first control on every app viewport, directly
   under the bar, with a visible label ("Where do you need to be?").
2. **The room code is the only headline.** Everything else on an answer is small and labelled.
   Hierarchy comes from scale contrast, not from tinted boxes.
3. **Cards are objects, not containers.** Only three things are card objects: the destination
   card (and its block/service variants), the account card on sign-in, and the visitor pass /
   your card on the profile. Lists, the services board and the plan controls are flat rows on
   hairlines. Never nest a card in a card.
4. **Hairline seams, no shadows.** Depth is flat. The only shadow (`--lift`) is on things that
   float over the plan: the zoom stack, the stage message and menus.
5. **The plan gets the space.** It opens at stage width on the lobby end; the block rail beside
   it keeps the whole corridor in view.
6. **Nothing invented.** Every field, step and landmark comes from the API's plan geometry.

---

## 2. Colour

Strategy: **Committed shell, restrained work areas.** SDU navy owns the bar, the search well
and every card band; peach is the one accent and means "your destination"; green and red are state only.

| Token | Light | Dark | Steppe | Role |
|---|---|---|---|---|
| `--navy` | `#2F345C` | `#2F345C` | `#0D4A5C` | bar, search well, card bands, primary button on stock, current floor, rail position |
| `--navy-hi` | `#3B4172` | `#3E4475` | `#17637A` | hover on navy |
| `--on-navy` / `--on-navy-2` | `#FFF` / `#C6CAE2` | same | `#FFF` / `#C2E2EA` | text on navy; secondary is tinted from navy, never grey |
| `--peach` | `#E89A64` | `#E89A64` | `#E8B23A` | the card stripe, the destination route chip, the lit room (`--target-fill`), the rail's destination foot, the pin's stripe |
| `--on-peach` | `#2B1A0C` | same | `#2A2008` | text on peach |
| `--dest` | `#B4501A` | `#F29D66` | `#A8431A` | "your destination" as text/stroke (5:1 on white); focus ring |
| `--dest-soft` | `#FCEADD` | `#3A2418` | `#F8E5D8` | destination tint |
| `--exit` / `--exit-soft` | `#0B7A47` / `#DEF0E6` | `#45C98D` / `#11301F` | `#11784B` | evacuation green: exits, stairs, open |
| `--alarm` / `--alarm-soft` | `#B93A2C` / `#FBE6E2` | `#FF7B6F` / `#3B1C1B` | `#B8322B` | errors only. **"Closed" is not an error** — it uses a hollow grey lamp |
| `--ground` | `#E9EBF2` | `#0B0E20` | `#E3EDF0` | behind everything |
| `--paper` | `#F3F4F8` | `#10132A` | `#EEF5F6` | the answers panel, sign-in and profile pages |
| `--stock` / `--stock-2` | `#FFF` / `#F6F7FA` | `#181C38` / `#1F2444` | `#FFF` / `#F2F7F8` | card stock / recessed stock |
| `--ink` / `--ink-2` / `--ink-3` | `#191D3A` / `#454B6C` / `#5C6384` | `#ECEEF7` / `#B7BCD6` / `#9198BA` | teal inks | text hierarchy; `--ink-3` ≥ 4.5:1 on stock and paper |
| `--line` / `--line-2` | `#DFE2EB` / `#C7CBDA` | `#2A2F52` / `#3C4270` | | seams / control borders |
| `--map-*` | bg, slab, hall, room, wall, ink | | | the plan's own drawing tokens |
| `--action` / `--on-action` | navy / white | `#4A5196` / white | navy / white | the main button on card stock |

**Rule of the main button:** on card stock it is navy (`#4A5196` in dark); on the navy search well it is white card stock with navy ink. Peach is never a button.

Themes: no stored choice follows the device (Light/Dark). `theme.js` stores `sdu-theme`
(`light`, `dark`, `steppe`) and sets `data-theme` on `<html>`; an inline `<head>` snippet applies
it before first paint. The browser's `theme-color` follows the band colour.

---

## 3. Typography

One family: **Onest** (Google Fonts, 400–800), chosen for its Cyrillic — questions arrive in
Russian ("Кабинет Д217") and must render in the same voice. Fallback `Segoe UI, system-ui`.
`font-variant-numeric: tabular-nums` everywhere (room codes, hours, IDs line up).

| Token | Size | Use |
|---|---|---|
| `--t-code` | `clamp(2.75rem, 2.1rem + 1.6vw, 3.5rem)`, 800, −0.04em, lh .92 | the room code — the only headline on a card |
| `--t-28` | 28px, 800, −0.03em | named destinations ("Library"), page titles, sign-in h1 |
| `--t-22` | 22px, 700, −0.02em | search label on desktop, section titles on profile |
| `--t-18` | 18px, 700 | prompt and list titles, search label on phone |
| `--t-16` | 16px, 700 | panel section titles ("Try one of these"), buttons |
| `--t-15` | 15px, 400–600 | body, route steps (lh 1.55), field values |
| `--t-14` | 14px | secondary text, rows, controls |
| `--t-13` | 13px | hints, tags, route signs |
| `--t-12` | 12px, 600, +0.07em, UPPERCASE | **field labels only** (`dt`, `.field-label`, card bands) — the card's printed captions. Never as a kicker above a heading. |

Inputs are 16px so phones never zoom. Headings use `text-wrap: balance`; paragraphs `pretty`.
Body measure is capped at 60–62ch.

---

## 4. Space, shape, depth

- **Space:** 4px base — `--s1` 4 · `--s2` 8 · `--s3` 12 · `--s4` 16 · `--s5` 20 · `--s6` 24 · `--s8` 32 · `--s10` 40.
  Turns are 32px apart; card internals 16px (12px on phones). More space above a heading than below.
- **Radius:** `--r-card` 14px (card objects: the ISO ID-card corner, scaled) · 10px (rows, portrait,
  rail, segmented controls, menus) · `--r-ctl` 8px (inputs, buttons) · `--r-tag` 4px (tags, route signs).
  Round only for status lamps and step numbers.
- **Borders:** 1px `--line` seams inside cards; 1px `--line-2` around card objects and controls;
  1.5px on text inputs.
- **Depth:** flat. `--lift` (navy-tinted, offset, soft) only on the zoom stack, stage message and
  theme menu — never together with a border.
- **Texture:** `--guilloche`, the fine security-line pattern printed on ID cards, white at 10%,
  only on card bands and the profile's photo slot.

---

## 5. Components

### Bar (`.bar`)
Navy, 60px (56 on phones). SDU mark on a white tile, "Campus Assistant", stats line. Right:
theme menu, account name (or the **Visitor pass** chip — peach, uppercase), profile, sign out.
Phones: stats line and name hide; sign-out collapses to its icon (label kept for screen readers).

### Search well (`.composer`)
Continues the navy from the bar over the answer column; closed by a 4px peach stripe (inset
shadow). Visible label, 52px white input with search icon, white **Find** button with navy ink, hint line.
Under 1024px it is **sticky** at the top; `--composer-h` feeds `scroll-margin-top` so a focused
or scrolled-to turn is never hidden under it. Under 380px "Find" collapses to its arrow.

### Destination card (`.answer.card`)
```
┌ card-band: DESTINATION ───────────── (navy + guilloche) ┐
├──────────────── peach stripe (draws in) ────────────────┤
│ [portrait 5:6]   D105                (--t-code, navy)   │
│ [plan crop lit]  Specialised room    (id-sub)           │
├─ BLOCK ──────────────┬─ FLOOR ──────────────────────────┤
├─ FACULTY ───────────────────────────────────────────────┤
├─ LANDMARK ──────────────────────────────────────────────┤
│ HOW TO GET THERE                                        │
│ [→ Main lobby] [↑ Block D wing] [↑ Last door ▓peach▓]   │
│ ① step … ② step … ❹ the door step (navy) ◼ landmark     │
├─ foot: [📍 Show on plan]                    (stock-2)   ┤
└─────────────────────────────────────────────────────────┘
```
- **Portrait** (`.portrait`): an SVG crop of the room's own floor, centred on the room, the room
  filled peach with a `--dest` outline, doors on the way tinted, exits green; caption "Floor N".
  Drawn from `/api/map` geometry by `portrait()` in `app.js`.
- **Fields** (`dl.fields`): two short fields per row, wide fields span; an odd short field spans.
  Empty fields are dropped, never shown as "—".
- **Variants:** room (Destination), block (letter as the code; Rooms, Floors, Landmark; "Rooms
  you'll find here" tags), service (name as a named code, status lamp, Opening hours timetable,
  route or "isn't on the digitised plans yet").
- **Past turns** (`.turn.past`): fold to band + small portrait + code; foot offers "Show the route
  again", which unfolds and re-pins the plan.

### Listing (`.listing`)
Title + summary, then rows: navy code tag · purpose · "Floor N · Block X" · arrow. Folded after 12
rows behind "Show all N".

### Prompt (`.prompt`)
For `ambiguous`, `no_match`, `not_found`, `error`: icon + title, lede, and either **choices**
(full-width rows with arrows, for "which one?") or tags ("Try one of these" / "Ask again").
Error icon is `--alarm`; miss is `--ink-2`.

### Services board (`.directory`)
Flat rows inside one bordered list: lamp · name · state. Open first; open lamps are green with a
soft ring and their state ("until 17:30") is green; closed lamps are hollow grey and the state
reads "opens tomorrow at 08:30". Header shows "N open now" or "All closed right now". Folded
after 6 behind "Show all N".

### Plan (`.map`)
- **Map bar:** floor segmented control (current = navy), the live readout
  "Floor 1 · Block D" (`#map-where`, `aria-live`), and the key (≥1280px).
- **Block rail** (`#block-seg`): a vertical strip down the plan's left edge; blocks in walking
  order (sorted by `y0`), each segment's height proportional to its run along the corridor
  (`flex-grow` = `y1 − y0`). The block at the centre of the view is navy (`aria-current`); the
  answer's block wears `--dest-soft` with a peach foot stripe. Click = centre that block.
- **Stage:** opens at stage width on the lobby end (`overview()`); "whole floor" is the fit button.
  Zoom stack bottom-right (44px targets); credit bottom-left on a stock chip.
- **Pin:** a small card — navy face, white code, peach stripe.

### Buttons
| Class | Look | Use |
|---|---|---|
| `.btn-go` | navy (white with navy ink on the navy well; `#4A5196` in dark), 52px, 700 | the one main action per view |
| `.btn-line` | stock, 1px `--line-2`, icon in `--dest` | secondary ("Show on plan", "Sign out") |
| `.btn-text` | text only | tertiary ("Show the route again") |
| `.icon-btn` | outline on navy, 40px | bar actions |
| `.pick` | stock tag 40px → navy on hover | suggestions |
| `.linkish` | underlined in its own colour at 40% | inline links on forms |
All have hover, `:active` (1px press), `:focus-visible` (2px `--focus` ring; white on navy) and
disabled (60% + progress cursor).

### Inputs (`.field`)
Visible label above, 50px input, 1.5px `--line-2` border, focus = navy border + navy halo at 22% (periwinkle `#8C93D6` in dark),
`.good` green border, `.bad` red border + `--alarm-soft` fill with the hint turned red and
specific. Password rules as round checks that fill green as they pass. Errors (`.form-error`,
`role="alert"`) sit above the submit button; the failing field gets focus.

### Sign-in (`auth.html`)
Desktop: two columns — SDU's entrance at night in its own colours under a navy dusk (sticky),
with the brand, "Every route starts at these doors.", and the photo credit; the
other column on paper holds a 460px stack: the **account card** (navy band "SDU account",
segmented Sign in / Create account, title, form) and the **visitor pass** (same card, card-stock
band with navy ink and the peach stripe under it, "Visitor pass · No account needed", outline navy "Continue as a visitor"). Under 1024px the
photo becomes a band across the top.

### Profile (`profile.html`)
The app's navy bar with "Back to the map". **Your card**: navy band "SDU University · Student",
initials in a guilloche photo slot, name, then fields University email and Student ID (large,
tracked digits), foot with Sign out. Beside it (stacked on phones) the Change password card.
Visitors see their **visitor pass** with "Sign in".

---

## 6. Layout and breakpoints

| Width | Layout |
|---|---|
| ≥1360 | grid `440px | 1fr`: bar across; search well + answers left; plan right |
| 1024–1359 | same, answers column `minmax(380px, 420px)`; key hides under 1280 |
| 640–1023 | one column: bar · sticky search · plan band (52dvh, 340–620px) · answers (max 760px, centred); suggestions in two columns; portrait 136px |
| <640 | as above; stats line, account name, plan credit hide; card insets 12px; portrait 96px; list rows drop the location column |
| <380 | "Find" becomes its arrow; mark 36px |

`100dvh` with `100vh` fallback; `env(safe-area-inset-*)` on the bar and the end of the thread.
No horizontal scroll at any width (grid tracks are `minmax(0, 1fr)`).

---

## 7. Accessibility rules

- Contrast: body and placeholders ≥ 4.5:1 in every theme; `--ink-3` is the floor for text.
- Every input has a visible label; the search keeps its label in every state.
- Skip link to the search field; one icon sprite, every icon `aria-hidden`, every icon-only button
  has `aria-label`.
- Live regions: the answers log (`aria-live="polite"`), the map readout, the stage message
  (`role="status"`), form errors (`role="alert"`). Loading cards carry `aria-busy`.
- Plan rooms are focusable buttons (`role="button"`, Enter/Space ask about them).
- Touch targets ≥ 40px (44px on the plan controls and on phones); 8px between adjacent targets.
- Focus is never hidden under the sticky search (`scroll-padding-top` / `scroll-margin-top`).
- `prefers-reduced-motion` collapses every animation and transition; colour never carries
  state alone (lamps pair with words; destination pairs with outline weight and the pin).

---

## 8. Motion

One authored moment: **the card is issued.** It rises 10px (420ms, `cubic-bezier(.16,1,.3,1)`),
the peach stripe under the band draws in from the left (520ms, 80ms delay), the room in the
portrait lights once. The plan pans 640ms to the room and the pin pings. Everything else is a
160ms colour/transform transition. A loading card appears only after 180ms. No scroll-driven
effects, no parallax, no bounce.

---

## 9. Don'ts

- No chat bubbles, no gradient text, no glass on working surfaces, no coloured side stripes on
  rows or alerts, no kicker labels above headings, no emoji icons.
- No red for "closed" — closed is a normal state, not an error.
- No new card objects: if it isn't a destination, an account, or a pass, it's a row.
- Don't shrink the plan to fit the whole floor by default; don't let the rail lie about order.
