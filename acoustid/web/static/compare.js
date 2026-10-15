// The comparison page: alignment slider, zoom and the score-by-offset chart.

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("compare");
  if (!root) return;
  const A = JSON.parse(root.dataset.a);
  const B = JSON.parse(root.dataset.b);
  const slider = document.getElementById("offset");
  const zoomGroup = root.querySelector("[data-zoom]");
  const scan = scanOffsets(A, B);
  let offset = scan.best.offset;
  slider.value = offset;
  let zoom = 2;

  const signed = (n) => `${n > 0 ? "+" : ""}${n}`;
  const seconds = (frames, d = 2) => `${(frames * FRAME_SEC).toFixed(d)} s`;

  function update() {
    const r = compareAt(A, B, offset);
    const [cls, text] = verdict(r.score);
    document.getElementById("offset-out").textContent = `${signed(offset)} frames (${seconds(offset)})`;
    document.getElementById("f-score").textContent = r.score.toFixed(2);
    document.getElementById("f-verdict").innerHTML = `<span class="pill ${cls}">${esc(text)}</span>`;
    document.getElementById("f-ber").textContent = fmt.pct(r.ber);
    document.getElementById("f-overlap").textContent = fmt.dur(r.overlap * FRAME_SEC);
    document.getElementById("f-frames").textContent = fmt.int(r.overlap);

    // Shared timeline: A starts at frame 0, B at `offset`.
    const start = Math.min(0, offset);
    const end = Math.max(A.length, B.length + offset);
    const frames = end - start;
    const widthPx = frames * zoom + "px";

    const cvA = document.getElementById("cv-a"), cvB = document.getElementById("cv-b");
    const cvD = document.getElementById("cv-d"), cvE = document.getElementById("cv-e");
    drawFingerprint(cvA, A, { start: -start, length: frames });
    drawFingerprint(cvB, B, { start: offset - start, length: frames });
    const xor = [];
    for (let t = start; t < end; t++) {
      const ia = t, ib = t - offset;
      xor.push(ia >= 0 && ia < A.length && ib >= 0 && ib < B.length ? A[ia] ^ B[ib] : null);
    }
    drawFingerprint(cvD, xor, { length: frames, diff: true });
    [cvA, cvB, cvD].forEach((c) => (c.style.width = widthPx));

    // Bit errors over time.
    const errs = smooth(errorTimeline(A, B, offset), 6);
    const dpr = window.devicePixelRatio || 1;
    cvE.style.width = widthPx;
    cvE.width = frames * zoom * dpr;
    cvE.height = 56 * dpr;
    const ctx = cvE.getContext("2d");
    ctx.scale(dpr, dpr);
    const yOf = (v) => 4 + (1 - v / 0.6) * 48;
    ctx.fillStyle = cssVar("--bg");
    ctx.fillRect(0, 0, frames * zoom, 56);
    ctx.strokeStyle = cssVar("--line-strong");
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(0, yOf(0.5)); ctx.lineTo(frames * zoom, yOf(0.5)); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = cssVar("--muted");
    ctx.font = "10px " + cssVar("--font");
    ctx.fillText("random (50 %)", 4, yOf(0.5) - 3);
    ctx.strokeStyle = cssVar("--fp-diff");
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let pen = false;
    errs.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      const x = i * zoom + zoom / 2, y = yOf(Math.min(v, 0.6));
      pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      pen = true;
    });
    ctx.stroke();

    timeAxis(document.getElementById("axis"), frames, start, zoom);

    lineChart(document.getElementById("scan"), {
      labels: scan.results.map((x) => x.offset),
      series: [{ name: "Score", color: cssVar("--series-1"), values: scan.results.map((x) => x.score), tipFormat: (v) => v.toFixed(3) }],
      height: 200,
      yFormat: (v) => v.toFixed(2),
      xTick: (o) => o % 20 === 0,
      xFormat: (o, long) => long ? `offset ${signed(o)} frames (${seconds(o, 1)})` : signed(o),
      area: true,
      markers: [
        { index: scan.results.findIndex((x) => x.offset === scan.best.offset), color: cssVar("--muted"), label: "best" },
        ...(offset !== scan.best.offset ? [{ index: scan.results.findIndex((x) => x.offset === offset), color: cssVar("--fp-diff"), label: "current" }] : []),
      ],
    });
  }

  slider.addEventListener("input", () => { offset = Number(slider.value); update(); });
  document.getElementById("auto").addEventListener("click", () => {
    offset = scan.best.offset;
    slider.value = offset;
    update();
  });
  zoomGroup.addEventListener("click", (e) => {
    const z = Number(e.target.dataset.z);
    if (!z) return;
    zoom = z;
    setPressed(zoomGroup, e.target);
    update();
  });

  const a = document.getElementById("pick-a"), b = document.getElementById("pick-b");
  const go = () => (location.href = `/fingerprint/${a.value}/compare/${b.value}`);
  a.addEventListener("change", go);
  b.addEventListener("change", go);

  update();
});
