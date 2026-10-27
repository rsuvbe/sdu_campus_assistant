"use strict";

const $ = (sel) => document.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "i") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

// Starting points: what you'd read on the door, then how people actually ask.
// Each one is a real question the assistant answers.
const EXAMPLES = [
  { tag: "D103", text: "Where is D103?", label: "A classroom by its door code" },
  { tag: "A1", text: "Hall A1", label: "The round hall everyone calls A1" },
  { tag: "Д217", text: "Кабинет Д217", label: "Asked in Russian" },
  { tag: "204", text: "Room 204", label: "A number that's in several blocks" },
  { tag: "Route", text: "From D103 to F204", label: "Directions from one room to another", plain: true },
  { tag: "Library", text: "Is the library open?", plain: true },
];

// Room labels are part of the drawing, so they only make sense once the plan is
// large enough to read: below LABEL_SCALE the map shows block letters instead.
// The two zoom levels below are absolute (1 = one plan pixel per screen pixel),
// so an answer always lands at the same readable size whatever the floor size.
const LABEL_SCALE = 0.5;
const ROOM_ZOOM = 1.15;
const BLOCK_ZOOM = 0.72;
// Answers come back in about a millisecond; a skeleton only appears when the
// network is slow, so a fast answer never flickers through a loading state.
const LOADING_DELAY = 180;

const LIST_ROWS = 12;
// how close a route is framed: never so far out that its turns can't be read
const ROUTE_MAX_ZOOM = 1.3;
const TRIP_CORNER = 18;     // how round a route's corners are drawn (plan px)
const TRIP_CHEVRON = 64;    // about how far apart its arrowheads are

const state = {
  floors: [],
  context: null,        // what the last answer asked the user to pin down
  floor: null,          // the floor currently drawn
  result: null,         // last room/service answer that has a position
  route: null,          // the walking route on show, drawn on every floor it crosses
  routeDrawn: null,     // the route and floor last drawn, so a repaint doesn't replay its draw-in
  routeFloor: null,
  view: { s: 1, fit: 1, tx: 0, ty: 0 },
  inView: null,         // the block at the centre of the stage
  cover: 0,             // how much of the stage the answers sheet hides (phone)
};

const phone = () => matchMedia("(max-width: 1023px)").matches;
// a phone held in the hand: the plan fills the screen and the answers are a sheet over it
const handset = () => matchMedia("(max-width: 767px)").matches;
const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

/* ------------------------------------------------------------ API */
async function api(path, options) {
  const res = await fetch(path, options);
  if (res.status === 401) { window.location.replace("/login"); throw new Error("signed out"); }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/* ------------------------------------------------------------ bar and services */
async function loadHeader() {
  try {
    const { user } = await api("/api/auth/me");
    const visitor = user.role === "visitor";
    const who = $("#account-who");
    $("#account").hidden = false;
    // a visitor carries a visitor pass; an account holder, their name
    // on a phone the pass is just "Visitor", the second word stays for screen readers
    if (visitor) who.innerHTML = `Visitor<span class="pass-word"> pass</span>`;
    else who.textContent = user.full_name || user.student_id;
    who.classList.toggle("pass", visitor);
    who.title = visitor ? "Looking around without an account" : user.email;
    $("#signout-label").textContent = visitor ? "Sign in" : "Sign out";
    $("#profile-link").hidden = visitor;   // a visitor has no account, so no profile
    $("#signout").setAttribute("aria-label", visitor ? "Sign in with an SDU account" : "Sign out");
    $("#signout").title = visitor ? "You're looking around as a visitor" : `Signed in as ${user.full_name || user.email}`;
  } catch { /* the 401 above already redirected */ }

  try {
    const s = await api("/api/stats");
    $("#stats-line").textContent = `SDU University · ${s.rooms} rooms on 3 floors`;
  } catch { /* keep default copy */ }

  loadServices();
}

/* The services page: every service by category, where it is and whether it is
   open now. A category chip narrows the list; a row asks about that service, so
   its room lights up on the plan and its card comes up in the answers. */
async function loadServices() {
  const box = $("#services");
  let services;
  try {
    services = await api("/api/services");
  } catch {
    box.closest(".directory").hidden = true;   // the page is optional; the assistant still works
    return;
  }
  // only hours a service has confirmed are counted as open; the rest are a guess
  const open = services.filter((svc) => svc.open_now === true && !guessed(svc)).length;
  const likely = services.filter((svc) => svc.open_now === true && guessed(svc)).length;
  $("#dir-summary").innerHTML = open || likely
    ? `<i class="lamp open" aria-hidden="true"></i><span>${open} open now${likely ? `<span class="likely">, ${likely} more probably</span>` : ""}</span>`
    : "All closed right now";

  const groups = [];
  services.forEach((svc) => {
    let g = groups.find((x) => x.key === svc.group);
    if (!g) groups.push(g = { key: svc.group, label: svc.group_label, items: [] });
    g.items.push(svc);
  });
  box.innerHTML = groups.map((g) => `
    <section class="dir-group" data-group="${esc(g.key)}" aria-labelledby="grp-${esc(g.key)}">
      <h3 class="dir-group-title" id="grp-${esc(g.key)}">${esc(g.label)}<span>${g.items.length}</span></h3>
      <ul class="dir-list">${g.items.map(serviceRow).join("")}</ul>
    </section>`).join("");
  if (services.some(guessed)) {
    box.insertAdjacentHTML("beforeend", `<p class="dir-note"><span aria-hidden="true">≈</span> Hours the service
      hasn't confirmed yet: the team's best reading, so check before you go.</p>`);
  }
  box.querySelectorAll("[data-ask]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.ask)));

  const filter = $("#dir-filter");
  const chips = [{ key: "", label: "All" }, ...groups];
  filter.innerHTML = chips.map((c) =>
    `<button type="button" class="chip" data-group="${esc(c.key)}" aria-pressed="${c.key === ""}">${esc(c.label)}</button>`).join("");
  filter.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
    filter.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    box.querySelectorAll(".dir-group").forEach((sec) => {
      sec.hidden = !!chip.dataset.group && sec.dataset.group !== chip.dataset.group;
    });
  }));
  if (location.hash === "#services") $("#services-page").scrollIntoView({ block: "start" });
}

// hours on file that the service itself hasn't confirmed
const guessed = (svc) => svc.kind !== "rooms" && svc.hours_approximate && svc.hours?.length > 0;

function serviceRow(svc) {
  const cls = svc.open_now === true ? "open" : svc.open_now === false ? "closed" : "";
  const where = svc.location ? svc.location.text : "Not on the plans yet";
  const guess = guessed(svc);
  const aside = svc.kind === "rooms" ? `${svc.location.count} rooms` : `${guess ? "≈ " : ""}${shortStatus(svc)}`;
  const status = guess ? `${svc.status} (hours not confirmed yet)` : svc.status;
  // long office names are shown by their short name; the full one is in the tooltip
  return `<li><button type="button" class="dir-row ${cls}${guess ? " guess" : ""}${svc.kind === "rooms" ? " rooms" : ""}" data-ask="${esc(svc.ask)}"
      title="${esc(svc.name)}. ${esc(status)}" aria-label="${esc(svc.name)}, ${esc(where)}, ${esc(status)}">
      <i class="lamp ${cls}" aria-hidden="true"></i>
      <span class="dir-text"><b>${esc(svc.short_name || svc.name)}</b><span class="where">${esc(where)}</span></span>
      <span class="state">${esc(aside)}</span></button></li>`;
}

function shortStatus(svc) {
  // the row has room for the closing time only; the lunch break and the rest
  // of the sentence are in the row's tooltip and in the answer
  if (svc.open_now === true) return (svc.status.match(/until \d{1,2}:\d{2}/) || ["open"])[0];
  if (svc.open_now === false) return (svc.status.match(/opens .*?\d{1,2}:\d{2}/) || ["closed"])[0];
  return "no hours yet";
}

/* ------------------------------------------------------------ conversation */
function renderExamples() {
  const list = $("#examples");
  EXAMPLES.forEach((ex) => {
    const li = document.createElement("li");
    li.innerHTML = `<button type="button" class="dest">
      <span class="tag${ex.plain ? " plain" : ""}">${esc(ex.tag)}</span>
      <span class="what">${esc(ex.label || ex.text)}</span>${icon("right")}</button>`;
    li.querySelector("button").addEventListener("click", () => ask(ex.text));
    list.appendChild(li);
  });
}

