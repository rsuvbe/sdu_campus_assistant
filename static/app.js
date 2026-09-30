"use strict";

const $ = (sel) => document.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const EXAMPLES = [
  "Where is D103?",
  "Где находится F207?",
  "Кабинет Д217",
  "Where can I get lunch?",
  "Is the library open?",
  "Room 204",
  "Hall A1",
];

// Room labels are part of the drawing, so they only make sense once the plan is
// large enough to read: below LABEL_SCALE the map shows block letters instead.
// The two zoom levels below are absolute (1 = one plan pixel per screen pixel),
// so an answer always lands at the same readable size whatever the floor size.
const LABEL_SCALE = 0.5;
const ROOM_ZOOM = 1.15;
const BLOCK_ZOOM = 0.72;

const state = {
  floors: [],
  context: null,        // what the last answer asked the user to pin down
  floor: null,          // the floor currently drawn
  result: null,         // last room/service answer that has a position
  view: { s: 1, fit: 1, tx: 0, ty: 0 },
};

/* ------------------------------------------------------------ API */
async function api(path, options) {
  const res = await fetch(path, options);
  if (res.status === 401) { window.location.replace("/login"); throw new Error("signed out"); }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/* ------------------------------------------------------------ header */
async function loadHeader() {
  try {
    const { user } = await api("/api/auth/me");
    const visitor = user.role === "visitor";
    $("#account").hidden = false;
    $("#account").classList.toggle("guest", visitor);
    $("#account-who").textContent = visitor ? "Visitor" : (user.full_name || user.student_id);
    $("#account-who").title = visitor ? "Looking around without an account" : user.email;
    $("#signout").textContent = visitor ? "Sign in" : "Sign out";
  } catch { /* the 401 above already redirected */ }

  try {
    const s = await api("/api/stats");
    $("#stats-line").textContent =
      `${s.rooms} rooms across blocks C to I on 3 floors. Ask for one and it lights up on the plan.`;
  } catch { /* keep default copy */ }

  try {
    const services = await api("/api/services");
    const ul = $("#services");
    ul.innerHTML = "";
    services.forEach((svc) => {
      const li = document.createElement("li");
      const cls = svc.open_now === true ? "open" : svc.open_now === false ? "closed" : "";
      li.innerHTML = `<button type="button"><i class="dot ${cls}"></i><b>${esc(svc.name)}</b><span>${esc(shortStatus(svc))}</span></button>`;
      li.querySelector("button").addEventListener("click", () => ask(svc.name));
      ul.appendChild(li);
    });
  } catch { /* services strip is optional */ }
}

function shortStatus(svc) {
  if (svc.open_now === true) return svc.status.replace("Open until", "open until");
  if (svc.open_now === false) return "closed now";
  return "hours coming soon";
}

/* ------------------------------------------------------------ conversation */
function renderExamples() {
  const box = $("#examples");
  EXAMPLES.forEach((text) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = text;
    b.addEventListener("click", () => ask(text));
    box.appendChild(b);
  });
}

async function ask(text) {
  const query = text.trim();
  if (!query) return;
  const thread = $("#thread");

  const q = document.createElement("div");
  q.className = "q";
  q.textContent = query;
  thread.appendChild(q);

  let data;
  try {
    const carried = state.context ? `&context=${encodeURIComponent(state.context)}` : "";
    data = await api(`/api/search?q=${encodeURIComponent(query)}${carried}`);
  } catch (err) {
    data = { kind: "error", title: "Couldn't reach the server", summary: `The request failed (${err.message}). Check that the API is running, then try again.`, suggestions: [] };
  }

  state.context = data.context ?? null;
  const card = renderCard(data);
  thread.appendChild(card);
  card.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  showResultOnMap(data);
}

function suggestionChips(list) {
  if (!list || !list.length) return "";
  return `<div class="sugg">${list.map((s) => `<button type="button" class="chip code" data-ask="${esc(s)}">${esc(s)}</button>`).join("")}</div>`;
}

