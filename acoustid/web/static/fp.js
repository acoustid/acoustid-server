// Fingerprint rendering and comparison.
//
// A Chromaprint fingerprint is an array of 32-bit integers, one per frame.
// Each frame covers ~0.1238 s of audio (4096 / 11025 / 3).

const FRAME_SEC = 4096 / 11025 / 3;

function popcount(x) {
  x = x - ((x >>> 1) & 0x55555555);
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// Draw fingerprints horizontally: x = time (frame), y = bit (0 at top).
// `rows` is an array of {data, offset, mode}; mode "bits" or "diff" (data is XOR).
function drawFingerprint(canvas, data, { start = 0, length = null, diff = false } = {}) {
  const on = hexToRgb(cssVar(diff ? "--fp-diff" : "--fp-on"));
  const off = hexToRgb(cssVar(diff ? "--fp-same" : "--fp-off"));
  const bg = hexToRgb(cssVar("--bg-sunk"));
  const width = length ?? data.length;
  canvas.width = width;
  canvas.height = 32;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(width, 32);
  for (let x = 0; x < width; x++) {
    const i = x - start;
    const present = i >= 0 && i < data.length && data[i] !== null;
    const v = present ? data[i] : 0;
    for (let b = 0; b < 32; b++) {
      const c = !present ? bg : (v >>> b) & 1 ? on : off;
      const p = (b * width + x) * 4;
      img.data[p] = c[0]; img.data[p + 1] = c[1]; img.data[p + 2] = c[2]; img.data[p + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}

// Bit error rate between a and b when b is shifted by `offset` frames
// (b[i] is aligned with a[i + offset]).
function compareAt(a, b, offset) {
  const start = Math.max(0, offset);
  const end = Math.min(a.length, b.length + offset);
  let errors = 0;
  for (let i = start; i < end; i++) errors += popcount(a[i] ^ b[i - offset]);
  const n = Math.max(0, end - start);
  const ber = n ? errors / (32 * n) : 0.5;
  return { offset, overlap: n, ber, score: Math.max(0, 1 - 2 * ber) };
}

// Unrelated audio gives a BER of ~0.5, identical audio 0. The score maps
// that range to 0..1, which is roughly how the server-side matcher thinks.
function scanOffsets(a, b, maxOffset = 80) {
  const minOverlap = Math.min(a.length, b.length) * 0.5;
  const results = [];
  let best = null;
  for (let off = -maxOffset; off <= maxOffset; off++) {
    const r = compareAt(a, b, off);
    results.push(r);
    if (r.overlap >= minOverlap && (!best || r.score > best.score)) best = r;
  }
  return { results, best: best ?? compareAt(a, b, 0) };
}

function errorTimeline(a, b, offset) {
  // Per-frame fraction of differing bits on the shared timeline.
  const start = Math.min(0, offset);
  const end = Math.max(a.length, b.length + offset);
  const out = [];
  for (let t = start; t < end; t++) {
    const ia = t, ib = t - offset;
    out.push(ia >= 0 && ia < a.length && ib >= 0 && ib < b.length ? popcount(a[ia] ^ b[ib]) / 32 : null);
  }
  return out;
}

function smooth(values, radius) {
  return values.map((_, i) => {
    let s = 0, n = 0;
    for (let j = i - radius; j <= i + radius; j++) {
      if (values[j] != null) { s += values[j]; n++; }
    }
    return values[i] == null || !n ? null : s / n;
  });
}

function verdict(score) {
  if (score >= 0.6) return ["good", "Same recording"];
  if (score >= 0.35) return ["warn", "Possibly related"];
  return ["bad", "Different audio"];
}

// Color for a similarity score. Matches (>= 0.6) blend from bg to series-1
// so differences between good matches stay visible; weaker scores get a
// tint of the verdict color.
function scoreColor(score) {
  const a = hexToRgb(cssVar("--bg-sunk"));
  if (score < 0.6) {
    const v = hexToRgb(cssVar(score < 0.35 ? "--bad" : "--warn"));
    const c = a.map((x, i) => Math.round(x + (v[i] - x) * 0.35));
    return { bg: `rgb(${c})`, fg: cssVar("--ink") };
  }
  const b = hexToRgb(cssVar("--series-1"));
  const t = 0.15 + 0.85 * Math.max(0, Math.min(1, (score - 0.6) / 0.4));
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return { bg: `rgb(${c})`, fg: t > 0.55 ? "#fff" : cssVar("--ink") };
}

function timeAxis(el, frames, startFrame, pxPerFrame) {
  el.innerHTML = "";
  el.style.width = frames * pxPerFrame + "px";
  const totalSec = frames * FRAME_SEC;
  const step = [5, 10, 15, 30, 60].find((s) => (s / FRAME_SEC) * pxPerFrame >= 60) ?? 60;
  const startSec = startFrame * FRAME_SEC;
  for (let s = Math.ceil(startSec / step) * step; s <= startSec + totalSec; s += step) {
    const span = document.createElement("span");
    span.style.left = ((s - startSec) / FRAME_SEC) * pxPerFrame + "px";
    span.textContent = s < 0 ? `−${fmt.dur(-s)}` : fmt.dur(s);
    el.append(span);
  }
}

// Color barcodes.
//
// Each frame packs 16 filter outputs, each quantized to 4 levels and stored
// as 2 Gray-coded bits. Averaging the decoded levels over windows of about
// 10 seconds gives one 16-value summary per window, which barely changes
// with bit errors, small offsets or remastering, but does change with the
// music. The summaries are projected onto 3 fixed directions, which become a
// color, so the same song gets the same colors on every page, and a song
// linked to the wrong recording stands out. A swatch at the start of each
// barcode is the color of the whole song.
//
// The constants are fitted by scripts/barcode/fit.py, which also mirrors
// the code below to score it; keep the two in sync.

// BEGIN BARCODE_BASIS (written by scripts/barcode/fit.py)
const BARCODE_BASIS = {
  window: 80,
  step: 40,
  mean: [1.45198, 1.47214, 1.34037, 1.42130, 1.38258, 1.53602, 1.61593, 1.44225, 1.52569, 1.59377, 1.36732, 1.39922, 1.32260, 1.55829, 1.57790, 1.67647],
  std: [0.80101, 0.77711, 0.78229, 0.15444, 0.12761, 0.73440, 0.75389, 0.10696, 0.17056, 0.10335, 0.41538, 0.14060, 0.15380, 0.11199, 0.75420, 0.17330],
  axes: [
    [-0.20527, 0.14487, 0.90112, -0.04797, 0.03665, 0.21502, 0.10761, 0.00172, 0.03612, 0.03025, -0.12817, 0.06726, 0.00325, -0.02420, 0.19534, 0.03847],
    [-0.18612, 0.41891, 0.10447, 0.01142, 0.00046, 0.20600, -0.27003, -0.00655, -0.04814, 0.04406, 0.80631, -0.07084, 0.02502, 0.04473, -0.02961, 0.02281],
    [0.46996, -0.44075, 0.03703, 0.01214, -0.08482, 0.00324, 0.10732, -0.04385, -0.03359, 0.03827, 0.52837, 0.01061, -0.06463, 0.02542, 0.52395, -0.03850],
  ],
  quantiles: [
    [-3.1099, -1.6548, -1.4227, -1.2270, -1.0884, -0.9803, -0.8565, -0.7565, -0.6703, -0.5891, -0.5090, -0.4349, -0.3622, -0.2826, -0.2048, -0.1259, -0.0504, 0.0311, 0.1112, 0.1818, 0.2629, 0.3512, 0.4393, 0.5353, 0.6389, 0.7456, 0.8702, 0.9966, 1.1624, 1.3434, 1.5695, 1.8931, 3.3167],
    [-2.9162, -1.6533, -1.3815, -1.1801, -1.0436, -0.9335, -0.8269, -0.7477, -0.6724, -0.5916, -0.5236, -0.4562, -0.3925, -0.3291, -0.2625, -0.1992, -0.1357, -0.0616, 0.0154, 0.0925, 0.1709, 0.2547, 0.3431, 0.4396, 0.5516, 0.6782, 0.8157, 0.9615, 1.1145, 1.3197, 1.6547, 2.2408, 5.0948],
    [-2.1085, -1.2955, -1.1091, -0.9880, -0.8837, -0.7823, -0.6869, -0.6120, -0.5378, -0.4699, -0.4089, -0.3405, -0.2776, -0.2176, -0.1518, -0.0997, -0.0467, 0.0105, 0.0680, 0.1289, 0.1944, 0.2564, 0.3257, 0.3962, 0.4702, 0.5532, 0.6451, 0.7511, 0.8640, 1.0108, 1.2215, 1.5841, 3.6289],
  ],
};
// END BARCODE_BASIS

const GRAY_LEVEL = [0, 1, 3, 2];
// A thumbnail that matches the page's reference at least this well
// ("possibly related") shares its swatch range.
const SWATCH_MIN_SCORE = 0.35;
// Shared audio needed to average every matching swatch over the same range.
const SWATCH_MIN_COMMON = 240; // frames, ~30 s

// One 16-value summary per window, a window every `step` frames.
function barcodeWindows(data, { length = null } = {}) {
  const { window: size, step } = BARCODE_BASIS;
  const n = Math.min(data.length, length ?? data.length);
  const levels = Array.from({ length: 16 }, () => new Float32Array(n + 1));
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 16; k++) {
      const level = GRAY_LEVEL[(data[i] >>> (30 - 2 * k)) & 3];
      levels[k][i + 1] = levels[k][i] + level; // running sums
    }
  }
  const windows = [];
  for (let s = 0; s + size <= n; s += step) {
    windows.push(Float64Array.from(levels, (sums) => (sums[s + size] - sums[s]) / size));
  }
  return windows;
}

// The mean of the windows that lie within frames [start, end), or of the
// ones that touch it if none fits, or of all of them.
function barcodeSwatch(windows, start = 0, end = Infinity) {
  const { window: size, step } = BARCODE_BASIS;
  if (!windows.length) return null;
  let picked = windows.filter((_, i) => i * step >= start && i * step + size <= end);
  if (!picked.length) picked = windows.filter((_, i) => i * step < end && i * step + size > start);
  if (!picked.length) picked = windows;
  const mean = new Float64Array(16);
  for (const w of picked) for (let k = 0; k < 16; k++) mean[k] += w[k] / picked.length;
  return mean;
}

// Where b lines up with a (b[i] with a[i + offset]) at any offset, overlapping
// by at least min(minOverlap, half the shorter one). Every 4th frame first,
// then every frame near the best offset. Null if they never overlap that much.
function findOffset(a, b, minOverlap) {
  minOverlap = Math.max(minOverlap, Math.min(a.length, b.length) * 0.5);
  const at = (off, every) => {
    const s = Math.max(0, off), e = Math.min(a.length, b.length + off);
    if (e - s < minOverlap) return null;
    let errors = 0, n = 0;
    for (let i = s; i < e; i += every, n++) errors += popcount(a[i] ^ b[i - off]);
    return errors / (32 * n);
  };
  let best = null;
  for (let off = -b.length; off <= a.length; off++) {
    const ber = at(off, 4);
    if (ber !== null && (!best || ber < best.ber)) best = { ber, offset: off };
  }
  if (!best) return null;
  let fine = null;
  for (let off = best.offset - 3; off <= best.offset + 3; off++) {
    const ber = at(off, 1);
    if (ber !== null && (!fine || ber < fine.ber)) fine = { ber, offset: off };
  }
  return fine;
}

// Swatches for the thumbnails of one page. Each is aligned with a reference
// (the first long enough one; on a recording page the most submitted
// AcoustID), and the ones that match are averaged over the audio they all
// share, so a cut or shifted copy of a song gets the same swatch as the
// rest. One that doesn't match keeps the swatch of all of it.
// `items` is [{data, windows}], the result is one swatch (or null) each.
function barcodeSwatches(items) {
  if (!items.length) return [];
  let ref = items.findIndex((t) => t.data.length >= SWATCH_MIN_COMMON);
  if (ref < 0) ref = 0;
  const spans = items.map((t, i) => {
    if (i === ref) return { offset: 0, start: 0, end: t.data.length };
    const r = findOffset(items[ref].data, t.data, BARCODE_BASIS.window);
    if (!r || 1 - 2 * r.ber < SWATCH_MIN_SCORE) return null;
    return {
      offset: r.offset,
      start: Math.max(0, r.offset),
      end: Math.min(items[ref].data.length, t.data.length + r.offset),
    };
  });
  const long = spans.filter((s) => s && s.end - s.start >= SWATCH_MIN_COMMON);
  let common = null;
  if (long.length) {
    const start = Math.max(...long.map((s) => s.start));
    const end = Math.min(...long.map((s) => s.end));
    if (end - start >= SWATCH_MIN_COMMON) common = { start, end };
  }
  return items.map((t, i) => {
    const s = spans[i];
    if (!t.windows.length) return null;
    if (!s) return barcodeSwatch(t.windows);
    let { start, end } = s;
    if (common && end - start >= SWATCH_MIN_COMMON) ({ start, end } = common);
    return barcodeSwatch(t.windows, start - s.offset, end - s.offset);
  });
}

function projectWindow(w, { mean, std, axes } = BARCODE_BASIS) {
  return axes.map((axis) => axis.reduce((s, a, k) => s + a * (w[k] - mean[k]) / std[k], 0));
}

// Where x falls in a sorted table of quantiles, from 0 to 1.
function quantileRank(x, q) {
  if (x <= q[0]) return 0;
  if (x >= q[q.length - 1]) return 1;
  let i = 1;
  while (q[i] < x) i++;
  return (i - 1 + (x - q[i - 1]) / (q[i] - q[i - 1])) / (q.length - 1);
}

function oklabToLinear(L, a, b) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
}

// The largest OKLab chroma that sRGB can show at this lightness and hue.
function maxChroma(L, hue) {
  let lo = 0, hi = 0.4;
  for (let i = 0; i < 20; i++) {
    const mid = (lo + hi) / 2;
    const c = oklabToLinear(L, mid * Math.cos(hue), mid * Math.sin(hue));
    if (c.every((v) => v >= -1e-6 && v <= 1 + 1e-6)) lo = mid; else hi = mid;
  }
  return lo;
}

// The first direction sets the OKLab lightness, the other two a point in a
// square that becomes hue and chroma, with chroma scaled to what the screen
// can show there, so no color gets clipped into another.
function barcodeColor(w, { quantiles } = BARCODE_BASIS) {
  const t = projectWindow(w).map((x, c) => quantileRank(x, quantiles[c]));
  const L = 0.45 + 0.43 * t[0];
  const u = 2 * t[1] - 1, v = 2 * t[2] - 1;
  const hue = Math.atan2(v, u);
  const C = maxChroma(L, hue) * (0.25 + 0.75 * Math.min(1, Math.max(Math.abs(u), Math.abs(v))));
  return oklabToLinear(L, C * Math.cos(hue), C * Math.sin(hue)).map((c) => {
    c = Math.max(0, Math.min(1, c));
    return Math.round(255 * (c > 0.0031308 ? 1.055 * c ** (1 / 2.4) - 0.055 : 12.92 * c));
  });
}

// Drawn at the screen's resolution, so bands keep even widths at any size.
// The swatch comes first, then one band per window, centered on its window,
// on the same time scale as drawFingerprint() with the same `length`, so
// shorter fingerprints leave the same blank space.
function drawBarcode(canvas, windows, { length = null, swatch = null } = {}) {
  const { window: size, step } = BARCODE_BASIS;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round((canvas.clientWidth || 200) * ratio));
  const height = Math.max(1, Math.round((canvas.clientHeight || 22) * ratio));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = cssVar("--bg-sunk");
  ctx.fillRect(0, 0, width, height);
  let x0 = 0;
  if (swatch) {
    const w = Math.round(height * 1.5);
    ctx.fillStyle = `rgb(${barcodeColor(swatch)})`;
    ctx.fillRect(0, 0, w, height);
    x0 = w + Math.max(1, Math.round(2 * ratio));
  }
  if (!windows.length) return;
  const frames = (windows.length - 1) * step + size;
  const scale = (width - x0) / (length ?? frames);
  const edge = (i) => (i <= 0 ? 0 : i >= windows.length ? frames : i * step + (size - step) / 2);
  windows.forEach((w, i) => {
    const a = Math.round(x0 + edge(i) * scale), b = Math.round(x0 + edge(i + 1) * scale);
    ctx.fillStyle = `rgb(${barcodeColor(w)})`;
    ctx.fillRect(a, 0, Math.max(1, b - a), height);
  });
}
