"use strict";

/* The events page (US19, US20): what is coming up, soonest first. The
   search box and the period go to the server, which asks the events table; the
   page shows the answer. A row goes to the map and asks about that event, so its
   room lights up on the plan and its card comes up in the answers.

   Below the events, the university's own news from sdu.edu.kz. An administrator
   (CAMPUS_ADMINS on the server) also gets Add, Edit and Delete, and can start an
   event from a news story. */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "i") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

const EVENT_TYPING_DELAY = 200;
const eventsView = {
  seq: 0,          // the request on its way; an older answer that comes back late is dropped
  timer: null,
  ranges: null,    // today, this week and this month as the server counts them
  chip: "",        // the period chip pressed: "" for all, null once the dates are set by hand
};

function setupEvents() {
  const from = $("#ev-from"), to = $("#ev-to");
  $("#ev-q").addEventListener("input", () => {
    clearTimeout(eventsView.timer);
    eventsView.timer = setTimeout(loadEvents, EVENT_TYPING_DELAY);
  });
  [from, to].forEach((input) => input.addEventListener("change", () => {
    eventsView.chip = null;
    loadEvents();
  }));
  $("#ev-filter").querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
    const key = chip.dataset.range;
    const range = eventsView.ranges?.[key];
    if (key && !range) return;       // the first answer has not come back yet
    from.value = range ? range.from : "";
    to.value = range ? range.to : "";
    eventsView.chip = key;
    loadEvents();
  }));
}

async function loadEvents() {
  clearTimeout(eventsView.timer);
  const seq = ++eventsView.seq;
  const list = $("#ev-list");
  const params = new URLSearchParams();
  const fields = { q: $("#ev-q").value.trim(), from: $("#ev-from").value, to: $("#ev-to").value };
  Object.entries(fields).forEach(([key, value]) => { if (value) params.set(key, value); });

  // a chip shows the period in force: all when no dates are set, none once they are typed in
  const pressed = eventsView.chip ?? (fields.from || fields.to ? null : "");
  $("#ev-filter").querySelectorAll(".chip").forEach((chip) =>
    chip.setAttribute("aria-pressed", String(chip.dataset.range === pressed)));

  let data;
  try {
    const res = await fetch(`/api/events?${params}`);
    if (res.status === 401) { window.location.replace("/login?next=%2Fevents"); return; }
    if (res.status === 400) {
      const { detail } = await res.json();
      if (seq === eventsView.seq) showEventsMessage(detail?.message || "Those dates can't be used.");
      return;
    }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    data = await res.json();
  } catch (err) {
    if (seq === eventsView.seq) {
      showEventsMessage(`Couldn't load the events (${err.message}). Check your connection and try again.`, true);
    }
    return;
  }
  if (seq !== eventsView.seq) return;

  eventsView.ranges = data.ranges;
  $("#ev-controls").hidden = !data.total;     // nothing to search in an empty list
  const noun = (n) => `${n} ${n === 1 ? "event" : "events"}`;
  $("#ev-count").textContent = !data.total ? ""
    : data.count === data.total ? `${noun(data.count)} upcoming`
    : `${data.count} of ${data.total} upcoming events`;

  shownEvents = data.events;
  if (data.events.length) {
    list.innerHTML = `<ul class="dir-list">${data.events.map(eventRow).join("")}</ul>`;
    list.querySelectorAll("[data-ev-edit]").forEach((b) => b.addEventListener("click", () =>
      openEventForm(shownEvents.find((e) => e.event_id === b.dataset.evEdit))));
    list.querySelectorAll("[data-ev-delete]").forEach((b) => b.addEventListener("click", () => deleteEvent(b)));
  } else if (data.total) {
    // events exist, but the search or the dates took every one of them out
    list.innerHTML = `<div class="ev-empty">
      <p><b>No upcoming events match.</b> Try another word, or a longer period.</p>
      <button type="button" class="btn-line" data-ev-clear>Clear search and dates</button></div>`;
    list.querySelector("[data-ev-clear]").addEventListener("click", () => {
      $("#ev-q").value = $("#ev-from").value = $("#ev-to").value = "";
      eventsView.chip = "";
      loadEvents();
      $("#ev-q").focus();
    });
  } else {
    list.innerHTML = `<div class="ev-empty"><p><b>No events have been added yet.</b> They'll appear here, soonest first. Until then, the university's latest news is below.</p></div>`;
  }
}

