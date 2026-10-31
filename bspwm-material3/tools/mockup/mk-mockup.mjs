// mk-mockup.mjs — честный «скриншот» десктопа bspwm-material3.
// Компонует SVG из РЕАЛЬНЫХ артефактов темы (polybar/colors.ini, Xresources,
// theme.json, обои) и рендерит в PNG через @resvg/resvg-js.
//
//   node tools/mockup/mk-mockup.mjs [out.png]
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { Resvg } = require("@resvg/resvg-js");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");

//----------------------------------------------------------------------------
// 1. Данные из сгенерированных файлов темы
//----------------------------------------------------------------------------
const colorsIni = readFileSync(path.join(ROOT, "polybar/colors.ini"), "utf8");
const pb = {};
for (const m of colorsIni.matchAll(/^\s*([a-z0-9-]+)\s*=\s*(#ff[0-9a-f]{6})\s*$/gim))
  pb[m[1]] = "#" + m[2].slice(3);           // #AARRGGBB → #RRGGBB

const xres = readFileSync(path.join(ROOT, "generated/Xresources.md3"), "utf8");
const ansi = {};
for (const m of xres.matchAll(/\*color(\d+):\s*(#[0-9a-f]{6})/gi)) ansi[+m[1]] = m[2];

const theme = JSON.parse(readFileSync(path.join(ROOT, "generated/theme.json"), "utf8"));
const R = theme.roles;

const C = {
  barBg:      pb["bar-bg"]      ?? R.surfaceContainer,
  barFg:      pb["bar-fg"]      ?? R.onSurface,
  clockBg:    pb["clock-bg"]    ?? R.primaryContainer,
  clockFg:    pb["clock-fg"]    ?? R.onPrimaryContainer,
  primary:    R.primary,
  onSurface:  R.onSurface,
  osv:        R.onSurfaceVariant,
  outline:    R.outline,
  outVar:     R.outlineVariant,
  primCont:   R.primaryContainer,
  onPrimCont: R.onPrimaryContainer,
  secCont:    R.secondaryContainer,
  tert:       R.tertiary,
  error:      R.error,
  surface:    R.surface,
  surfLow:    pb["surface-container-lowest"] ?? "#0f0d13",
  termBg:     pb["surface-container-lowest"] ?? "#0f0d13",
};

const W = 1920, H = 1080, BAR_H = 38, GAP = 12, BORD = 2, RAD = 12;

//----------------------------------------------------------------------------
// 2. SVG-хелперы
//----------------------------------------------------------------------------
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const out = [];
const rect = (x, y, w, h, fill, extra = "") =>
  out.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" ${extra}/>`);
const rrect = (x, y, w, h, r, fill, extra = "") =>
  out.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" ${extra}/>`);
// текст с цветными сегментами: segs = [[color, str], …]
function txt(x, y, segs, size = 15, extra = "") {
  const tsp = segs.map(([c, s]) => `<tspan fill="${c}">${esc(s)}</tspan>`).join("");
  out.push(`<text x="${x}" y="${y}" font-size="${size}" xml:space="preserve" ${extra}>${tsp}</text>`);
}
const ADV = (size) => size * 0.6;   // JetBrains Mono: advance = 0.6em

//----------------------------------------------------------------------------
// 3. Обои + панель
//----------------------------------------------------------------------------
const wp = readFileSync(path.join(ROOT, "wallpapers/md3-dark.png")).toString("base64");
out.push(`<image x="0" y="0" width="${W}" height="${H}" href="data:image/png;base64,${wp}" preserveAspectRatio="xMidYMid slice"/>`);

// панель (elevation 2)
rect(0, 0, W, BAR_H, C.barBg);
out.push(`<defs><filter id="winsh" x="-20%" y="-20%" width="140%" height="140%">
<feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000000" flood-opacity="0.5"/>
</filter></defs>`);

// -- модули слева: workspace-пилюли + заголовок окна
let x = 10;
const ws = [
  { n: "1", st: "focused" }, { n: "2", st: "occ" }, { n: "3", st: "occ" },
  { n: "4", st: "occ" }, { n: "5", st: "urgent" }, { n: "6", st: "free" },
];
for (const w of ws) {
  if (w.st === "focused") {
    rrect(x, 7, 26, 24, 8, C.primCont);
    txt(x + 13 - ADV(13) / 2, 24, [[C.onPrimCont, w.n]], 13);
  } else if (w.st === "free") {
    txt(x + 13 - ADV(13) / 2, 24, [[C.outVar, w.n]], 13);
  } else {
    txt(x + 13 - ADV(13) / 2, 24, [[w.st === "urgent" ? C.error : C.osv, w.n]], 13);
  }
  x += 30;
}
x += 6;
rect(x, 11, 1, 16, C.outVar); x += 10;                      // sep
txt(x, 24, [[C.osv, "htop — bspwm-material3 — alacritty"]], 13);

// -- модули справа (cpu mem volume battery network date powermenu)
const dot = (cx, color) => out.push(`<circle cx="${cx}" cy="19" r="4" fill="${color}"/>`);
let rx = W - 14;
// powermenu: кружок с насечкой
out.push(`<circle cx="${rx - 8}" cy="19" r="7" fill="none" stroke="${C.osv}" stroke-width="1.6"/>`);
out.push(`<line x1="${rx - 8}" y1="11" x2="${rx - 8}" y2="18" stroke="${C.osv}" stroke-width="1.6"/>`);
rx -= 26;
rect(rx - 8, 11, 1, 16, C.outVar); rx -= 14;               // sep
// date (clock-bg)
const clock = "21:34";
const cw = clock.length * ADV(13) + 24;
rect(rx - cw, 0, cw, BAR_H, C.clockBg);
txt(rx - cw + 12, 24, [[C.clockFg, clock]], 13);
rx -= cw + 8;
rect(rx - 6, 11, 1, 16, C.outVar); rx -= 12;
// network
txt(rx - 34, 24, [[C.osv, "eth"]], 13); dot(rx - 44, C.outline); rx -= 48;
rect(rx - 6, 11, 1, 16, C.outVar); rx -= 12;
// battery
txt(rx - 36, 24, [[C.osv, "87%"]], 13); dot(rx - 46, C.osv); rx -= 50;
rect(rx - 6, 11, 1, 16, C.outVar); rx -= 12;
// volume
txt(rx - 36, 24, [[C.osv, "65%"]], 13); dot(rx - 46, R.secondary); rx -= 50;
rect(rx - 6, 11, 1, 16, C.outVar); rx -= 12;
// mem
txt(rx - 40, 24, [[C.osv, "3.1G"]], 13); dot(rx - 50, C.tert); rx -= 54;
rect(rx - 6, 11, 1, 16, C.outVar); rx -= 12;
// cpu
txt(rx - 36, 24, [[C.osv, "42%"]], 13); dot(rx - 46, C.primary); rx -= 50;

//----------------------------------------------------------------------------
// 4. Окна (bspwm: gap 12, border 2, picom radius 12)
//----------------------------------------------------------------------------
const topY = BAR_H + GAP, botY = H - GAP;
const leftW = 1156, rightX = GAP + leftW + GAP, rightW = W - rightX - GAP;

function window(x, y, w, h, border, draw) {
  out.push(`<g filter="url(#winsh)">`);
  rrect(x, y, w, h, RAD, border);
  rrect(x + BORD, y + BORD, w - 2 * BORD, h - 2 * BORD, RAD - 3, C.termBg);
  out.push(`</g>`);
  const id = `clip${x}_${y}`;
  out.push(`<clipPath id="${id}"><rect x="${x + BORD}" y="${y + BORD}" width="${w - 2 * BORD}" height="${h - 2 * BORD}" rx="${RAD - 3}"/></clipPath>`);
  out.push(`<g clip-path="url(#${id})">`);
  draw(x + BORD, y + BORD, w - 2 * BORD, h - 2 * BORD);
  out.push(`</g>`);
}

// ---- левое окно: htop ------------------------------------------------------
const bar = (load, kern) => {
  const seg = [];
  const cells = 20;
  const l = Math.round(cells * load), k = Math.round(cells * kern);
  seg.push([ansi[7], "["]);
  seg.push([ansi[2], "|".repeat(l)]);
  seg.push([ansi[1], "|".repeat(k)]);
  seg.push([ansi[8], "-".repeat(cells - l - k)]);
  seg.push([ansi[7], "]"]);
  return seg;
};
function htop(x, y, w, h) {
  const S = 15, LH = 23, x0 = x + 14;
  let ly = y + 30;
  const line = (segs) => { txt(x0, ly, segs, S); ly += LH; };
  line([[ansi[7], "  CPU "], ...bar(0.42, 0.06), [ansi[7], "  42.0%"],
        [ansi[7], "   CPU "], ...bar(0.13, 0.02), [ansi[7], "  13.2%"]]);
  line([[ansi[7], "  Mem "], ...bar(0.40, 0.0), [ansi[7], "  3.10G/7.68G"],
        [ansi[7], "   Swp "], ...bar(0.0, 0.0), [ansi[7], "     0K/0K"]]);
  line([[ansi[7], "  Uptime: 3 days, 4:12   Tasks: 41, 108 thr; 2 running   Load average: 0.52 0.48 0.41"]]);
  ly += 6;
  line([[ansi[12], "  PID USER      PRI  NI  VIRT   RES   SHR S CPU%  MEM%   TIME+  Command"]]);
  const procs = [
    [" 1412", "user   ", "  20   0  884M  312M  98M S  12.5   4.0   1:12.44", "firefox", ansi[7]],
    [" 2287", "user   ", "  20   0  512M  188M  61M S   8.3   2.4   0:41.09", "alacritty", ansi[7]],
    ["  934", "user   ", "  20   0  398M  121M  44M S   6.1   1.6   0:27.83", "picom", ansi[7]],
    [" 1876", "user   ", "  39  19  221M   64M  21M S   4.2   0.8   0:15.30", "polybar", ansi[7]],
    ["  611", "root   ", "  20   0  164M   38M  16M S   2.1   0.5   0:08.77", "Xorg", ansi[7]],
    [" 3120", "user   ", "  20   0  145M   29M  12M S   1.4   0.4   0:05.02", "htop", ansi[2]],
    ["  402", "root   ", "  20   0   98M   18M   9M S   0.7   0.2   0:03.44", "bspwm", ansi[4]],
    ["  289", "root   ", "  20   0   76M   12M   7M S   0.3   0.2   0:01.91", "sxhkd", ansi[4]],
    [" 1043", "user   ", "  20   0  312M   84M  30M S   0.2   1.1   0:09.18", "dunst", ansi[7]],
    ["  777", "user   ", "  20   0   64M   11M   6M S   0.1   0.1   0:00.62", "ssh-agent", ansi[7]],
    [" 2450", "user   ", "  20   0  267M   71M  26M S   0.1   0.9   0:04.87", "rofi", ansi[7]],
    ["    1", "root   ", "  20   0  168M   13M   8M S   0.0   0.2   0:04.25", "systemd", ansi[8]],
    ["    2", "root   ", "  20   0     0     0    0 S   0.0   0.0   0:00.02", "kthreadd", ansi[8]],
    ["   17", "root   ", "  20   0     0     0    0 S   0.0   0.0   0:00.41", "ksoftirqd/0", ansi[8]],
    ["   24", "root   ", "  20   0     0     0    0 S   0.0   0.0   0:00.19", "kworker/0:1", ansi[8]],
    ["   31", "root   ", "  20   0     0     0    0 S   0.0   0.0   0:00.07", "kdevtmpfs", ansi[8]],
    ["  102", "root   ", "  20   0     0     0    0 S   0.0   0.0   0:00.03", "kauditd", ansi[8]],
    ["  208", "root   ", "  20   0   45M    8M   5M S   0.0   0.1   0:00.94", "systemd-journald", ansi[8]],
    ["  244", "root   ", "  20   0   28M    6M   4M S   0.0   0.1   0:00.38", "systemd-udevd", ansi[8]],
    ["  512", "root   ", "  20   0   34M    9M   6M S   0.0   0.1   0:01.12", "NetworkManager", ansi[8]],
    ["  590", "root   ", "  20   0   22M    5M   3M S   0.0   0.1   0:00.27", "crond", ansi[8]],
    ["  648", "user   ", "  20   0   41M   10M   7M S   0.0   0.1   0:02.05", "pipewire", ansi[8]],
    ["  651", "user   ", "  20   0   39M    9M   6M S   0.0   0.1   0:01.44", "wireplumber", ansi[8]],
    ["  705", "user   ", "  20   0   58M   14M   9M S   0.0   0.2   0:03.61", "mako", ansi[8]],
    ["  812", "user   ", "  20   0  187M   46M  19M S   0.0   0.6   0:06.33", "pcmanfm", ansi[8]],
    ["  923", "user   ", "  20   0  143M   33M  15M S   0.0   0.4   0:02.88", "nvim", ansi[8]],
    [" 1187", "user   ", "  20   0  122M   27M  12M S   0.0   0.3   0:01.73", "zsh", ansi[8]],
  ];
  for (const [pid, usr, mid, cmd, col] of procs)
    line([[ansi[12], pid], [ansi[7], " " + usr], [col, mid], [col, "  " + cmd]]);
  // F-клавиши у нижней кромки
  const fy = y + h - 12;
  const fkeys = ["F1Help", "F2Setup", "F3Search", "F4Filter", "F5Tree", "F6SortBy", "F7Nice-", "F8Nice+", "F9Kill", "F10Quit"];
  const segs = [];
  for (const f of fkeys) segs.push([ansi[4], f.slice(0, 2)], [ansi[7], f.slice(2) + "  "]);
  txt(x0, fy, segs, S);
}

// ---- правое окно: md3_theme.py show ---------------------------------------
function themeshow(x, y, w, h) {
  const S = 14, LH = 22, x0 = x + 14;
  let ly = y + 28;
  const line = (segs) => { txt(x0, ly, segs, S); ly += LH; };
  line([[ansi[2], "$ "], [ansi[7], "python3 tools/md3_theme.py show"]]);
  line([[ansi[7], "seed        : "], [ansi[12], theme.seed], [ansi[8], "  (HCT hue 298.98 chroma 47.86)"]]);
  line([[ansi[7], "scheme      : "], [ansi[10], `${theme.scheme} / ${theme.contrast} / dark`]]);
  line([[ansi[7], "shape       : corner-radius "], [ansi[10], "12dp"], [ansi[8], " (md.sys.shape.medium)"]]);
  line([[ansi[7], "elevation   : level 2, shadow @ 0.32, blur 16px"]]);
  ly += 8;
  line([[ansi[7], "roles:"]]);
  const roles = ["primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
                 "secondaryContainer", "tertiary", "error", "surface", "onSurfaceVariant", "outlineVariant"];
  const swX = x0 + ADV(S) * 35;
  for (const r of roles) {
    const ty = ly;
    line([[ansi[7], "  " + r.padEnd(24)], [ansi[12], R[r]]]);
    rrect(swX, ty - 12, 46, 15, 4, R[r], `stroke="${C.outVar}" stroke-width="1"`);
  }
  ly += 8;
  line([[ansi[7], "contrast (WCAG):"]]);
  for (const row of (theme.contrastReport || []).slice(0, 6)) {
    const okk = row.ratio >= 4.5;
    line([[okk ? ansi[2] : ansi[1], okk ? "  [ok ] " : "  [LOW] "],
          [ansi[7], `${row.fg} on ${row.bg}`.padEnd(46)],
          [ansi[10], `${row.ratio.toFixed(2)}:1`]]);
  }
  ly += 8;
  line([[ansi[7], "tonal palette (md.ref.palette.primary):"]]);
  const tones = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100];
  const tw = 48, gapx = 4;
  tones.forEach((t, i) => {
    const hx = x0 + 2 + i * (tw + gapx);
    rrect(hx, ly - 4, tw, 26, 8, theme.palettes.primary[String(t)],
          `stroke="${C.outVar}" stroke-width="1"`);
    txt(hx + tw / 2 - ADV(10) * String(t).length / 2, ly + 34, [[C.osv, String(t)]], 10);
  });
  ly += 46;
  ly += 6;
  line([[ansi[2], "$ "], [ansi[7], " "]]);
  rect(x0 + ADV(S) * 2, ly - LH - 13, 8, 16, C.primary);   // курсор
}

window(GAP, topY, leftW, botY - topY, C.primary, htop);            // фокус: primary
window(rightX, topY, rightW, botY - topY, C.outVar, themeshow);    // неактивное: outlineVariant

//----------------------------------------------------------------------------
// 5. Рендер
//----------------------------------------------------------------------------
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs><style>text{font-family:"JetBrains Mono";}</style></defs>
${out.join("\n")}
</svg>`;
writeFileSync(path.join(HERE, "mockup.svg"), svg);

const resvg = new Resvg(svg, {
  fitTo: { mode: "width", value: W },
  font: { fontFiles: [path.join(HERE, "font.ttf")], loadSystemFonts: false, defaultFontFamily: "JetBrains Mono" },
});
const png = resvg.render().asPng();
const outPath = process.argv[2] ? path.resolve(process.argv[2]) : path.join(ROOT, "screenshot.png");
writeFileSync(outPath, png);
console.log("✔", outPath, png.length, "bytes");