function stepsList(steps) {
  if (!steps || !steps.length) return "";
  return `<ol class="steps">${steps.map((s) => `<li class="${s.startsWith("Landmark:") ? "landmark" : ""}">${esc(s)}</li>`).join("")}</ol>`;
}

function hoursLine(hours) {
  if (!hours || !hours.length) return "";
  const same = hours.every((h) => h.open === hours[0].open && h.close === hours[0].close);
  if (same && hours.length === 5 && hours[0].day === "Monday" && hours[4].day === "Friday") {
    return `<p class="hours">Monday to Friday, ${esc(hours[0].open)} to ${esc(hours[0].close)}. Closed at weekends.</p>`;
  }
  return `<p class="hours">${hours.map((h) => `${esc(h.day)} ${esc(h.open)} to ${esc(h.close)}`).join("<br>")}</p>`;
}

function renderCard(d) {
  const card = document.createElement("article");
  const foot = (withMapLink) => `<div class="card-foot"><span>Answered in ${d.elapsed_ms ?? "–"} ms</span>${withMapLink ? `<button type="button" class="linkish" data-refocus>Show on plan</button>` : ""}</div>`;

  if (d.kind === "room") {
    const r = d.room;
    card.className = "card";
    card.innerHTML = `
      <div class="card-head">
        <div class="plate">${esc(r.room_number)}</div>
        <div class="head-text">
          <div class="head-title">Floor ${esc(r.floor_number)}, Block ${esc(r.building_id)}</div>
          <div class="head-sub">${esc(r.building_name.replace(/^Block \w+ — /, ""))}${r.facts.length ? `<br>${esc(r.facts.join(", "))}` : ""}</div>
        </div>
      </div>
      ${stepsList(d.steps)}
      ${d.note ? `<p class="note">${esc(d.note)}</p>` : ""}
      ${foot(!!d.map)}`;
  } else if (d.kind === "block") {
    const b = d.block;
    card.className = "card";
    card.innerHTML = `
      <div class="card-head">
        <div class="plate">${esc(b.building_id)}</div>
        <div class="head-text">
          <div class="head-title">${esc(b.name.replace(/^Block \w+ — /, ""))}</div>
          <div class="head-sub">${b.rooms} rooms on floor${b.floors.length > 1 ? "s" : ""} ${esc(b.floors.join(", "))}</div>
        </div>
      </div>
      ${stepsList(d.steps)}
      <p class="summary">Rooms in this block:</p>
      ${suggestionChips(d.suggestions)}
      ${foot(!!d.map)}`;
  } else if (d.kind === "service") {
    const s = d.service;
    const cls = s.open_now === true ? "open" : s.open_now === false ? "closed" : "";
    card.className = "card";
    card.innerHTML = `
      <div class="card-head">
        <div class="plate svc">${esc(d.title)}</div>
        <div class="head-text"><span class="status ${cls}"><i class="dot ${cls}"></i>${esc(s.status)}</span></div>
      </div>
      ${hoursLine(s.hours)}
      ${d.map ? stepsList(d.steps) : `<p class="summary">Its exact room isn't on the digitised plans yet, so there's no route to show.</p>`}
      ${d.note ? `<p class="note">${esc(d.note)}</p>` : ""}
      ${foot(!!d.map)}`;
  } else {
    card.className = "card miss";
    const plate = d.kind === "error" ? "×" : "?";
    card.innerHTML = `
      <div class="card-head">
        <div class="plate">${plate}</div>
        <div class="head-text"><div class="head-title">${esc(d.title)}</div></div>
      </div>
      <p class="summary">${esc(d.summary)}</p>
      ${suggestionChips(d.suggestions)}
      ${foot(false)}`;
  }

  card.querySelectorAll("[data-ask]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.ask)));
  const refocus = card.querySelector("[data-refocus]");
  if (refocus) refocus.addEventListener("click", () => showResultOnMap(d));
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
      if (f.kind === "atrium") {
        // its outline is already part of the envelope — only the name is drawn
        const top = Math.min(...f.points.map((p) => p[1]));
        el("text", { class: "feature-label", x: cx, y: top + 34 }, features).textContent = f.label;
      } else {
        const cy = f.points.reduce((a, p) => a + p[1], 0) / f.points.length;
        el("polygon", { class: `feature ${f.kind}`, points: path(f.points) }, features);
        el("text", { class: "feature-label", x: cx, y: cy + 4 }, features).textContent = f.label;
      }
    }
  });

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
      const label = el("text", { x: room.x, y: room.y + 4.5 }, g);
      if (room.angle) label.setAttribute("transform", `rotate(${room.angle} ${room.x} ${room.y})`);
      label.textContent = room.label;
    }
    const open = () => ask(room.label === "Medcenter" ? "Medcenter" : room.code);
    g.addEventListener("click", open);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

  floor.blocks.forEach((b) => {
    const g = el("g", { class: "block-tag" }, blocks);
    el("text", { class: "letter", x: b.tag_x, y: (b.y0 + b.y1) / 2 }, g).textContent = b.id;
    el("text", { class: "caption", x: b.tag_x, y: (b.y0 + b.y1) / 2 + 34 }, g).textContent =
      b.annex ? "annex — mirrors H" : `Block ${b.id}`;
  });

  floor.landmarks.forEach((lm) => {
    const g = el("g", { class: `mark ${lm.type}` }, marks);
    el("rect", { x: lm.x - 11, y: lm.y - 11, width: 22, height: 22, rx: 5 }, g);
    el("text", { x: lm.x, y: lm.y + 5 }, g).textContent =
      lm.type === "exit" ? "↦" : lm.type === "stairs" ? "⇅" : "•";
    el("title", {}, g).textContent = lm.name;
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
    g.classList.remove("is-target", "is-near", "hl-passed", "hl-opposite", "hl-neighbour");
  });

  const res = state.result;
  const map = res && res.map;
  if (!map || map.floor !== state.floor.floor) { $(".map").classList.remove("focused"); return; }
  $(".map").classList.add("focused");

  (map.highlights || []).forEach((h) => {
    const g = $(`#canvas .room[data-code="${CSS.escape(h.room_number)}"]`);
    if (g) g.classList.add("is-near", `hl-${h.role}`);
  });

  if (map.landmark) {
    const l = map.landmark;
    const g = el("g", { class: "landmark-call" }, layer);
    el("line", { x1: map.x, y1: map.y, x2: l.x, y2: l.y }, g);
    el("circle", { cx: l.x, cy: l.y, r: 17 }, g);
  }

  const target = $(`#canvas .room[data-code="${CSS.escape(map.room_number)}"]`);
  if (target) target.classList.add("is-target");

  const pin = el("g", { class: "target" }, layer);
  const reach = Math.max(40, (map.radius || 0) + 14);
  // a hall is big enough that the ping has to start outside it, or it sweeps
  // across the name printed in the middle
  el("circle", { class: map.radius ? "pulse wide" : "pulse", cx: map.x, cy: map.y, r: reach }, pin);
  const flag = el("g", { class: "flag", transform: `translate(${map.x}, ${map.y - reach - 14})` }, pin);
  const label = map.room_number;
  const w = 20 + label.length * 12;
  el("rect", { x: -w / 2, y: -20, width: w, height: 30, rx: 6 }, flag);
  el("polygon", { points: "-7,10 7,10 0,19" }, flag);
  el("text", { x: 0, y: 1 }, flag).textContent = label;
}

