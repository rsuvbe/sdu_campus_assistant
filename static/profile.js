"use strict";

/* The profile: who is signed in, the timetable (US17), the password change (US4)
   and the way out. The server checks everything again (app/auth.py, app/main.py);
   the forms only make the rules quicker to see. */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\"";
let studentId = "";
let nameParts = [];   // a member of staff's name and surname, which the password may not hold

const RULES = {
  length: (pw) => pw.length >= 8 && pw.length <= 72,
  upper: (pw) => /[A-Z]/.test(pw),
  lower: (pw) => /[a-z]/.test(pw),
  digit: (pw) => /\d/.test(pw),
  special: (pw) => [...pw].some((c) => SPECIALS.includes(c)),
  notid: (pw) => !/\s/.test(pw) && !(studentId && pw.includes(studentId))
    && !nameParts.some((part) => pw.toLowerCase().includes(part)),
};

function checkRules() {
  const pw = $("#new_password").value;
  let all = true;
  document.querySelectorAll("#rules li").forEach((li) => {
    const ok = RULES[li.dataset.rule](pw);
    li.classList.toggle("ok", ok && pw.length > 0);
    if (!ok) all = false;
  });
  return all;
}

function clearMessages() {
  $("#form-error").hidden = true;
  $("#form-ok").hidden = true;
  document.querySelectorAll(".field").forEach((f) => f.classList.remove("bad"));
}

function showError(message, field) {
  const box = $("#form-error");
  box.textContent = message;
  box.hidden = false;
  if (field) {
    const input = $(`#${field}`);
    if (input) { input.closest(".field").classList.add("bad"); input.focus(); }
  }
}

async function load() {
  const res = await fetch("/api/auth/me");
  if (res.status === 401) { window.location.replace("/login"); return; }
  const { user } = await res.json();
  if (user.role === "visitor") { $("#visitor").hidden = false; return; }
  studentId = user.student_id || "";
  const staff = user.role === "staff";
  if (staff) nameParts = user.email.split("@")[0].split(/[.-]/).filter((part) => part.length >= 3);
  // a member of staff signs in with their name, and has no student number
  $("#p-band-role").textContent = staff ? "Staff" : "Student";
  $("#p-name").textContent = user.full_name || "Not given";
  // the card is headed by the name; without one on file, by the student ID.
  // The photo slot holds the initials, or the SDU mark when there is no name.
  const headline = $("#p-headline");
  headline.textContent = user.full_name || user.student_id || user.email;
  headline.classList.toggle("number", !user.full_name);
  // the ID already heads the card, so its own field would only repeat it
  $("#p-id").parentElement.hidden = !user.full_name || staff;
  const initials = (user.full_name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("");
  if (initials) $("#p-initials").textContent = initials.toUpperCase();
  else $("#p-initials").innerHTML = '<img src="/static/img/sdu-mark.png" alt="">';
  $("#p-email").textContent = user.email;
  $("#p-id").textContent = user.student_id;
  $("#p-username").value = user.email;
  $("#member").hidden = false;
  loadTimetable();
  if (location.hash === "#timetable") $("#timetable").scrollIntoView({ block: "start" });
}

/* ------------------------------------------------------------ timetable */
let classes = [];
let editing = null;   // the class the form is changing, or null when it adds a new one

async function loadTimetable() {
  try {
    const [week, rooms] = await Promise.all([fetch("/api/schedule"), fetch("/api/rooms")]);
    if (week.status === 401) { window.location.replace("/login"); return; }
    classes = (await week.json()).classes;
    $("#tt-rooms").innerHTML = (await rooms.json())
      .map((r) => `<option value="${esc(r.value)}" label="${esc(r.label)}"></option>`).join("");
    renderWeek();
  } catch (err) {
    $("#tt-week").innerHTML = `<p class="tt-empty">Couldn't load your timetable (${esc(err.message)}). Reload the page to try again.</p>`;
  }
}

function renderWeek() {
  $("#tt-count").textContent = classes.length ? `${classes.length} class${classes.length === 1 ? "" : "es"} a week` : "";
  if (!classes.length) {
    $("#tt-week").innerHTML = `<p class="tt-empty">No classes yet. Add your first one with the form.</p>`;
    return;
  }
  const days = [...new Set(classes.map((c) => c.day))];
  $("#tt-week").innerHTML = days.map((day) => {
    const rows = classes.filter((c) => c.day === day);
    return `<section class="tt-day" aria-label="${esc(rows[0].day_name)}">
      <h3 class="tt-day-name">${esc(rows[0].day_name)}</h3>
      <ul class="tt-list">${rows.map(classRow).join("")}</ul>
    </section>`;
  }).join("");
  document.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => startEdit(Number(b.dataset.edit))));
  document.querySelectorAll("[data-delete]").forEach((b) => b.addEventListener("click", () => removeClass(Number(b.dataset.delete))));
}

