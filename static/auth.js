"use strict";

/* Sign-in / sign-up. The same rules run on the server (app/auth.py); the
   checks here only make the form quicker to fill in. */

const $ = (sel) => document.querySelector(sel);
const EMAIL_RE = /^\d{9}@sdu\.edu\.kz$/;
const SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\"";

const RULES = {
  length: (pw) => pw.length >= 8 && pw.length <= 72,
  upper: (pw) => /[A-Z]/.test(pw),
  lower: (pw) => /[a-z]/.test(pw),
  digit: (pw) => /\d/.test(pw),
  special: (pw) => [...pw].some((c) => SPECIALS.includes(c)),
  notid: (pw, email) => !/\s/.test(pw) && !(idOf(email) && pw.includes(idOf(email))),
};

const COPY = {
  login: { title: "Welcome back", lead: "Sign in with your SDU account to open the campus map.", submit: "Sign in", switch: 'No account yet? <button type="button" class="linkish" data-mode="register">Create one</button>' },
  register: { title: "Create your account", lead: "Only SDU addresses can register — that keeps the map inside the university.", submit: "Create account", switch: 'Already registered? <button type="button" class="linkish" data-mode="login">Sign in</button>' },
};

let mode = "login";

function idOf(email) {
  const at = (email || "").indexOf("@");
  return at > 0 ? email.slice(0, at) : "";
}

/* ------------------------------------------------------------ mode switch */
function setMode(next) {
  mode = next;
  const copy = COPY[mode];
  $("#auth-title").textContent = copy.title;
  $("#auth-lead").textContent = copy.lead;
  $("#submit").textContent = copy.submit;
  $("#auth-switch").innerHTML = copy.switch;
  $("#field-name").hidden = mode !== "register";
  $("#rules").hidden = mode !== "register";
  $("#password").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
  document.querySelectorAll(".auth-tabs button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  });
  hideError();
  checkPassword();
}

/* ------------------------------------------------------------ validation */
function checkEmail(showProblem) {
  const value = $("#email").value.trim().toLowerCase();
  const field = $("#email").closest(".field");
  const hint = $("#email-hint");
  const ok = EMAIL_RE.test(value);
  field.classList.toggle("good", ok);
  field.classList.toggle("bad", !ok && showProblem && value !== "");
  hint.classList.toggle("bad", !ok && showProblem && value !== "");
  hint.innerHTML = ok
    ? `Signing in as student <b>${idOf(value)}</b>.`
    : 'Nine digits and <b>@sdu.edu.kz</b> — the address printed on your student card.';
  return ok;
}

function checkPassword() {
  const pw = $("#password").value;
  const email = $("#email").value.trim().toLowerCase();
  let all = true;
  $("#rules").querySelectorAll("li").forEach((li) => {
    const pass = RULES[li.dataset.rule](pw, email);
    li.classList.toggle("ok", pass && pw.length > 0);
    if (!pass) all = false;
  });
  return mode === "login" ? pw.length > 0 : all;
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
function hideError() {
  $("#form-error").hidden = true;
  document.querySelectorAll(".field").forEach((f) => f.classList.remove("bad"));
}

/* ------------------------------------------------------------ submit */
async function submit(event) {
  event.preventDefault();
  hideError();
  const email = $("#email").value.trim().toLowerCase();
  const password = $("#password").value;

  if (!checkEmail(true)) {
    return showError("Use your SDU address: nine digits and @sdu.edu.kz, for example 240103048@sdu.edu.kz.", "email");
  }
  if (!checkPassword()) {
    return showError(mode === "register"
      ? "Your password still misses one of the rules below."
      : "Enter your password.", "password");
  }

  const button = $("#submit");
  button.disabled = true;
  button.textContent = mode === "register" ? "Creating…" : "Signing in…";

  const body = { email, password };
  if (mode === "register") body.full_name = $("#full_name").value.trim() || null;

  try {
    const res = await fetch(`/api/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) { window.location.replace("/"); return; }
    const data = await res.json().catch(() => ({}));
    const detail = data.detail;
    if (detail && typeof detail === "object") showError(detail.message, detail.field);
    else showError(typeof detail === "string" ? detail : "Something went wrong. Try again.");
  } catch (err) {
    showError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
  button.textContent = COPY[mode].submit;
}

/* ------------------------------------------------------------ decoration */
function drawAsidePlan() {
  const rooms = ["D101", "D102", "D103", "D104", "D105"];
  const wing = rooms.map((code, i) => `
    <g class="r${i === 2 ? " on" : ""}">
      <rect x="${138 + i * 62}" y="58" width="60" height="74" rx="2"/>
      <text x="${168 + i * 62}" y="99">${code}</text>
    </g>`).join("");
  $("#aside-plan").innerHTML = `
    <svg viewBox="0 0 470 250" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect class="spine" x="96" y="20" width="34" height="210" rx="2"/>
      <path class="hall" d="M130 141 H452"/>
      <g class="rooms">${wing}
        <g class="r"><rect x="150" y="150" width="120" height="62" rx="2" transform="rotate(4 210 181)"/><text x="210" y="186">D108</text></g>
        <g class="r"><rect x="286" y="146" width="110" height="62" rx="2" transform="rotate(4 341 177)"/><text x="341" y="182">D107</text></g>
        <g class="r"><rect x="136" y="16" width="66" height="30" rx="2"/><text x="169" y="36">C111</text></g>
      </g>
      <circle class="ping" cx="298" cy="95" r="34"/>
      <circle class="dot" cx="298" cy="95" r="5"/>
    </svg>`;
}

/* ------------------------------------------------------------ boot */
drawAsidePlan();
$("#auth-form").addEventListener("submit", submit);
$("#email").addEventListener("input", () => { checkEmail(false); checkPassword(); });
$("#email").addEventListener("blur", () => checkEmail(true));
$("#password").addEventListener("input", checkPassword);
$("#pw-toggle").addEventListener("click", () => {
  const input = $("#password");
  const shown = input.type === "text";
  input.type = shown ? "password" : "text";
  $("#pw-toggle").textContent = shown ? "Show" : "Hide";
  $("#pw-toggle").setAttribute("aria-label", shown ? "Show password" : "Hide password");
});
document.addEventListener("click", (e) => {
  const target = e.target.closest("[data-mode]");
  if (target) setMode(target.dataset.mode);
});
setMode(new URLSearchParams(location.search).get("mode") === "register" ? "register" : "login");
