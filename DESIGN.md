---
name: SDU Campus Assistant
description: A wayfinding assistant that issues you a destination card in SDU's own card language.
colors:
  sdu-navy: "#2F345C"
  navy-deep: "#252949"
  navy-hover: "#3B4172"
  on-navy: "#FFFFFF"
  on-navy-2: "#C6CAE2"
  on-navy-3: "#A0A6C9"
  sdu-peach: "#E89A64"
  peach-hover: "#F0AC7C"
  on-peach: "#2B1A0C"
  destination: "#B4501A"
  destination-soft: "#FCEADD"
  evacuation-green: "#0B7A47"
  evacuation-green-soft: "#DEF0E6"
  alarm: "#B93A2C"
  alarm-soft: "#FBE6E2"
  ground: "#E9EBF2"
  paper: "#F3F4F8"
  card-stock: "#FFFFFF"
  card-stock-2: "#F6F7FA"
  ink: "#191D3A"
  ink-2: "#454B6C"
  ink-3: "#5C6384"
  seam: "#DFE2EB"
  seam-strong: "#C7CBDA"
  lamp-off: "#9AA0BC"
  map-bg: "#E4E7F0"
  map-slab: "#FAFBFD"
  map-hall: "#EEF0F6"
  map-room: "#FFFFFF"
  map-wall: "#A3A9C1"
  target-fill: "color-mix(in srgb, #E89A64 55%, #FFFFFF)"
typography:
  display:
    fontFamily: "Onest, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "clamp(2.75rem, 2.1rem + 1.6vw, 3.5rem)"
    fontWeight: 800
    lineHeight: 0.92
    letterSpacing: "-0.04em"
    fontFeature: "tnum"
  headline:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title-small:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  field-value:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.35
  label:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.07em"
  band:
    fontFamily: "Onest, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    letterSpacing: "0.08em"
rounded:
  card: "14px"
  row: "10px"
  control: "8px"
  tag: "4px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "20px"
  s6: "24px"
  s8: "32px"
  s10: "40px"
components:
  button-primary:
    backgroundColor: "{colors.sdu-navy}"
    textColor: "{colors.on-navy}"
    rounded: "{rounded.control}"
    padding: "0 18px 0 20px"
    height: "52px"
    typography: "{typography.title-small}"
  button-primary-hover:
    backgroundColor: "{colors.navy-hover}"
  button-find:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.sdu-navy}"
    rounded: "{rounded.control}"
    height: "52px"
  button-line:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "40px"
  input-search:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px 0 44px"
    height: "52px"
  input-field:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "50px"
  card:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
  card-band:
    backgroundColor: "{colors.sdu-navy}"
    textColor: "{colors.on-navy}"
    typography: "{typography.band}"
    padding: "6px 16px 10px"
    height: "38px"
  tag-code:
    backgroundColor: "{colors.sdu-navy}"
    textColor: "{colors.on-navy}"
    rounded: "{rounded.tag}"
    padding: "4px 8px"
  route-sign:
    backgroundColor: "{colors.card-stock-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tag}"
    padding: "5px 11px 5px 8px"
    height: "34px"
  route-sign-destination:
    backgroundColor: "{colors.sdu-peach}"
    textColor: "{colors.on-peach}"
    rounded: "{rounded.tag}"
  pick:
    backgroundColor: "{colors.card-stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
    height: "40px"
  pick-hover:
    backgroundColor: "{colors.sdu-navy}"
    textColor: "{colors.on-navy}"
  floor-current:
    backgroundColor: "{colors.sdu-navy}"
    textColor: "{colors.on-navy}"
    width: "40px"
    height: "36px"
---

# Design System: SDU Campus Assistant

## Overview

**Creative North Star: "The Student Card"**

Every answer is issued as a card in SDU's own card language: a navy band with a fine guilloche, the peach stripe under it, white card stock, labelled fields in small capitals, and a portrait slot that holds the room lit on its own corner of the floor plan. The room code is the only headline on the card. The interface refuses the chat-bubble assistant and the white-card maps panel: the shell is a plain working app (a navy bar, a search well, an answer column, the plan), and the card is the one object the world lends it.

