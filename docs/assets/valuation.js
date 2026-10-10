/*
 * Renders a valuation snapshot from docs/data/.
 *
 * Page config lives on <body>:
 *   data-index = "nasdaq" | "sp500"     which docs/data/{source}/{index}/ to read
 *   data-mode  = "full"   | "summary"   full adds the chart and the all-stocks table
 *
 * Valuation source (switch on the page, ?source=, remembered per browser):
 *   alphaspread   AlphaSpread intrinsic value and solvency score
 *   fairvalue     Fair Value and solvency score from our own Fair Value clone
 *   combined      per stock, the average of both sources' valuation gap and
 *                 solvency where both exist, otherwise whichever source has it
 *
 * The newest date in docs/data/{source}/manifest.js is shown by default;
 * ?date=YYYY-MM-DD (kept in sync with the date picker) selects another snapshot.
 * In combined mode each source contributes its newest snapshot on or before the
 * chosen date (at most a week older).
 *
 * Data files are loaded with <script> tags rather than fetch() so the pages also
 * work when opened straight from disk (file://). Each file registers its JSON
 * payload under window.nexusData[key]; see scripts/publish_site_data.py.
 *
 * Sign convention (from scripts/visualize.py): valuation_score > 0 means the
 * stock trades below its intrinsic value (undervalued), < 0 means overvalued.
 */
