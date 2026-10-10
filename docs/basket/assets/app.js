/* app.js — shared runtime for the Basket Rotation pages.
 *
 * Data comes from data/manifest.js and data/runs/<id>.js, written by
 * `python -m mrscore.cli.export_web`. They are loaded as <script> tags (not
 * fetch) so every page also works when opened straight from disk (file://).
 */
(function () {
  "use strict";

  const RUN_KEY = "basket-rotation.run";

  window.nexusData = window.nexusData || {};

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.onload = resolve;
      el.onerror = () => reject(new Error("Could not load " + src));
      document.head.appendChild(el);
    });
  }

  // nexus.js is loaded in each page's <head>; kept so callers can still await it.
  async function ensureNexus() {}

  const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);
  function merge(base, extra) {
    const out = { ...base };
    for (const [k, v] of Object.entries(extra || {})) out[k] = isObj(v) && isObj(base[k]) ? merge(base[k], v) : v;
    return out;
  }

  // ------------------------------------------------------------------ runs
  const params = new URLSearchParams(location.search);

  function storedRun() { try { return localStorage.getItem(RUN_KEY); } catch (_) { return null; } }
  function storeRun(id) { try { localStorage.setItem(RUN_KEY, id); } catch (_) { /* private mode */ } }

  async function loadManifest() {
    await loadScript("data/manifest.js?v=" + Date.now());
    return window.nexusData.basket_manifest || [];
  }

  /** Load the run named in ?run=, else the last one viewed, else the newest. */
  async function loadRun() {
    const [manifest] = await Promise.all([loadManifest(), ensureNexus()]);
    if (!manifest.length) throw new Error("No runs published yet. From the basket/ folder run: PYTHONPATH=src python3 -m mrscore.cli.export_web");
    const ids = manifest.map((m) => m.id);
    let id = params.get("run");
    if (!ids.includes(id)) id = ids.includes(storedRun()) ? storedRun() : ids[0];
    storeRun(id);
    const key = "runs/" + id;
    if (!window.nexusData[key]) await loadScript("data/runs/" + id + ".js");
    return { manifest, run: window.nexusData[key], id, isLatest: id === ids[0] };
  }

  function withRun(href, id, extra) {
    const u = new URL(href, location.href);
    u.searchParams.set("run", id);
    for (const [k, v] of Object.entries(extra || {})) u.searchParams.set(k, v);
    return u.pathname.split("/").pop() + u.search;
  }

  /** Run picker in the Nexus .date-bar control group; navigation keeps other URL params. */
  function mountRunPicker(el, manifest, id) {
    el.innerHTML = `<label for="run-select">Run</label>
      <button class="btn" data-step="1" title="Older run" aria-label="Older run">‹</button>
      <select id="run-select">${manifest.map((m) => `<option value="${m.id}">${runLabel(m)}</option>`).join("")}</select>
      <button class="btn" data-step="-1" title="Newer run" aria-label="Newer run">›</button>
      <button class="btn primary" data-latest>Latest</button>`;
    const sel = el.querySelector("select");
    sel.value = id;
    const go = (to) => { if (to && to !== id) { storeRun(to); const u = new URL(location.href); u.searchParams.set("run", to); location.href = u.toString(); } };
    sel.onchange = () => go(sel.value);
    const i = manifest.findIndex((m) => m.id === id);
    el.querySelectorAll("[data-step]").forEach((b) => {
      const j = i + Number(b.dataset.step);
      b.disabled = j < 0 || j >= manifest.length;
      b.onclick = () => go(manifest[j].id);
    });
    const latest = el.querySelector("[data-latest]");
    latest.disabled = i === 0;
    latest.onclick = () => go(manifest[0].id);
  }

  function runLabel(m) {
    const d = new Date(m.created_at);
    return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) + " · " + m.config_hash;
  }

  /** Point nav links at the current run. */
  function wireNav(id) {
    document.querySelectorAll(".nav a, a[data-keep-run]").forEach((a) => {
      const href = a.getAttribute("href");
      if (href && !href.startsWith("http") && !href.startsWith("#")) a.setAttribute("href", withRun(href, id));
    });
  }

  function showError(err) {
    const box = document.getElementById("error");
    if (box) { box.textContent = err.message || String(err); box.hidden = false; }
    console.error(err);
  }

  // ------------------------------------------------------------ formatting
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  const fmt = {
    pct: (v, d = 1) => (isNum(v) ? (v * 100).toFixed(d) + "%" : "–"),
    spct: (v, d = 1) => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%" : "–"),
    num: (v, d = 2) => (isNum(v) ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "–"),
    sig: (v, s = 4) => (isNum(v) ? Number(v.toPrecision(s)).toString() : "–"),
    int: (v) => (isNum(v) ? Math.round(v).toLocaleString("en-US") : "–"),
    money: (v, d = 0) => (isNum(v) ? (v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "–"),
    smoney: (v, d = 0) => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "–"),
    date: (s) => (s ? new Date(s + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "–"),
  };
  const sign = (v) => (isNum(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "dim");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function chips(list, role) { return `<span class="chips">${list.map((s) => `<span class="chip ${role}">${esc(s)}</span>`).join("")}</span>`; }
  function ratioHTML(job) {
    return `<span class="ratio">${chips(job.num, "num")}<span class="over-sign" aria-label="divided by">÷</span>${chips(job.den, "den")}</span>`;
  }

  // ------------------------------------------------------- derived figures
  /** Equal-weight buy & hold of `idx` columns from bar i0, scaled to `cash`. */
  function buyHold(panel, idx, i0, cash) {
    const T = panel.dates.length, out = new Array(T).fill(null);
    for (let t = i0; t < T; t++) {
      let s = 0;
      for (const j of idx) s += panel.close[j][t] / panel.close[j][i0];
      out[t] = (cash * s) / idx.length;
    }
    return out;
  }

  /** Metrics + benchmarks for a top-k entry, memoized on the object. */
  function derive(run, job) {
    if (job._d) return job._d;
    const bt = job.backtest;
    const d = { metrics: bt ? window.mrscore.metrics(bt) : null };
    if (bt && bt.equity.i.length) {
      const i0 = bt.equity.i[0], cash = bt.initial_cash, all = run.panel.symbols.map((_, j) => j);
      d.i0 = i0;
      d.bench = { num: buyHold(run.panel, job.num_idx, i0, cash), den: buyHold(run.panel, job.den_idx, i0, cash), all: buyHold(run.panel, all, i0, cash) };
      d.benchReturn = Object.fromEntries(Object.entries(d.bench).map(([k, v]) => [k, v[v.length - 1] / cash - 1]));
    }
    const e = job.engine;
    d.reversionRate = e.total ? e.reverted / e.total : NaN;
    return (job._d = d);
  }

  /** Inline SVG sparkline of an equity curve, coloured by its overall sign. */
  function sparkline(values, w = 120, h = 30) {
    if (!values || values.length < 2) return "";
    const step = Math.max(1, Math.floor(values.length / w));
    const v = values.filter((_, i) => i % step === 0 || i === values.length - 1);
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = v.map((y, i) => `${((i / (v.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((y - lo) / span) * (h - 4)).toFixed(1)}`).join(" ");
    const up = v[v.length - 1] >= v[0];
    const col = up ? "var(--under)" : "var(--over)";
    const baseY = (h - 2 - ((v[0] - lo) / span) * (h - 4)).toFixed(1);
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-label="Equity ${up ? "up" : "down"}">
      <line x1="1" x2="${w - 1}" y1="${baseY}" y2="${baseY}" stroke="var(--border-strong)" stroke-width="1"/>
      <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
  }

  // ---------------------------------------------------------------- charts
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  function palette() {
    const c = window.Nexus.colors;
    return Object.assign({}, c, { num: css("--leg-num") || c.accent, den: css("--leg-den") || c.series2, grey: c.faint });
  }
  const layout = (extra) => window.Nexus.plotlyLayout(merge({ hovermode: "x unified", margin: { l: 60, r: 18, t: 10, b: 40 },
    legend: { orientation: "h", y: 1.08, x: 0, bgcolor: "rgba(0,0,0,0)" }, xaxis: { showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: window.Nexus.colors.borderStrong, spikedash: "solid" } }, extra));
  const config = () => Object.assign({}, window.Nexus.plotlyConfig);

  /** Keep the x-range of several Plotly charts in lockstep (zoom/pan/reset). */
  function syncX(ids) {
    let busy = false;
    ids.forEach((id) => {
      const el = document.getElementById(id);
      el.on("plotly_relayout", (ev) => {
        if (busy) return;
        const upd = {};
        if (ev["xaxis.autorange"]) upd["xaxis.autorange"] = true;
        else if (ev["xaxis.range[0]"] !== undefined) upd["xaxis.range"] = [ev["xaxis.range[0]"], ev["xaxis.range[1]"]];
        else if (ev["xaxis.range"]) upd["xaxis.range"] = ev["xaxis.range"];
        else return;
        busy = true;
        Promise.all(ids.filter((o) => o !== id).map((o) => Plotly.relayout(o, upd))).finally(() => { busy = false; });
      });
    });
  }

  window.BN = { loadScript, loadRun, ensureNexus, mountRunPicker, wireNav, withRun, showError, fmt, sign, esc, chips, ratioHTML,
    derive, buyHold, sparkline, palette, layout, config, syncX, merge, isNum, params };
})();