async function ask(text) {
  const query = text.trim();
  if (!query) return;
  const log = $("#log");
  $("#thread").classList.add("asked");
  if (handset()) {
    // the keyboard goes away and the sheet makes room for the plan the answer lands on
    $("#q").blur();
    setSnap("half");
  }
  const go = $("#composer .btn-go");

  // every question opens a turn at the top; earlier answers fold underneath it
  log.querySelectorAll(".turn:not(.past)").forEach((t) => t.classList.add("past"));
  const turn = document.createElement("section");
  turn.className = "turn";
  turn.setAttribute("aria-label", `Answer to: ${query}`);
  const q = document.createElement("p");
  q.className = "q";
  q.innerHTML = `${icon("search")}<span></span>`;
  q.querySelector("span").textContent = query;
  turn.appendChild(q);
  log.prepend(turn);
  bringIntoView(turn);

  // a card-shaped placeholder, only if the answer is slow to come back
  const pending = document.createElement("article");
  pending.className = "answer card loading";
  pending.setAttribute("aria-busy", "true");
  pending.innerHTML = `<div class="card-band"><span class="skel" style="width:6rem"></span></div>
    <div class="card-id"><div class="portrait"></div>
    <div class="id-main"><span class="skel tall" style="width:7rem"></span><span class="skel" style="width:11rem"></span></div></div>
    <span class="visually-hidden">Finding ${esc(query)}…</span>`;
  const showPending = setTimeout(() => turn.appendChild(pending), LOADING_DELAY);
  go.disabled = true;

  let data;
  try {
    const carried = state.context ? `&context=${encodeURIComponent(state.context)}` : "";
    data = await api(`/api/search?q=${encodeURIComponent(query)}${carried}`);
  } catch (err) {
    data = { kind: "error", title: "Couldn't reach the campus server",
             summary: `The request didn't go through (${err.message}). Check your connection and ask again.`,
             suggestions: [query] };
  }
  clearTimeout(showPending);
  pending.remove();
  go.disabled = false;

  state.context = data.context ?? null;
  turn.appendChild(renderCard(data));
  bringIntoView(turn);
  showResultOnMap(data);
}

// The newest turn sits at the top of the answers: on a laptop or in the phone's
// sheet the answers scroll back to it; on a tablet the page brings it up under
// the search field.
function bringIntoView(turn) {
  if (!phone() || handset()) { $("#thread").scrollTo({ top: 0, behavior: smooth() }); return; }
  const top = turn.getBoundingClientRect().top + window.scrollY - $("#composer").offsetHeight - 12;
  window.scrollTo({ top: Math.max(top, 0), behavior: smooth() });
}

function picks(list, cls = "picks") {
  if (!list || !list.length) return "";
  return `<div class="${cls}">${list.map((s) => `<button type="button" class="pick" data-ask="${esc(s)}">${esc(s)}${
    cls === "choices" ? icon("right") : ""}</button>`).join("")}</div>`;
}

// The route in brief, the way the corridor signs read: entrance, wing, door.
// The last sign is the door you want.
function signStrip(route) {
  if (!route || !route.length) return "";
  return `<ol class="signs" aria-label="Route in brief">${route.map((r, i) => {
    const last = i === route.length - 1 && route.length > 1;
    return `<li class="${last ? "dest-sign" : ""}">${icon(r.icon)}<span>${esc(r.text)}</span></li>`;
  }).join("")}</ol>`;
}

function stepsList(steps) {
  if (!steps || !steps.length) return "";
  return `<ol class="steps">${steps.map((s) => s.startsWith("Landmark:")
    ? `<li class="landmark">${icon("exit")}<span>${esc(capitalise(s.replace(/^Landmark:\s*/, "")))}</span></li>`
    : `<li><span>${esc(s)}</span></li>`).join("")}</ol>`;
}

// On a card: the route in brief, then a "How do I get there?" action that asks
// for the walk itself, from the main entrance unless another start is picked.
// A question that named its own start ("from D103 to F204") comes with the walk.
function routeBlock(d) {
  const to = d.map?.code;
  if (!to) {
    if (!d.route?.length && !d.steps?.length) return "";
    return `<section class="route" aria-label="How to get there">
      <h4 class="field-label">How to get there</h4>${signStrip(d.route)}${stepsList(d.steps)}</section>`;
  }
  return `<section class="route" aria-label="How to get there">
    <h4 class="field-label">How to get there</h4>
    <div class="trip" data-to="${esc(to)}">${d.directions ? tripBody(d.directions) : `
      ${signStrip(d.route)}
      <button type="button" class="btn-go trip-go" data-directions>${icon("ahead")}How do I get there?</button>`}
    </div></section>`;
}

let tripSeq = 0;
const startLabel = (place) => capitalise(place.label.replace(/^the /, ""));

function tripBody(r, error = null) {
  const id = `from-${++tripSeq}`;
  const value = r ? startLabel(r.from) : "";
  const form = `<form class="trip-from" data-trip-from>
      <label class="field-label" for="${id}">${icon("entrance")}Starting from</label>
      <div class="trip-row">
        <input id="${id}" name="from" list="places" value="${esc(value)}" maxlength="200" autocomplete="off"
          placeholder="Main entrance, or any room" enterkeyhint="go" aria-describedby="${id}-hint">
        <button type="submit" class="btn-line">Go</button>
      </div>
      <p class="trip-hint" id="${id}-hint">Change it to any room, and the route is worked out again from there.</p>
    </form>`;
  if (error) {
    return `${form}<p class="trip-error" role="alert">${icon("alert")}<span><b>${esc(error.title)}.</b> ${esc(error.summary)}</span></p>
      ${picks(error.suggestions)}`;
  }
  const floors = r.floors.length > 1
    ? `<div class="trip-floors" role="group" aria-label="Show a floor of the route">${r.floors.map((f, i) =>
        `${i ? icon("right", "i sep") : ""}<button type="button" class="chip" data-route-floor="${f}">Floor ${f}</button>`).join("")}</div>`
    : "";
  const steps = r.steps.map((s, i) => {
    const f = r.step_floors?.[i];
    return `<li${f != null ? ` data-floor="${f}"` : ""}><span>${esc(s)}</span></li>`;
  }).join("");
  return `${form}
    <p class="trip-sum">${esc(r.summary)}</p>
    ${signStrip(r.signs)}
    ${floors}
    <ol class="steps trip-steps" aria-label="Step by step">${steps}</ol>
    ${note(r.note)}`;
}

// Fill a card's route from the server: on the first press, and every time the
// start is changed (the old route is replaced, on the card and on the plan).
async function loadTrip(card, d, from) {
  const trip = card.querySelector(".trip");
  trip.setAttribute("aria-busy", "true");
  let r;
  try {
    const q = `to=${encodeURIComponent(trip.dataset.to)}${from ? `&from=${encodeURIComponent(from)}` : ""}`;
    r = await api(`/api/route?${q}`);
  } catch (err) {
    r = { kind: "route_error", title: "Couldn't reach the campus server",
          summary: `The request didn't go through (${err.message}). Check your connection and try again.`, suggestions: [] };
  }
  trip.removeAttribute("aria-busy");
  if (r.kind === "route_error") {
    trip.innerHTML = tripBody(null, r);
    trip.querySelector("input").value = from || "";
  } else {
    d.directions = r;
    trip.innerHTML = tripBody(r);
    showRoute(r, undefined, d);
  }
  wireTrip(card, d);
  return r;
}

function wireTrip(card, d) {
  const trip = card.querySelector(".trip");
  if (!trip) return;
  const go = trip.querySelector("[data-directions]");
  if (go) go.addEventListener("click", async () => {
    go.disabled = true;
    await loadTrip(card, d, null);
    trip.querySelector(".trip-steps")?.scrollIntoView({ block: "nearest", behavior: smooth() });
  });
  const form = trip.querySelector("[data-trip-from]");
  if (form) form.addEventListener("submit", (e) => {
    e.preventDefault();
    const value = form.from.value.trim();
    form.from.blur();
    loadTrip(card, d, value || null);
  });
  trip.querySelectorAll("[data-ask]").forEach((b) => b.addEventListener("click", () => loadTrip(card, d, b.dataset.ask)));
  trip.querySelectorAll("[data-route-floor]").forEach((b) => b.addEventListener("click", () => {
    if (d.directions) showRoute(d.directions, Number(b.dataset.routeFloor), d);
  }));
  trip.querySelectorAll(".trip-steps li[data-floor]").forEach((li) => li.addEventListener("click", () => {
    if (d.directions && Number(li.dataset.floor) !== state.floor?.floor) showRoute(d.directions, Number(li.dataset.floor), d);
  }));
  markRouteFloor(trip);
}

