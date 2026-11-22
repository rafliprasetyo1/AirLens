// Membangun logo AirLens sebagai SVG mandiri (teks diubah ke path, jadi tidak butuh font terpasang).
const fs = require("fs");
const path = require("path");
const opentype = require("opentype.js");

const FONT_DIR = path.join(__dirname, "..", "node_modules", "@fontsource");
const font = (pkg, w) => opentype.loadSync(path.join(FONT_DIR, pkg, "files", `${pkg}-latin-${w}-normal.woff`));
const sg600 = font("space-grotesk", 600);
const sg700 = font("space-grotesk", 700);
const inter600 = font("inter", 600);

const C = {
  navy: "#0F3D52",   // selaras dengan biru tua logo kampus
  sky: "#2BA8E0",    // selaras dengan biru HIMASISTIFO
  amber: "#F2994A",  // titik "lokasimu" / peringatan
  paper: "#FFFFFF",
  night: "#0B1F2A",
};

// Lambang: cincin lensa yang terbuka di kanan, tiga garis angin; garis tengah keluar lewat celah dan berakhir di titik.
function mark({ ring, wind, dot }, x = 0, y = 0, s = 1) {
  const r = 80, cx = 100, cy = 100, gap = 21 * Math.PI / 180;
  const p = (a) => [(cx + r * Math.cos(a)).toFixed(2), (cy + r * Math.sin(a)).toFixed(2)];
  const [x1, y1] = p(gap), [x2, y2] = p(-gap);
  return `<g transform="translate(${x} ${y}) scale(${s})" fill="none" stroke-linecap="round">
    <path d="M${x1} ${y1} A${r} ${r} 0 1 1 ${x2} ${y2}" stroke="${ring}" stroke-width="15"/>
    <path d="M50 72 H116 A15 15 0 1 0 101 57" stroke="${wind}" stroke-width="12"/>
    <path d="M38 100 H168" stroke="${wind}" stroke-width="12"/>
    <path d="M66 128 H122 A13 13 0 1 1 109 141" stroke="${wind}" stroke-width="12"/>
    <circle cx="193" cy="100" r="10" fill="${dot}" stroke="none"/>
  </g>`;
}

function textPath(f, str, x, y, size, fill, tracking = 0) {
  let d = "", cx = x;
  for (const ch of str) {
    const g = f.charToGlyph(ch);
    d += g.getPath(cx, y, size).toPathData(2);
    cx += (g.advanceWidth / f.unitsPerEm) * size + tracking;
  }
  return { svg: `<path d="${d}" fill="${fill}"/>`, end: cx };
}

function horizontal(theme) {
  const dark = theme === "dark";
  const ring = dark ? C.paper : C.navy, word2 = dark ? C.paper : C.navy;
  const tag = dark ? "#9FC7DA" : "#4E6E7E";
  const a = textPath(sg600, "Air", 250, 128, 104, C.sky, -2);
  const b = textPath(sg700, "Lens", a.end + 2, 128, 104, word2, -2);
  const t = textPath(inter600, "HYPERLOCAL AIR, EXPLAINED", 254, 176, 25, tag, 3.2);
  const w = Math.ceil(Math.max(b.end, t.end) + 30);
  const bg = dark ? `<rect width="${w}" height="220" fill="${C.night}"/>` : "";
  return { w, svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} 220" width="${w}" height="220">
  ${bg}${mark({ ring, wind: C.sky, dot: C.amber }, 10, 10, 1)}${a.svg}${b.svg}${t.svg}</svg>` };
}

function icon(theme) {
  const dark = theme === "dark";
  const bg = dark ? C.night : C.paper;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <rect width="256" height="256" rx="56" fill="${bg}"/>${mark({ ring: dark ? C.paper : C.navy, wind: C.sky, dot: C.amber }, 22, 28, 1)}</svg>`;
}

const out = __dirname;
for (const th of ["light", "dark"]) {
  fs.writeFileSync(path.join(out, `airlens_logo_${th}.svg`), horizontal(th).svg);
  fs.writeFileSync(path.join(out, `airlens_icon_${th}.svg`), icon(th));
}
console.log("ok", horizontal("light").w);
