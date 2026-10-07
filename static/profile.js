"use strict";

/* The profile: who is signed in, the password change (US4) and the way out.
   The server checks everything again (app/auth.py, change_password); the form
   only makes the rules quicker to see. */

const $ = (sel) => document.querySelector(sel);
const SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\"";
let studentId = "";

const RULES = {
  length: (pw) => pw.length >= 8 && pw.length <= 72,
  upper: (pw) => /[A-Z]/.test(pw),
  lower: (pw) => /[a-z]/.test(pw),
  digit: (pw) => /\d/.test(pw),
  special: (pw) => [...pw].some((c) => SPECIALS.includes(c)),
  notid: (pw) => !/\s/.test(pw) && !(studentId && pw.includes(studentId)),
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
  $("#p-name").textContent = user.full_name || "Not given";
  // the card is headed by the name; without one on file, by the student ID.
  // The photo slot holds the initials, or the SDU mark when there is no name.
  const headline = $("#p-headline");
  headline.textContent = user.full_name || user.student_id || user.email;
  headline.classList.toggle("number", !user.full_name);
  // the ID already heads the card, so its own field would only repeat it
  $("#p-id").parentElement.hidden = !user.full_name;
  const initials = (user.full_name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("");
  if (initials) $("#p-initials").textContent = initials.toUpperCase();
  else $("#p-initials").innerHTML = '<img src="/static/img/sdu-mark.png" alt="">';
  $("#p-email").textContent = user.email;
  $("#p-id").textContent = user.student_id;
  $("#p-username").value = user.email;
  $("#member").hidden = false;
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