Density is that of a printed ID: small, labelled, tabular, with hierarchy carried by scale contrast alone (a 44–56px room code over 12–15px fields). Depth is flat, with hairline seams between fields and around card objects; only things floating over the plan lift. Evacuation-plan green marks exits and things that are open, because the floor plans are redrawn from SDU's own evacuation sheets. SDU navy and peach come off the university mark and are a brand commitment.

Three complete themes share the same card: **Light** (default), **Dark** ("the same card at night": bands stay SDU navy, stock turns ink-blue) and **Steppe** (sky teal `#0D4A5C` replaces navy, sun gold `#E8B23A` takes the stripe, terracotta `#A8431A` the destination). A fourth menu option, **Match device**, follows `prefers-color-scheme` between Light and Dark. The choice is stored in `localStorage` (`sdu-theme`), set as `data-theme` on `<html>` before first paint, and the browser `theme-color` follows the band.

**Key Characteristics:**
- The destination card: navy guilloche band, 4px peach stripe, portrait of the lit room, room code as sole headline, labelled two-up fields on hairline seams.
- One family, Onest, Latin and Cyrillic, tabular numerals everywhere.
- Navy owns the bar, the search well, card bands, code tags, the current floor and the main button on stock.
- Peach means "this is the card" or "this is your destination", nothing else.
- Flat surfaces, hairline seams; one lift shadow only over the plan.
- One authored motion: the card being issued.

## Colors

A committed navy shell over cool paper and white card stock, one warm accent with two jobs, and green and red reserved for state.

### Primary
- **SDU Navy** (`sdu-navy`): the top bar, the search well that continues it into the answer column, every card band, code tags, the current floor in the floor switch, the current block on the rail, the plan pin's face, the main button on card stock, and the room code itself in Light and Steppe. Hover on navy steps to **Navy Hover** (`navy-hover`). Text on navy is white, with secondaries tinted from navy (`on-navy-2`, `on-navy-3`), never grey. In Dark the bands stay SDU navy but the main button on stock lifts to `#4A5196` (hover `#5860A8`) so it reads against ink-blue stock.

### Secondary
- **SDU Peach** (`sdu-peach`): the 4px stripe under every card band and under the search well, the visitor-pass chip and the pass band's stripe, the destination sign at the end of the route strip, the lit room in the portrait, the foot stripe on the destination's block in the rail, and the stripe on the plan pin. On the plan the lit room uses **Target Fill** (`target-fill`, peach mixed 55% into white; `#F4B98F` in Dark). Text on peach is **On Peach** (`on-peach`).
- **Destination** (`destination`): "your destination" as text and strokes (5:1 on white): the lit room's outline, hover on plan rooms and arrows, the focus ring, the caret, icons inside secondary buttons. Its tint **Destination Soft** (`destination-soft`) fills a hovered plan room and the destination block on the rail.

### Tertiary
- **Evacuation Green** (`evacuation-green`): exits and stairs on the plan (as the evacuation sheets draw them), the landmark step in a route, an open service's lamp and state, passed password rules, valid fields. Soft tint `evacuation-green-soft` behind success messages.
- **Alarm** (`alarm`): errors only (failed fields, form errors, the error prompt icon), with `alarm-soft` behind them.

### Neutral
- **Ground** (`ground`): behind everything in the app.
- **Paper** (`paper`): the answer column, the sign-in and profile pages.
- **Card Stock** (`card-stock`) and **Recessed Stock** (`card-stock-2`): card faces; recessed stock for card feet, notes, route signs, segmented-control wells, hover rows.
- **Ink** (`ink`, `ink-2`, `ink-3`): text hierarchy; `ink-3` is the floor for any text and still clears 4.5:1 on stock and paper.
- **Seam** (`seam`) and **Strong Seam** (`seam-strong`): 1px hairlines between fields and rows; the stronger one around card objects and controls.
- **Lamp Off** (`lamp-off`): the hollow ring of a closed service's lamp.
- **The plan's own drawing** (`map-bg`, `map-slab`, `map-hall`, `map-room`, `map-wall`, plus map ink = navy): a separate set so the plan can be redrawn per theme without touching the card.

### Named Rules
**The Stripe Rule.** Peach marks exactly two things: the card (its stripe, the visitor pass) and your destination (the last route sign, the lit room, the rail foot, the pin). Never a generic accent, link colour or decoration.

**The Closed Is Not an Error Rule.** A closed service is a normal state: a hollow grey lamp and an ink-2/ink-3 state line ("opens tomorrow at 08:30"). Red is for errors only.

