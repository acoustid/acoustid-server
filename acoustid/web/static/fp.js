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
// as 2 Gray-coded bits. Averaging the decoded levels over windows of a few
// seconds gives one 16-value summary per window, which barely changes with
// bit errors or small offsets but does change with the music. The summaries
// are projected onto 3 fixed directions and those are drawn as colors, so
// similar audio gets similar colors, on every page.

const BARCODE_WINDOW = 24; // frames, ~3 s
const BARCODE_STEP = 8; // frames, ~1 s
const GRAY_LEVEL = [0, 1, 3, 2];

function barcodeWindows(data, { length = null } = {}) {
  const n = Math.min(data.length, length ?? data.length);
  const levels = Array.from({ length: 16 }, () => new Float32Array(n + 1));
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 16; k++) {
      const level = GRAY_LEVEL[(data[i] >>> (30 - 2 * k)) & 3];
      levels[k][i + 1] = levels[k][i] + level; // running sums
    }
  }
  const windows = [];
  for (let s = 0; s + BARCODE_WINDOW <= n; s += BARCODE_STEP) {
    windows.push(Float64Array.from(levels, (sums) => (sums[s + BARCODE_WINDOW] - sums[s]) / BARCODE_WINDOW));
  }
  return windows;
}

// The 3 directions in which the window summaries of different fingerprints
// differ most, relative to how much they vary within one fingerprint (LDA),
// fitted on 10,000 random fingerprints from the database. Songs get a
// steady color of their own instead of flickering with every bar. For each
// direction, `quantiles` holds 33 evenly spaced points of its distribution
// over that sample, so that every color gets used about equally. Changing
// any of this changes every barcode's colors.
const BARCODE_BASIS = {
  mean: [1.49787, 1.50680, 1.32962, 1.41684, 1.38171, 1.52191, 1.55498, 1.44065, 1.52935, 1.59389, 1.35023, 1.39726, 1.31871, 1.56333, 1.55397, 1.68188],
  std: [0.92719, 0.94487, 0.92213, 0.36092, 0.27873, 0.85465, 0.87213, 0.22686, 0.42783, 0.20291, 0.50265, 0.30505, 0.37624, 0.23622, 0.89651, 0.39105],
  axes: [
    [-0.43415, -0.26660, 0.02455, 0.02021, -0.00491, 0.43706, 0.61369, 0.03498, -0.02716, 0.00298, 0.05003, 0.04252, 0.01048, 0.05460, 0.40297, -0.00274],
    [-0.61142, -0.03460, 0.06802, 0.02202, 0.04584, 0.18581, -0.22234, 0.00948, -0.01668, -0.02961, 0.72448, 0.02855, 0.02804, 0.05796, -0.04092, -0.03228],
    [0.41249, 0.39964, -0.07833, -0.00841, 0.03717, 0.70644, 0.07032, -0.01770, 0.05806, 0.01840, 0.15375, -0.01742, 0.04417, -0.07780, -0.34978, -0.01544],
  ],
  quantiles: [
    [-3.4867, -1.8206, -1.5529, -1.3653, -1.2119, -1.0798, -0.9615, -0.8529, -0.7516, -0.6549, -0.5602, -0.4678, -0.3792, -0.2906, -0.2041, -0.1185, -0.0330, 0.0538, 0.1405, 0.2283, 0.3182, 0.4106, 0.5066, 0.6062, 0.7108, 0.8247, 0.9472, 1.0823, 1.2319, 1.4141, 1.6504, 2.0075, 3.7728],
    [-2.9933, -1.5169, -1.3096, -1.1674, -1.0509, -0.9497, -0.8580, -0.7721, -0.6907, -0.6139, -0.5396, -0.4679, -0.3971, -0.3269, -0.2570, -0.1872, -0.1164, -0.0443, 0.0287, 0.1046, 0.1839, 0.2664, 0.3523, 0.4448, 0.5458, 0.6563, 0.7804, 0.9249, 1.1018, 1.3296, 1.6527, 2.2136, 4.3055],
    [-3.7405, -1.8945, -1.5828, -1.3718, -1.2061, -1.0641, -0.9390, -0.8263, -0.7219, -0.6227, -0.5284, -0.4375, -0.3497, -0.2643, -0.1796, -0.0960, -0.0122, 0.0723, 0.1558, 0.2404, 0.3271, 0.4154, 0.5060, 0.6005, 0.7019, 0.8105, 0.9286, 1.0589, 1.2091, 1.3893, 1.6205, 1.9702, 3.9153],
  ],
};

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

// The first direction sets the lightness, the other two the red-green and
// blue-yellow axes of CIELAB, where equal steps look about equally different.
function barcodeColor(w, { quantiles } = BARCODE_BASIS) {
  const t = projectWindow(w).map((x, c) => quantileRank(x, quantiles[c]));
  return labToRgb(28 + 62 * t[0], (t[1] - 0.5) * 120, (t[2] - 0.5) * 120);
}

function labToRgb(L, a, b) {
  const fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200;
  const f = (t) => (t ** 3 > 0.008856 ? t ** 3 : (t - 16 / 116) / 7.787);
  const x = 0.95047 * f(fx), y = f(fy), z = 1.08883 * f(fz);
  const lin = [
    3.2406 * x - 1.5372 * y - 0.4986 * z,
    -0.9689 * x + 1.8758 * y + 0.0415 * z,
    0.0557 * x - 0.204 * y + 1.057 * z,
  ];
  return lin.map((c) => {
    const s = c > 0.0031308 ? 1.055 * c ** (1 / 2.4) - 0.055 : 12.92 * c;
    return Math.round(255 * Math.max(0, Math.min(1, s)));
  });
}

// One column per window, on the same time scale as drawFingerprint() with
// the same `length`, so shorter fingerprints leave the same blank space.
function drawBarcode(canvas, windows, { length = null } = {}) {
  const frames = length ?? (windows.length - 1) * BARCODE_STEP + BARCODE_WINDOW;
  const width = Math.max(1, Math.floor((frames - BARCODE_WINDOW) / BARCODE_STEP) + 1);
  const bg = hexToRgb(cssVar("--bg-sunk"));
  canvas.width = width;
  canvas.height = 1;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(width, 1);
  for (let x = 0; x < width; x++) {
    const c = x < windows.length ? barcodeColor(windows[x]) : bg;
    img.data.set([c[0], c[1], c[2], 255], x * 4);
  }
  ctx.putImageData(img, 0, 0);
}