// The start can be any room, a named place or an entrance: the field offers them all.
function fillPlaces() {
  const list = $("#places");
  if (!list || !state.floors.length) return;
  const seen = new Set();
  const opts = [];
  const add = (value, label) => {
    if (seen.has(value)) return;
    seen.add(value);
    opts.push(`<option value="${esc(value)}"${label && label !== value ? ` label="${esc(label)}"` : ""}></option>`);
  };
  add("Main entrance");
  state.floors.forEach((f) => f.landmarks.filter((lm) => lm.type === "exit" && !/main entrance/.test(lm.name))
    .forEach((lm) => add(capitalise(lm.name))));
  state.floors.forEach((f) => f.rooms.forEach((r) => add(r.ask || r.code, `${r.label} · Floor ${f.floor}, Block ${r.block}`)));
  list.innerHTML = opts.join("");
}

// Opening hours as a timetable: consecutive days with the same times share a
// line ("Mon–Fri 08:30–17:30, lunch 12:30–13:30"), the way a door sign prints them.
const SHORT_DAY = { Monday: "Mon", Tuesday: "Tue", Wednesday: "Wed", Thursday: "Thu", Friday: "Fri", Saturday: "Sat", Sunday: "Sun" };
const WEEK = Object.keys(SHORT_DAY);
function hoursLine(hours) {
  if (!hours || !hours.length) return "";
  const runs = [];
  hours.forEach((h) => {
    const key = `${h.open}|${h.close}|${h.break || ""}`;
    const last = runs[runs.length - 1];
    if (last && last.key === key && WEEK.indexOf(h.day) === WEEK.indexOf(last.to) + 1) last.to = h.day;
    else runs.push({ key, from: h.day, to: h.day, h });
  });
  const rows = runs.map((r) => {
    const days = r.from === r.to ? SHORT_DAY[r.from] : `${SHORT_DAY[r.from]}–${SHORT_DAY[r.to]}`;
    return `<li><span class="days">${days}</span><span class="times">${esc(r.h.open)}–${esc(r.h.close)}</span>${
      r.h.break ? `<span class="brk">lunch ${esc(r.h.break)}</span>` : ""}</li>`;
  });
  // say which weekend days are closed, if any
  const covered = new Set(hours.map((h) => h.day));
  const shut = ["Saturday", "Sunday"].filter((d) => !covered.has(d)).map((d) => SHORT_DAY[d]);
  if (shut.length) rows.push(`<li class="off"><span class="days">${shut.join("–")}</span><span class="times">closed</span></li>`);
  return `<div class="hours"><h4 class="field-label">${icon("clock")}Opening hours</h4><ul>${rows.join("")}</ul></div>`;
}

const capitalise = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const note = (text) => (text ? `<p class="note">${icon("info")}<span>${esc(text)}</span></p>` : "");
const shortName = (name) => name.replace(/^Block \w+ — /, "");
const faculty = (name) => (/ — /.test(name) ? shortName(name) : "");

// The card's labelled fields: one row per fact, nothing ranked by boxes.
function fields(list) {
  const rows = list.filter((f) => f && f.value !== "" && f.value != null);
  if (!rows.length) return "";
  // short fields pair up; an odd one out takes the whole row
  const short = rows.filter((f) => !f.wide);
  if (short.length % 2) short[short.length - 1].wide = true;
  return `<dl class="fields">${rows.map((f) => `<div class="${f.wide ? "wide" : ""}"><dt>${esc(f.label)}</dt><dd>${f.html ?? esc(f.value)}</dd></div>`).join("")}</dl>`;
}

function landmarkOf(d) {
  if (d.map?.landmark?.name) return capitalise(d.map.landmark.name);
  const step = (d.steps || []).find((s) => s.startsWith("Landmark:"));
  return step ? capitalise(step.replace(/^Landmark:\s*/, "")).replace(/ —.*$/, "") : "";
}

/* The portrait: where an ID card has its photo, the destination card has the
   room's own corner of the floor plan, the room lit. Drawn from the same
   geometry as the big plan. */
function portrait(d) {
  const m = d.map;
  const floor = m && state.floors.find((f) => f.floor === m.floor);
  if (!floor) return `<div class="portrait empty" aria-hidden="true">${icon("pin")}</div>`;
  const code = m.code || m.room_number;
  const room = floor.rooms.find((r) => r.code === code);
  let x0 = m.x - 30, x1 = m.x + 30, y0 = m.y - 30, y1 = m.y + 30;
  if (room?.kind === "circle") { x0 = room.cx - room.r; x1 = room.cx + room.r; y0 = room.cy - room.r; y1 = room.cy + room.r; }
  else if (room?.points) {
    const xs = room.points.map((p) => p[0]), ys = room.points.map((p) => p[1]);
    x0 = Math.min(...xs); x1 = Math.max(...xs); y0 = Math.min(...ys); y1 = Math.max(...ys);
  }
  const w = Math.max(250, (x1 - x0) * 2.1, ((y1 - y0) * 1.9) / 1.2);
  const h = w * 1.2;
  const vx = (x0 + x1) / 2 - w / 2, vy = (y0 + y1) / 2 - h / 2;
  const inBox = (x, y, pad = 120) => x > vx - pad && x < vx + w + pad && y > vy - pad && y < vy + h + pad;
  const pts = (p) => p.map((q) => `${q[0]},${q[1]}`).join(" ");
  const near = new Set((m.highlights || []).map((hl) => hl.room_number));
  const shapes = floor.rooms.filter((r) => inBox(r.x ?? r.cx, r.y ?? r.cy, 260)).map((r) => {
    const cls = r.code === code ? "tgt" : near.has(r.code) ? "near" : "";
    return r.kind === "circle"
      ? `<circle class="${cls}" cx="${r.cx}" cy="${r.cy}" r="${r.r}"/>`
      : `<polygon class="${cls}" points="${pts(r.points)}"/>`;
  }).join("");
  const exits = floor.landmarks.filter((lm) => lm.type === "exit" && inBox(lm.x, lm.y, 0))
    .map((lm) => `<rect class="ex" x="${lm.x - 11}" y="${lm.y - 11}" width="22" height="22" rx="2"/>`).join("");
  return `<figure class="portrait">
    <svg viewBox="${vx} ${vy} ${w} ${h}" role="img" aria-label="${esc(m.room_number)} on the floor ${m.floor} plan">
      <g class="p-slab">${floor.areas.map((a) => `<polygon points="${pts(a.points)}"/>`).join("")}</g>
      <g class="p-hall">${floor.circulation.map((c) => `<polygon points="${pts(c.points)}"/>`).join("")}</g>
      <g class="p-rooms">${shapes}</g>${exits}
    </svg>
    <figcaption>Floor ${esc(m.floor)}</figcaption>
  </figure>`;
}

function foot(d, withMapLink) {
  return `<footer class="answer-foot" title="Answered in ${d.elapsed_ms ?? "–"} ms">${
    withMapLink ? `<button type="button" class="btn-line" data-refocus>${icon("pin")}Show on plan</button>` : ""}
    <button type="button" class="btn-text" data-expand>Show the route again${icon("down")}</button></footer>`;
}

