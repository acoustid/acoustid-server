#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Fit the colors of the fingerprint barcodes (see acoustid/web/static/fp.js).

Reads the files written by extract.py, prints how well the colors keep
copies of the same audio together and unrelated songs apart (on recordings
held out from the fit), refits on everything and prints the constants, or
writes them into fp.js with --write. Needs only numpy:

    uv run --with numpy scripts/barcode/fit.py barcode-data
    uv run --with numpy scripts/barcode/fit.py barcode-data --write acoustid/web/static/fp.js

How the colors are chosen:

- Each band summarizes WINDOW frames: the 16 Gray-decoded filter levels,
  averaged.
- The 3 color directions are the ones in which window summaries vary most
  across songs (from random fingerprints), relative to how much they differ
  between copies of the same audio that come from different AcoustIDs of
  one recording (remasters, other encodes and rips, aligned window by
  window). So colors follow the song, not the mastering.
- Each direction is mapped through its quantiles, so every color gets used
  about equally: first to OKLab lightness, the other two to hue and chroma,
  with chroma scaled to what sRGB can show at that lightness and hue.
- The song swatch is the mean of the window summaries, colored the same
  way. The page averages it over the audio that all matching fingerprints
  share, see page_swatches(), so a cut or shifted copy of a song gets the
  same swatch as the rest.

