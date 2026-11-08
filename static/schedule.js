"use strict";

/* Your timetable (US17, US18): the week as the student portal draws it, days
   across and hours down; adding, editing and deleting a class; reading a
   screenshot of the portal's Course Schedule into classes; and the reminders.
   The server checks everything again (app/main.py). */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const R = window.SDUReminders;
const SHORT = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const FIRST = 8 * 60 + 30;     // the portal's day: 08:30 ...
const LAST = 22 * 60 + 20;     // ... to 22:20
const hhmm = (n) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

let classes = [];
let editing = null;            // the class the form changes, or null when it adds one
let shown = null;              // the class on the card

/* ---------------------------------------------------------------- loading */
async function boot() {
  const res = await fetch("/api/auth/me");
  if (res.status === 401) { location.replace("/login?next=%2Fschedule"); return; }
  const { user } = await res.json();
  if (user.role === "visitor") { $("#visitor").hidden = false; return; }
  $("#member").hidden = false;
  setupReminders();
  await loadWeek();
  if (location.hash === "#import") openImport();
}

async function loadWeek() {
  try {
    const [week, rooms] = await Promise.all([fetch("/api/schedule"), fetch("/api/rooms")]);
    if (week.status === 401) { location.replace("/login?next=%2Fschedule"); return; }
    classes = (await week.json()).classes;
    $("#tt-rooms").innerHTML = (await rooms.json())
      .map((r) => `<option value="${esc(r.value)}" label="${esc(r.label)}"></option>`).join("");
    changed();
  } catch (err) {
    $("#sch-grid").innerHTML = `<p class="tt-empty">Couldn't load your timetable (${esc(err.message)}). Reload the page to try again.</p>`;
  }
}

// after any change: the grid, the next class, the reminders
function changed() {
  classes.sort((a, b) => a.day - b.day || a.start.localeCompare(b.start));
  renderGrid();
  renderNext();
  R.setClasses(classes);
  const n = classes.length;
  $("#sch-count").textContent = n ? `${n} class${n === 1 ? "" : "es"} a week · only you can see it`
    : "Only you can see it.";
}

/* ------------------------------------------------------------ the grid */
function parts(subject) {
  // "INF 304 [04-P]" -> the course and its group, as the portal prints them
  const m = /^(.*?)\s*\[([^\]]+)\]\s*$/.exec(subject);
  return m ? { name: m[1], group: m[2] } : { name: subject, group: "" };
}

