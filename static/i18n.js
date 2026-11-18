"use strict";

/* The interface language (US21). The server sends each page already in its
   language (app/pages.py) with the texts its scripts write in
   window.SDU_I18N; t() and tn() look them up, keeping the English when a text
   has no translation. The switch stores the choice in the `sdu-lang` cookie, so
   the server sends every page, answer and message in it, and loads the page
   again. Nothing is translated by a machine. */

(() => {
  const data = window.SDU_I18N || { lang: "en", strings: {} };
  const LANGS = [
    { id: "en", short: "EN", name: "English" },
    { id: "ru", short: "RU", name: "Русский" },
    { id: "kk", short: "ҚАЗ", name: "Қазақша" },
  ];
  const fill = (text, values) => (values
    ? text.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m))
    : text);

  function plural(n) {
    n = Math.abs(n);
    if (data.lang === "ru") {
      if (n % 10 === 1 && n % 100 !== 11) return 0;
      if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 1;
      return 2;
    }
    if (data.lang === "kk") return 0;
    return n === 1 ? 0 : 1;
  }

  window.LANG = data.lang;
  // the locale dates and times are written in
  window.LOCALE = { en: "en-GB", ru: "ru-RU", kk: "kk-KZ" }[data.lang] || "en-GB";

  window.t = (text, values) => {
    let found = data.strings[text];
    if (Array.isArray(found)) found = found[0];
    return fill(found || text, values);
  };

  window.tn = (n, one, other, values) => {
    let forms = data.strings[one];
    if (typeof forms === "string") forms = [forms];
    const all = { n, ...(values || {}) };
    if (!forms || !forms.length) return fill(n === 1 ? one : other, all);
    return fill(forms[Math.min(plural(n), forms.length - 1)], all);
  };

  function choose(id) {
    document.cookie = `sdu-lang=${id}; path=/; max-age=31536000; samesite=lax`;
    location.reload();
  }

  const icon = (name) => `<svg class="i" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function mount(host, n) {
    const here = LANGS.find((l) => l.id === data.lang) || LANGS[0];
    const menuId = `lang-menu-${n}`;
    host.innerHTML = `
      <button type="button" class="theme-btn lang-btn" aria-haspopup="true" aria-expanded="false" aria-controls="${menuId}"
        aria-label="${t("Language: {name}. Change language", { name: here.name })}" title="${t("Language")}">
        ${icon("globe")}<span class="lang-code">${here.short}</span></button>
      <div class="theme-menu lang-menu" id="${menuId}" role="radiogroup" aria-label="${t("Language")}" hidden>
        ${LANGS.map((l) => `
          <button type="button" role="radio" class="theme-opt" data-lang-id="${l.id}" lang="${l.id}" aria-checked="${l.id === data.lang}">
            <span class="lang-tag" aria-hidden="true">${l.short}</span>
            <span class="opt-text"><b>${l.name}</b></span>
          </button>`).join("")}
      </div>`;
    const btn = host.querySelector(".lang-btn");
    const menu = host.querySelector(".lang-menu");
    const opts = [...menu.querySelectorAll(".theme-opt")];
    const open = (yes) => {
      menu.hidden = !yes;
      btn.setAttribute("aria-expanded", String(yes));
      if (yes) (opts.find((o) => o.getAttribute("aria-checked") === "true") || opts[0]).focus();
    };
    btn.addEventListener("click", () => open(menu.hidden));
    opts.forEach((o, i) => {
      o.addEventListener("click", () => {
        if (o.dataset.langId === data.lang) { open(false); btn.focus(); return; }
        choose(o.dataset.langId);
      });
      o.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          opts[(i + (e.key === "ArrowDown" ? 1 : opts.length - 1)) % opts.length].focus();
        }
      });
    });
    document.addEventListener("click", (e) => { if (!host.contains(e.target)) open(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { open(false); btn.focus(); } });
  }

  const mountAll = () => document.querySelectorAll("[data-lang-switch]").forEach(mount);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAll);
  else mountAll();
})();
