// Background art for the landing page hero.

const HERO_W = 1200, HERO_H = 320;

function smoothPath(points) {
  // Catmull-Rom spline through the points, as cubic Bezier segments.
  let d = `M${points[0][0].toFixed(1)},${points[0][1].toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i], p1 = points[i], p2 = points[i + 1], p3 = points[i + 2] ?? p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

// Soft sweeping ribbons, like the acoustid.biz header but tone-on-tone on
// the light background. Each ribbon is a band between two nearby curves,
// widest in the middle, with a faint edge line.
function artRibbons(fp) {
  const samples = 60;
  const ribbons = [
    // [center y, amplitude, cycles across, phase, max width]
    [150, 70, 0.55, 0.4, 46],
    [190, 55, 0.8, 2.1, 30],
    [120, 90, 0.45, 3.6, 22],
    [210, 40, 1.1, 5.0, 16],
    [170, 80, 0.65, 1.2, 10],
  ];
  // Nudge the phases with the fingerprint so the drawing is ours.
  const nudge = (k) => ((fp[k * 101] >>> 0) % 1000) / 1000;
  let out = "";
  ribbons.forEach(([cy, amp, cyc, ph, maxW], k) => {
    const p = ph + nudge(k) * 0.8;
    const top = [], bottom = [];
    for (let i = 0; i < samples; i++) {
      const t = i / (samples - 1);
      const x = -40 + t * (HERO_W + 80);
      const y = cy + amp * Math.sin(2 * Math.PI * cyc * t + p);
      const w = maxW * (0.15 + 0.85 * Math.sin(Math.PI * t) ** 2) * (0.6 + 0.4 * Math.sin(2 * Math.PI * cyc * 1.7 * t + p * 2));
      top.push([x, y - w / 2]);
      bottom.push([x, y + w / 2]);
    }
    const edge = smoothPath(top);
    const back = smoothPath(bottom.slice().reverse()).replace(/^M/, "L");
    out += `<path d="${edge}${back}Z" fill="var(--ink)" fill-opacity="0.028"/>`;
    out += `<path d="${edge}" fill="none" stroke="var(--ink)" stroke-opacity="0.06" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
  });
  return out;
}

function drawHeroArt(el, fp) {
  // Stretched to the band; strokes don't scale.
  el.innerHTML = `<svg viewBox="0 0 ${HERO_W} ${HERO_H}" preserveAspectRatio="none" aria-hidden="true">${artRibbons(fp)}</svg>`;
}