function showResultOnMap(d) {
  if (!["room", "service", "block"].includes(d.kind)) return;
  if (!d.map) {
    if (d.kind === "service") showStageMsg(`${d.title} isn't pinned to a room yet, so there's nothing to show on the plan.`);
    return;
  }
  state.result = d;
  const changed = state.floor?.floor !== d.map.floor;
  openFloor(d.map.floor, { focus: { x: d.map.x, y: d.map.y }, fitFirst: changed });
}

/* ------------------------------------------------------------ map: controls */
function openFloor(number, { focus = null, fitFirst = true, clearResult = false } = {}) {
  const floor = state.floors.find((f) => f.floor === number) || state.floors[0];
  const changed = state.floor !== floor;
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
    fitView(false);
  } else {
    updateDetail();
  }
}

function renderControls() {
  const floorSeg = $("#floor-seg");
  floorSeg.innerHTML = `<span class="lbl">Floor</span>` + state.floors.map((f) =>
    `<button type="button" data-floor="${f.floor}" aria-pressed="${state.floor?.floor === f.floor}">${f.floor}</button>`).join("");
  floorSeg.querySelectorAll("button").forEach((b) => b.addEventListener("click",
    () => openFloor(Number(b.dataset.floor), { clearResult: true })));

  const blockSeg = $("#block-seg");
  blockSeg.innerHTML = `<span class="lbl">Block</span>` + state.floor.blocks.map((b) =>
    `<button type="button" data-block="${b.id}" title="${esc(b.name)}">${b.id}</button>`).join("");
  blockSeg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const block = state.floor.blocks.find((x) => x.id === b.dataset.block);
    focusOn(block.x + 250, (block.y0 + block.y1) / 2, BLOCK_ZOOM, true);
  }));
}