function renderCard(d) {
  const card = document.createElement("article");
  card.className = "answer";

  if (d.kind === "room") {
    const r = d.room;
    const named = r.room_number.length > 5;
    card.classList.add("card");
    card.innerHTML = `
      <header class="card-band"><span>SDU University</span><span class="band-where">Floor ${esc(r.floor_number)} · Block ${esc(r.building_id)}</span></header>
      <div class="card-id">
        ${portrait(d)}
        <div class="id-main">
          <h3 class="code${named ? " named" : ""}">${esc(r.room_number)}</h3>
          ${r.facts.length ? `<p class="id-sub">${esc(r.facts.join(" · "))}</p>` : ""}
        </div>
      </div>
      ${fields([
        { label: "Block", value: r.building_id },
        { label: "Floor", value: r.floor_number },
        { label: "Faculty", value: faculty(r.building_name), wide: true },
        { label: "Landmark", value: landmarkOf(d), wide: true },
      ])}
      ${routeBlock(d)}
      ${note(d.note)}
      ${picks(d.suggestions)}
      ${foot(d, !!d.map)}`;
  } else if (d.kind === "list") {
    // every room with that purpose: a short directory, closest match first
    const rows = d.results.map((r, i) => `
      <li${i >= LIST_ROWS ? ' class="more"' : ""}><button type="button" class="hit" data-ask="${esc(r.ask)}">
        <span class="tag">${esc(r.room_number)}</span>
        <span class="what">${esc(r.purpose || "")}</span>
        <span class="loc">Floor ${esc(r.floor_number)} · Block ${esc(r.building_id)}</span>${icon("right")}</button></li>`).join("");
    card.classList.add("listing");
    card.innerHTML = `
      <header class="listing-head">
        <h3>${esc(d.title)}</h3>
        <p>${esc(d.summary)}</p>
      </header>
      <ul class="hits">${rows}</ul>
      ${d.results.length > LIST_ROWS ? `<button type="button" class="btn-line" data-more>Show all ${d.results.length}</button>` : ""}
      ${foot(d, !!d.map)}`;
    const more = card.querySelector("[data-more]");
    if (more) more.addEventListener("click", () => { card.querySelector(".hits").classList.add("open"); more.remove(); });
  } else if (d.kind === "block") {
    const b = d.block;
    card.classList.add("card");
    card.innerHTML = `
      <header class="card-band"><span>SDU University</span><span class="band-where">Block ${esc(b.building_id)} · Floor${b.floors.length > 1 ? "s" : ""} ${esc(b.floors.join("–"))}</span></header>
      <div class="card-id">
        ${portrait(d)}
        <div class="id-main">
          <h3 class="code">${esc(b.building_id)}</h3>
          <p class="id-sub">${esc(shortName(b.name))}</p>
        </div>
      </div>
      ${fields([
        { label: "Rooms", value: b.rooms },
        { label: "Floors", value: b.floors.join(", ") },
        { label: "Landmark", value: landmarkOf(d), wide: true },
      ])}
      ${routeBlock(d)}
      ${d.suggestions?.length ? `<h4 class="field-label picks-label">Rooms you'll find here</h4>${picks(d.suggestions)}` : ""}
      ${foot(d, !!d.map)}`;
  } else if (d.kind === "service") {
    const s = d.service;
    const cls = s.open_now === true ? "open" : s.open_now === false ? "closed" : "";
    const r = d.room;
    // a long official name goes under the headline; the headline carries the short one
    const head = d.title.length > 22 && s.short_name ? s.short_name : d.title;
    card.classList.add("card");
    card.innerHTML = `
      <header class="card-band"><span>SDU University</span><span class="band-where">${r ? `Floor ${esc(r.floor_number)} · Block ${esc(r.building_id)}` : "Not on the plans yet"}</span></header>
      <div class="card-id">
        ${portrait(d)}
        <div class="id-main">
          <h3 class="code named">${esc(head)}</h3>
          ${head !== d.title ? `<p class="id-sub">${esc(d.title)}</p>` : ""}
          <p class="status ${cls}"><i class="lamp" aria-hidden="true"></i>${esc(s.status)}</p>
        </div>
      </div>
      ${fields(r ? [
        { label: "Block", value: r.building_id },
        { label: "Floor", value: r.floor_number },
        { label: "Room", value: r.room_number !== d.title ? r.room_number : "" },
        { label: "Landmark", value: landmarkOf(d), wide: true },
      ] : [])}
      ${hoursLine(s.hours)}
      ${s.notes ? `<p class="extra">${icon("info")}<span>${esc(s.notes)}</span></p>` : ""}
      ${d.map ? routeBlock(d)
              : `<p class="lede">Its exact room isn't on the digitised plans yet, so there's no route to show.</p>`}
      ${note(d.note)}
      ${picks(d.suggestions)}
      ${foot(d, !!d.map)}`;
  } else if (d.kind === "ambiguous") {
    // the assistant asks back: each choice is one tap away
    card.classList.add("prompt");
    card.innerHTML = `
      <header class="prompt-head">${icon("question")}<h3>${esc(d.title)}</h3></header>
      <p class="lede">${esc(d.summary)}</p>
      ${picks(d.suggestions, "choices")}`;
  } else {
    const isError = d.kind === "error";
    card.classList.add("prompt", isError ? "is-error" : "is-miss");
    card.innerHTML = `
      <header class="prompt-head">${icon(isError ? "alert" : "question")}<h3>${esc(d.title)}</h3></header>
      <p class="lede">${esc(d.summary)}</p>
      ${d.suggestions?.length ? `<h4 class="field-label picks-label">${isError ? "Ask again" : "Try one of these"}</h4>` : ""}
      ${picks(d.suggestions)}`;
  }

  card.querySelectorAll("[data-ask]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.ask)));
  const refocus = card.querySelector("[data-refocus]");
  if (refocus) refocus.addEventListener("click", () => {
    if (handset()) setSnap("peek");
    else if (phone()) $("#map").scrollIntoView({ block: "start", behavior: smooth() });
    showResultOnMap(d);
  });
  const expand = card.querySelector("[data-expand]");
  if (expand) expand.addEventListener("click", () => {
    card.closest(".turn").classList.remove("past");
    showResultOnMap(d);
  });
  wireTrip(card, d);
  return card;
}


/* ------------------------------------------------------------ map: drawing */
const el = (name, attrs = {}, parent = null) => {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (parent) parent.appendChild(node);
  return node;
};
const path = (points) => points.map((p) => `${p[0]},${p[1]}`).join(" ");

function drawFloor(floor) {
  const canvas = $("#canvas");
  canvas.innerHTML = "";
  canvas.style.width = `${floor.width}px`;
  canvas.style.height = `${floor.height}px`;

  const svg = el("svg", {
    class: "plan", viewBox: `0 0 ${floor.width} ${floor.height}`,
    width: floor.width, height: floor.height,
    role: "img", "aria-label": `Floor ${floor.floor}, blocks ${floor.blocks.map((b) => b.id).join(", ")}`,
  }, canvas);

  const layer = (name) => el("g", { class: `lay-${name}` }, svg);
  const shell = layer("shell");
  const circulation = layer("circulation");
  const features = layer("features");
  const rooms = layer("rooms");
  const blocks = layer("blocks");
  const marks = layer("marks");
  const focus = layer("focus");

  // The envelope is drawn twice: once with a fat wall stroke, then again with
  // fill only, which hides the seams where the parts overlap and leaves one
  // continuous outline for the whole floor.
  const walls = el("g", { class: "walls" }, shell);
  const slab = el("g", { class: "slab" }, shell);
  floor.areas.forEach((a) => {
    el("polygon", { points: path(a.points) }, walls);
    el("polygon", { points: path(a.points) }, slab);
  });
  floor.volumes.forEach((v) => el("polygon", { class: "volume", points: path(v.points) }, shell));
  floor.spines.forEach((s) => el("rect", {
    class: "spine", x: s.x - floor.spine_half, y: s.y0,
    width: floor.spine_half * 2, height: s.y1 - s.y0, rx: 3,
  }, circulation));
  floor.circulation.forEach((c) => el("polygon", { class: "hall", points: path(c.points) }, circulation));

  floor.features.forEach((f) => {
    if (f.kind === "wifi") {
      for (let i = 3; i >= 1; i--) {
        el("circle", { class: "wifi", cx: f.cx, cy: f.cy, r: (f.r * i) / 3 }, features);
      }
      el("text", { class: "feature-label", x: f.cx, y: f.cy + 5 }, features).textContent = f.label;
    } else {
      const cx = f.points.reduce((a, p) => a + p[0], 0) / f.points.length;
      if (f.kind === "atrium" || f.kind === "foyer") {
        // its outline is already part of the envelope — only the name is drawn
        const top = Math.min(...f.points.map((p) => p[1]));
        if (f.label) el("text", { class: "feature-label", x: cx, y: top + 34 }, features).textContent = f.label;
      } else {
        const cy = f.points.reduce((a, p) => a + p[1], 0) / f.points.length;
        el("polygon", { class: `feature ${f.kind}`, points: path(f.points) }, features);
        el("text", { class: "feature-label", x: cx, y: cy + 4 }, features).textContent = f.label;
      }
    }
  });

  // rooms the plans draw but nobody has named: part of the building, not a destination
  (floor.fixtures || []).forEach((f) => el("polygon", { class: "fixture", points: path(f.points) }, rooms));

  const serviceLabels = [];
  floor.rooms.forEach((room) => {
    const g = el("g", {
      class: `room t-${(room.type || "none").toLowerCase()}${room.approx ? " approx" : ""}`,
      "data-code": room.code, tabindex: "0", role: "button",
      "aria-label": `Show directions to ${room.label}`,
    }, rooms);
    if (room.kind === "circle") el("circle", { cx: room.cx, cy: room.cy, r: room.r }, g);
    else el("polygon", { points: path(room.points) }, g);
    if (room.kind === "circle") {
      // a round lecture hall: its code, and the name the campus uses for it
      const cy = room.barrel ? room.cy - 4 : room.cy + 4.5;
      el("text", { x: room.cx, y: cy }, g).textContent = room.label;
      if (room.barrel) {
        el("text", { class: "barrel", x: room.cx, y: room.cy + 17 }, g).textContent = room.barrel;
      }
    } else {
      const label = el("text", { x: room.x, y: room.y + (room.sub ? -3 : 4.5) }, g);
      if (room.angle) label.setAttribute("transform", `rotate(${room.angle} ${room.x} ${room.y})`);
      label.textContent = room.label;
      if (room.service && !room.angle) {
        g.classList.add("has-svc");
        el("title", {}, g).textContent = `${room.label} — ${room.service}`;
        serviceLabels.push({ g, label, room });
      }
      if (room.sub) {
        // a second line for the floor note: "Red Canteen" / "3rd floor"
        const sub = el("text", { class: "sub", x: room.x, y: room.y + 14 }, g);
        if (room.angle) sub.setAttribute("transform", `rotate(${room.angle} ${room.x} ${room.y})`);
        sub.textContent = room.sub;
      }
    }
    const open = () => ask(room.ask || room.code);
    g.addEventListener("click", open);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

  floor.blocks.forEach((b) => {
    const g = el("g", { class: "block-tag" }, blocks);
    el("text", { class: "letter", x: b.tag_x, y: b.tag_y }, g).textContent = b.id;
    el("text", { class: "caption", x: b.tag_x, y: b.tag_y + 34 }, g).textContent =
      b.annex ? "annex — mirrors H" : `Block ${b.id}`;
  });

  // exits and stairs are drawn; amenities like the Wi-Fi zone are already part of the plan
  floor.landmarks.filter((lm) => lm.type !== "amenity").forEach((lm) => {
    const g = el("g", { class: `mark ${lm.type}` }, marks);
    el("rect", { x: lm.x - 13, y: lm.y - 13, width: 26, height: 26, rx: 3 }, g);
    el("use", { href: lm.type === "stairs" ? "#i-stairs" : "#i-exit", x: lm.x - 9, y: lm.y - 9, width: 18, height: 18 }, g);
    el("title", {}, g).textContent = lm.name;
  });


  // the office name goes under the room number only where it fits between the
  // walls; a narrow room keeps its tint and says it on hover instead
  serviceLabels.forEach(({ g, label, room }) => {
    const box = g.querySelector("polygon")?.getBBox();
    if (!box) return;
    const sub = el("text", { class: "svc-name", x: room.x, y: room.y + 13 }, g);
    sub.textContent = room.service;
    if (sub.getComputedTextLength() > box.width - 10 || box.height < 40) { sub.remove(); return; }
    label.setAttribute("y", room.y - 3);
  });

  state.svg = svg;
  state.focusLayer = focus;
}

/* ------------------------------------------------------------ map: answer */
function paintResult() {
  const layer = state.focusLayer;
  if (!layer) return;
  layer.innerHTML = "";
  $("#canvas").querySelectorAll(".room.is-target, .room.is-near").forEach((g) => {
    g.classList.remove("is-target", "is-near", "hl-passed", "hl-opposite", "hl-neighbour", "hl-start");
  });

  const routeHere = paintRoute(layer);
  const res = state.result;
  const map = res && res.map;
  if (!map || map.floor !== state.floor.floor) { $(".map").classList.toggle("focused", routeHere); return; }
  $(".map").classList.add("focused");

  (map.highlights || []).forEach((h) => {
    const g = $(`#canvas .room[data-code="${CSS.escape(h.room_number)}"]`);
    if (g) g.classList.add("is-near", `hl-${h.role}`);
  });

  // the landmark that says where a room is gives way to a route that walks there
  if (map.landmark && !routeHere) {
    const l = map.landmark;
    const g = el("g", { class: "landmark-call" }, layer);
    // start clear of the room's own label, so the dashes never strike through it
    const dx = l.x - map.x, dy = l.y - map.y, dist = Math.hypot(dx, dy) || 1;
    const lead = Math.min(30, dist / 2);
    el("line", { x1: map.x + (dx / dist) * lead, y1: map.y + (dy / dist) * lead, x2: l.x, y2: l.y }, g);
    el("circle", { cx: l.x, cy: l.y, r: 17 }, g);
  }

  const target = $(`#canvas .room[data-code="${CSS.escape(map.code || map.room_number)}"]`);
  if (target) target.classList.add("is-target");

  const pin = el("g", { class: "target" }, layer);
  const reach = Math.max(40, (map.radius || 0) + 14);
  // the flag stands above the room's outline, never over the label inside it
  const box = target?.getBBox();
  const flagY = Math.min(map.y - reach - 14, box ? box.y - 16 : Infinity);
  // a hall is big enough that the ping has to start outside it, or it sweeps
  // across the name printed in the middle
  el("circle", { class: map.radius ? "pulse wide" : "pulse", cx: map.x, cy: map.y, r: reach }, pin);
  const flag = el("g", { class: "flag", transform: `translate(${map.x}, ${flagY})` }, pin);
  const label = map.room_number;
  const w = 26 + label.length * 12.5;
  el("polygon", { points: "-8,12 8,12 0,21" }, flag);
  el("rect", { class: "face", x: -w / 2, y: -22, width: w, height: 34, rx: 3 }, flag);
  el("rect", { class: "rule", x: -w / 2, y: 7, width: w, height: 5 }, flag);
  el("text", { x: 0, y: -6 }, flag).textContent = label;
}

