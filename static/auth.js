"use strict";

/* Sign-in / sign-up. The same rules run on the server (app/auth.py); the
   checks here only make the form quicker to fill in. */

const $ = (sel) => document.querySelector(sel);
const EMAIL_RE = /^\d{9}@sdu\.edu\.kz$/;                                  // a student's number
const STAFF_RE = /^([a-z]+(?:-[a-z]+)*)\.([a-z]+(?:-[a-z]+)*)@sdu\.edu\.kz$/;  // staff: name.surname
const EMAIL_HINT = t("Use your SDU address: your student number (240103048@sdu.edu.kz), or for staff your name and surname (aidana.serikova@sdu.edu.kz).");
// a link in the sentence that switches the form: "No account yet? <Create one>"
const switcher = (lead, label, to) => `${esc(lead)} <button type="button" class="linkish" data-mode="${to}">${esc(label)}</button>`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/\\|`~'\"";

const RULES = {
  length: (pw) => pw.length >= 8 && pw.length <= 72,
  upper: (pw) => /[A-Z]/.test(pw),
  lower: (pw) => /[a-z]/.test(pw),
  digit: (pw) => /\d/.test(pw),
  special: (pw) => [...pw].some((c) => SPECIALS.includes(c)),
  notid: (pw, email) => !/\s/.test(pw) && !(idOf(email) && pw.includes(idOf(email)))
    && !nameParts(email).some((part) => pw.toLowerCase().includes(part)),
};

const COPY = {
  login: { title: t("Welcome back"), lead: t("Sign in with your SDU account to open the campus map."), submit: t("Sign in"), switch: () => switcher(t("No account yet?"), t("Create one"), "register") },
  register: { title: t("Create your account"), lead: t("Only SDU addresses can register, which keeps the map inside the university."), submit: t("Create account"), switch: () => switcher(t("Already registered?"), t("Sign in"), "login") },
  forgot: { title: t("Forgot your password?"), lead: t("Enter your SDU address and we'll email you a link to choose a new one."), submit: t("Send reset link"), switch: () => switcher(t("Remembered it?"), t("Sign in"), "login") },
  reset: { title: t("Choose a new password"), lead: t("Pick a new password for your SDU account. Anywhere still signed in with the old one is signed out."), submit: t("Save new password"), switch: () => switcher(t("Link not working?"), t("Send a new one"), "forgot") },
};

let mode = "login";
// The reset link carries its one-time token in the URL fragment (#reset=…),
// which never reaches a server log. It is read once and wiped from the address bar.
let resetToken = null;

// a student's number, from their address (staff have none)
function idOf(email) {
  return EMAIL_RE.test(email || "") ? email.slice(0, email.indexOf("@")) : "";
}

// a member of staff's name and surname, from their address, which a password may not hold
function nameParts(email) {
  const m = STAFF_RE.exec(email || "");
  return m ? `${m[1]}.${m[2]}`.split(/[.-]/).filter((part) => part.length >= 3) : [];
}

// Signed in (or let in as a visitor) on this visit: the pages behind the door
// check for this mark, so a reload keeps the session and a new visit starts at
// this page again (see the first script in index.html).
function enter() {
  try { sessionStorage.setItem("sdu-visit", "1"); } catch { /* storage off: the session still works */ }
  window.location.replace(nextPage());
}

// The page asked for before signing in (a reminder's way to a class, the
// timetable). Only a path on this site: a browser reads "//elsewhere" and
// "/\elsewhere" as another site, after dropping tabs and line breaks, so a
// backslash, a space or a control character anywhere sends it to the map.
function nextPage() {
  const next = new URLSearchParams(location.search).get("next") || "";
  const plain = next.startsWith("/") && !next.startsWith("//") && !/[\u0000-\u0020\u007f\\]/.test(next);
  return plain && !/^\/login\b/.test(next) ? next : "/";
}

/* ------------------------------------------------------------ mode switch */
function setMode(next) {
  mode = next;
  const copy = COPY[mode];
  $("#auth-title").textContent = copy.title;
  $("#auth-lead").textContent = copy.lead;
  $("#submit").textContent = copy.submit;
  $("#auth-switch").innerHTML = copy.switch();
  const choosing = mode === "register" || mode === "reset";
  $("#field-name").hidden = mode !== "register";
  $("#field-email").hidden = mode === "reset";
  $("#field-password").hidden = mode === "forgot";
  $("#field-confirm").hidden = mode !== "reset";
  $("#forgot-link").hidden = mode !== "login";
  $("#password-label").textContent = mode === "reset" ? t("New password") : t("Password");
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
  const staff = STAFF_RE.test(value);
  const ok = EMAIL_RE.test(value) || staff;
  field.classList.toggle("good", ok);
  field.classList.toggle("bad", !ok && showProblem && value !== "");
  hint.classList.toggle("bad", !ok && showProblem && value !== "");
  const who = `<b>${esc(staff ? value.slice(0, value.indexOf("@")) : idOf(value))}</b>`;
  const say = {
    forgot: staff ? "The link goes to staff member {who}." : "The link goes to student {who}.",
    register: staff ? "Registering staff member {who}." : "Registering student {who}.",
  }[mode] || (staff ? "Signing in as staff member {who}." : "Signing in as student {who}.");
  hint.innerHTML = ok
    ? esc(t(say)).replace("{who}", who)
    : esc(t("Your student number, or for staff your {name}, and {domain}.")).replace("{name}", "<b>name.surname</b>").replace("{domain}", "<b>@sdu.edu.kz</b>");
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
    ? t("Use letters only, as your name is written: Aidana Serikova.")
    : !ok && showProblem ? t("Enter your full name.") : t("As it is written in your university records.");
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
    return showError(t("Enter your full name, as it is written in your university records."), "full_name");
  }
  if (!checkEmail(true)) {
    return showError(EMAIL_HINT, "email");
  }
  if (!checkPassword()) {
    return showError(mode === "register"
      ? t("Your password still misses one of the rules below.")
      : t("Enter your password."), "password");
  }

  const button = $("#submit");
  button.disabled = true;
  button.textContent = mode === "register" ? t("Creating…") : t("Signing in…");

  const body = { email, password };
  if (mode === "register") body.full_name = $("#full_name").value.trim().replace(/\s+/g, " ");

  try {
    const res = await fetch(`/api/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) { enter(); return; }
    const data = await res.json().catch(() => ({}));
    const detail = data.detail;
    if (detail && typeof detail === "object") showError(detail.message, detail.field);
    else showError(typeof detail === "string" ? detail : t("Something went wrong. Try again."));
  } catch (err) {
    showError(t("Couldn't reach the server ({error}).", { error: err.message }));
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
  else showError(typeof detail === "string" ? detail : t("Something went wrong. Try again."));
}