function renderGrid() {
  const days = classes.some((c) => c.day === 6) ? 7 : 6;
  const starts = classes.map((c) => R.minutes(c.start));
  const ends = classes.map((c) => R.minutes(c.end));
  // whole portal hours, stretched to fit a class before 08:30 or after 22:20
  const first = Math.min(FIRST, ...starts.map((m) => FIRST - Math.ceil((FIRST - m) / 60) * 60));
  const slots = Math.ceil((Math.max(LAST, ...ends) - first) / 60);
  const today = R.campus().day;
  const next = R.nextClass(classes).next;

  let html = `<div class="sch-corner">Day/<br>Hour</div>`;
  for (let d = 0; d < days; d++) {
    html += `<div class="sch-dayhead${d === today ? " today" : ""}"><b>${SHORT[d]}</b><span>${d === today ? "Today" : R.DAY_NAMES[d]}</span></div>`;
  }
  html += `<div class="sch-hours">${Array.from({ length: slots }, (_, i) =>
    `<div class="sch-hour"><b>${hhmm(first + i * 60)}</b><span>${hhmm(first + i * 60 + 50)}</span></div>`).join("")}</div>`;
  for (let d = 0; d < days; d++) {
    const mine = classes.filter((c) => c.day === d);
    html += `<div class="sch-col${d === today ? " today" : ""}" data-day="${d}">`;
    for (let i = 0; i < slots; i++) {
      const at = hhmm(first + i * 60);
      html += `<button type="button" class="sch-slot" data-day="${d}" data-at="${at}" aria-label="Add a class on ${R.DAY_NAMES[d]} at ${at}"></button>`;
    }
    for (const { c, lane, lanes } of placed(mine)) {
      const top = (R.minutes(c.start) - first) / 60;
      const len = (R.minutes(c.end) - R.minutes(c.start)) / 60;
      const { name, group } = parts(c.subject);
      // an hour or less: the row already says when, so the room keeps the space
      const short = len <= 1 ? " short" : "";
      html += `<button type="button" class="sch-class${short}${c.on_campus === false ? " away" : ""}${next && next.class_id === c.class_id ? " next" : ""}"
        data-id="${c.class_id}"
        style="--top:${top};--len:${len};--lane:${lane};--lanes:${lanes}"
        aria-label="${esc(c.subject)}, ${esc(c.day_name)} ${esc(c.start)} to ${esc(c.end)}, ${esc(c.room_label)}">
        <span class="sch-code">${esc(name)}${group ? ` <i>[${esc(group)}]</i>` : ""}</span>
        <span class="sch-room"><svg class="i" aria-hidden="true"><use href="#i-pin"/></svg>${esc(c.room_label)}</span>
        <span class="sch-span">${esc(c.start)}–${esc(c.end)}</span>
      </button>`;
    }
    html += `</div>`;
  }
  const grid = $("#sch-grid");
  grid.style.setProperty("--days", days);
  grid.style.setProperty("--slots", slots);
  grid.dataset.first = first;
  grid.innerHTML = html;
  grid.querySelectorAll(".sch-slot").forEach((b) => b.addEventListener("click", () =>
    openForm(null, { day: +b.dataset.day, start: b.dataset.at })));
  grid.querySelectorAll(".sch-class").forEach((b) => b.addEventListener("click", () => openCard(+b.dataset.id)));
  $("#sch-hint").textContent = classes.length
    ? "Tap a class for the way to it, or an empty hour to add one there."
    : "Your week is empty. Import a screenshot of the portal's Course Schedule, or tap an hour to add a class.";
  drawNow();
  scrollToToday();
}

/* Classes that overlap share their column side by side. */
function placed(list) {
  const out = [];
  let group = [], end = -1;
  const flush = () => {
    const lanes = [];
    for (const c of group) {
      let lane = lanes.findIndex((e) => e <= R.minutes(c.start));
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = R.minutes(c.end);
      out.push({ c, lane, lanes: 0 });
    }
    out.slice(-group.length).forEach((p) => { p.lanes = lanes.length; });
    group = [];
  };
  for (const c of list) {
    if (group.length && R.minutes(c.start) >= end) flush();
    group.push(c);
    end = Math.max(end, R.minutes(c.end));
  }
  if (group.length) flush();
  return out;
}

// the line across today at this minute
function drawNow() {
  document.querySelector(".sch-now")?.remove();
  const col = document.querySelector(".sch-col.today");
  if (!col) return;
  const first = +$("#sch-grid").dataset.first;
  const at = (R.campus().minute - first) / 60;
  const slots = +$("#sch-grid").style.getPropertyValue("--slots");
  if (at < 0 || at > slots) return;
  const line = document.createElement("div");
  line.className = "sch-now";
  line.style.setProperty("--top", at);
  line.setAttribute("aria-hidden", "true");
  col.append(line);
}

let scrolled = false;
function scrollToToday() {
  if (scrolled) return;
  scrolled = true;
  const box = $("#sch-scroll");
  const col = document.querySelector(".sch-col.today");
  if (col && box.scrollWidth > box.clientWidth) box.scrollLeft = Math.max(0, col.offsetLeft - 64 - 8);
}

