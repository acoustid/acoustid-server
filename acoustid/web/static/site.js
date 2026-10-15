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

  // Switching the thumbnails between raw bits and color barcodes. The choice
  // is remembered, and the barcodes are only computed when first shown.
  const thumbs = [...document.querySelectorAll("canvas.fp-thumb[data-fp]")].map((canvas) => ({
    canvas,
    data: JSON.parse(canvas.dataset.fp),
    length: canvas.dataset.frames ? Number(canvas.dataset.frames) : null,
  }));
  const modeSwitches = document.querySelectorAll("[data-fp-mode]");
  if (thumbs.length && modeSwitches.length) {
    let swatches = null;
    const show = (mode) => {
      if (mode === "colors" && !swatches) {
        for (const t of thumbs) t.windows = barcodeWindows(t.data, { length: t.length });
        swatches = barcodeSwatches(thumbs);
      }
      thumbs.forEach((t, i) => {
        if (mode === "colors") {
          drawBarcode(t.canvas, t.windows, { length: t.length, swatch: swatches[i] });
        } else {
          drawFingerprint(t.canvas, t.data, { length: t.length });
        }
        t.canvas.classList.toggle("is-barcode", mode === "colors");
      });
      for (const group of modeSwitches) setPressed(group, group.querySelector(`[data-mode="${mode}"]`));
      for (const group of orderSwitches) group.hidden = mode !== "colors";
      if (mode !== "colors") sortRows("sources");
    };

    // With colors shown, the rows can also be ordered by color: the first row,
    // then always the one whose swatch is closest to any taken so far, so
    // rows that sound alike end up together and the odd ones come last. An
    // expanded row moves with its row, and rows without a swatch stay at the
    // end in their original order.
    const orderSwitches = document.querySelectorAll("[data-fp-order]");
    const tbody = thumbs[0].canvas.closest("tbody");
    const rows = [...tbody.children].filter((tr) => !tr.classList.contains("links-row"));
    const details = new Map(rows.map((tr) => {
      const next = tr.nextElementSibling;
      return [tr, next?.classList.contains("links-row") ? next : null];
    }));
    const sortRows = (order) => {
      let sorted = rows;
      if (order === "color" && swatches) {
        const points = new Map();
        thumbs.forEach((t, i) => {
          if (!swatches[i]) return;
          const { t: ranks, u, v } = barcodePoint(swatches[i]);
          points.set(t.canvas.closest("tr"), [2 * ranks[0] - 1, u, v]);
        });
        const dist = (a, b) => points.get(a).reduce((sum, x, k) => sum + (x - points.get(b)[k]) ** 2, 0);
        const left = rows.filter((tr) => points.has(tr));
        sorted = left.length ? [left.shift()] : [];
        const nearest = new Map(left.map((tr) => [tr, dist(tr, sorted[0])]));
        while (left.length) {
          const next = left.reduce((best, tr) => (nearest.get(tr) < nearest.get(best) ? tr : best));
          sorted.push(next);
          left.splice(left.indexOf(next), 1);
          for (const tr of left) nearest.set(tr, Math.min(nearest.get(tr), dist(tr, next)));
        }
        sorted.push(...rows.filter((tr) => !points.has(tr)));
      }
      for (const tr of sorted) {
        tbody.append(tr);
        if (details.get(tr)) tbody.append(details.get(tr));
      }
      for (const group of orderSwitches) setPressed(group, group.querySelector(`[data-order="${order}"]`));
    };
    for (const group of orderSwitches) {
      group.addEventListener("click", (e) => {
        const order = e.target.closest("button[data-order]")?.dataset.order;
        if (order) sortRows(order);
      });
    }

    let saved = null;
    try { saved = localStorage.getItem("fp-thumb-mode"); } catch {}
    if (saved === "colors") show("colors");
    for (const group of modeSwitches) {
      group.addEventListener("click", (e) => {
        const mode = e.target.closest("button[data-mode]")?.dataset.mode;
        if (!mode) return;
        show(mode);
        try { localStorage.setItem("fp-thumb-mode", mode); } catch {}
      });
    }
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
      el._extraTip = (i) => `<div class="row"><span class="muted">Hit rate</span><b>${(all.values[i] ? fmt.pct(hits.values[i] / all.values[i]) : "–")}</b></div>`;
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

  // Hovering a similarity grid cell highlights the two fingerprints or
  // AcoustIDs it compares, in the table above and in the grid's labels.
  for (const matrix of document.querySelectorAll("table.matrix[data-highlights]")) {
    const table = document.getElementById(matrix.dataset.highlights);
    if (!table) continue;
    const clear = () => {
      for (const el of document.querySelectorAll(".is-highlighted")) el.classList.remove("is-highlighted");
    };
    matrix.addEventListener("mouseover", (e) => {
      const cell = e.target.closest("td[data-a]");
      clear();
      if (!cell) return;
      const letter = (l) => `[data-letter="${CSS.escape(l)}"]`;
      // Both rows in the table, but in the grid only the cell's own row
      // label and column header.
      for (const l of [cell.dataset.a, cell.dataset.b]) {
        table.querySelector(`tr${letter(l)}`)?.classList.add("is-highlighted");
      }
      matrix.querySelector(`th.row${letter(cell.dataset.a)}`)?.classList.add("is-highlighted");
      matrix.querySelector(`th:not(.row)${letter(cell.dataset.b)}`)?.classList.add("is-highlighted");
    });
    matrix.addEventListener("mouseleave", clear);
  }

  // Rows that expand to show more, like all recordings an AcoustID is
  // linked to. Every button controlling the same row stays in sync.
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("button.row-toggle, button.link-button");
    const row = btn && document.getElementById(btn.getAttribute("aria-controls"));
    if (!row) return;
    row.hidden = !row.hidden;
    for (const b of document.querySelectorAll(`button.row-toggle[aria-controls="${CSS.escape(row.id)}"]`)) {
      b.setAttribute("aria-expanded", !row.hidden);
    }
  });

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
