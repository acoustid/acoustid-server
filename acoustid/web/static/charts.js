// Tiny dependency-free SVG line chart with a hover crosshair.

function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}

function lineChart(el, { labels, series, height = 220, yFormat = fmt.compact, xFormat = (x) => x, yMin = 0, area = false, markers = [], xTick = null }) {
  const W = 720, H = height, L = 48, R = 12, T = 12, B = 26;
  const vals = series.flatMap((s) => s.values).filter((v) => v != null);
  const yMax = niceMax(Math.max(...vals));
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, labels.length - 1);
  const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);

  const ticks = 4;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map((s) => s.name).join(", "))}">`;
  svg += `<g class="grid axis">`;
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + ((yMax - yMin) * i) / ticks;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
    svg += `<text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${yFormat(v)}</text>`;
  }
  const every = Math.ceil(labels.length / 7);
  labels.forEach((l, i) => {
    if (xTick ? xTick(l, i) : i % every === 0) svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(xFormat(l))}</text>`;
  });
  svg += `</g>`;

  for (const m of markers) {
    svg += `<line x1="${x(m.index)}" x2="${x(m.index)}" y1="${T}" y2="${H - B}" stroke="${m.color}" stroke-dasharray="3 3"/>`;
    if (m.label) svg += `<text x="${x(m.index) + 4}" y="${T + 10}" font-size="11" fill="${m.color}">${esc(m.label)}</text>`;
  }

  for (const s of series) {
    let d = "", pen = false;
    s.values.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    if (area && s.values.every((v) => v != null)) {
      svg += `<path d="${d}L${x(s.values.length - 1)},${y(yMin)}L${x(0)},${y(yMin)}Z" fill="${s.color}" opacity="0.08"/>`;
    }
    svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width ?? 2}" stroke-linejoin="round" stroke-linecap="round"${s.dash ? ` stroke-dasharray="${s.dash}"` : ""}/>`;
  }
  svg += `<line class="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="${cssVar("--line-strong")}" visibility="hidden"/>`;
  svg += series.map((s, k) => `<circle class="dot dot-${k}" r="4" fill="${s.color}" stroke="${cssVar("--bg")}" stroke-width="2" visibility="hidden"/>`).join("");
  svg += `<rect class="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/>`;
  svg += `</svg>`;

  el.classList.add("chart");
  el.innerHTML = svg + `<div class="tip" hidden></div>`;
  const root = el.querySelector("svg");
  const tip = el.querySelector(".tip");
  const cross = root.querySelector(".cross");

  root.querySelector(".hit").addEventListener("pointermove", (ev) => {
    const pt = root.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const p = pt.matrixTransform(root.getScreenCTM().inverse());
    const i = Math.max(0, Math.min(labels.length - 1, Math.round(((p.x - L) / (W - L - R)) * (labels.length - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    series.forEach((s, k) => {
      const dot = root.querySelector(`.dot-${k}`);
      if (s.values[i] == null) { dot.setAttribute("visibility", "hidden"); return; }
      dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(s.values[i])); dot.setAttribute("visibility", "visible");
    });
    tip.innerHTML = `<div class="muted">${esc(xFormat(labels[i], true))}</div>` +
      series.filter((s) => !s.hideInTip).map((s) =>
        `<div class="row"><span><span class="swatch" style="background:${s.color}"></span>${esc(s.name)}</span><b>${(s.tipFormat ?? fmt.int)(s.values[i])}</b></div>`).join("") +
      (el._extraTip ? el._extraTip(i) : "");
    const scale = root.clientWidth / W;
    tip.style.left = x(i) * scale + "px";
    tip.style.top = Math.min(...series.map((s) => s.values[i] == null ? H : y(s.values[i]))) * scale + "px";
    tip.hidden = false;
  });
  root.querySelector(".hit").addEventListener("pointerleave", () => {
    tip.hidden = true;
    cross.setAttribute("visibility", "hidden");
    root.querySelectorAll(".dot").forEach((d) => d.setAttribute("visibility", "hidden"));
  });
}