const RESEND_AFTER = 60;   // seconds; the server refuses a second link sooner anyway

async function requestReset(email) {
  if (!checkEmail(true)) {
    return showError(EMAIL_HINT, "email");
  }
  const button = $("#submit");
  button.disabled = true;
  button.textContent = t("Sending…");
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
      go.textContent = t("Set a new password");
      $("#form-ok").after(go);
      go.focus();
    } else if (data.delivery === "email") {
      showOk(`${data.message} ${t("Open the letter on this device and follow the link. Not there? Check spam, or ask again below.")}`);
      countdown(button);
      return;
    } else {
      showError(data.message);
    }
  } catch (err) {
    showError(t("Couldn't reach the server ({error}).", { error: err.message }));
  }
  button.textContent = COPY.forgot.submit;
  button.disabled = false;
}

function countdown(button) {
  let left = RESEND_AFTER;
  const tick = () => {
    if (mode !== "forgot" || left <= 0) {
      button.disabled = false;
      button.textContent = mode === "forgot" ? t("Send the link again") : COPY[mode].submit;
      return;
    }
    button.disabled = true;
    button.textContent = t("Send again in {n} s", { n: left-- });
    setTimeout(tick, 1000);
  };
  tick();
}

async function saveNewPassword(password) {
  if (!resetToken) {
    return showError(t("This page needs the link from the email. Ask for a new one below."));
  }
  if (!checkPassword()) return showError(t("Your new password still misses one of the rules below."), "password");
  if (password !== $("#confirm").value) return showError(t("The two passwords don't match."), "confirm");
  const button = $("#submit");
  button.disabled = true;
  button.textContent = t("Saving…");
  try {
    const { res, data } = await postJSON("/api/auth/reset", { token: resetToken, password });
    if (res.ok) { enter(); return; }
    serverError(data);
  } catch (err) {
    showError(t("Couldn't reach the server ({error}).", { error: err.message }));
  }
  button.disabled = false;
  button.textContent = COPY.reset.submit;
}

/* ------------------------------------------------------------ visitors */
async function enterAsVisitor() {
  const button = $("#guest");
  button.disabled = true;
  button.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-entrance"/></svg>${esc(t("Opening…"))}`;
  try {
    const res = await fetch("/api/auth/guest", { method: "POST" });
    if (res.ok) { enter(); return; }
    showError(t("Couldn't open the campus assistant. Try again."));
  } catch (err) {
    showError(t("Couldn't reach the server ({error}).", { error: err.message }));
  }
  button.disabled = false;
  button.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-entrance"/></svg>${esc(t("Continue as a visitor"))}`;
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
  $("#pw-toggle").textContent = shown ? t("Show") : t("Hide");
  $("#pw-toggle").setAttribute("aria-label", shown ? t("Show password") : t("Hide password"));
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