The color code in this file mirrors fp.js and site.js; keep them in sync.
"""

import argparse
import json
import re
import zlib

import numpy as np

THUMBNAIL_FRAMES = 948
GRAY_LEVEL = np.array([0, 1, 3, 2])
POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)

SHARED_BER = 0.3  # copies of the same audio stay below this bit error rate
CHUNK = 160  # frames compared at a time when looking for shared audio, ~20 s
MIN_MATCH_SCORE = 0.35  # "possibly related" in fp.js
MIN_COMMON = 240  # frames of shared audio needed for a common swatch range, ~30 s
NUM_QUANTILES = 33


# ---------------------------------------------------------------- fingerprints


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def to_u32(fp):
    return (np.array(fp[:THUMBNAIL_FRAMES], dtype=np.int64) & 0xFFFFFFFF).astype(
        np.uint32
    )


def levels(u32):
    """frames x 16 filter levels, 0..3; filter 0 is in the top two bits."""
    a = u32.astype(np.int64)
    return np.stack([GRAY_LEVEL[(a >> (30 - 2 * k)) & 3] for k in range(16)], 1).astype(
        float
    )


def windows(lv, window, step, starts=None):
    """Window summaries, one row per window start (every `step` frames by default)."""
    if starts is None:
        starts = np.arange(0, len(lv) - window + 1, step)
    starts = np.asarray(starts, dtype=int)
    sums = np.vstack([np.zeros(16), np.cumsum(lv, 0)])
    return (sums[starts + window] - sums[starts]) / window


def ber(a, b):
    if not len(a):
        return 0.5
    return POPCOUNT[(a ^ b).view(np.uint8)].sum() / (32 * len(a))


def find_shared(a, b):
    """Best (ber, offset) of CHUNK-frame pieces of either fingerprint slid over the
    other, at any offset; b[i] lines up with a[i + offset], like compareAt() in fp.js.
    """
    best = (0.5, 0)
    for x, y, sign in ((a, b, 1), (b, a, -1)):
        if len(x) < CHUNK or len(y) < CHUNK:
            continue
        views = np.lib.stride_tricks.sliding_window_view(y, CHUNK)
        for s in range(0, len(x) - CHUNK + 1, CHUNK // 2):
            errors = (
                POPCOUNT[(views ^ x[s : s + CHUNK]).view(np.uint8)]
                .reshape(len(views), -1)
                .sum(1)
            )
            j = int(errors.argmin())
            e = errors[j] / (32 * CHUNK)
            if e < best[0]:
                best = (e, sign * (s - j))
    return best


def find_offset(a, b, min_overlap):
    """findOffset() in fp.js: (ber, offset) of the best overlap of b with a at any
    offset, b[i] lining up with a[i + offset]. Every 4th frame first, then every
    frame near the best one. None if they never overlap by min_overlap frames."""
    min_overlap = max(min_overlap, min(len(a), len(b)) * 0.5)

    def at(off, every):
        s, e = max(0, off), min(len(a), len(b) + off)
        if e - s < min_overlap:
            return None
        return ber(a[s:e:every], b[s - off : e - off : every])

    best = None
    for off in range(-len(b), len(a) + 1):
        e = at(off, 4)
        if e is not None and (best is None or e < best[0]):
            best = (e, off)
    if best is None:
        return None
    fine = None
    for off in range(best[1] - 3, best[1] + 4):
        e = at(off, 1)
        if e is not None and (fine is None or e < fine[0]):
            fine = (e, off)
    return fine


# ---------------------------------------------------------------- colors (fp.js)


def oklab_to_linear(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return np.stack(
        [
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        ],
        -1,
    )


def linear_to_oklab(c):
    c = np.clip(c, 0, 1)
    l = np.cbrt(  # noqa: E741
        0.4122214708 * c[..., 0] + 0.5363325363 * c[..., 1] + 0.0514459929 * c[..., 2]
    )
    m = np.cbrt(
        0.2119034982 * c[..., 0] + 0.6806995451 * c[..., 1] + 0.1073969566 * c[..., 2]
    )
    s = np.cbrt(
        0.0883024619 * c[..., 0] + 0.2817188376 * c[..., 1] + 0.6299787075 * c[..., 2]
    )
    return np.stack(
        [
            0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
        ],
        -1,
    )


def max_chroma(L, hue):
    """Largest OKLab chroma that sRGB shows at this lightness and hue."""
    lo, hi = np.zeros_like(L), np.full_like(L, 0.4)
    for _ in range(20):
        mid = (lo + hi) / 2
        c = oklab_to_linear(L, mid * np.cos(hue), mid * np.sin(hue))
        ok = np.all((c >= -1e-6) & (c <= 1 + 1e-6), -1)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
    return lo


def rank_color(t):
    """Three ranks in 0..1 to a linear sRGB color, like barcodeColor() in fp.js."""
    t = np.atleast_2d(t)
    L = 0.45 + 0.43 * t[:, 0]
    u, v = 2 * t[:, 1] - 1, 2 * t[:, 2] - 1
    hue = np.arctan2(v, u)
    rel = np.clip(np.maximum(np.abs(u), np.abs(v)), 0, 1)
    C = max_chroma(L, hue) * (0.25 + 0.75 * rel)
    return oklab_to_linear(L, C * np.cos(hue), C * np.sin(hue))


def to_srgb8(c):
    c = np.clip(c, 0, 1)
    s = np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.round(s * 255).astype(int)


class Basis:
    def __init__(self, d):
        self.d = d
        self.mean, self.std = np.array(d["mean"]), np.array(d["std"])
        self.axes = np.array(d["axes"])
        self.q = np.array(d["quantiles"])

    def project(self, w):
        return ((np.atleast_2d(w) - self.mean) / self.std) @ self.axes.T

    @staticmethod
    def rank(p, q):
        grid = np.linspace(0, 1, q.shape[1])
        return np.stack([np.interp(p[:, c], q[c], grid) for c in range(3)], 1)

    def band_colors(self, w):
        return (
            rank_color(self.rank(self.project(w), self.q))
            if len(w)
            else np.zeros((0, 3))
        )

    def swatch_color(self, w):
        return rank_color(self.rank(self.project(np.mean(w, 0)), self.q))[0]


def delta_e(c1, c2):
    """OKLab distance x 100; about 2 is the smallest visible difference."""
    return np.linalg.norm(linear_to_oklab(c1) - linear_to_oklab(c2), axis=-1) * 100


# ---------------------------------------------------------------- page swatches (site.js)


def swatch_windows(w, window, step, start, end):
    """barcodeSwatch() in fp.js: the windows within frames [start, end)."""
    starts = np.arange(len(w)) * step
    inside = (starts >= start) & (starts + window <= end)
    if not inside.any():
        inside = (starts < end) & (starts + window > start)
    return w[inside] if inside.any() else w


def page_swatches(fps, ws, basis):
    """Swatch colors for the thumbnails of one page, like site.js: every thumbnail
    is aligned with a reference one, and those that match are averaged over the
    audio they all share, so a cut or shifted copy of the same song gets the same
    swatch. One that doesn't match keeps the swatch of all of it."""
    window, step = basis.d["window"], basis.d["step"]
    ref = next((i for i, f in enumerate(fps) if len(f) >= MIN_COMMON), 0)
    spans = []  # (offset, overlap start, overlap end) in reference frames, or None
    for i, f in enumerate(fps):
        if i == ref:
            spans.append((0, 0, len(f)))
            continue
        r = find_offset(fps[ref], f, window)
        if r and 1 - 2 * r[0] >= MIN_MATCH_SCORE:
            off = r[1]
            spans.append((off, max(0, off), min(len(fps[ref]), len(f) + off)))
        else:
            spans.append(None)
    long_enough = [s for s in spans if s and s[2] - s[1] >= MIN_COMMON]
    common = None
    if long_enough:
        lo, hi = max(s[1] for s in long_enough), min(s[2] for s in long_enough)
        if hi - lo >= MIN_COMMON:
            common = (lo, hi)
    out = []
    for w, s in zip(ws, spans):
        if not len(w):
            out.append(None)
            continue
        if s is None:
            out.append(basis.swatch_color(w))
            continue
        off, lo, hi = s
        if common and hi - lo >= MIN_COMMON:
            lo, hi = common
        out.append(
            basis.swatch_color(swatch_windows(w, window, step, lo - off, hi - off))
        )
    return out