// a message where the list would be: the server's own words for a bad date, or a failed request
function showEventsMessage(text, retry = false) {
  $("#ev-count").textContent = "";
  $("#ev-list").innerHTML = `<div class="ev-error" role="alert">${icon("alert")}<span>${esc(text)}</span></div>${
    retry ? `<button type="button" class="btn-line ev-retry" data-ev-retry>Try again</button>` : ""}`;
  $("#ev-list [data-ev-retry]")?.addEventListener("click", loadEvents);
}

function eventRow(ev) {
  const [weekday, dayNum, month] = ev.date.split(" ");
  const where = ev.where ? `, ${ev.where}` : "";
  const more = [
    ev.link ? `<a class="btn-text ev-link" href="${esc(ev.link)}" target="_blank" rel="noopener noreferrer">Announcement${icon("out-link")}</a>` : "",
    admin && ev.editable ? `<button type="button" class="btn-text" data-ev-edit="${esc(ev.event_id)}">Edit</button>
      <button type="button" class="btn-text" data-ev-delete="${esc(ev.event_id)}">Delete</button>` : "",
  ].join("");
  return `<li class="ev-item"><a class="dir-row ev-row${ev.on_now ? " open" : ""}" href="/?ask=${encodeURIComponent(ev.ask)}"
      title="${esc(ev.title)}${where ? ` (${esc(ev.where)})` : ""}"
      aria-label="${esc(`${ev.title}, ${ev.date}, ${ev.time}, ${ev.place}${where}${ev.on_now ? ", on now" : ""}`)}">
      <span class="ev-date"><span>${esc(weekday)}</span><b>${esc(dayNum)}</b><span>${esc(month)}</span></span>
      <span class="dir-text ev-text"><b>${esc(ev.title)}</b><span class="where">${esc(ev.place)} · ${esc(ev.time)}</span>${
        ev.description ? `<span class="ev-desc">${esc(ev.description)}</span>` : ""}</span>
      ${ev.on_now ? `<span class="state">On now</span>` : ""}</a>
      ${more ? `<div class="ev-more">${more}</div>` : ""}</li>`;
}

/* ------------------------------------------------------- news from SDU */
let news = [];

async function loadNews() {
  const list = $("#news-list");
  try {
    const res = await fetch("/api/news");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    news = data.items;
    list.removeAttribute("aria-busy");
    if (!news.length) {
      list.innerHTML = `<li class="ev-empty"><p>The university's site couldn't be reached just now. <a href="${esc(data.source)}" target="_blank" rel="noopener noreferrer">Open sdu.edu.kz</a> for its news.</p></li>`;
      return;
    }
    list.innerHTML = news.map(newsItem).join("");
    list.querySelectorAll("[data-make]").forEach((b) => b.addEventListener("click", () => {
      const item = news[Number(b.dataset.make)];
      openEventForm(null, { title: item.title, description: item.excerpt, link: item.link });
    }));
    if (data.stale && data.fetched_at) {
      $("#news-intro").textContent = `The latest from the university's site as of ${data.fetched_at}; it couldn't be reached just now.`;
    }
  } catch (err) {
    list.removeAttribute("aria-busy");
    list.innerHTML = `<li class="ev-error" role="alert">${icon("alert")}<span>Couldn't load the news (${esc(err.message)}).</span></li>`;
  }
}

