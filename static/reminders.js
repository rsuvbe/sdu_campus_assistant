"use strict";

/* Reminders before a class (US18): a note a few minutes before each class of the
   week, with its room and the way there. Every page of the site loads this, so
   a reminder comes in whichever page is open; the phone's calendar file
   (/api/schedule.ics) covers the time the site is closed.

   A system notification goes through a service worker (/sw.js): Android shows
   none from a page directly, and a press on it opens the way. A banner on the
   page comes too, so a reminder is seen even with notifications refused.

   Campus time is UTC+5, all year: Kazakhstan moved to it in March 2024 and keeps
   no summer time. The device's own time zone doesn't matter. */

(() => {
  const KEY = "sdu-remind";
  const SEEN = "sdu-reminded:";
  const OFFSET = 5 * 3600e3;
  const DAY = 864e5;
  const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
    del(key) { try { localStorage.removeItem(key); } catch { /* private mode */ } },
  };

  function settings() {
    try {
      const s = JSON.parse(store.get(KEY) || "{}");
      return { on: !!s.on, lead: [5, 10, 15, 30].includes(s.lead) ? s.lead : 10 };
    } catch { return { on: false, lead: 10 }; }
  }
  function save(next) {
    store.set(KEY, JSON.stringify({ ...settings(), ...next }));
    refresh();
  }

  const minutes = (hhmm) => +hhmm.slice(0, 2) * 60 + +hhmm.slice(3, 5);

  /* Now in campus time: the weekday (0 = Monday), the minute of the day, and the
     moment campus midnight was, as a real timestamp. */
  function campus(now = Date.now()) {
    const local = new Date(now + OFFSET);
    const minute = local.getUTCHours() * 60 + local.getUTCMinutes();
    const midnight = now - (minute * 6e4 + local.getUTCSeconds() * 1e3 + local.getUTCMilliseconds());
    return { day: (local.getUTCDay() + 6) % 7, minute, midnight };
  }

  /* When a class next starts, as a timestamp: later today, or on its day this
     week or next. A class under way has started; its next start is a week on. */
  function nextStart(entry, now = Date.now()) {
    const c = campus(now);
    let at = c.midnight + ((entry.day - c.day + 7) % 7) * DAY + minutes(entry.start) * 6e4;
    if (at <= now) at += 7 * DAY;
    return at;
  }

  /* The class on now and the next one to start, as the "next class" answer finds them. */
  function nextClass(classes, now = Date.now()) {
    if (!classes.length) return { onNow: null, next: null, at: null };
    const c = campus(now);
    const onNow = classes.find((e) => e.day === c.day && minutes(e.start) <= c.minute && c.minute < minutes(e.end)) || null;
    let next = null, at = Infinity;
    for (const e of classes) {
      const t = nextStart(e, now);
      if (t < at) { at = t; next = e; }
    }
    return { onNow, next, at };
  }

  /* "today", "tomorrow", "on Thursday", "next Monday", from campus time. */
  function whenSaid(at, now = Date.now()) {
    const days = Math.round((campus(at).midnight - campus(now).midnight) / DAY);
    if (days === 0) return "today";
    if (days === 1) return "tomorrow";
    const name = DAY_NAMES[campus(at).day];
    return days >= 7 ? `next ${name}` : `on ${name}`;
  }

  // the way to the next class: the assistant starts it from the class before
  const NEXT_ROUTE = `/?ask=${encodeURIComponent("How do I get to my next class?")}`;
  const routeTo = (entry) => `/?ask=${encodeURIComponent(`How do I get to ${entry.room_value}?`)}`;

  /* ------------------------------------------------------------ the watch */
  let classes = null;
  let loading = null;
  let timer = null;

  async function load() {
    if (loading) return loading;
    loading = (async () => {
      try {
        const res = await fetch("/api/schedule", { headers: { Accept: "application/json" } });
        classes = res.ok ? (await res.json()).classes : [];
      } catch { /* offline: keep what we had */ }
      loading = null;
    })();
    return loading;
  }

  function setClasses(list) {
    classes = list;
    check();
  }

  async function refresh() {
    clearInterval(timer);
    timer = null;
    if (!settings().on) return;
    if (classes === null) await load();
    registerWorker();
    check();
    // every 20 seconds: a hidden tab's timers slow down, and a laptop sleeps;
    // checking the clock again survives both
    timer = setInterval(check, 20e3);
  }

  function check() {
    const s = settings();
    if (!s.on || !classes) return;
    const now = Date.now();
    for (const entry of classes) {
      const at = nextStart(entry, now - 1);          // not yet begun
      if (now >= at - s.lead * 6e4 && now < at) remind(entry, at);
    }
  }

  function remind(entry, at) {
    const key = `${SEEN}${entry.class_id}:${at}`;
    if (store.get(key)) return;                     // another tab has said it
    store.set(key, "1");
    forgetOld();
    const mins = Math.max(1, Math.round((at - Date.now()) / 6e4));
    const title = `${entry.subject} in ${mins} min`;
    const place = entry.on_campus === false ? entry.room_label : `${entry.room_label}, ${entry.where}`;
    const url = entry.on_campus === false ? "/schedule" : NEXT_ROUTE;
    banner(entry, mins, url);
    notify(title, `${entry.start}–${entry.end} · ${place}${entry.on_campus === false ? "" : ". Tap for the way there."}`, key, url);
  }

  function forgetOld() {
    try {
      const old = Date.now() - 2 * DAY;
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && k.startsWith(SEEN) && +k.split(":").pop() < old) localStorage.removeItem(k);
      }
    } catch { /* private mode */ }
  }

  /* ------------------------------------------------------- what is shown */
  let worker = null;
  function registerWorker() {
    if (worker || !("serviceWorker" in navigator)) return;
    worker = navigator.serviceWorker.register("/sw.js").catch(() => null);
  }

  async function notify(title, body, tag, url) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const options = { body, tag, data: { url }, icon: "/static/img/favicon.png", badge: "/static/img/favicon.png" };
    try {
      const reg = worker && await worker;
      if (reg && reg.showNotification) { await reg.showNotification(title, options); return; }
      const n = new Notification(title, options);
      n.onclick = () => { window.focus(); location.href = url; n.close(); };
    } catch { /* the banner is still there */ }
  }

  function banner(entry, mins, url) {
    document.querySelector(".reminder-toast")?.remove();
    const box = document.createElement("aside");
    box.className = "reminder-toast";
    box.setAttribute("role", "status");
    const where = entry.on_campus === false ? `${esc(entry.room_label)} · no longer in the room directory`
      : `${esc(entry.room_label)} · ${esc(entry.where)}`;
    box.innerHTML = `
      <p class="reminder-kicker">In ${mins} min · ${esc(entry.start)}–${esc(entry.end)}</p>
      <p class="reminder-title">${esc(entry.subject)}</p>
      <p class="reminder-where">${where}</p>
      <div class="reminder-actions">
        ${entry.on_campus === false ? "" : `<a class="btn-go" href="${url}">How do I get there</a>`}
        <button type="button" class="btn-text" data-dismiss>Dismiss</button>
      </div>`;
    box.querySelector("[data-dismiss]").addEventListener("click", () => box.remove());
    document.body.append(box);
    // gone once the class has begun
    setTimeout(() => box.remove(), (mins + 10) * 6e4);
  }

  async function askPermission() {
    if (!("Notification" in window)) return "unsupported";
    if (Notification.permission !== "default") return Notification.permission;
    try { return await Notification.requestPermission(); } catch { return "denied"; }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && settings().on) load().then(check);
  });
  // a change made in another tab
  window.addEventListener("storage", (e) => { if (e.key === KEY) refresh(); });

  window.SDUReminders = { settings, save, refresh, setClasses, askPermission, campus, nextStart,
                          nextClass, whenSaid, minutes, routeTo, NEXT_ROUTE, DAY_NAMES };
  if (settings().on) refresh();
})();