(function () {
  "use strict";

  const BUCKETS = [
    { label: "Strongly undervalued (>30%)", type: "Undervalued", min: 30, max: Infinity, token: "--under", alpha: 1 },
    { label: "Moderately undervalued (10–30%)", type: "Undervalued", min: 10, max: 30, token: "--under", alpha: 0.75 },
    { label: "Slightly undervalued (<10%)", type: "Undervalued", min: -Infinity, max: 10, token: "--under", alpha: 0.5 },
    { label: "Slightly overvalued (<10%)", type: "Overvalued", min: -Infinity, max: 10, token: "--over", alpha: 0.5 },
    { label: "Moderately overvalued (10–30%)", type: "Overvalued", min: 10, max: 30, token: "--over", alpha: 0.75 },
    { label: "Strongly overvalued (>30%)", type: "Overvalued", min: 30, max: Infinity, token: "--over", alpha: 1 },
  ];

  const body = document.body;
  const INDEX = body.dataset.index;
  const MODE = body.dataset.mode || "full";
  const $ = (id) => document.getElementById(id);

  const SOURCES = {
    alphaspread: { label: "AlphaSpread", value: "AlphaSpread intrinsic value", note: 'Valuations from <a href="https://www.alphaspread.com" target="_blank" rel="noopener">AlphaSpread</a>' },
    fairvalue: { label: "Fair Value", value: "Fair Value", note: 'Valuations from our <a href="fairvalue/index.html">Fair Value model</a> (SEC filings + market prices)' },
    combined: { label: "Combined", value: "combined AlphaSpread + Fair Value value", note: 'Average of <a href="https://www.alphaspread.com" target="_blank" rel="noopener">AlphaSpread</a> and our <a href="fairvalue/index.html">Fair Value model</a>' },
  };
  const COMBINE_MAX_LAG_DAYS = 7;
  let source = "alphaspread";
  let manifests = { alphaspread: {}, fairvalue: {} };
  let combineInfo = null;

  let manifestDates = [];
  let weights = null;
  let records = [];
  let chartSort = "solvency";
  let tableSort = { key: "valuation_score", dir: -1 };

  // ---------- formatting ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 2) => (typeof v === "number" && isFinite(v) ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
  const longDate = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const shortDate = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const verdictWord = (score) => (score >= 0 ? "undervalued" : "overvalued");
  function verdictHTML(score, digits = 1) {
    if (typeof score !== "number" || !isFinite(score)) return '<span class="muted">—</span>';
    const cls = score >= 0 ? "under" : "over";
    const word = score >= 0 ? "Undervalued" : "Overvalued";
    return `<span class="verdict ${cls}">${word} ${Math.abs(score).toFixed(digits)}%</span>`;
  }

  // ---------- data ----------
  // fresh: append a cache-buster for files that change between runs (the manifest).
  function loadData(key, fresh) {
    const store = (window.nexusData = window.nexusData || {});
    if (store[key]) return Promise.resolve(store[key]);
    return new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = `data/${key}.js` + (fresh ? `?v=${Date.now()}` : "");
      el.onload = () => (el.remove(), store[key] ? resolve(store[key]) : reject(new Error(`data/${key}.js did not register its data`)));
      el.onerror = () => (el.remove(), reject(new Error(`data/${key}.js could not be loaded`)));
      document.head.appendChild(el);
    });
  }

  function clean(data) {
    return Object.values(data).filter((r) => r && r.symbol && !r.error && typeof r.valuation_score === "number");
  }

  // ---------- sources ----------
  function datesFor(src) {
    if (src !== "combined") return manifests[src][INDEX] || [];
    const all = new Set([...(manifests.alphaspread[INDEX] || []), ...(manifests.fairvalue[INDEX] || [])]);
    return [...all].sort().reverse();
  }

  // Newest snapshot of `src` on or before `date`, at most COMBINE_MAX_LAG_DAYS older.
  function snapshotOnOrBefore(src, date) {
    const lagMs = COMBINE_MAX_LAG_DAYS * 864e5;
    return (manifests[src][INDEX] || []).find((d) => d <= date && Date.parse(date) - Date.parse(d) <= lagMs) || null;
  }

  async function loadRecords(date) {
    if (source !== "combined") {
      combineInfo = null;
      return clean(await loadData(`${source}/${INDEX}/${date}`));
    }
    const dA = snapshotOnOrBefore("alphaspread", date), dG = snapshotOnOrBefore("fairvalue", date);
    const [a, g] = await Promise.all([
      dA ? loadData(`alphaspread/${INDEX}/${dA}`).then(clean) : [],
      dG ? loadData(`fairvalue/${INDEX}/${dG}`).then(clean) : [],
    ]);
    const bySym = new Map();
    for (const r of a) bySym.set(r.symbol, { a: r });
    for (const r of g) bySym.set(r.symbol, { ...(bySym.get(r.symbol) || {}), g: r });
    const mean = (xs) => { const v = xs.filter((x) => typeof x === "number" && isFinite(x)); return v.length ? v.reduce((p, q) => p + q, 0) / v.length : null; };
    let both = 0;
    const out = [];
    for (const [sym, { a: ra, g: rg }] of bySym) {
      if (ra && rg) both++;
      const score = mean([ra?.valuation_score, rg?.valuation_score]);
      out.push({
        symbol: sym,
        company: ra?.company || rg?.company,
        url: ra?.url || rg?.url,
        fv_url: rg?.url || null,
        valuation_score: score,
        valuation_type: score >= 0 ? "Undervalued" : "Overvalued",
        intrinsic_value: mean([ra?.intrinsic_value, rg?.intrinsic_value]),
        current_price_approx: rg?.current_price_approx ?? ra?.current_price_approx,
        solvency_score: (() => { const v = mean([ra?.solvency_score, rg?.solvency_score]); return v === null ? null : Math.round(v); })(),
        market_cap: rg?.market_cap,
        as_score: ra?.valuation_score ?? null,
        fair_val: rg?.valuation_score ?? null,
      });
    }
    combineInfo = { dA, dG, both, total: out.length };
    return out;
  }

  function sourceFromURL() {
    const q = new URLSearchParams(location.search).get("source");
    if (q && SOURCES[q]) return q;
    try { const s = localStorage.getItem("nexus-valuation-source"); if (s && SOURCES[s]) return s; } catch (e) { /* storage blocked */ }
    return "alphaspread";
  }

  // The switch in the page header, and its floating copy (#source-dock) that nexus.js
  // shows once the header scrolls away. Both render the same buttons and stay in sync.
  function setupSourceSwitch() {
    const buttons = Object.entries(SOURCES)
      .map(([k, v]) => `<button class="btn" data-source="${k}" aria-pressed="false">${v.label}</button>`).join("");
    ["source-switch", "source-dock"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.innerHTML = '<label>Source</label>' + buttons;
      el.addEventListener("click", (e) => {
        const b = e.target.closest("button[data-source]");
        if (b && b.dataset.source !== source) switchSource(b.dataset.source, true);
      });
    });
  }

  function syncSourceSwitch() {
    document.querySelectorAll("#source-switch button[data-source], #source-dock button[data-source]").forEach((b) => {
      const on = b.dataset.source === source;
      b.classList.toggle("primary", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.disabled = b.dataset.source !== "combined" && !(manifests[b.dataset.source][INDEX] || []).length;
    });
    const note = $("source-note");
    if (note) note.innerHTML = `${SOURCES[source].note}, refreshed daily. Not investment advice.`;
  }

  function switchSource(src, push) {
    const current = $("date-select").value;
    source = src;
    try { localStorage.setItem("nexus-valuation-source", src); } catch (e) { /* storage blocked */ }
    manifestDates = datesFor(src);
    fillPicker();
    syncSourceSwitch();
    if (!manifestDates.length) { showError(`No ${SOURCES[src].label} snapshots have been published for this index yet.`); return; }
    load(manifestDates.includes(current) ? current : manifestDates[0], push);
  }

  function summarize(rs) {
    const scores = rs.map((r) => r.valuation_score).sort((a, b) => a - b);
    const n = scores.length;
    const mean = n ? scores.reduce((a, b) => a + b, 0) / n : NaN;
    const median = n ? (n % 2 ? scores[(n - 1) / 2] : (scores[n / 2 - 1] + scores[n / 2]) / 2) : NaN;
    const solv = rs.map((r) => r.solvency_score).filter((v) => typeof v === "number");
    let wSum = 0, wScore = 0, wN = 0;
    for (const r of rs) {
      const w = (weights && weights[r.symbol]) || r.market_cap;
      if (w) { wSum += w; wScore += w * r.valuation_score; wN++; }
    }
    return {
      n, mean, median,
      capWeighted: wSum ? wScore / wSum : NaN, capN: wN,
      under: rs.filter((r) => r.valuation_type === "Undervalued").length,
      over: rs.filter((r) => r.valuation_type === "Overvalued").length,
      avgSolvency: solv.length ? solv.reduce((a, b) => a + b, 0) / solv.length : NaN,
    };
  }

  // ---------- date picker ----------
  function currentDateFromURL() {
    const d = new URLSearchParams(location.search).get("date");
    return d && manifestDates.includes(d) ? d : manifestDates[0];
  }

  function fillPicker() {
    $("date-select").innerHTML = manifestDates
      .map((d, i) => `<option value="${d}">${shortDate(d)}${i === 0 ? " · latest" : ""}</option>`)
      .join("");
  }

  function setupPicker() {
    const sel = $("date-select");
    fillPicker();
    sel.addEventListener("change", () => go(sel.value));
    $("date-prev").addEventListener("click", () => step(1));
    $("date-next").addEventListener("click", () => step(-1));
    $("date-latest").addEventListener("click", () => go(manifestDates[0]));
    window.addEventListener("popstate", () => {
      const src = sourceFromURL();
      if (src !== source) { source = src; manifestDates = datesFor(src); fillPicker(); syncSourceSwitch(); }
      load(currentDateFromURL(), false);
    });
  }

  function step(delta) {
    const i = manifestDates.indexOf($("date-select").value) + delta;
    if (i >= 0 && i < manifestDates.length) go(manifestDates[i]);
  }

  function go(date) { load(date, true); }

  function syncPicker(date) {
    const i = manifestDates.indexOf(date);
    $("date-select").value = date;
    $("date-prev").disabled = i >= manifestDates.length - 1;
    $("date-next").disabled = i <= 0;
    $("date-latest").disabled = i === 0;
  }

  // ---------- render ----------
  async function load(date, push) {
    syncPicker(date);
    if (push) {
      const url = new URL(location.href);
      if (date === manifestDates[0]) url.searchParams.delete("date");
      else url.searchParams.set("date", date);
      url.searchParams.set("source", source);
      history.pushState(null, "", url);
    }
    body.classList.add("loading");
    try {
      records = await loadRecords(date);
    } catch (e) {
      showError(`Could not load the snapshot for ${date}. ${e.message}`);
      return;
    } finally {
      body.classList.remove("loading");
    }
    renderAsOf(date);
    if (!records.length) {
      showError(`The ${date} snapshot contains no valued stocks.`);
      return;
    }
    $("error").hidden = true;
    const s = summarize(records);
    renderKPIs(s);
    renderNarrative(s, date);
    renderDistribution();
    renderExtremes();
    if (MODE === "full") {
      renderChart(s);
      renderTable();
    }
  }

  function renderAsOf(date) {
    const latest = date === manifestDates[0];
    let combined = "";
    if (combineInfo) {
      const part = (label, d) => (d ? `${label} ${esc(shortDate(d))}` : `no ${label} snapshot`);
      combined = `<span class="muted small">${part("AlphaSpread", combineInfo.dA)} + ${part("Fair Value", combineInfo.dG)} · ` +
        `${combineInfo.both} of ${combineInfo.total} stocks valued by both</span>`;
    }
    $("as-of").innerHTML =
      `<span>Showing <span class="hl-accent">${esc(SOURCES[source].label)}</span> data for <mark>${esc(longDate(date))}</mark></span>` +
      (latest
        ? '<span class="badge live">Latest snapshot</span>'
        : `<span class="badge past">Historical — latest is ${esc(shortDate(manifestDates[0]))}</span>`) + combined;
    document.title = `${body.dataset.title} · ${date}`;
  }

  function kpiGap(score, note) {
    if (!isFinite(score)) return { value: "—", sub: note };
    const cls = score >= 0 ? "under" : "over";
    return { value: `${Math.abs(score).toFixed(1)}%`, sub: `<span class="verdict ${cls}">${score >= 0 ? "Undervalued" : "Overvalued"}</span> · ${note}` };
  }

  function renderKPIs(s) {
    const capNote = s.capN ? `${s.capN} / ${s.n} with market cap` : "market-cap data unavailable";
    $("kpis").innerHTML = [
      { label: "Stocks valued", value: s.n, sub: `<span class="verdict under">${s.under} under</span> &nbsp; <span class="verdict over">${s.over} over</span>` },
      { label: "Equal-weight", ...kpiGap(s.mean, "average gap") },
      { label: "Median stock", ...kpiGap(s.median, "middle of the index") },
      { label: "Market-cap weighted", ...kpiGap(s.capWeighted, capNote) },
      { label: "Avg. solvency", value: isFinite(s.avgSolvency) ? `${s.avgSolvency.toFixed(0)}<span class="muted small"> / 100</span>` : "—", sub: "balance-sheet strength" },
    ]
      .map((k) => `<div class="panel kpi"><div class="label">${k.label}</div><div class="value">${k.value}</div><div class="sub">${k.sub}</div></div>`)
      .join("");
  }

  function renderNarrative(s, date) {
    const el = $("narrative");
    if (!el) return;
    const parts = [
      `On <mark>${esc(shortDate(date))}</mark>, <span class="hl-accent">${s.under} of ${s.n}</span> stocks trade below their ${esc(SOURCES[source].value)}.`,
      `The equal-weight portfolio is <mark>${verdictWord(s.mean)} by ${Math.abs(s.mean).toFixed(1)}%</mark>`,
    ];
    if (isFinite(s.capWeighted)) {
      parts[1] += `, while the market-cap weighted portfolio is <mark>${verdictWord(s.capWeighted)} by ${Math.abs(s.capWeighted).toFixed(1)}%</mark>.`;
    } else {
      parts[1] += ".";
    }
    el.innerHTML = parts.join(" ");
  }

  function bucketOf(r) {
    const mag = Math.abs(r.valuation_score);
    return BUCKETS.findIndex((b) => b.type === r.valuation_type && mag > (b.min === -Infinity ? -1 : b.min) && mag <= b.max);
  }

  function renderDistribution() {
    const counts = BUCKETS.map(() => 0);
    for (const r of records) {
      const i = bucketOf(r);
      if (i >= 0) counts[i]++;
    }
    const max = Math.max(1, ...counts);
    $("distribution").innerHTML = BUCKETS.map(
      (b, i) => `<div class="dist-row">
          <div class="dist-label">${b.label}</div>
          <div class="dist-track"><div class="dist-bar" style="width:${(counts[i] / max) * 100}%;background:var(${b.token});opacity:${b.alpha}"></div></div>
          <div class="dist-count">${counts[i]}</div>
        </div>`
    ).join("");
  }

  const linkAttrs = (url) => (/^https?:/.test(url || "") ? ' target="_blank" rel="noopener"' : "");

  function extremesTable(rows) {
    return `<div class="table-wrap"><table class="data">
      <thead><tr><th>Symbol</th><th>Company</th><th class="num">Valuation</th><th class="num">Solvency</th></tr></thead>
      <tbody>${rows
        .map((r) => `<tr><td><a class="sym" href="${esc(r.url)}"${linkAttrs(r.url)}>${esc(r.symbol)}</a></td>
          <td class="company">${esc(r.company)}</td><td class="num">${verdictHTML(r.valuation_score, 0)}</td>
          <td class="num">${r.solvency_score ?? "—"}</td></tr>`)
        .join("")}</tbody></table></div>`;
  }

  function renderExtremes() {
    const sorted = [...records].sort((a, b) => b.valuation_score - a.valuation_score);
    const k = MODE === "full" ? 10 : 8;
    $("most-under").innerHTML = extremesTable(sorted.slice(0, k));
    $("most-over").innerHTML = extremesTable(sorted.slice(-k).reverse());
  }

  // ---------- chart ----------
  function renderChart(s) {
    const C = Nexus.colors;
    if (!window.Plotly) return;
    const rs = [...records].sort((a, b) =>
      chartSort === "solvency"
        ? (a.solvency_score ?? 0) - (b.solvency_score ?? 0) || a.valuation_score - b.valuation_score
        : b.valuation_score - a.valuation_score
    );
    const custom = rs.map((r) => [
      r.company || r.symbol,
      `${r.valuation_type} by ${Math.abs(r.valuation_score).toFixed(0)}%`,
      num(r.intrinsic_value),
      num(r.current_price_approx),
      r.solvency_score ?? "n/a",
    ]);
    const trace = {
      type: "bar",
      x: rs.map((r) => r.symbol),
      y: rs.map((r) => r.valuation_score),
      marker: { color: rs.map((r) => (r.valuation_type === "Overvalued" ? C.negative : C.positive)), cornerradius: 3 },
      customdata: custom,
      hovertemplate:
        "<b>%{customdata[0]}</b> (%{x})<br>%{customdata[1]}<br>Intrinsic value: %{customdata[2]}<br>" +
        "Price: ~%{customdata[3]}<br>Solvency: %{customdata[4]}/100<extra></extra>",
    };
    const avgColor = s.mean >= 0 ? C.positiveInk : C.negativeInk;
    const layout = Nexus.plotlyLayout({
      margin: { l: 56, r: 16, t: 16, b: 70 },
      bargap: 0.15,
      showlegend: false,
      xaxis: { tickangle: -90, tickfont: { size: rs.length > 150 ? 7 : 9 }, title: { text: chartSort === "solvency" ? "Ticker (sorted by solvency ↑)" : "Ticker (most undervalued → most overvalued)", standoff: 8 } },
      yaxis: { title: { text: "Valuation gap (%)" }, zeroline: true, ticksuffix: "%" },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: s.mean, y1: s.mean, line: { color: avgColor, width: 1.5, dash: "dash" } }],
      annotations: [{ xref: "paper", x: 1, y: s.mean, yanchor: "bottom", xanchor: "right", yshift: 2, showarrow: false, bgcolor: Nexus.rgba(C.surface, 0.9), borderpad: 3, text: `equal-weight avg ${s.mean >= 0 ? "+" : ""}${s.mean.toFixed(1)}%`, font: { color: avgColor, size: 12 } }],
    });
    Plotly.react("chart", [trace], layout, Nexus.plotlyConfig);
  }

  // ---------- table ----------
  const BASE_COLUMNS = [
    { key: "symbol", label: "Symbol" },
    { key: "company", label: "Company" },
    { key: "valuation_score", label: "Valuation", num: true },
    { key: "intrinsic_value", label: "Intrinsic value", num: true },
    { key: "current_price_approx", label: "Price", num: true },
    { key: "solvency_score", label: "Solvency", num: true },
  ];
  function columns() {
    if (source === "fairvalue") return [...BASE_COLUMNS, { key: "quality_score", label: "Quality Score", num: true }];
    if (source === "combined") return [...BASE_COLUMNS, { key: "as_score", label: "AlphaSpread", num: true, verdict: true }, { key: "fair_val", label: "Fair Value", num: true, verdict: true }];
    return BASE_COLUMNS;
  }
  function extraCells(r) {
    if (source === "fairvalue") return `<td class="num">${r.quality_score ?? "—"}</td>`;
    if (source === "combined") {
      const gf = r.fv_url ? `<a href="${esc(r.fv_url)}">${verdictHTML(r.fair_val, 0)}</a>` : verdictHTML(r.fair_val, 0);
      return `<td class="num">${verdictHTML(r.as_score, 0)}</td><td class="num">${gf}</td>`;
    }
    return "";
  }

  function highlight(text, q) {
    const s = esc(text);
    if (!q) return s;
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig");
    return s.replace(re, "<mark>$1</mark>");
  }

  function renderTable() {
    const q = ($("search").value || "").trim();
    const filter = $("filter").value;
    const ql = q.toLowerCase();
    let rows = records.filter(
      (r) =>
        (!ql || r.symbol.toLowerCase().includes(ql) || (r.company || "").toLowerCase().includes(ql)) &&
        (filter === "all" || r.valuation_type === filter)
    );
    const { key, dir } = tableSort;
    rows.sort((a, b) => {
      const va = a[key], vb = b[key];
      if (typeof va === "number" || typeof vb === "number") return ((va ?? -Infinity) - (vb ?? -Infinity)) * dir;
      return String(va ?? "").localeCompare(String(vb ?? "")) * dir;
    });
    $("table-head").innerHTML =
      "<tr>" +
      columns().map(
        (c) => `<th class="sortable${c.num ? " num" : ""}" data-key="${c.key}">${c.label}${c.key === key ? `<span class="arrow">${dir > 0 ? "↑" : "↓"}</span>` : ""}</th>`
      ).join("") +
      "</tr>";
    $("table-body").innerHTML = rows
      .map(
        (r) => `<tr>
          <td><a class="sym" href="${esc(r.url)}"${linkAttrs(r.url)}>${highlight(r.symbol, q)}</a></td>
          <td class="company">${highlight(r.company, q)}</td>
          <td class="num">${verdictHTML(r.valuation_score, 0)}</td>
          <td class="num">${num(r.intrinsic_value)}</td>
          <td class="num">${num(r.current_price_approx)}</td>
          <td class="num">${r.solvency_score ?? "—"}</td>${extraCells(r)}
        </tr>`
      )
      .join("");
    $("table-count").innerHTML = `Showing <span class="hl-accent">${rows.length}</span> of ${records.length} stocks`;
  }

  function setupTable() {
    $("search").addEventListener("input", renderTable);
    $("filter").addEventListener("change", renderTable);
    $("table-head").addEventListener("click", (e) => {
      const th = e.target.closest("th[data-key]");
      if (!th) return;
      const k = th.dataset.key;
      tableSort = tableSort.key === k ? { key: k, dir: -tableSort.dir } : { key: k, dir: k === "symbol" || k === "company" ? 1 : -1 };
      renderTable();
    });
    document.querySelectorAll("[data-chart-sort]").forEach((b) =>
      b.addEventListener("click", () => {
        chartSort = b.dataset.chartSort;
        document.querySelectorAll("[data-chart-sort]").forEach((x) => x.classList.toggle("primary", x === b));
        renderChart(summarize(records));
      })
    );
  }

  function showError(msg) {
    const el = $("error");
    el.textContent = msg;
    el.hidden = false;
  }

  async function init() {
    try {
      const [ma, mg, w] = await Promise.all([
        loadData("alphaspread/manifest", true).then((m) => m).catch(() => ({})),
        loadData("fairvalue/manifest", true).then((m) => m).catch(() => ({})),
        loadData("sp500_weights").catch(() => null),
      ]);
      manifests = { alphaspread: ma || {}, fairvalue: mg || {} };
      weights = w;
      source = sourceFromURL();
      if (source !== "combined" && !datesFor(source).length) source = datesFor("alphaspread").length ? "alphaspread" : "fairvalue";
      manifestDates = datesFor(source);
    } catch (e) {
      showError(`Could not load the list of available dates. ${e.message}`);
      return;
    }
    if (!manifestDates.length) {
      showError("No snapshots have been published for this index yet.");
      return;
    }
    setupSourceSwitch();
    syncSourceSwitch();
    setupPicker();
    if (MODE === "full") setupTable();
    load(currentDateFromURL(), false);
  }

  init();
})();