**The Exit Is Green Rule.** Exits, stairs and "open" use evacuation green in every theme, as on SDU's evacuation sheets.

## Typography

**Display Font:** Onest (Google Fonts, weights 400–800), with Segoe UI, system-ui, -apple-system, sans-serif
**Body Font:** Onest, same stack
**Label Font:** Onest, small capitals by uppercase and tracking

**Character:** One humanist grotesque with full Cyrillic, because questions arrive in Russian ("Кабинет Д217") and must answer in the same voice. `font-variant-numeric: tabular-nums` is set on the body so room codes, hours and student IDs line up.

### Hierarchy
- **Display** (800, `clamp(2.75rem, 2.1rem + 1.6vw, 3.5rem)`, line-height 0.92, −0.04em): the room or block code on a destination card. Nothing else. A named destination ("Library") steps down to 28px, 800.
- **Headline** (800, 1.75rem, 1.1, −0.03em): sign-in and pass titles, a past card's code, a named destination. The sign-in photo line ("Every route starts at these doors.") is the one larger outlier at `clamp(2rem, 1.2rem + 2.2vw, 3rem)`, 800, −0.035em.
- **Title** (700–800, 1.375rem, −0.02em): the search label on desktop ("Where do you need to be?"), profile section titles, the name on your card. 1.125rem/700 for listing and prompt titles and the search label on phones; 1rem/700 for panel section titles and buttons.
- **Body** (400, 0.9375rem, 1.5): running text; route steps at line-height 1.55, capped at 62ch. Field values are 0.9375rem/600. Secondary text 0.875rem, hints and route signs 0.8125rem. Inputs are 16px so phones never zoom.
- **Label** (600, 0.75rem, +0.07em, uppercase): the card's printed captions: field labels (`Block`, `Floor`, `Landmark`), "How to get there", "Opening hours", the floor switch's "Floor". Card bands use the same size at 700, +0.08em.

### Named Rules
**The One Headline Rule.** On a card, the code is the only headline; everything else is small and labelled. Hierarchy comes from scale contrast, not from tinted boxes.

**The Caption Not Kicker Rule.** Uppercase tracked labels caption a field or the block of content they sit on, as printed on an ID card. They never sit above a heading as a kicker or eyebrow.

## Layout

A fixed app grid, not a page. On desktop the shell is `minmax(380px, 420px) | 1fr` (440px column from 1360px): the navy bar spans the top; under it on the left the search well, then the scrolling answer column (welcome destinations and the "Campus services" board on first visit, issued cards after); the plan fills the right, with the map bar on top and the block rail down its left edge.

- **Breakpoints:** ≥1360px widens the answer column to 440px; <1280px hides the plan's key; <1024px becomes one column (bar, sticky search well, plan band at 52dvh between 340 and 620px, answers centred at max 760px) with `--composer-h` (92px) feeding `scroll-padding-top` / `scroll-margin-top` so nothing hides under the sticky search; 640–1023px sets suggestions two-up and a 136px portrait; <640px hides the stats line and account name, insets cards 12px, uses a 96px portrait, keeps the route strip on one row; <380px collapses "Find" to its arrow.
- **Spacing:** 4px base (`s1`–`s10`). Turns are 32px apart; card internals 16px (12px on phones); more space above a heading than below.
- **Sign-in:** two columns, `5fr | minmax(480px, 6fr)`: SDU's entrance at night (sticky, full height) beside a 460px stack of the account card and the visitor pass on paper. Under 1024px the photo becomes a band across the top.
- **Profile:** your card (400px) beside the change-password card (480px), stacked under 1024px.
- `100dvh` with `100vh` fallback; safe-area insets on the bar and the end of the thread; grid tracks are `minmax(0, 1fr)` so nothing scrolls sideways.

## Elevation & Depth

Flat by default. Depth is drawn with 1px hairline seams and with inset shadows that paint stripes and outlines (the peach stripe under bands and the search well is `inset 0 -4px 0`). One drop shadow exists, and it belongs only to things floating over the plan or the page.

### Shadow Vocabulary
- **Lift** (`box-shadow: 0 1px 2px rgba(31,36,72,.10), 0 8px 20px -8px rgba(31,36,72,.30)`): the zoom stack, the stage message over the plan, the theme menu. Navy-tinted in Light, black in Dark, teal-tinted in Steppe. Never combined with a border.

