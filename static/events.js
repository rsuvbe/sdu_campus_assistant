"use strict";

/* The events page (US19, US20): what is coming up, soonest first. The search box
   and the period go to the server, which asks the events table; the page shows
   the answer. A row goes to the map and asks about that event, so its room lights
   up on the plan and its card comes up in the answers. */

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
    if (res.status === 401) { window.location.replace("/login"); return; }
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

  if (data.events.length) {
    list.innerHTML = `<ul class="dir-list">${data.events.map(eventRow).join("")}</ul>`;
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
    list.innerHTML = `<div class="ev-empty"><p><b>No events have been added yet.</b> They'll appear here, soonest first.</p></div>`;
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
  const [weekday, ...day] = ev.date.split(" ");
  const where = ev.where ? `, ${ev.where}` : "";
  return `<li><a class="dir-row ev-row${ev.on_now ? " open" : ""}" href="/?ask=${encodeURIComponent(ev.ask)}"
      title="${esc(ev.title)}${where ? ` (${esc(ev.where)})` : ""}"
      aria-label="${esc(`${ev.title}, ${ev.date}, ${ev.time}, ${ev.place}${where}${ev.on_now ? ", on now" : ""}`)}">
      <span class="ev-date"><span>${esc(weekday)}</span><b>${esc(day.join(" "))}</b></span>
      <span class="dir-text ev-text"><b>${esc(ev.title)}</b><span class="where">${esc(ev.place)} · ${esc(ev.time)}</span></span>
      ${ev.on_now ? `<span class="state">On now</span>` : ""}</a></li>`;
}

setupEvents();
loadEvents();