/* The walk itself: one line down the corridors on each floor it crosses, from
   the wall of the room it starts in to the wall of the room it ends in, with
   chevrons pointing the way you walk and a tag at each staircase saying which
   floor it leads to. */
function paintRoute(layer) {
  const r = state.route;
  if (!r || !state.floor) return false;
  const f = state.floor.floor;
  const legs = r.legs.filter((l) => l.floor === f);
  if (!legs.length) return false;
  // the line draws itself in when a route or a floor of it is first shown, not
  // every time the plan is repainted
  const fresh = state.routeDrawn !== r || state.routeFloor !== f;
  state.routeDrawn = r;
  state.routeFloor = f;
  const g = el("g", { class: `trip-path${fresh ? " fresh" : ""}` }, layer);
  const first = r.legs[0], last = r.legs[r.legs.length - 1];
  const lines = legs.map((l) => {
    let pts = l.points;
    // a room the walk starts or ends in is lit instead, so the line stops at its
    // wall, where the door is, and never crosses the room's name
    if (l === first && r.from.kind === "room") pts = fromWall(pts, r.from.code);
    // from an entrance, the line starts at the ring round its sign
    if (l === first && r.from.kind === "exit") pts = cutStart(pts, 21);
    if (l === last && r.to.kind === "room") pts = fromWall([...pts].reverse(), r.to.code).reverse();
    return { leg: l, pts };
  });
  lines.forEach(({ pts }) => {
    const d = roundedPath(pts, TRIP_CORNER);
    const casing = el("path", { class: "trip-case", d }, g);
    const line = el("path", { class: "trip-line", d }, g);
    const len = line.getTotalLength();
    [casing, line].forEach((p) => p.style.setProperty("--len", Math.ceil(len) + 2));
    chevrons(line, len, g);
  });
  r.stairs.filter((m) => m.floor === f).forEach((m) => {
    const [mx, my] = m.mark || [m.x, m.y];
    // the plan draws the stairwell a few steps past the end of the corridor
    if (Math.hypot(mx - m.x, my - m.y) > 14) el("line", { class: "trip-link", x1: m.x, y1: m.y, x2: mx, y2: my }, g);
    const text = m.arrive ? `From floor ${m.to}` : `${m.to > f ? "Up" : "Down"} to floor ${m.to}`;
    // the tag goes on the side away from the corridor the line comes down
    const near = lines.map(({ pts }) => pts).filter((p) => p.length > 1).map((p) =>
      same(p[0], [m.x, m.y]) ? p[1] : same(p[p.length - 1], [m.x, m.y]) ? p[p.length - 2] : null).find(Boolean);
    const w = 22 + text.length * 8.4;
    const tagX = near && near[0] > mx + 4 ? -18 - w : 18;
    const s = el("g", { class: "trip-stairs", transform: `translate(${mx}, ${my})` }, g);
    el("rect", { class: "tag", x: tagX, y: -15, width: w, height: 30, rx: 4 }, s);
    el("text", { x: tagX + w / 2, y: 1 }, s).textContent = text;
    el("rect", { class: "box", x: -13, y: -13, width: 26, height: 26, rx: 3 }, s);
    el("use", { href: "#i-stairs", x: -9, y: -9, width: 18, height: 18 }, s);
    el("title", {}, s).textContent = m.name;
  });
  const startLine = lines.find(({ leg }) => leg === first);
  if (startLine) {
    const [x, y] = r.from.kind === "exit" ? startLine.leg.points[0] : startLine.pts[0];
    const s = el("g", { class: "trip-start" }, g);
    // an entrance keeps its own sign, with a ring round it; a room's door gets a dot
    if (r.from.kind === "exit") el("circle", { class: "ring", cx: x, cy: y, r: 21 }, s);
    else {
      el("circle", { cx: x, cy: y, r: 11 }, s);
      el("circle", { class: "core", cx: x, cy: y, r: 4.5 }, s);
    }
    const room = r.from.code && $(`#canvas .room[data-code="${CSS.escape(r.from.code)}"]`);
    if (room) room.classList.add("is-near", "hl-start");
  }
  const endLine = lines.find(({ leg }) => leg === last);
  if (endLine && r.to.kind === "room" && endLine.pts.length > 1) {
    const [x, y] = endLine.pts[endLine.pts.length - 1];
    el("circle", { class: "trip-door", cx: x, cy: y, r: 6.5 }, g);
  }
  if (r.to.floor === f) {
    const room = $(`#canvas .room[data-code="${CSS.escape(r.to.code)}"]`);
    if (room) room.classList.add("is-target");
  }
  return true;
}

