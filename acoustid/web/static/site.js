// Small enhancements on top of the server-rendered pages. Data comes from
// data-* attributes the templates fill in.

const fmt = {
  int: (n) => n == null ? "–" : n.toLocaleString("en-US"),
  compact: (n) => Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n),
  pct: (x, d = 1) => (100 * x).toFixed(d) + " %",
  dur: (s) => s == null ? "–" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`,
  date: (s) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  longDate: (s) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }),
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function setPressed(group, button) {
  group.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b === button));
}

document.addEventListener("DOMContentLoaded", () => {
  // Fingerprint thumbnails and inline drawings.
  for (const canvas of document.querySelectorAll("canvas[data-fp]")) {
    const frames = canvas.dataset.frames ? Number(canvas.dataset.frames) : null;
    drawFingerprint(canvas, JSON.parse(canvas.dataset.fp), { length: frames });
  }

  // Hero background.
  for (const el of document.querySelectorAll(".band-art[data-fp]")) {
    drawHeroArt(el, JSON.parse(el.dataset.fp));
  }

  // Charts on the stats page.
  for (const el of document.querySelectorAll("[data-chart]")) {
    const chart = JSON.parse(el.dataset.chart);
    if (chart.tip === "hit-rate") {
      const [all, hits] = chart.series;
      el._extraTip = (i) => `<div class="row"><span class="muted">Hit rate</span><b>${fmt.pct(hits.values[i] / all.values[i])}</b></div>`;
    }
    lineChart(el, {
      labels: chart.labels,
      series: chart.series,
      area: chart.area,
      xFormat: (d, long) => long ? fmt.longDate(d) : fmt.date(d),
    });
  }

  // A single fingerprint with zoom buttons.
  for (const view of document.querySelectorAll("[data-fp-view]")) {
    const data = JSON.parse(view.dataset.fp);
    const canvas = view.querySelector("canvas");
    const axis = view.querySelector(".time-axis");
    const zoom = view.closest("section").querySelector("[data-zoom]");
    const draw = (z) => {
      drawFingerprint(canvas, data);
      canvas.style.width = data.length * z + "px";
      timeAxis(axis, data.length, 0, z);
    };
    zoom?.addEventListener("click", (e) => {
      const z = Number(e.target.dataset.z);
      if (!z) return;
      setPressed(zoom, e.target);
      draw(z);
    });
    draw(1);
  }

  // Copy buttons.
  for (const btn of document.querySelectorAll("button[data-copy]")) {
    btn.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(btn.dataset.copy); btn.textContent = "Copied"; }
      catch { btn.textContent = "Copy failed"; }
      setTimeout(() => (btn.textContent = "Copy"), 1200);
    });
  }

  // Picking two fingerprints on the track page.
  const table = document.getElementById("fingerprints");
  const compareBtn = document.getElementById("compare-btn");
  if (table && compareBtn) {
    const selected = () => [...table.querySelectorAll("input:checked")].map((i) => i.value);
    table.addEventListener("change", (e) => {
      if (selected().length > 2) e.target.checked = false;
      compareBtn.disabled = selected().length !== 2;
    });
    compareBtn.addEventListener("click", () => {
      const [a, b] = selected();
      location.href = `/fingerprint/${a}/compare/${b}`;
    });
  }

  // "Compare with any fingerprint" on the fingerprint page.
  for (const form of document.querySelectorAll("form[data-compare-with]")) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const other = form.other.value.trim().replace(/^#/, "");
      if (other) location.href = `/fingerprint/${form.dataset.compareWith}/compare/${encodeURIComponent(other)}`;
    });
  }
});