function showStageMsg(text) {
  const m = $("#stage-msg");
  m.textContent = text;
  m.hidden = false;
  clearTimeout(showStageMsg.t);
  showStageMsg.t = setTimeout(hideStageMsg, 7000);
}
function hideStageMsg() { $("#stage-msg").hidden = true; }

/* ------------------------------------------------------------ map: pan & zoom */
function applyView(animate) {
  const c = $("#canvas");
  c.classList.toggle("animate", !!animate);
  const v = state.view;
  c.style.transform = `translate(${v.tx}px, ${v.ty}px) scale(${v.s})`;
  c.style.setProperty("--inv", (1 / v.s).toFixed(4));
  updateDetail();
}

function updateDetail() {
  $("#canvas").classList.toggle("far", state.view.s < LABEL_SCALE);
}

function stageRect() { return $("#stage").getBoundingClientRect(); }

function fitView(animate) {
  if (!state.floor) return;
  const r = stageRect();
  const s = Math.min(r.width / state.floor.width, r.height / state.floor.height) * 0.96;
  state.view = { s, fit: s, tx: (r.width - state.floor.width * s) / 2, ty: (r.height - state.floor.height * s) / 2 };
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

function zoomBy(k, cx, cy) {
  const r = stageRect();
  const mx = cx ?? r.width / 2, my = cy ?? r.height / 2;
  const v = state.view;
  const ns = Math.min(Math.max(v.s * k, v.fit * 0.8), v.fit * 12);
  const px = (mx - v.tx) / v.s, py = (my - v.ty) / v.s;
  v.s = ns; v.tx = mx - px * ns; v.ty = my - py * ns;
  applyView(cx === undefined);
}

function setupPanZoom() {
  const stage = $("#stage");
  let drag = null;
  stage.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, tx: state.view.tx, ty: state.view.ty };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("dragging");
  });
  stage.addEventListener("pointermove", (e) => {
    if (!drag) return;
    state.view.tx = drag.tx + (e.clientX - drag.x);
    state.view.ty = drag.ty + (e.clientY - drag.y);
    applyView(false);
  });
  const end = () => { drag = null; stage.classList.remove("dragging"); };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
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
      if (map && map.floor === state.floor?.floor) { fitView(false); focusOn(map.x, map.y, ROOM_ZOOM, false); }
      else fitView(false);
    }, 120);
  }).observe(stage);
}

/* ------------------------------------------------------------ boot */
async function boot() {
  renderExamples();
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
  } catch (err) {
    showStageMsg(`Couldn't load the floor plans (${err.message}).`);
  }
}

boot();