function classRow(c) {
  return `<li class="tt-row${editing === c.class_id ? " editing" : ""}">
    <span class="tt-time">${esc(c.start)}–${esc(c.end)}</span>
    <span class="tt-what"><b>${esc(c.subject)}</b><span>${esc(c.room_label)} · ${esc(c.where)}</span></span>
    <span class="tt-row-actions">
      <button type="button" class="btn-text" data-edit="${c.class_id}" aria-label="Edit ${esc(c.subject)}, ${esc(c.day_name)} ${esc(c.start)}">Edit</button>
      <button type="button" class="btn-text" data-delete="${c.class_id}" aria-label="Delete ${esc(c.subject)}, ${esc(c.day_name)} ${esc(c.start)}">Delete</button>
    </span>
  </li>`;
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

function startEdit(id) {
  const c = classes.find((x) => x.class_id === id);
  if (!c) return;
  editing = id;
  ttClear();
  $("#tt-subject").value = c.subject;
  $("#tt-day").value = c.day;
  $("#tt-start").value = c.start;
  $("#tt-end").value = c.end;
  $("#tt-room").value = c.room_value;
  $("#tt-form-title").textContent = "Edit the class";
  $("#tt-submit").textContent = "Save changes";
  $("#tt-cancel").hidden = false;
  renderWeek();
  $("#tt-form").scrollIntoView({ block: "nearest" });
  $("#tt-subject").focus();
}

function stopEdit() {
  editing = null;
  ttClear();
  // the day stays as it was: the next class is usually on the same one
  ["#tt-subject", "#tt-start", "#tt-end", "#tt-room"].forEach((sel) => { $(sel).value = ""; });
  $("#tt-form-title").textContent = "Add a class";
  $("#tt-submit").textContent = "Add class";
  $("#tt-cancel").hidden = true;
  renderWeek();
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
      classes = classes.filter((c) => c.class_id !== data.class_id).concat(data)
        .sort((a, b) => a.day - b.day || a.start.localeCompare(b.start));
      stopEdit();
      $("#tt-subject").focus();
    } else if (res.status === 401) {
      window.location.replace("/login");
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

async function removeClass(id) {
  try {
    const res = await fetch(`/api/schedule/${id}`, { method: "DELETE" });
    if (res.status === 401) { window.location.replace("/login"); return; }
    if (!res.ok && res.status !== 404) throw new Error(res.statusText);
    classes = classes.filter((c) => c.class_id !== id);
    if (editing === id) stopEdit(); else renderWeek();
  } catch (err) {
    ttError(`Couldn't delete that class (${err.message}).`);
  }
}

async function submit(event) {
  event.preventDefault();
  clearMessages();
  const current = $("#current_password").value;
  const next = $("#new_password").value;
  if (!current) return showError("Enter your current password.", "current_password");
  if (!checkRules()) return showError("Your new password still misses one of the rules below it.", "new_password");
  if (next !== $("#confirm").value) return showError("The two new passwords don't match.", "confirm");
  if (next === current) return showError("Choose a password different from the current one.", "new_password");

  const button = $("#pw-submit");
  button.disabled = true;
  button.textContent = "Changing…";
  try {
    const res = await fetch("/api/profile/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      $("#pw-form").reset();
      checkRules();
      const ok = $("#form-ok");
      ok.textContent = data.message || "Your password is changed.";
      ok.hidden = false;
    } else if (res.status === 401) {
      window.location.replace("/login");
    } else {
      const d = data.detail;
      if (d && typeof d === "object") showError(d.message, d.field);
      else showError(typeof d === "string" ? d : "Something went wrong. Try again.");
    }
  } catch (err) {
    showError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
  button.textContent = "Change password";
}

$("#pw-form").addEventListener("submit", submit);
$("#tt-form").addEventListener("submit", saveClass);
$("#tt-cancel").addEventListener("click", stopEdit);
$("#new_password").addEventListener("input", checkRules);
document.querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", () => {
  const input = $(`#${b.dataset.toggle}`);
  const shown = input.type === "text";
  input.type = shown ? "password" : "text";
  b.textContent = shown ? "Show" : "Hide";
  b.setAttribute("aria-label", shown ? "Show password" : "Hide password");
}));
$("#signout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.replace("/login");
});
load();
