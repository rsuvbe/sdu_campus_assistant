"use strict";

/* The service worker behind class reminders (static/reminders.js). It does one
   thing: show a reminder as a system notification, and open the way to the class
   when it is pressed. It caches nothing, so the site works as it always has. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil((async () => {
    // a tab of the site already open keeps its session: use it
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of open) {
      if (new URL(client.url).origin !== self.location.origin) continue;
      try {
        await client.focus();
        // a page this worker doesn't control can't be sent elsewhere: a new tab then
        const moved = "navigate" in client ? await client.navigate(url) : null;
        if (moved) return moved;
      } catch { /* fall through to a new tab */ }
      break;
    }
    return self.clients.openWindow(url);
  })());
});
