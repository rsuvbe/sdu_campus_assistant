"use strict";

/* The theme menu, shared by the app and the sign-in page.
   No stored choice: follow the device (light or dark). A stored choice sets
   data-theme on <html>; the inline snippet in each page's <head> applies it
   before the first paint, so the page never flashes the wrong theme. */

(() => {
  const KEY = "sdu-theme";
  const THEMES = [
    { id: "", label: "Match device", icon: "device", note: "Light or dark, as your device is set" },
    { id: "light", label: "Light", icon: "sun", note: "SDU navy on white card stock" },
    { id: "dark", label: "Dark", icon: "moon", note: "The same card at night" },
    { id: "steppe", label: "Steppe", icon: "steppe", note: "Sky teal and sun gold" },
  ];
  // the browser's own chrome follows the band colour of the theme
  const BAR = { light: "#2F345C", dark: "#2F345C", steppe: "#0D4A5C" };

  const read = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
  const write = (id) => { try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY); } catch { /* private mode */ } };
  const icon = (name) => `<svg class="i" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function apply(id) {
    const root = document.documentElement;
    if (id) root.dataset.theme = id; else delete root.dataset.theme;
    const dark = id === "dark" || (!id && matchMedia("(prefers-color-scheme: dark)").matches);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = BAR[id || (dark ? "dark" : "light")];
  }

  function mount(host) {
    host.innerHTML = `
      <button type="button" class="theme-btn" aria-haspopup="true" aria-expanded="false" aria-controls="theme-menu"></button>
      <div class="theme-menu" id="theme-menu" role="radiogroup" aria-label="Theme" hidden>
        ${THEMES.map((t) => `
          <button type="button" role="radio" class="theme-opt" data-theme-id="${t.id}" aria-checked="false">
            <span class="swatch ${t.id ? `sw-${t.id}` : "sw-auto"}" aria-hidden="true"></span>
            <span class="opt-text"><b>${t.label}</b><small>${t.note}</small></span>
          </button>`).join("")}
      </div>`;
    const btn = host.querySelector(".theme-btn");
    const menu = host.querySelector(".theme-menu");
    const opts = [...menu.querySelectorAll(".theme-opt")];

    const sync = () => {
      const current = read();
      const t = THEMES.find((x) => x.id === current) || THEMES[0];
      btn.innerHTML = `${icon(t.icon)}<span class="theme-label">${t.label}</span>`;
      btn.setAttribute("aria-label", `Theme: ${t.label}. Change theme`);
      btn.title = `Theme: ${t.label}`;
      opts.forEach((o) => o.setAttribute("aria-checked", String(o.dataset.themeId === current)));
    };
    const open = (yes) => {
      menu.hidden = !yes;
      btn.setAttribute("aria-expanded", String(yes));
      if (yes) (opts.find((o) => o.getAttribute("aria-checked") === "true") || opts[0]).focus();
    };

    btn.addEventListener("click", () => open(menu.hidden));
    opts.forEach((o, i) => {
      o.addEventListener("click", () => { write(o.dataset.themeId); apply(o.dataset.themeId); sync(); open(false); btn.focus(); });
      o.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          opts[(i + (e.key === "ArrowDown" ? 1 : opts.length - 1)) % opts.length].focus();
        }
      });
    });
    document.addEventListener("click", (e) => { if (!host.contains(e.target)) open(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { open(false); btn.focus(); } });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => apply(read()));
    sync();
  }

  apply(read());
  document.querySelectorAll("[data-theme-switch]").forEach(mount);
})();