# ---------------------------------------------------------------- fitting


def shared_pairs(recordings):
    """(a, b, offset) for enabled AcoustIDs of one recording that share audio."""
    pairs = []
    for rec in recordings:
        tracks = [
            to_u32(t["fingerprint"]) for t in rec["tracks"] if not t.get("disabled")
        ]
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                e, off = find_shared(tracks[i], tracks[j])
                if e < SHARED_BER:
                    pairs.append((tracks[i], tracks[j], off))
    return pairs


def aligned_windows(a, b, off, window, step):
    """Window summaries of a and b over the same audio, where it really matches."""
    starts = np.arange(max(0, off), min(len(a), len(b) + off) - window + 1, step)
    starts = np.array(
        [
            s
            for s in starts
            if ber(a[s : s + window], b[s - off : s - off + window]) < SHARED_BER
        ],
        dtype=int,
    )
    if not len(starts):
        return None
    return windows(levels(a), window, step, starts), windows(
        levels(b), window, step, starts - off
    )


def fit(random_fps, pairs, window, step):
    rw = [windows(levels(f), window, step) for f in random_fps]
    rw = [w for w in rw if len(w)]
    allw = np.vstack(rw)
    mean, std = allw.mean(0), allw.std(0)
    z = (allw - mean) / std
    total = np.cov(z.T)

    diffs = []
    for a, b, off in pairs:
        r = aligned_windows(a, b, off, window, step)
        if r:
            diffs.append(((r[0] - mean) / std) - ((r[1] - mean) / std))
    d = np.vstack(diffs)
    noise = d.T @ d / len(d) / 2

    vals, vecs = np.linalg.eig(np.linalg.solve(noise, total))
    order = np.argsort(-vals.real)[:3]
    axes = vecs[:, order].real.T
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    axes *= np.sign(axes[np.arange(3), np.abs(axes).argmax(1)])[:, None]  # stable signs

    grid = np.linspace(0, 1, NUM_QUANTILES)
    p = z @ axes.T
    return {
        "window": window,
        "step": step,
        "mean": mean.tolist(),
        "std": std.tolist(),
        "axes": axes.tolist(),
        "quantiles": np.quantile(p, grid, axis=0).T.tolist(),
        "_stats": {
            "windows": len(allw),
            "noise_windows": len(d),
            "song_to_mastering": (np.var(z @ axes.T, 0) / (np.var(d @ axes.T, 0) / 2))
            .round(1)
            .tolist(),
        },
    }


