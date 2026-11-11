"use strict";

/* What an event poster's text says about its time and place.

   The events page reads an SDU Life poster in the administrator's browser
   (tesseract.js) and hands the words to readPoster(). What it finds only fills
   in the correction form: the reader takes 17:30 for 17:50 and drops the 1 of
   18:00 often enough that nothing is saved before a person has compared it
   with the picture.

   Only times written with a colon count ("12.11" is a date, not 12:11), and the
   day stays SDU Life's: a poster's date is read less reliably than its hours.
   Places are halls, blocks and zones as the posters name them. */

const PosterOCR = (() => {
  const TIME = /\b([01]?\d|2[0-3]):([0-5]\d)\b(?:\s*[-–—]\s*([01]?\d|2[0-3]):([0-5]\d)\b)?/g;
  const PLACE = new RegExp([
    String.raw`\b(?:mini\s+)?(?:red|blue|green|sport|main|conference|assembly)\s+hall\b`,
    String.raw`\b(?:wi-?fi|shanyraq)\s+zone\b`,
    String.raw`\b[A-J]\d{3}\b`,
    String.raw`\b[A-J](?:\s*[-–]\s*[A-J])?\s+(?:block|блок)s?\b`,
  ].join("|"), "gi");

  const pad = (n) => String(n).padStart(2, "0");
  const tidy = (s) => s.replace(/\s+/g, " ").replace(/\s*[-–]\s*/g, "-").trim();
  // "BLUE HALL" -> "Blue Hall", "G-H BLOCK" -> "G-H block", "f202" -> "F202"
  const title = (s) => /^[a-j]\d{3}$/i.test(s) ? s.toUpperCase()
    : s.replace(/\b([a-z])([a-z]*)\b/gi, (w, a, b) => (/^(block|blocks|блок)$/i.test(w) ? w.toLowerCase()
      : w.length === 1 ? w.toUpperCase() : a.toUpperCase() + b.toLowerCase()))
      .replace(/\bWi-?fi\b/i, "WiFi");

  function readPoster(text) {
    const flat = String(text || "").replace(/[|]/g, " ").replace(/\s+/g, " ");
    const times = [];
    for (const m of flat.matchAll(TIME)) {
      times.push({ start: `${pad(m[1])}:${m[2]}`, end: m[3] ? `${pad(m[3])}:${m[4]}` : null });
    }
    // a range says more than a lone hour
    const time = times.find((t) => t.end) || times[0] || null;
    const places = [];
    for (const m of flat.matchAll(PLACE)) {
      const p = title(tidy(m[0]));
      if (!places.some((q) => q.toLowerCase() === p.toLowerCase())) places.push(p);
    }
    // a hall or a room says more than a block
    places.sort((a, b) => /block|блок/i.test(a) - /block|блок/i.test(b));
    return { start: time?.start || null, end: time?.end || null, places };
  }

  return { readPoster };
})();

if (typeof module !== "undefined") module.exports = PosterOCR;
