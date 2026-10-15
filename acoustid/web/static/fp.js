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

// The 3 main directions (PCA) of the standardized window summaries of
// 10,000 random fingerprints from the database, and the 2nd and 98th
// percentile of each projection for scaling it to a color. Changing these
// changes every barcode's colors.
const BARCODE_BASIS = {
  mean: [1.49787, 1.50680, 1.32962, 1.41684, 1.38171, 1.52191, 1.55498, 1.44065, 1.52935, 1.59389, 1.35023, 1.39726, 1.31871, 1.56333, 1.55397, 1.68188],
  std: [0.92719, 0.94487, 0.92213, 0.36092, 0.27873, 0.85465, 0.87213, 0.22686, 0.42783, 0.20291, 0.50265, 0.30505, 0.37624, 0.23622, 0.89651, 0.39105],
  axes: [
    [0.04297, -0.05624, 0.01300, -0.27542, 0.58504, 0.02060, 0.04389, -0.29510, -0.57835, 0.07438, 0.02434, 0.22827, 0.08614, -0.23452, 0.00702, 0.17908],
    [0.19873, -0.07312, -0.22318, -0.00715, -0.02386, 0.41236, 0.51879, -0.11977, 0.05701, -0.05633, -0.41948, 0.16769, 0.04581, 0.14254, 0.43850, -0.16124],
    [0.15258, 0.23862, 0.09258, -0.05209, -0.05096, -0.10469, -0.09355, -0.46498, 0.14704, 0.22188, 0.25025, 0.44206, 0.15994, 0.48591, -0.09608, -0.26488],
  ],
  lo: [-2.79346, -2.69326, -2.46803],
  hi: [2.86299, 2.28688, 2.50811],
};

function projectWindow(w, { mean, std, axes } = BARCODE_BASIS) {
  return axes.map((axis) => axis.reduce((s, a, k) => s + a * (w[k] - mean[k]) / std[k], 0));
}

// The first component sets the lightness, the other two the red-green and
// blue-yellow axes of CIELAB, where equal steps look about equally different.
function barcodeColor(w, { lo, hi } = BARCODE_BASIS) {
  const t = projectWindow(w).map((x, c) => Math.max(0, Math.min(1, (x - lo[c]) / (hi[c] - lo[c]))));
  return labToRgb(32 + 58 * t[0], (t[1] - 0.5) * 96, (t[2] - 0.5) * 96);
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