const same = (a, b) => Math.abs(a[0] - b[0]) < 0.5 && Math.abs(a[1] - b[1]) < 0.5;

function inRoom(room, [x, y]) {
  if (room.kind === "circle") return Math.hypot(x - room.cx, y - room.cy) < room.r;
  const p = room.points;
  let inside = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    if ((p[i][1] > y) !== (p[j][1] > y) && x < ((p[j][0] - p[i][0]) * (y - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]) {
      inside = !inside;
    }
  }
  return inside;
}

/** The walk out of a room, from the point where it crosses the room's wall. */
function fromWall(pts, code) {
  const room = state.floor.rooms.find((rm) => rm.code === code);
  if (!room || pts.length < 2 || !inRoom(room, pts[0])) return pts;
  let i = 0;
  while (i < pts.length - 1 && inRoom(room, pts[i + 1])) i++;
  // stairs that come up inside the room: nothing to draw across it
  if (i === pts.length - 1) return [pts[pts.length - 1]];
  let a = pts[i], b = pts[i + 1];
  for (let k = 0; k < 20; k++) {
    const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    if (inRoom(room, m)) a = m; else b = m;
  }
  return [b, ...pts.slice(i + 1)];
}

/** The polyline without its first `len` px. */
function cutStart(pts, len) {
  for (let i = 0; i < pts.length - 1; i++) {
    const [a, b] = [pts[i], pts[i + 1]];
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (d > len) return [[a[0] + ((b[0] - a[0]) * len) / d, a[1] + ((b[1] - a[1]) * len) / d], ...pts.slice(i + 1)];
    len -= d;
  }
  return pts;
}