### Named Rules
**The Float Only Rule.** Cards, rows and controls sit flat on hairlines. A drop shadow means the thing floats over the plan or opens over the page.

**The Guilloche Rule.** The guilloche (fine white security lines at 10% opacity, a 96×20 SVG tile) is texture for navy card bands and the profile's photo slot only.

## Shapes

Corners are graded by object: **card corner** (14px) for card objects, the ID-card corner scaled; **row corner** (10px) for row lists, the portrait, the block rail, segmented wells, menus and the stage message; **control corner** (8px) for inputs, buttons and picks; **tag corner** (4px) for code tags, route signs, the visitor-pass chip and portrait captions. Fully round is reserved for status marks: lamps, step numbers, password-rule checks. Borders are 1px (`seam` inside, `seam-strong` around), 1.5px on form inputs and the visitor button, 2px on the search input. Card objects clip their content (`overflow: hidden`) so the band and stripe run edge to edge. The portrait and the profile photo slot are 5:6, the proportion of an ID photo.

## Components

### Buttons
Firm and plain: solid fills, 700 weight, a 1px press on `:active`.
- **Shape:** control corner (8px).
- **Primary (Go):** navy on card stock, white text, 52px tall, 16px/700, a trailing arrow that nudges 2px right on hover; hover steps to navy-hover. Dark uses `#4A5196`.
- **Find (on the navy well):** the inverse: white card stock with navy ink and a faint white inset edge; hover `#E8EAF4`.
- **Line (secondary):** card stock, 1px strong seam, 40px, 14px/600, its icon in destination; hover darkens the border to ink-2. "Show on plan", "Sign out".
- **Text (tertiary):** ink-2 text, no fill; hover to ink. "Show the route again".
- **On the bar:** 40px outline buttons in white at 24% border; hover fills navy-hover. Focus rings on navy turn white.
- **Visitor button:** card stock with a 1.5px navy outline and navy ink; hover fills navy.
- **Disabled:** 60% opacity with a progress cursor. **Focus:** 2px destination ring, 2px offset.

### Chips
- **Code tag:** navy, white, 13px/700, tag corner. Leads each suggestion and listing row; a plain variant on recessed stock marks non-room destinations.
- **Route signs:** the route in brief as a row of 34px tags on recessed stock with an inset strong-seam outline and a direction icon; the last sign, the destination, is solid peach with on-peach ink.
- **Pick:** a 40px suggestion on card stock with a strong-seam border that turns solid navy on hover.
- **Visitor pass:** the bar's peach chip, 12px/700 uppercase, tag corner.

### Cards / Containers
Only three things are card objects: the destination card (room, block and service variants), the account card and visitor pass on sign-in, and your card on the profile. Everything else is a row.
- **Corner Style:** card corner (14px).
- **Background:** card stock; feet and notes on recessed stock.
- **Shadow Strategy:** none (see Elevation).
- **Border:** 1px strong seam; past cards soften to the plain seam.
- **Internal Padding:** 16px (12px on phones); sign-in card bodies 20–24px.
- **The band:** navy with guilloche, 38px, 12px/700 uppercase +0.08em, institution left ("SDU University") and location right ("Floor 1 · Block D") in on-navy-2, closed by the 4px peach stripe. The **visitor pass** is the same card with a recessed-stock band in navy ink over the peach stripe.
- **Fields:** a `dl`, two short fields per row on 1px seams, wide fields span; empty fields are dropped, never shown as a dash.
- **Past turns** fold to band, a 56px portrait and a 28px code, with "Show the route again" in the foot.
- **Rows** (welcome destinations, the services board, listings) are flat lines on 1px seams inside one bordered row-corner list, never cards in cards.

### Inputs / Fields
- **Search:** 52px, solid white in every theme with navy ink, 16px/600, a leading search icon, 2px transparent border. Focus: navy border plus a 3px white halo against the well.
- **Form fields:** visible 14px/600 label above, 50px input, 1.5px strong seam, card stock; hover darkens the border to ink-3. Focus: navy border with a 3px navy halo at 22% (periwinkle `#8C93D6` in Dark).
- **Valid / Error:** green border; error is an alarm border on alarm-soft with the hint turned red and specific. Form errors sit above the submit button on alarm-soft with an inset alarm outline.
- **Password rules:** a two-column list of round marks that fill green with a white check as each rule passes.