/* ----------------------------------------------------------- next class */
function renderNext() {
  const box = $("#sch-next");
  const { onNow, next, at } = R.nextClass(classes);
  if (!next) { box.hidden = true; return; }
  const when = R.whenSaid(at);
  const away = next.on_campus === false;
  box.innerHTML = `
    <div class="sch-next-text">
      <p class="field-label">Your next class${onNow ? ` · on now: ${esc(onNow.subject)} until ${esc(onNow.end)}` : ""}</p>
      <p class="sch-next-title">${esc(next.subject)}</p>
      <p class="sch-next-when">${esc(when[0].toUpperCase() + when.slice(1))}, ${esc(next.start)}–${esc(next.end)} · <b>${esc(next.room_label)}</b> · ${esc(next.where)}</p>
    </div>
    ${away ? "" : `<a class="btn-go" href="${R.NEXT_ROUTE}">How do I get there<svg class="i" aria-hidden="true"><use href="#i-right"/></svg></a>`}`;
  box.hidden = false;
}

// once a minute: the line moves, and a class that has begun hands "next" on
setInterval(() => { drawNow(); renderNext(); }, 60e3);

/* ----------------------------------------------------------- dialogs */
function openDialog(d) {
  if (!d.open) d.showModal();
}
document.querySelectorAll("dialog").forEach((d) => {
  d.addEventListener("click", (e) => {
    // a press on the backdrop, or on a close button
    if (e.target === d || e.target.closest("[data-close]")) d.close();
  });
});

function openCard(id) {
  shown = classes.find((c) => c.class_id === id);
  if (!shown) return;
  const c = shown;
  $("#cc-day").textContent = c.day_name;
  $("#cc-title").textContent = c.subject;
  $("#cc-time").textContent = `${c.start}–${c.end}`;
  $("#cc-room").textContent = c.room_label;
  $("#cc-where").textContent = c.where;
  const route = $("#cc-route");
  route.hidden = c.on_campus === false;
  route.href = R.routeTo(c);
  const del = $("#cc-delete");
  del.textContent = "Delete";
  delete del.dataset.sure;
  openDialog($("#class-card"));
}

$("#cc-edit").addEventListener("click", () => {
  $("#class-card").close();
  openForm(shown);
});

$("#cc-delete").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  if (!button.dataset.sure) {             // a second press deletes
    button.dataset.sure = "1";
    button.textContent = "Press again to delete";
    return;
  }
  try {
    const res = await fetch(`/api/schedule/${shown.class_id}`, { method: "DELETE" });
    if (res.status === 401) { location.replace("/login?next=%2Fschedule"); return; }
    if (!res.ok && res.status !== 404) throw new Error(res.statusText);
    classes = classes.filter((c) => c.class_id !== shown.class_id);
    $("#class-card").close();
    changed();
  } catch (err) {
    button.textContent = `Couldn't delete (${err.message})`;
  }
});

/* ------------------------------------------------------- add or edit */
function openForm(entry, preset = {}) {
  editing = entry ? entry.class_id : null;
  ttClear();
  $("#tt-form-title").textContent = entry ? "Edit the class" : "Add a class";
  $("#tt-submit").textContent = entry ? "Save changes" : "Add class";
  $("#tt-subject").value = entry ? entry.subject : "";
  $("#tt-day").value = entry ? entry.day : (preset.day ?? R.campus().day % 7);
  $("#tt-start").value = entry ? entry.start : (preset.start || "");
  $("#tt-end").value = entry ? entry.end : (preset.start ? hhmm(R.minutes(preset.start) + 50) : "");
  $("#tt-room").value = entry ? entry.room_value : "";
  openDialog($("#class-form"));
  $("#tt-subject").focus();
}

function ttClear() {
  $("#tt-error").hidden = true;
  document.querySelectorAll(".tt-form .field").forEach((f) => f.classList.remove("bad"));
}

function ttError(message, field) {
  const box = $("#tt-error");
  box.textContent = message;
  box.hidden = false;
  const wrap = field && $(`#tt-field-${field}`);
  if (wrap) { wrap.classList.add("bad"); wrap.querySelector("input, select").focus(); }
}