function newsItem(item, i) {
  return `<li class="news-item">
    <a class="news-link" href="${esc(item.link)}" target="_blank" rel="noopener noreferrer">
      ${item.image ? `<img class="news-pic" src="${esc(item.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span class="news-pic none" aria-hidden="true"></span>`}
      <span class="news-text">
        <span class="news-date">${esc(item.date)}</span>
        <b>${esc(item.title)}</b>
        ${item.excerpt ? `<span class="news-excerpt">${esc(item.excerpt)}</span>` : ""}
      </span>
    </a>
    ${admin ? `<button type="button" class="btn-text news-make" data-make="${i}">${icon("plus")}Make it an event</button>` : ""}
  </li>`;
}

/* ------------------------------------------- adding events (administrators) */
let admin = false;
let shownEvents = [];
let editingEvent = null;

async function whoAmI() {
  try {
    const res = await fetch("/api/auth/me");
    if (!res.ok) return;
    admin = !!(await res.json()).user.admin;
  } catch { /* not an administrator, as far as this page knows */ }
  if (!admin) return;
  $("#ev-add").hidden = false;
  $("#ev-add").addEventListener("click", () => openEventForm(null));
  try {
    const rooms = await (await fetch("/api/rooms")).json();
    $("#ef-rooms").innerHTML = rooms.map((r) => `<option value="${esc(r.value)}" label="${esc(r.label)}"></option>`).join("");
  } catch { /* the room can still be typed */ }
}

const EF = { title: "#ef-title-input", description: "#ef-description", starts: "#ef-starts", ends: "#ef-ends",
             room: "#ef-room", place: "#ef-place", link: "#ef-link" };

function openEventForm(ev, preset = {}) {
  editingEvent = ev ? ev.event_id : null;
  efClear();
  $("#ef-title").textContent = ev ? "Edit the event" : "Add an event";
  $("#ef-submit").textContent = ev ? "Save changes" : "Add the event";
  const values = ev ? { title: ev.title, description: ev.description, starts: ev.starts_input, ends: ev.ends_input,
                        room: ev.room_value || "", place: ev.place, link: ev.link || "" }
                    : { title: "", description: "", starts: "", ends: "", room: "", place: "", link: "", ...preset };
  Object.entries(EF).forEach(([k, sel]) => { $(sel).value = values[k] ?? ""; });
  const d = $("#ev-dialog");
  if (!d.open) d.showModal();
  $(EF.title).focus();
}

function efClear() {
  $("#ef-error").hidden = true;
  document.querySelectorAll("#ev-form .field").forEach((f) => f.classList.remove("bad"));
}

function efError(message, field) {
  const box = $("#ef-error");
  box.textContent = message;
  box.hidden = false;
  const wrap = field && $(`#ef-field-${field}`);
  if (wrap) { wrap.classList.add("bad"); wrap.querySelector("input, textarea").focus(); }
}

$("#ev-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  efClear();
  const body = Object.fromEntries(Object.entries(EF).map(([k, sel]) => [k, $(sel).value.trim()]));
  if (!body.title) return efError("Give the event a title.", "title");
  if (!body.starts) return efError("Give the day and time it starts.", "starts");
  if (!body.ends) return efError("Give the day and time it ends.", "ends");
  if (body.ends <= body.starts) return efError("An event has to end after it starts.", "ends");
  if (!body.room && !body.place) return efError("Say where it is, or choose a room.", "place");
  const button = $("#ef-submit");
  button.disabled = true;
  try {
    const res = await fetch(editingEvent ? `/api/events/${encodeURIComponent(editingEvent)}` : "/api/events", {
      method: editingEvent ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      $("#ev-dialog").close();
      loadEvents();
    } else {
      const d = data.detail;
      if (d && typeof d === "object") efError(d.message, d.field);
      else efError(typeof d === "string" ? d : "Something went wrong. Try again.");
    }
  } catch (err) {
    efError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
});

async function deleteEvent(button) {
  if (!button.dataset.sure) {            // a second press deletes
    button.dataset.sure = "1";
    button.textContent = "Press again to delete";
    return;
  }
  button.disabled = true;
  const res = await fetch(`/api/events/${encodeURIComponent(button.dataset.evDelete)}`, { method: "DELETE" }).catch(() => null);
  if (res && (res.ok || res.status === 404)) loadEvents();
  else { button.disabled = false; button.textContent = "Couldn't delete"; }
}

document.querySelectorAll("dialog").forEach((d) => d.addEventListener("click", (e) => {
  if (e.target === d || e.target.closest("[data-close]")) d.close();
}));

setupEvents();
whoAmI().then(() => { loadEvents(); loadNews(); });