/** A polyline as a path whose corners are rounded the way a walker turns. */
function roundedPath(pts, radius) {
  const xy = (p) => `${+p[0].toFixed(1)},${+p[1].toFixed(1)}`;
  let d = `M${xy(pts[0])}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i - 1], q = pts[i], n = pts[i + 1];
    const l1 = Math.hypot(q[0] - p[0], q[1] - p[1]), l2 = Math.hypot(n[0] - q[0], n[1] - q[1]);
    const k = Math.min(radius, l1 / 2, l2 / 2);
    if (k < 1) { d += ` L${xy(q)}`; continue; }
    const a = [q[0] + ((p[0] - q[0]) * k) / l1, q[1] + ((p[1] - q[1]) * k) / l1];
    const b = [q[0] + ((n[0] - q[0]) * k) / l2, q[1] + ((n[1] - q[1]) * k) / l2];
    d += ` L${xy(a)} Q${xy(q)} ${xy(b)}`;
  }
  return pts.length > 1 ? `${d} L${xy(pts[pts.length - 1])}` : d;
}

/** Small arrowheads along a line, spaced evenly, pointing the way you walk. */
function chevrons(line, len, g) {
  if (len < TRIP_CHEVRON * 1.2) return;
  const count = Math.floor(len / TRIP_CHEVRON);
  const gap = len / (count + 1);
  for (let i = 1; i <= count; i++) {
    const p = line.getPointAtLength(gap * i);
    const q = line.getPointAtLength(Math.min(len, gap * i + 2));
    const deg = (Math.atan2(q.y - p.y, q.x - p.x) * 180) / Math.PI;
    el("path", {
      class: "trip-chev", d: "M-2.8,-4 L1.6,0 L-2.8,4",
      transform: `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) rotate(${deg.toFixed(0)})`,
      style: `--at: ${(i / (count + 1)).toFixed(3)}`,
    }, g);
  }
}

function showResultOnMap(d) {
  const placed = ["room", "service", "block", "list"].includes(d.kind) && d.map;
  if (!placed) {
    // a new question always takes the last answer's room off the plan, even
    // when this answer has no room of its own to put there
    if (state.result || state.route) {
      state.result = null;
      state.route = null;
      paintResult();
      renderControls();
    }
    if (d.kind === "service") showStageMsg(`${d.title} isn't pinned to a room yet, so there's nothing to show on the plan.`);
    return;
  }
  state.result = d;
  if (d.directions) { showRoute(d.directions); return; }
  state.route = null;
  const changed = state.floor?.floor !== d.map.floor;
  openFloor(d.map.floor, { focus: { x: d.map.x, y: d.map.y }, fitFirst: changed });
}

/** Put a route on the plan, on the floor it starts on (or the one asked for),
    framed so the whole of that floor's part can be read. */
function showRoute(r, floorNo, card = null) {
  state.route = r;
  // the destination pinned on the plan is the one this route goes to
  if (card) state.result = card;
  // on a phone the sheet makes room, so the route can be seen above the steps
  if (handset() && $("#sheet").dataset.snap === "full") setSnap("half");
  const f = floorNo ?? r.floors[0];
  openFloor(f);
  requestAnimationFrame(() => fitRoute(f, true));
}

function fitRoute(f, animate) {
  const pts = (state.route?.legs || []).filter((l) => l.floor === f).flatMap((l) => l.points);
  if (!pts.length) return;
  // the staircase tags are part of the route: framed with it, not under the rail
  (state.route.stairs || []).filter((m) => m.floor === f).forEach((m) => {
    const [mx, my] = m.mark || [m.x, m.y];
    pts.push([mx - 150, my], [mx + 150, my]);
  });
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const r = stageRect();
  const pad = 70;
  const s = Math.min(r.width / (x1 - x0 + pad * 2), r.height / (y1 - y0 + pad * 2), ROUTE_MAX_ZOOM);
  focusOn((x0 + x1) / 2, (y0 + y1) / 2, s, animate);
}

// a route's floor chips say which of its floors the plan is showing
function markRouteFloor(trip) {
  const f = state.floor?.floor;
  trip.querySelectorAll("[data-route-floor]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.routeFloor) === f)));
}

/* ------------------------------------------------------------ map: controls */
function openFloor(number, { focus = null, fitFirst = true, clearResult = false } = {}) {
  const floor = state.floors.find((f) => f.floor === number) || state.floors[0];
  const changed = state.floor !== floor;
  const before = state.floor ? { ...state.view } : null;   // the zoom we leave the old floor at
  if (clearResult) state.result = null;
  state.floor = floor;
  if (changed) drawFloor(floor);
  renderControls();
  paintResult();
  hideStageMsg();

  if (focus) {
    if (fitFirst || changed) fitView(false);
    requestAnimationFrame(() => focusOn(focus.x, focus.y, ROOM_ZOOM, true));
  } else if (changed) {
    const r = stageRect();
    const zoomed = before && before.s > before.fit * 1.05;
    const spot = zoomed && { x: (r.width / 2 - before.tx) / before.s, y: (r.height / 2 - before.ty) / before.s };
    fitView(false);
    if (zoomed) focusOn(spot.x, spot.y, before.s, false);
    // zoomed out to the whole floor (or further): the next floor at the same scale
    else if (before) zoomTo(before.s, r.width / 2, r.height / 2, false);
    else overview(false);
  } else {
    updateDetail();
  }
}

function renderControls() {
  const floorSeg = $("#floor-seg");
  floorSeg.innerHTML = `<span class="lbl">Floor</span>` + state.floors.map((f) =>
    `<button type="button" data-floor="${f.floor}" aria-pressed="${state.floor?.floor === f.floor}" aria-label="Floor ${f.floor}">${f.floor}</button>`).join("");
  floorSeg.querySelectorAll("button").forEach((b) => b.addEventListener("click",
    () => openFloor(Number(b.dataset.floor), { clearResult: true })));

  // The block rail is the corridor drawn to scale: blocks in the order you walk
  // them, each as long as it runs along the plan. The answer's block carries
  // the destination stripe; the block at the centre of the view is filled.
  const blockSeg = $("#block-seg");
  const res = state.result;
  const here = res?.map?.floor === state.floor.floor ? (res.room?.building_id || res.block?.building_id) : null;
  const order = [...state.floor.blocks].sort((a, b) => a.y0 - b.y0);
  blockSeg.innerHTML = order.map((b) =>
    `<button type="button" data-block="${b.id}" title="${esc(b.name)}" aria-label="${esc(b.name)}"
      style="flex-grow:${Math.round(b.y1 - b.y0)}"${b.id === here ? ' class="here"' : ""}><span>${b.id}</span></button>`).join("");
  blockSeg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const block = state.floor.blocks.find((x) => x.id === b.dataset.block);
    focusOn(block.focus_x, (block.y0 + block.y1) / 2, BLOCK_ZOOM, true);
  }));
  state.inView = undefined;
  markInView();
  document.querySelectorAll(".trip").forEach(markRouteFloor);
}

/** Which block sits at the centre of the stage: filled on the rail, named in the bar. */
function markInView() {
  if (!state.floor) return;
  const r = stageRect();
  const v = state.view;
  let id = null;
  if (v.s > v.fit * 1.15) {
    const px = (r.width / 2 - v.tx) / v.s, py = (r.height / 2 - v.ty) / v.s;
    const hit = state.floor.blocks.filter((b) => py >= b.y0 && py <= b.y1)
      .sort((a, b) => Math.abs(px - a.focus_x) - Math.abs(px - b.focus_x));
    id = hit[0]?.id ?? null;
  }
  if (id === state.inView) return;
  state.inView = id;
  const seg = $("#block-seg");
  seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.block === id)));
  // on a phone the rail is a strip that scrolls: keep the block in view on it
  const current = id && seg.querySelector(`[data-block="${id}"]`);
  if (current && seg.scrollWidth > seg.clientWidth) {
    seg.scrollTo({ left: current.offsetLeft - (seg.clientWidth - current.offsetWidth) / 2, behavior: smooth() });
  }
  $("#map-where").innerHTML = `<b>Floor ${state.floor.floor}</b><span>${id ? `Block ${id}` : "Whole floor"}</span>`;
}

function showStageMsg(text) {
  const m = $("#stage-msg");
  m.innerHTML = `${icon("info")}<span>${esc(text)}</span>`;
  m.hidden = false;
  clearTimeout(showStageMsg.t);
  showStageMsg.t = setTimeout(hideStageMsg, 7000);
}
function hideStageMsg() { $("#stage-msg").hidden = true; }

/* ------------------------------------------------------------ map: pan & zoom */
// The plan can be dragged and zoomed, but never lost: at least this much of it
// (in screen pixels, or a third of the stage on a small screen) stays in view.
const KEEP_IN_VIEW = 140;
const MIN_ZOOM = 0.8;   // x "whole floor"
const MAX_ZOOM = 12;

function clampView() {
  if (!state.floor) return;
  const r = stageRect();
  const v = state.view;
  const w = state.floor.width * v.s, h = state.floor.height * v.s;
  const keepX = Math.min(KEEP_IN_VIEW, r.width / 3, w), keepY = Math.min(KEEP_IN_VIEW, r.height / 3, h);
  v.tx = Math.min(Math.max(v.tx, keepX - w), r.width - keepX);
  v.ty = Math.min(Math.max(v.ty, keepY - h), r.height - keepY);
}

function applyView(animate) {
  const c = $("#canvas");
  c.classList.toggle("animate", !!animate);
  clampView();
  const v = state.view;
  c.style.transform = `translate(${v.tx}px, ${v.ty}px) scale(${v.s})`;
  c.style.setProperty("--inv", (1 / v.s).toFixed(4));
  updateDetail();
}

function updateDetail() {
  $("#canvas").classList.toggle("far", state.view.s < LABEL_SCALE);
  markInView();
}

// The part of the stage you can see: on a phone the sheet lies over its bottom,
// so the plan centres, fits and clamps to what is left above it.
function stageRect() {
  const r = $("#stage").getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: Math.max(r.height - state.cover, 96) };
}

function fitView(animate) {
  if (!state.floor) return;
  const r = stageRect();
  const s = Math.min(r.width / state.floor.width, r.height / state.floor.height) * 0.96;
  state.view = { s, fit: s, tx: (r.width - state.floor.width * s) / 2, ty: (r.height - state.floor.height * s) / 2 };
  applyView(animate);
}

/** The opening view. A floor is a long corridor, so fitting all of it leaves a
    sliver; instead the plan opens at the width of the stage on the lobby end,
    where every route starts. The rail beside it keeps the whole corridor in view. */
function overview(animate) {
  if (!state.floor) return;
  fitView(false);
  const r = stageRect();
  const pts = state.floor.areas.flatMap((a) => a.points);
  const x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]));
  const y0 = Math.min(...pts.map((p) => p[1]));
  // never below the scale where room codes can be read; on a narrow stage
  // that means the corridor end of the lobby, not the whole width
  const across = (r.width * 0.92) / (x1 - x0);
  const s = Math.min(Math.max(across, LABEL_SCALE * 1.1), state.view.fit * 6);
  if (s <= state.view.fit * 1.15) return;   // the floor already fills the stage
  const spine = state.floor.blocks[0]?.x ?? (x0 + x1) / 2;
  const cx = s > across ? Math.min(Math.max(spine + 60, x0 + r.width / 2 / s), x1 - r.width / 2 / s) : (x0 + x1) / 2;
  state.view.s = s;
  state.view.tx = r.width / 2 - cx * s;
  state.view.ty = 28 - y0 * s;
  applyView(animate);
}

/** Centre the plan on a point at an absolute scale (never below "whole floor"). */
function focusOn(x, y, scale, animate) {
  const r = stageRect();
  const s = Math.max(scale, state.view.fit);
  state.view.s = s;
  state.view.tx = r.width / 2 - x * s;
  state.view.ty = r.height / 2 - y * s;
  applyView(animate);
}

/** Zoom to an absolute scale, keeping the plan point under (mx, my) where it is. */
function zoomTo(scale, mx, my, animate) {
  const v = state.view;
  const ns = Math.min(Math.max(scale, v.fit * MIN_ZOOM), v.fit * MAX_ZOOM);
  const px = (mx - v.tx) / v.s, py = (my - v.ty) / v.s;
  v.s = ns; v.tx = mx - px * ns; v.ty = my - py * ns;
  applyView(animate);
}

function zoomBy(k, cx, cy) {
  const r = stageRect();
  zoomTo(state.view.s * k, cx ?? r.width / 2, cy ?? r.height / 2, cx === undefined);
}

function setupPanZoom() {
  const stage = $("#stage");
  // one finger or the mouse drags; two fingers pinch to zoom around their midpoint
  const pointers = new Map();
  let drag = null, pinch = null;
  const local = (e) => { const r = stageRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const startDrag = (p) => { drag = { x: p.x, y: p.y, tx: state.view.tx, ty: state.view.ty }; };
  const startPinch = () => {
    const [a, b] = [...pointers.values()];
    pinch = { dist: Math.hypot(b.x - a.x, b.y - a.y) || 1, s: state.view.s,
              mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, tx: state.view.tx, ty: state.view.ty };
    drag = null;
  };

  // A press only becomes a drag once the pointer has moved: until then it is a
  // tap, so a room or a zoom button on the stage gets its click. The pointer is
  // captured from that moment on, and the click that ends a drag is swallowed.
  const DRAG_START = 4;
  let swallowClick = false;
  const capture = (id) => { try { stage.setPointerCapture(id); } catch { /* a pointer that is already gone */ } };

  stage.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button, a")) return;   // the zoom buttons are pressed, not dragged
    pointers.set(e.pointerId, local(e));
    if (pointers.size === 2) {
      pointers.forEach((_, id) => capture(id));
      stage.classList.add("dragging");
      startPinch();
    } else if (pointers.size === 1) startDrag(local(e));
  });
  stage.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, local(e));
    if (pinch && pointers.size >= 2) {
      const [a, b] = [...pointers.values()];
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      // move with the fingers' midpoint, then scale around it
      state.view.tx = pinch.tx + (mx - pinch.mx);
      state.view.ty = pinch.ty + (my - pinch.my);
      const factor = Math.hypot(b.x - a.x, b.y - a.y) / pinch.dist;
      const ratio = (pinch.s * factor) / state.view.s;
      zoomTo(state.view.s * ratio, mx, my, false);
      pinch.tx = state.view.tx; pinch.ty = state.view.ty; pinch.mx = mx; pinch.my = my;
      pinch.s = state.view.s; pinch.dist = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    } else if (drag) {
      const p = pointers.get(e.pointerId);
      if (!drag.moved) {
        if (Math.hypot(p.x - drag.x, p.y - drag.y) < DRAG_START) return;
        drag.moved = true;
        capture(e.pointerId);
        stage.classList.add("dragging");
      }
      state.view.tx = drag.tx + (p.x - drag.x);
      state.view.ty = drag.ty + (p.y - drag.y);
      applyView(false);
    }
  });
  const end = (e) => {
    if (!pointers.delete(e.pointerId)) return;
    if (pinch || drag?.moved) swallowClick = true;
    if (pointers.size === 1) {
      pinch = null;
      startDrag([...pointers.values()][0]);
      drag.moved = true;   // the finger left on the glass keeps dragging
    }
    if (pointers.size === 0) { drag = null; pinch = null; stage.classList.remove("dragging"); }
  };
  stage.addEventListener("click", (e) => {
    if (!swallowClick) return;
    swallowClick = false;
    e.stopPropagation();
    e.preventDefault();
  }, true);
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
  // a press that leaves the stage before it turned into a drag was never captured
  stage.addEventListener("pointerleave", (e) => { if (!stage.hasPointerCapture(e.pointerId)) end(e); });
  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = stageRect();
    zoomBy(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });

  $("#zoom-in").addEventListener("click", () => zoomBy(1.4));
  $("#zoom-out").addEventListener("click", () => zoomBy(1 / 1.4));
  $("#zoom-fit").addEventListener("click", () => fitView(true));

  let resizeT;
  new ResizeObserver(() => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      const map = state.result?.map;
      if (state.route?.floors.includes(state.floor?.floor)) { fitView(false); fitRoute(state.floor.floor, false); }
      else if (map && map.floor === state.floor?.floor) { fitView(false); focusOn(map.x, map.y, ROOM_ZOOM, false); }
      else if (state.view.s > state.view.fit * 1.05) overview(false);
      else fitView(false);
    }, 120);
  }).observe(stage);
}

/* ------------------------------------------------------------ phone: the sheet */
// On a phone the search and the answers are one sheet over the plan. It rests
// at three heights: "peek" shows the search alone, "half" shares the screen
// with the plan, "full" is for reading. Its head drags it; a tap on the handle
// steps it up, and from the top back to half.
const SNAPS = ["peek", "half", "full"];

function snapOffset(snap) {
  const sheet = $("#sheet");
  const h = sheet.offsetHeight;
  if (snap === "full") return 0;
  const head = $("#composer").offsetTop + $("#composer").offsetHeight;
  const peek = h - head - parseFloat(getComputedStyle(sheet).paddingBottom || 0);
  if (snap === "peek") return Math.max(0, peek);
  return Math.min(Math.max(0, h - Math.round(window.innerHeight * 0.5)), peek);
}

function setSnap(snap, animate = true) {
  if (!handset()) return;
  const sheet = $("#sheet");
  const prev = sheet.dataset.snap;
  sheet.dataset.snap = snap;
  sheet.classList.toggle("dragging", !animate);
  const off = snapOffset(snap);
  sheet.style.setProperty("--sheet-y", `${off}px`);
  // what the sheet will hide once it rests, so the plan can centre above it now
  const stage = $("#stage").getBoundingClientRect();
  const sheetTop = $(".app").getBoundingClientRect().bottom - sheet.offsetHeight + off;
  state.cover = Math.max(0, stage.bottom - sheetTop);
  $("#map").style.setProperty("--cover", `${state.cover}px`);
  const handle = $("#sheet-handle");
  handle.setAttribute("aria-label", snap === "full" ? "Show the plan" : "Show more of the answers");
  handle.setAttribute("aria-expanded", String(snap === "full"));
  if (!animate) requestAnimationFrame(() => sheet.classList.remove("dragging"));
  // the answer's room stays in sight above the sheet
  const map = state.result?.map;
  if (prev !== snap && snap !== "full" && map && map.floor === state.floor?.floor) {
    focusOn(map.x, map.y, Math.max(state.view.s, ROOM_ZOOM), animate);
  }
}

function setupSheet() {
  const sheet = $("#sheet");
  const handle = $("#sheet-handle");
  let drag = null;
  let swallowClick = false;

  const offsetNow = () => new DOMMatrixReadOnly(getComputedStyle(sheet).transform).m42;
  const begin = (e) => {
    if (!handset() || e.button > 0) return;
    swallowClick = false;
    // the field and the Find button keep their own taps
    if (e.target.closest("input, .btn-go")) return;
    drag = { id: e.pointerId, y0: e.clientY, off0: offsetNow(), moved: false, last: e.clientY, t: e.timeStamp, v: 0 };
  };
  const move = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dy = e.clientY - drag.y0;
    if (!drag.moved) {
      if (Math.abs(dy) < 6) return;
      drag.moved = true;
      sheet.classList.add("dragging");
      e.target.setPointerCapture?.(e.pointerId);
    }
    const max = snapOffset("peek");
    const off = Math.min(Math.max(drag.off0 + dy, 0), max);
    sheet.style.setProperty("--sheet-y", `${off}px`);
    const dt = e.timeStamp - drag.t;
    if (dt > 0) drag.v = (e.clientY - drag.last) / dt;
    drag.last = e.clientY; drag.t = e.timeStamp;
  };
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag;
    drag = null;
    sheet.classList.remove("dragging");
    if (!d.moved) return;
    swallowClick = true;
    // where the flick would carry the sheet, then the nearest resting height
    const landing = offsetNow() + d.v * 180;
    const best = SNAPS.map((sn) => [sn, Math.abs(snapOffset(sn) - landing)]).sort((a, b) => a[1] - b[1])[0][0];
    setSnap(best);
  };
  [handle, $("#composer")].forEach((el) => {
    el.addEventListener("pointerdown", begin);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  });
  handle.addEventListener("click", () => {
    if (swallowClick) { swallowClick = false; return; }
    const snap = sheet.dataset.snap;
    setSnap(snap === "peek" ? "half" : snap === "half" ? "full" : "half");
  });
  // typing wants room: the sheet rises with the field above the keyboard
  $("#q").addEventListener("focus", () => { if (handset()) setSnap("full"); });

  let resizeT;
  const settle = () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      if (handset()) setSnap(sheet.dataset.snap || "half", false);
      else { state.cover = 0; sheet.style.removeProperty("--sheet-y"); }
    }, 60);
  };
  window.addEventListener("resize", settle);
  setSnap(sheet.dataset.snap || "half", false);
}

/* ------------------------------------------------------------ boot */
async function boot() {
  renderExamples();
  setupSheet();
  setupPanZoom();
  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#q");
    const text = input.value;
    input.value = "";
    ask(text);
  });
  $("#signout").addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  });
  loadHeader();
  try {
    const data = await api("/api/map");
    state.floors = data.floors;
    openFloor(1);
    fillPlaces();
  } catch (err) {
    showStageMsg(`Couldn't load the floor plans (${err.message}).`);
  }
}

boot();