async function saveClass(event) {
  event.preventDefault();
  ttClear();
  const body = { subject: $("#tt-subject").value.trim(), day: Number($("#tt-day").value),
                 start: $("#tt-start").value, end: $("#tt-end").value, room: $("#tt-room").value.trim() };
  if (!body.subject) return ttError("Enter the subject.", "subject");
  if (!body.start) return ttError("Enter when the class starts.", "start");
  if (!body.end) return ttError("Enter when the class ends.", "end");
  if (body.end <= body.start) return ttError("A class has to end after it starts.", "end");
  if (!body.room) return ttError("Choose the room.", "room");

  const button = $("#tt-submit");
  button.disabled = true;
  try {
    const res = await fetch(editing ? `/api/schedule/${editing}` : "/api/schedule", {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      classes = classes.filter((c) => c.class_id !== data.class_id).concat(data);
      $("#class-form").close();
      changed();
    } else if (res.status === 401) {
      location.replace("/login?next=%2Fschedule");
    } else {
      const d = data.detail;
      if (d && typeof d === "object") ttError(d.message, d.field);
      else ttError(typeof d === "string" ? d : "Something went wrong. Try again.");
    }
  } catch (err) {
    ttError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
}

$("#tt-form").addEventListener("submit", saveClass);
$("#open-add").addEventListener("click", () => openForm(null));

/* --------------------------------------------------------- reminders */
function setupReminders() {
  const lead = $("#rm-lead");
  const toggle = $("#rm-toggle");
  const s = R.settings();
  lead.value = String(s.lead);
  const paint = () => {
    const { on, lead: mins } = R.settings();
    toggle.setAttribute("aria-pressed", String(on));
    toggle.querySelector("span").textContent = on ? "Turn off reminders" : "Turn on reminders";
    $("#rm-ics").href = `/api/schedule.ics?lead=${mins}`;
    const perm = "Notification" in window ? Notification.permission : "unsupported";
    $("#rm-state").textContent = !on ? "Reminders are off."
      : perm === "granted" ? `On: a notification and a note on the page ${mins} minutes before each class.`
      : perm === "denied" ? `On, as a note on the page ${mins} minutes before each class. Notifications are blocked for this site in your browser's settings.`
      : perm === "unsupported" ? `On, as a note on the page ${mins} minutes before each class. This browser can't show notifications; add the calendar file for those.`
      : `On, as a note on the page ${mins} minutes before each class.`;
  };
  lead.addEventListener("change", () => { R.save({ lead: Number(lead.value) }); paint(); });
  toggle.addEventListener("click", async () => {
    const on = !R.settings().on;
    if (on) await R.askPermission();
    R.save({ on });
    paint();
  });
  paint();
}

/* ------------------------------------------------- import a screenshot */
const TESSERACT = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
let reviewRows = [];
let shotUrl = null;

function openImport() {
  importStep("pick");
  $("#im-file").value = "";
  openDialog($("#import"));
}
$("#open-import").addEventListener("click", openImport);
$("#im-again").addEventListener("click", () => { importStep("pick"); $("#im-file").value = ""; });

function importStep(step) {
  $("#im-pick").hidden = step !== "pick";
  $("#im-work").hidden = step !== "work";
  $("#im-review").hidden = step !== "review";
}

function progress(fraction, text) {
  $("#im-bar").style.width = `${Math.round(fraction * 100)}%`;
  if (text) $("#im-status").textContent = text;
}

$("#im-file").addEventListener("change", (e) => { if (e.target.files[0]) readShot(e.target.files[0]); });
const drop = $("#im-drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
  if (file) readShot(file);
});
document.addEventListener("paste", (e) => {
  if (!$("#import").open || $("#im-pick").hidden) return;
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item) { e.preventDefault(); readShot(item.getAsFile()); }
});

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (window.Tesseract) { resolve(); return; }
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("couldn't load the text reader"));
    document.head.append(s);
  });
}