### Navigation
- **Bar:** navy, 60px (56px on phones): the SDU mark on a white 40px tile, "Campus Assistant" 16px/700 with a 12px stats line in on-navy-2; right side holds the theme menu, the account name (or the visitor-pass chip), profile and sign out. On phones the stats line and name hide and sign out collapses to its icon.
- **Theme menu:** a 256px radio list on card stock with Lift; each option shows its theme as a swatch of the card itself (band, stripe, stock).
- **Floor switch:** a segmented control on recessed stock with a 1px seam; 40×36px keys (44×40 on phones), 16px/700; the current floor is solid navy.

### The Destination Card's Portrait (signature)
Where an ID card has its photo, the destination card has a 5:6 crop of the room's own floor, drawn by `portrait()` from the plan geometry: slab and halls in the plan's tokens, neighbouring rooms tinted, the target room filled peach with a 2px destination outline and lit once, exits green, a navy "Floor N" caption chip bottom-left.

### The Block Rail (signature)
A 52px vertical strip (44px on phones) down the plan's left edge, row corner, inset strong-seam outline. Blocks are listed in walking order, each segment's height proportional to its run along the corridor, separated by inset hairlines. The block at the centre of the view is solid navy; the answer's block wears destination-soft with destination ink and a 4px peach foot.

### The Plan
The floor plans redrawn as SVG from SDU's evacuation sheets: room fills tinted by type from the map tokens, exits and stairs as the sheets' own squares (green and navy) with the icon family in white, the target room in target-fill with a 3.2px destination outline while the rest dim to 55%. The pin is a small card: navy face, white code, peach stripe. Zoom stack bottom-right (44px targets, Lift). The plan opens at stage width on the lobby end.

### Motion
One authored moment, **the card is issued**: the card rises 10px over 420ms on `cubic-bezier(.16,1,.3,1)`, the peach stripe draws in from the left over 520ms (80ms delay), and the portrait's room lights once. The plan pans to the room over 640ms and the pin pings. Everything else is a 160ms colour or transform transition; a loading card (the shape of a card, no spinner) appears only after 180ms. On sign-in and profile the cards mount with a 12px rise and their stripes draw in. `prefers-reduced-motion` collapses all of it.

## Do's and Don'ts

### Do:
- **Do** issue every answer as a card: navy guilloche band, 4px peach stripe, portrait, the code as the only headline, labelled fields on 1px seams.
- **Do** keep peach for the card and the destination only (The Stripe Rule).
- **Do** make the main button navy on card stock and white stock with navy ink on the navy well.
- **Do** use evacuation green for exits, stairs, open and valid, in every theme.
- **Do** show closed as a hollow grey lamp with a plain-language state line.
- **Do** set every number in Onest with tabular figures, and keep inputs at 16px.
- **Do** keep card objects to the destination card, the account card, the visitor pass and your card; everything else is a row on hairlines.
- **Do** give every theme the full token set, including the plan's own drawing tokens.

### Don't:
- **Don't** use chat bubbles or a white-card maps panel; the answer is a card, the shell is a plain app.
- **Don't** use red for "closed"; red is for errors only.
- **Don't** put a drop shadow on anything that does not float over the plan or the page.
- **Don't** use uppercase tracked labels as kickers above headings; they caption fields.
- **Don't** nest a card inside a card.
- **Don't** use guilloche anywhere but navy card bands and the profile photo slot.
- **Don't** shrink the plan to fit the whole floor by default, or let the block rail misstate the corridor's order or proportions.

## Imagery

| File | Source | License |
|---|---|---|
| `static/img/sdu-entrance-night.jpg` | [Sdu_night.jpg](https://commons.wikimedia.org/wiki/File:Sdu_night.jpg), Wikimedia Commons, by Tunceribrahim | CC0 1.0 (credited on the page anyway) |
| `static/img/sdu-logo.png`, `sdu-mark.png`, `favicon.png` | SDU University's own mark | university brand assets |

The entrance photo is the sign-in backdrop in its own colours under a navy dusk (a navy wash at 28% plus darker top and bottom gradients; teal in Steppe). The SDU mark always sits on a white tile.
