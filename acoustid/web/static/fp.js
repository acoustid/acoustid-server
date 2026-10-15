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
