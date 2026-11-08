"use strict";

/* Reading a timetable off a screenshot of the student portal's "Course Schedule"
   (US17): days across, hours down, each hour a cell with

       INF 304  [04-P]  (teacher icon)
       (house icon): F202

   Everything runs in the browser: tesseract.js reads the words, this file finds
   the table and puts each word in its cell. Nothing is sent anywhere.

   The steps, each a pure function so they can be checked outside a browser:
     findGrid(img)            the table's lines, from the portal's yellow borders
     prepare(img, scale)      a bigger black-on-white copy for the OCR, icons wiped out
     readTable(words, grid)   the words, cell by cell, into classes
   `img` is anything shaped like ImageData: { width, height, data (RGBA) }. */

(function (root) {
  const DAY_KEYS = { mo: 0, tu: 1, we: 2, th: 3, fr: 4, sa: 5, su: 6,
                     mon: 0, tue: 1, wed: 2, thu: 3, fri: 4, sat: 5, sun: 6 };

  const px = (img, x, y) => {
    const i = (y * img.width + x) * 4;
    return [img.data[i], img.data[i + 1], img.data[i + 2]];
  };

  // the portal draws its table in one warm yellow, (250, 209, 99)
  const isLine = (r, g, b) => r > 215 && g > 165 && g < 235 && b < 160 && r - b > 80;

  /* Where a long run of line pixels crosses: the x of every column border and
     the y of every row border. A border is a line that runs across most of the
     table, so text and icons never count as one. */
  function findGrid(img) {
    const { width: w, height: h } = img;
    const colHits = new Array(w).fill(0);
    const rowHits = new Array(h).fill(0);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const [r, g, b] = px(img, x, y);
        if (isLine(r, g, b)) { colHits[x]++; rowHits[y]++; }
      }
    }
    const peaks = (hits, min) => {
      const out = [];
      hits.forEach((n, i) => {
        if (n < min) return;
        // a border drawn two pixels wide is one border
        if (out.length && i - out[out.length - 1].end <= 2) { out[out.length - 1].end = i; return; }
        out.push({ start: i, end: i });
      });
      return out.map((p) => (p.start + p.end) / 2);
    };
    // a border spans at least a third of the picture's other side
    const xs = peaks(colHits, h / 3);
    const ys = peaks(rowHits, w / 3);
    return xs.length >= 3 && ys.length >= 3 ? { xs, ys } : null;
  }

  /* A copy `scale` times larger where text is black and the rest is white. The
     portal writes in blue (the course) and grey (the group, the room, the hours);
     the house and the teacher are coloured pictures, and go, so that "I 301"
     isn't read as "A:1301". */
  function prepare(img, scale) {
    const { width: w, height: h } = img;
    const W = Math.round(w * scale), H = Math.round(h * scale);
    const out = new Uint8ClampedArray(W * H * 4);
    for (let Y = 0; Y < H; Y++) {
      const sy = Math.min(h - 1.001, Math.max(0, (Y + 0.5) / scale - 0.5));
      const y0 = Math.floor(sy), fy = sy - y0;
      for (let X = 0; X < W; X++) {
        const sx = Math.min(w - 1.001, Math.max(0, (X + 0.5) / scale - 0.5));
        const x0 = Math.floor(sx), fx = sx - x0;
        let ink = 0;
        // bilinear over the four neighbours' ink, so the letters stay smooth
        for (const [dx, dy, wt] of [[0, 0, (1 - fx) * (1 - fy)], [1, 0, fx * (1 - fy)],
                                    [0, 1, (1 - fx) * fy], [1, 1, fx * fy]]) {
          const [r, g, b] = px(img, x0 + dx, y0 + dy);
          ink += wt * inkOf(r, g, b);
        }
        const v = ink > 0.45 ? 0 : 255;
        const o = (Y * W + X) * 4;
        out[o] = out[o + 1] = out[o + 2] = v;
        out[o + 3] = 255;
      }
    }
    return { width: W, height: H, data: out };
  }

  /* How much a pixel looks like writing, 0..1: grey from black to mid grey, or
     the portal's link blue. Any other colour (an icon, a fill, a border) is none. */
  function inkOf(r, g, b) {
    const hi = Math.max(r, g, b), lo = Math.min(r, g, b);
    if (hi - lo < 28) return Math.max(0, Math.min(1, (215 - (r + g + b) / 3) / 110));   // grey
    if (b > 150 && Math.abs(r - g) < 30 && b - r > 60) return Math.max(0, Math.min(1, (b - r) / 160));  // blue
    return 0;
  }

  const timeOf = (s) => {
    const m = /^(\d{1,2})[:.](\d{2})$/.exec(s);
    return m && +m[1] < 24 && +m[2] < 60 ? `${m[1].padStart(2, "0")}:${m[2]}` : null;
  };
  const minutes = (t) => +t.slice(0, 2) * 60 + +t.slice(3);
  const hhmm = (n) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

  /* The table's cells out of the OCR words: which column is which day (from the
     header, or Mo..Sa in order), which row is which hour (from the times read in
     the first column; an hour the OCR missed is filled in from its neighbours,
     as the portal's rows are an hour apart), and what each cell says. */
  function readTable(words, grid, scale = 1) {
    const ws = words.map((w) => ({
      text: String(w.text || "").trim(),
      x: (w.bbox.x0 + w.bbox.x1) / 2 / scale, y: (w.bbox.y0 + w.bbox.y1) / 2 / scale,
      top: w.bbox.y0 / scale,
    })).filter((w) => w.text);
    const { xs, ys } = grid;
    const colOf = (x) => xs.findIndex((v, i) => i < xs.length - 1 && x > v && x < xs[i + 1]);
    const rowOf = (y) => ys.findIndex((v, i) => i < ys.length - 1 && y > v && y < ys[i + 1]);

    // the header row: the one where the day names are
    const days = {};
    let headerRow = -1;
    for (const w of ws) {
      const key = w.text.toLowerCase().replace(/[^a-z]/g, "");
      if (key in DAY_KEYS && colOf(w.x) > 0) {
        days[colOf(w.x)] = DAY_KEYS[key];
        headerRow = Math.max(headerRow, rowOf(w.y));
      }
    }
    const nCols = xs.length - 1;
    if (Object.keys(days).length < 2) {
      // no header read: the columns after the hours are Monday onwards
      for (let c = 1; c < nCols; c++) days[c] = c - 1;
    } else {
      // a day the OCR missed sits between the ones it read
      for (let c = 1; c < nCols; c++) {
        if (days[c] == null && days[c - 1] != null) days[c] = days[c - 1] + 1;
      }
    }

    // the hours: each row's first time is its start, the second its end
    const rows = [];
    for (let r = headerRow + 1; r < ys.length - 1; r++) {
      const times = ws.filter((w) => colOf(w.x) === 0 && rowOf(w.y) === r)
        .sort((a, b) => a.y - b.y).map((w) => timeOf(w.text)).filter(Boolean);
      rows.push({ r, start: times[0] || null, end: times[1] || null });
    }
    const known = rows.filter((row) => row.start);
    if (!known.length) return { classes: [], problem: "Couldn't read the hours in the first column." };
    /* The rows are an hour apart, so one offset fits them all: the one most of
       the times that were read agree on. A time read wrong ("1:30" for 11:30)
       is outvoted, and an hour the OCR missed is filled in. */
    const offset = mode(rows.filter((row) => row.start).map((row) => minutes(row.start) - rows.indexOf(row) * 60));
    const len = (() => {
      const pairs = rows.filter((row) => row.start && row.end).map((row) => minutes(row.end) - minutes(row.start))
        .filter((n) => n > 0 && n <= 60);
      return pairs.length ? mode(pairs) : 50;
    })();
    rows.forEach((row, i) => {
      row.start = hhmm(offset + i * 60);
      row.end = hhmm(offset + i * 60 + len);
    });

    // each cell: its words in reading order, then what they say
    const cells = [];
    for (const row of rows) {
      for (let c = 1; c < nCols; c++) {
        if (days[c] == null) continue;
        const inCell = ws.filter((w) => colOf(w.x) === c && rowOf(w.y) === row.r);
        if (!inCell.length) continue;
        const parsed = parseCell(lines(inCell));
        if (parsed) cells.push({ ...parsed, day: days[c], start: row.start, end: row.end, row: row.r });
      }
    }
    return { classes: merge(agree(cells)), problem: null };
  }

  function mode(list) {
    const n = {};
    list.forEach((v) => { n[v] = (n[v] || 0) + 1; });
    return +Object.keys(n).sort((a, b) => n[b] - n[a])[0];
  }

  // a cell's words as lines of text, top to bottom
  function lines(words) {
    const sorted = [...words].sort((a, b) => a.top - b.top);
    const out = [];
    for (const w of sorted) {
      const line = out.find((l) => Math.abs(l.y - w.y) < 6);
      if (line) line.words.push(w); else out.push({ y: w.y, words: [w] });
    }
    return out.sort((a, b) => a.y - b.y)
      .map((l) => l.words.sort((a, b) => a.x - b.x).map((w) => w.text).join(" "));
  }

  /* "INF 304 [04-P]" and ": F202" -> the course, its group and the room. The OCR
     mixes up look-alike characters, so they are put right where the place in the
     text says which one it must be: letters in a course code, digits after it. */
  function parseCell(textLines) {
    const text = textLines.join("\n");
    const course = /([A-Za-z0-9]{2,4})\s*[-_]?\s*([0-9OoIlSZB]{3}[A-Za-z]?)\b/.exec(text);
    if (!course) return null;
    const code = toLetters(course[1]);
    if (!/^[A-Z]{2,4}$/.test(code)) return null;
    const number = toDigits(course[2].slice(0, 3)) + course[2].slice(3).toUpperCase();
    const group = /[\[({]\s*([0-9OoIl]{1,2})\s*[-–—~.,_]?\s*([A-Za-z0-9?]{1,2})\s*[\])}]?/.exec(text);
    let section = null;
    if (group) {
      // the portal's groups end in P (practice) or N (lecture); a 7 or a ? is a P read badly
      const kind = group[2].toUpperCase().replace(/^[7?]$/, "P").replace(/^[^PNL]$/, "");
      section = `${toDigits(group[1]).padStart(2, "0")}${kind ? "-" + kind : ""}`;
    }
    // the room is on the line after the course
    const after = textLines.slice(textLines.findIndex((l) => course[0] && l.includes(course[1])) + 1).join(" ");
    const room = roomOf(after);
    return { subject: `${code} ${number}`, section, room };
  }

  const toLetters = (s) => s.toUpperCase().replace(/0/g, "O").replace(/1/g, "I").replace(/5/g, "S")
    .replace(/8/g, "B").replace(/2/g, "Z");
  const toDigits = (s) => s.replace(/[Oo]/g, "0").replace(/[Il|]/g, "1").replace(/S/g, "5")
    .replace(/Z/g, "2").replace(/B/g, "8");

  /* The room line: whatever the house icon left behind, a colon, then the room,
     or two rooms for a hall with two numbers ("I 110, I 111"): the first is
     enough to find it. The text is kept as read; the server matches it against
     the room directory, look-alike characters and icon crumbs included. */
  function roomOf(line) {
    const clean = line.replace(/^[^:]*:\s*/, "").replace(/^[^A-Za-z0-9]+/, "").trim();
    return clean.split(/[,;]/)[0].trim().replace(/\s+/g, " ");
  }

  /* One course is written the same way all over the table, so a code read short
     in one cell ("NF 321") is put right by the same course read whole in another
     ("INF 321"): of the codes with one number, a code inside a longer one is that one. */
  function agree(cells) {
    const byNumber = {};
    for (const c of cells) {
      const [code, number] = c.subject.split(" ");
      (byNumber[number] ||= new Set()).add(code);
    }
    return cells.map((c) => {
      const [code, number] = c.subject.split(" ");
      const whole = [...byNumber[number]].filter((k) => k !== code && k.includes(code))
        .sort((a, b) => b.length - a.length)[0];
      return whole ? { ...c, subject: `${whole} ${number}` } : c;
    });
  }

  /* An hour cell after an hour cell of the same course, group and room is one
     class that runs over both: INF 376 at 09:30 and at 10:30 is 09:30–11:20. */
  function merge(cells) {
    const key = (c) => `${c.day}|${c.subject}|${c.section}|${c.room}`;
    const sorted = [...cells].sort((a, b) => a.day - b.day || a.row - b.row);
    const out = [];
    for (const c of sorted) {
      const last = out[out.length - 1];
      if (last && key(last) === key(c) && last.lastRow === c.row - 1) {
        last.end = c.end;
        last.lastRow = c.row;
      } else {
        out.push({ ...c, lastRow: c.row });
      }
    }
    return out.map(({ row, lastRow, ...c }) => c);
  }

  const api = { findGrid, prepare, readTable, parseCell, roomOf, merge, agree };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ScheduleOCR = api;
})(typeof self !== "undefined" ? self : this);