# ---------------------------------------------------------------- evaluation


def auc(closer, farther):
    """How often a pair from `closer` is closer than one from `farther`."""
    closer, farther = np.asarray(closer), np.asarray(farther)
    if not len(closer) or not len(farther):
        return float("nan")
    return float(np.mean(closer[:, None] < farther[None, :]))


def evaluate(basis, recordings, random_fps, rng):
    window, step = basis.d["window"], basis.d["step"]

    def lv(f):
        return windows(levels(f), window, step)

    def bands_de(a, b):  # band by band, unaligned, as the eye compares two rows
        ca, cb = basis.band_colors(lv(a)), basis.band_colors(lv(b))
        n = min(len(ca), len(cb))
        return float(delta_e(ca[:n], cb[:n]).mean()) if n else np.nan

    def swatch_pair(a, b):
        sw = page_swatches([a, b], [lv(a), lv(b)], basis)
        return delta_e(*sw) if sw[0] is not None and sw[1] is not None else np.nan

    shared = shared_pairs(recordings)
    if len(shared) > 2000:
        shared = [shared[i] for i in rng.choice(len(shared), 2000, replace=False)]
    unrelated = []
    for _ in range(min(2000, len(random_fps) * 2)):
        i, j = rng.choice(len(random_fps), 2, replace=False)
        unrelated.append((random_fps[i], random_fps[j]))

    cut = []
    for a, b, _ in shared:
        n = len(b)
        keep = int(n * rng.uniform(0.35, 0.7))
        start = int(rng.uniform(0, n - keep))
        cut.append((a, b[start : start + keep]))

    def whole(a, b):
        wa, wb = lv(a), lv(b)
        return (
            float(delta_e(basis.swatch_color(wa), basis.swatch_color(wb)))
            if len(wa) and len(wb)
            else np.nan
        )

    res = {
        "bands: same audio": [bands_de(a, b) for a, b, _ in shared],
        "bands: unrelated": [bands_de(a, b) for a, b in unrelated],
        "swatch, whole: same audio": [whole(a, b) for a, b, _ in shared],
        "swatch, whole: same audio, one cut": [whole(a, b) for a, b in cut],
        "swatch, page: same audio": [float(swatch_pair(a, b)) for a, b, _ in shared],
        "swatch, page: same audio, one cut": [float(swatch_pair(a, b)) for a, b in cut],
        "swatch, page: unrelated": [
            float(swatch_pair(a, b)) for a, b in unrelated[:500]
        ],
    }
    res = {k: np.array([x for x in v if np.isfinite(x)]) for k, v in res.items()}

    print(
        f"  {len(shared)} same-audio pairs from different AcoustIDs, {len(unrelated)} unrelated pairs"
    )
    print("  median color difference (OKLab x 100, about 2 is visible):")
    for k, v in res.items():
        print(f"    {k:38s} {np.median(v):5.1f}")
    print("  how often same audio looks closer than an unrelated pair:")
    print(
        f"    bands                                 {auc(res['bands: same audio'], res['bands: unrelated']):.1%}"
    )
    for name in ("same audio", "same audio, one cut"):
        print(
            f"    swatch, {name:30s}{auc(res['swatch, page: ' + name], res['swatch, page: unrelated']):6.1%}"
            f"  (whole song: {auc(res['swatch, whole: ' + name], res['swatch, page: unrelated']):.1%})"
        )

    # Disabled links are mostly wrong ones: they should look unlike the rest of the page.
    on, off = [], []
    for rec in recordings:
        tracks = rec["tracks"]
        if not any(t.get("disabled") for t in tracks) or all(
            t.get("disabled") for t in tracks
        ):
            continue
        fps = [to_u32(t["fingerprint"]) for t in tracks]
        sw = page_swatches(fps, [lv(f) for f in fps], basis)
        ref = next(i for i, t in enumerate(tracks) if not t.get("disabled"))
        for i, t in enumerate(tracks):
            if i != ref and sw[i] is not None and sw[ref] is not None:
                (off if t.get("disabled") else on).append(
                    float(delta_e(sw[i], sw[ref]))
                )
    if off:
        print(
            f"  swatch vs the top AcoustID of the page: enabled links {np.median(on):.1f}, "
            f"disabled links {np.median(off):.1f} ({len(off)} disabled); "
            f"disabled looks farther {auc(on, off):.1%} of the time"
        )