function imageOf(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("that file isn't a picture this browser can open"));
    img.src = URL.createObjectURL(file);
  });
}

async function readShot(file) {
  importStep("work");
  progress(0.02, "Opening the picture…");
  let worker = null;
  try {
    const img = await imageOf(file);
    if (shotUrl) URL.revokeObjectURL(shotUrl);
    shotUrl = img.src;
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);

    const grid = ScheduleOCR.findGrid(pixels);
    if (!grid) throw new Error("no timetable table found in it. Take the screenshot of the portal's Course Schedule, with the whole table in view");

    // small text reads better larger: about 2400 pixels across, by a whole
    // factor, which keeps every letter's strokes the same width
    const scale = Math.max(1, Math.min(3, Math.round(2400 / canvas.width)));
    const ready = ScheduleOCR.prepare(pixels, scale);
    const big = document.createElement("canvas");
    big.width = ready.width;
    big.height = ready.height;
    big.getContext("2d").putImageData(new ImageData(ready.data, ready.width, ready.height), 0, 0);

    progress(0.08, "Loading the text reader (once, about 4 MB)…");
    await loadScript(TESSERACT);
    worker = await Tesseract.createWorker("eng", 1, {
      logger: (m) => {
        if (m.status === "recognizing text") progress(0.25 + m.progress * 0.65, `Reading the timetable… ${Math.round(m.progress * 100)}%`);
        else if (/load/.test(m.status)) progress(0.08 + (m.progress || 0) * 0.17);
      },
    });
    await worker.setParameters({ tessedit_pageseg_mode: "11" });
    const { data } = await worker.recognize(big);
    const words = data.words.map((w) => ({ text: w.text, bbox: w.bbox }));
    const { classes: found, problem } = ScheduleOCR.readTable(words, grid, scale);
    if (problem) throw new Error(problem.replace(/\.$/, "").toLowerCase());
    if (!found.length) throw new Error("no classes found in the table");

    progress(0.95, "Finding the rooms on the plans…");
    const res = await fetch("/api/schedule/rooms", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(found.map((c) => ({ room: c.room || "" }))),
    });
    const rooms = res.ok ? await res.json() : found.map((c) => ({ on_campus: false, room_value: c.room, where: "" }));
    // a room that isn't in the directory can't be saved (US17): that class waits
    // unticked until a room from the list is chosen for it
    reviewRows = found.map((c, i) => ({ ...c, ...rooms[i], keep: !!rooms[i].on_campus }));
    showReview();
  } catch (err) {
    importStep("pick");
    const lead = $("#im-pick .auth-lead");
    lead.dataset.text ??= lead.innerHTML;
    lead.innerHTML = `<span class="form-error">Couldn't read it: ${esc(err.message)}.</span> ${lead.dataset.text}`;
  } finally {
    if (worker) worker.terminate();
  }
}

function showReview() {
  importStep("review");
  const n = reviewRows.length;
  const away = reviewRows.filter((r) => !r.on_campus).length;
  $("#im-found").textContent = `Found ${n} class${n === 1 ? "" : "es"}. Check them against your screenshot and put right anything read wrong`
    + (away ? `. ${away} room${away === 1 ? " isn't" : "s aren't"} in the room directory (an online class, another building): `
              + `choose a room from the list to keep ${away === 1 ? "it" : "them"}, or leave ${away === 1 ? "it" : "them"} out.` : ".");
  $("#im-shot").innerHTML = `<img src="${shotUrl}" alt="Your screenshot">`;
  $("#im-mode").hidden = !classes.length;
  $("#im-error").hidden = true;
  $("#im-rows").innerHTML = reviewRows.map((r, i) => `
    <tr data-row="${i}">
      <td><input type="checkbox" data-f="keep" ${r.keep ? "checked" : ""} aria-label="Keep this class"></td>
      <td><input type="text" data-f="subject" maxlength="80" value="${esc(r.subject + (r.section ? ` [${r.section}]` : ""))}" aria-label="Subject"></td>
      <td><select data-f="day" aria-label="Day">${SHORT.map((d, k) => `<option value="${k}"${k === r.day ? " selected" : ""}>${d}</option>`).join("")}</select></td>
      <td><input type="time" data-f="start" value="${esc(r.start)}" aria-label="Starts"></td>
      <td><input type="time" data-f="end" value="${esc(r.end)}" aria-label="Ends"></td>
      <td><input type="text" data-f="room" list="tt-rooms" maxlength="80" value="${esc(r.room_value)}" aria-label="Room">
          <span class="im-where${r.on_campus ? "" : " away"}">${esc(r.on_campus ? r.where : "Not in the room directory")}</span></td>
    </tr>`).join("");
}

