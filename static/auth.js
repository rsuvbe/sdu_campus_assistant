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
  register: { title: "Create your account", lead: "Only SDU addresses can register, which keeps the map inside the university.", submit: "Create account", switch: 'Already registered? <button type="button" class="linkish" data-mode="login">Sign in</button>' },
  forgot: { title: "Forgot your password?", lead: "Enter your SDU address and we'll email you a link to choose a new one.", submit: "Send reset link", switch: 'Remembered it? <button type="button" class="linkish" data-mode="login">Sign in</button>' },
  reset: { title: "Choose a new password", lead: "Pick a new password for your SDU account. Anywhere still signed in with the old one is signed out.", submit: "Save new password", switch: 'Link not working? <button type="button" class="linkish" data-mode="forgot">Send a new one</button>' },
};

let mode = "login";
// The reset link carries its one-time token in the URL fragment (#reset=…),
// which never reaches a server log. It is read once and wiped from the address bar.
let resetToken = null;

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
  const choosing = mode === "register" || mode === "reset";
  $("#field-name").hidden = mode !== "register";
  $("#field-email").hidden = mode === "reset";
  $("#field-password").hidden = mode === "forgot";
  $("#field-confirm").hidden = mode !== "reset";
  $("#forgot-link").hidden = mode !== "login";
  $("#password-label").textContent = mode === "reset" ? "New password" : "Password";
  $("#rules").hidden = !choosing;
  $("#password").setAttribute("autocomplete", choosing ? "new-password" : "current-password");
  $(".auth-tabs").hidden = mode === "forgot" || mode === "reset";
  document.querySelectorAll(".auth-tabs button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  });
  $("#form-ok").hidden = true;
  document.querySelectorAll(".reset-go").forEach((a) => a.remove());
  $("#submit").disabled = false;
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
    ? `${{ forgot: "The link goes to student", register: "Registering student" }[mode] || "Signing in as student"} <b>${idOf(value)}</b>.`
    : 'Nine digits and <b>@sdu.edu.kz</b>, the address printed on your student card.';
  return ok;
}

// The same rule the server applies (app/auth.py, normalise_name): letters of any
// alphabet, with spaces, hyphens or apostrophes between them, two letters at least.
const NAME_RE = /^\p{L}+(?:[ '’-]\p{L}+)*$/u;
function checkName(showProblem) {
  const field = $("#full_name").closest(".field");
  const hint = $("#name-hint");
  const value = $("#full_name").value.trim().replace(/\s+/g, " ");
  const ok = NAME_RE.test(value) && value.replace(/[^\p{L}]/gu, "").length >= 2;
  field.classList.toggle("good", ok);
  field.classList.toggle("bad", !ok && showProblem);
  hint.classList.toggle("bad", !ok && showProblem);
  hint.textContent = !ok && showProblem && value
    ? "Use letters only, as your name is written: Aidana Serikova."
    : !ok && showProblem ? "Enter your full name." : "As it is written in your student records.";
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

function showOk(message) {
  const box = $("#form-ok");
  box.textContent = message;
  box.hidden = false;
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

  if (mode === "forgot") return requestReset(email);
  if (mode === "reset") return saveNewPassword(password);

  if (mode === "register" && !checkName(true)) {
    return showError("Enter your full name, as it is written in your student records.", "full_name");
  }
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
  if (mode === "register") body.full_name = $("#full_name").value.trim().replace(/\s+/g, " ");

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

/* ------------------------------------------------------------ forgotten password */
async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { res, data: await res.json().catch(() => ({})) };
}

function serverError(data) {
  const detail = data.detail;
  if (detail && typeof detail === "object") showError(detail.message, detail.field === "token" ? null : detail.field);
  else showError(typeof detail === "string" ? detail : "Something went wrong. Try again.");
}

const RESEND_AFTER = 60;   // seconds; the server refuses a second link sooner anyway

async function requestReset(email) {
  if (!checkEmail(true)) {
    return showError("Use your SDU address: nine digits and @sdu.edu.kz, for example 240103048@sdu.edu.kz.", "email");
  }
  const button = $("#submit");
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    const { res, data } = await postJSON("/api/auth/forgot", { email });
    if (!res.ok) {
      serverError(data);
    } else if (data.delivery === "screen" && data.reset_url) {
      // no mail server on this computer: the link is handed over right here
      showOk(data.message);
      const go = document.createElement("a");
      go.className = "btn-go wide reset-go";
      go.href = data.reset_url;
      go.textContent = "Set a new password";
      $("#form-ok").after(go);
      go.focus();
    } else if (data.delivery === "email") {
      showOk(`${data.message} Open the letter on this device and follow the link. Not there? Check spam, or ask again below.`);
      countdown(button);
      return;
    } else {
      showError(data.message);
    }
  } catch (err) {
    showError(`Couldn't reach the server (${err.message}).`);
  }
  button.textContent = COPY.forgot.submit;
  button.disabled = false;
}

function countdown(button) {
  let left = RESEND_AFTER;
  const tick = () => {
    if (mode !== "forgot" || left <= 0) {
      button.disabled = false;
      button.textContent = mode === "forgot" ? "Send the link again" : COPY[mode].submit;
      return;
    }
    button.disabled = true;
    button.textContent = `Send again in ${left--} s`;
    setTimeout(tick, 1000);
  };
  tick();
}

async function saveNewPassword(password) {
  if (!resetToken) {
    return showError("This page needs the link from the email. Ask for a new one below.");
  }
  if (!checkPassword()) return showError("Your new password still misses one of the rules below.", "password");
  if (password !== $("#confirm").value) return showError("The two passwords don't match.", "confirm");
  const button = $("#submit");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const { res, data } = await postJSON("/api/auth/reset", { token: resetToken, password });
    if (res.ok) { window.location.replace("/"); return; }
    serverError(data);
  } catch (err) {
    showError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
  button.textContent = COPY.reset.submit;
}

/* ------------------------------------------------------------ visitors */
async function enterAsVisitor() {
  const button = $("#guest");
  button.disabled = true;
  button.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-entrance"/></svg>Opening…`;
  try {
    const res = await fetch("/api/auth/guest", { method: "POST" });
    if (res.ok) { window.location.replace("/"); return; }
    showError("Couldn't open the campus assistant. Try again.");
  } catch (err) {
    showError(`Couldn't reach the server (${err.message}).`);
  }
  button.disabled = false;
  button.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-entrance"/></svg>Continue as a visitor`;
}

/* ------------------------------------------------------------ boot */
$("#auth-form").addEventListener("submit", submit);
$("#guest").addEventListener("click", enterAsVisitor);
$("#email").addEventListener("input", () => { checkEmail(false); checkPassword(); });
$("#email").addEventListener("blur", () => checkEmail(true));
$("#password").addEventListener("input", checkPassword);
$("#full_name").addEventListener("input", () => checkName(false));
$("#full_name").addEventListener("blur", () => { if ($("#full_name").value.trim()) checkName(true); });
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
function takeResetLink() {
  const found = location.hash.match(/(?:^#|&)reset=([\w-]+)/);
  if (!found) return false;
  resetToken = found[1];
  history.replaceState(null, "", location.pathname);
  return true;
}
window.addEventListener("hashchange", () => { if (takeResetLink()) setMode("reset"); });
takeResetLink();
const asked = new URLSearchParams(location.search).get("mode");
setMode(resetToken ? "reset" : ["register", "forgot"].includes(asked) ? asked : "login");