# ---------------------------------------------------------------- output


def js_block(d):
    def nums(xs, digits):
        return "[" + ", ".join(f"{x:.{digits}f}" for x in xs) + "]"

    def rows(name, xss, digits):
        return (
            f"  {name}: [\n"
            + "".join(f"    {nums(xs, digits)},\n" for xs in xss)
            + "  ],\n"
        )

    return (
        "const BARCODE_BASIS = {\n"
        f"  window: {d['window']},\n"
        f"  step: {d['step']},\n"
        f"  mean: {nums(d['mean'], 5)},\n"
        f"  std: {nums(d['std'], 5)},\n"
        + rows("axes", d["axes"], 5)
        + rows("quantiles", d["quantiles"], 4)
        + "};\n"
    )


BLOCK_RE = re.compile(
    r"(// BEGIN BARCODE_BASIS[^\n]*\n).*?(// END BARCODE_BASIS)", re.S
)


def read_basis(path):
    """The basis currently in fp.js."""
    text = BLOCK_RE.search(open(path).read()).group(0)
    body = text[text.index("{") : text.rindex("}") + 1]
    body = re.sub(r"(\w+):", r'"\1":', body)
    body = re.sub(r",(\s*[\]}])", r"\1", body)
    return json.loads(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data", help="directory with random.jsonl and recordings.jsonl")
    ap.add_argument(
        "--window", type=int, default=80, help="frames per band (default 80, ~10 s)"
    )
    ap.add_argument(
        "--step", type=int, default=40, help="frames between bands (default 40, ~5 s)"
    )
    ap.add_argument(
        "--write", metavar="FP_JS", help="write the fitted constants into this fp.js"
    )
    ap.add_argument(
        "--current",
        metavar="FP_JS",
        help="also evaluate the constants currently in this fp.js",
    )
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    random_fps = [
        to_u32(r["fingerprint"]) for r in load_jsonl(f"{args.data}/random.jsonl")
    ]
    recordings = load_jsonl(f"{args.data}/recordings.jsonl")

    def held_out(r):
        return zlib.crc32(r["mbid"].encode()) % 2 == 1

    rec_train = [r for r in recordings if not held_out(r)]
    rec_test = [r for r in recordings if held_out(r)]
    rnd_train, rnd_test = random_fps[::2], random_fps[1::2]
    print(f"{len(random_fps)} random fingerprints, {len(recordings)} recordings")

    if args.current:
        print(f"\nConstants now in {args.current}, on the held-out half:")
        evaluate(
            Basis(read_basis(args.current)),
            rec_test,
            rnd_test,
            np.random.default_rng(args.seed),
        )

    print("\nFitted on half the recordings, scored on the other half:")
    d = fit(rnd_train, shared_pairs(rec_train), args.window, args.step)
    print(f"  song / mastering variance per axis: {d['_stats']['song_to_mastering']}")
    evaluate(Basis(d), rec_test, rnd_test, np.random.default_rng(args.seed))

    print("\nRefitting on everything")
    d = fit(random_fps, shared_pairs(recordings), args.window, args.step)
    print(
        f"  {d['_stats']['windows']} windows, {d['_stats']['noise_windows']} aligned same-audio windows, "
        f"song / mastering variance per axis: {d['_stats']['song_to_mastering']}"
    )
    block = js_block(d)
    if args.write:
        text = open(args.write).read()
        if not BLOCK_RE.search(text):
            raise SystemExit(f"{args.write} has no BEGIN/END BARCODE_BASIS markers")
        text = BLOCK_RE.sub(lambda m: m.group(1) + block + m.group(2), text)
        open(args.write, "w").write(text)
        print(f"Wrote the constants into {args.write}")
    else:
        print("\n" + block)


if __name__ == "__main__":
    main()