// an edit in the review table goes back into its row; a room is looked up again
let lookup = null;
$("#im-rows").addEventListener("input", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const row = reviewRows[+tr.dataset.row];
  const f = e.target.dataset.f;
  if (f === "keep") row.keep = e.target.checked;
  else if (f === "day") row.day = Number(e.target.value);
  else if (f === "subject") { row.subject = e.target.value; row.section = null; }
  else if (f === "room") {
    row.room_value = e.target.value;
    clearTimeout(lookup);
    lookup = setTimeout(async () => {
      const res = await fetch("/api/schedule/rooms", { method: "POST", headers: { "Content-Type": "application/json" },
                                                       body: JSON.stringify([{ room: row.room_value }]) });
      if (!res.ok) return;
      const [found] = await res.json();
      row.on_campus = found.on_campus;
      if (found.on_campus) row.room_value = found.room_value;
      const where = tr.querySelector(".im-where");
      where.textContent = found.on_campus ? found.where : "Not in the room directory";
      where.classList.toggle("away", !found.on_campus);
      // a room from the list now: the class can be kept
      if (found.on_campus && !row.keep) { row.keep = true; tr.querySelector('[data-f="keep"]').checked = true; tr.classList.remove("off"); }
    }, 350);
  } else row[f] = e.target.value;
  tr.classList.toggle("off", !row.keep);
});

$("#im-save").addEventListener("click", async () => {
  const keep = reviewRows.map((r, i) => ({ r, i })).filter(({ r }) => r.keep);
  const box = $("#im-error");
  box.hidden = true;
  document.querySelectorAll("#im-rows tr").forEach((tr) => tr.classList.remove("bad"));
  if (!keep.length) { box.textContent = "Tick at least one class to save."; box.hidden = false; return; }
  const roomless = keep.find(({ r }) => !r.on_campus);
  if (roomless) {
    document.querySelector(`#im-rows tr[data-row="${roomless.i}"]`)?.classList.add("bad");
    box.textContent = `${roomless.r.subject}: choose its room from the list, or untick it.`;
    box.hidden = false;
    return;
  }
  const replace = !classes.length || document.querySelector('input[name="im-mode"]:checked').value === "replace";
  const body = {
    replace,
    classes: keep.map(({ r }) => ({ subject: r.subject + (r.section ? ` [${r.section}]` : ""), day: r.day,
                                    start: r.start, end: r.end, room: r.room_value })),
  };
  const button = $("#im-save");
  button.disabled = true;
  try {
    const res = await fetch("/api/schedule/import", { method: "POST", headers: { "Content-Type": "application/json" },
                                                       body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      classes = data.classes;
      $("#import").close();
      changed();
    } else {
      const d = data.detail;
      const at = d && typeof d === "object" && d.row != null ? keep[d.row] : null;
      if (at) document.querySelector(`#im-rows tr[data-row="${at.i}"]`)?.classList.add("bad");
      box.textContent = (d && d.message) || (typeof d === "string" ? d : "Something went wrong. Try again.");
      box.hidden = false;
    }
  } catch (err) {
    box.textContent = `Couldn't reach the server (${err.message}).`;
    box.hidden = false;
  }
  button.disabled = false;
});

boot();
