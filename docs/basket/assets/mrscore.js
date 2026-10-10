/* mrscore.js — in-browser port of the mrscore engine and rotation backtester.
 *
 * Mirrors src/mrscore (components/*, core/engine.py, core/scoring.py,
 * backtest/backtester.py) step for step, so the Strategy Lab can re-run a scan
 * with edited parameters. The Python export stays the source of truth: the Lab
 * shows a parity check of this port against it on the unmodified config.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- estimators
  function RollingSMA(p) {
    const w = p.window;
    let buf, idx, count, sum;
    this.reset = () => { buf = new Float64Array(w); idx = 0; count = 0; sum = 0; this.value = 0; };
    this.isReady = () => count >= w;
    this.update = (x) => {
      if (count >= w) sum -= buf[idx]; else count++;
      buf[idx] = x; sum += x;
      if (++idx === w) idx = 0;
      return (this.value = sum / count);
    };
    this.reset();
  }

  function EMA(p) {
    const alpha = 2 / (p.span + 1), minP = p.min_periods ?? 1;
    let count, rsum, init;
    this.reset = () => { count = 0; rsum = 0; init = false; this.value = 0; };
    this.isReady = () => count >= minP;
    this.update = (x) => {
      count++;
      if (!init) {
        rsum += x; this.value = rsum / count;
        if (count >= minP) init = true;
        return this.value;
      }
      return (this.value = alpha * x + (1 - alpha) * this.value);
    };
    this.reset();
  }

  function KalmanMean(p) {
    const q = p.process_var, r = p.obs_var, minP = p.min_periods ?? 1;
    let count, P;
    this.reset = () => { count = 0; this.value = p.init_mean ?? 0; P = p.init_var ?? 1; };
    this.isReady = () => count >= minP;
    this.update = (y) => {
      count++;
      const Pp = P + q, x = this.value, K = Pp / (Pp + r);
      this.value = x + K * (y - x);
      P = (1 - K) * Pp;
      return this.value;
    };
    this.reset();
  }

  function EWMAVol(p) {
    const lam = 1 - 2 / (p.span + 1), minP = p.min_periods ?? 1, minVol = p.min_volatility ?? 0;
    let count, rss, s2, init;
    this.reset = () => { count = 0; rss = 0; s2 = 0; init = false; this.value = 0; };
    this.isReady = () => count >= minP;
    this.update = (x) => {
      count++;
      const x2 = x * x;
      if (!init) {
        rss += x2; s2 = rss / count; this.value = Math.sqrt(s2);
        if (count >= minP) init = true;
        if (this.value < minVol) this.value = minVol;
        return this.value;
      }
      s2 = lam * s2 + (1 - lam) * x2;
      const v = Math.sqrt(s2);
      return (this.value = v >= minVol ? v : minVol);
    };
    this.reset();
  }

  function RollingStd(p) {
    const w = p.window, minP = p.min_periods ?? 1, ddof = p.ddof ?? 0, minVol = p.min_volatility ?? 0;
    let buf, idx, count, sum, sumsq;
    this.reset = () => { buf = new Float64Array(w); idx = 0; count = 0; sum = 0; sumsq = 0; this.value = 0; };
    this.isReady = () => count >= minP;
    this.update = (x) => {
      if (count >= w) { const o = buf[idx]; sum -= o; sumsq -= o * o; } else count++;
      buf[idx] = x; sum += x; sumsq += x * x;
      if (++idx === w) idx = 0;
      const n = count, d = n - ddof;
      if (d <= 0) return (this.value = Math.max(minVol, 0));
      const m = sum / n;
      let v = (sumsq - n * m * m) / d;
      if (v < 0) v = 0;
      v = Math.sqrt(v);
      return (this.value = v >= minVol ? v : minVol);
    };
    this.reset();
  }

  function GARCH11Vol(p) {
    const minP = p.min_periods ?? 1, minS2 = (p.min_volatility ?? 0) ** 2;
    let count, s2, init;
    // Python's reset() always clears _initialized, so init_sigma2 never survives a run.
    this.reset = () => { count = 0; s2 = 0; init = false; this.value = 0; };
    this.isReady = () => count >= minP;
    this.update = (x) => {
      const x2 = x * x;
      count++;
      if (!init) { s2 = x2 > minS2 ? x2 : minS2; init = true; }
      else { s2 = p.omega + p.alpha * x2 + p.beta * s2; if (s2 < minS2) s2 = minS2; }
      return (this.value = Math.sqrt(s2));
    };
    this.reset();
  }

  const MEANS = { rolling_sma: RollingSMA, ema: EMA, kalman_mean: KalmanMean };
  const VOLS = { ewma: EWMAVol, rolling_std: RollingStd, garch11: GARCH11Vol };

  function buildComponents(cfg) {
    const M = MEANS[cfg.mean_estimator.type], V = VOLS[cfg.volatility_estimator.type];
    if (!M) throw new Error("Unsupported mean_estimator.type: " + cfg.mean_estimator.type);
    if (!V) throw new Error("Unsupported volatility_estimator.type: " + cfg.volatility_estimator.type);
    const dp = cfg.deviation_detector.params, fp = cfg.failure_criteria.params;
    const thr = dp.threshold, minMove = dp.min_absolute_move, tol = cfg.reversion_criteria.params.z_tolerance;
    const maxDur = fp.max_duration ?? null, maxZ = fp.max_zscore ?? null;
    return {
      mean: new M(cfg.mean_estimator.params),
      vol: new V(cfg.volatility_estimator.params),
      volUnit: cfg.volatility_estimator.params.volatility_unit || "returns",
      // ZScoreDeviationDetector: +1 = UP (below mean), -1 = DOWN (above mean), 0 = none
      detect(price, mean, vol) {
        if (vol <= 0) return 0;
        const move = price - mean;
        if (Math.abs(move) < minMove) return 0;
        const z = move / vol;
        if (Math.abs(z) < thr) return 0;
        return z > 0 ? -1 : 1;
      },
      isReverted: (z) => Math.abs(z) <= tol,
      isFailed: (dur, z) => (maxDur !== null && dur >= maxDur) || (maxZ !== null && Math.abs(z) >= maxZ),
    };
  }

  // ------------------------------------------------------------------- series
  function basketSeries(cols, idx, T) {
    const out = new Float64Array(T);
    for (let t = 0; t < T; t++) { let s = 0; for (const j of idx) s += cols[j][t]; out[t] = s; }
    return out;
  }

  function ratioSeries(cols, numIdx, denIdx, T) {
    const n = basketSeries(cols, numIdx, T), d = basketSeries(cols, denIdx, T), out = new Float64Array(T);
    for (let t = 0; t < T; t++) out[t] = n[t] / (d[t] + 1e-12);
    return out;
  }

  function returnsOf(p, mode) {
    const T = p.length, out = new Float64Array(Math.max(T - 1, 0));
    if (mode === "simple") for (let t = 1; t < T; t++) out[t - 1] = p[t] / p[t - 1] - 1;
    else if (mode === "log") for (let t = 1; t < T; t++) out[t - 1] = Math.log(p[t]) - Math.log(p[t - 1]);
    else throw new Error("Invalid returns mode: " + mode);
    return out;
  }

  // ------------------------------------------------------------------ scoring
  function quantileLinear(sorted, q) {
    const pos = q * (sorted.length - 1), lo = Math.floor(pos), hi = Math.min(lo + 1, sorted.length - 1), f = pos - lo;
    return sorted[lo] + (sorted[hi] - sorted[lo]) * f;
  }
  const meanFinite = (vs) => { const f = vs.filter(Number.isFinite); return f.length ? f.reduce((a, b) => a + b, 0) / f.length : NaN; };

  function scoreEvents(events, sc) {
    const total = events.length;
    let reverted = 0, failed = 0, expired = 0;
    for (const e of events) { if (e.status === "reverted") reverted++; else if (e.status === "failed") failed++; else expired++; }

    let byDir = null;
    if (sc.by_direction) {
      const r = (a, b) => (b === 0 ? (sc.record_empty_scores ? 0 : NaN) : a / b);
      const up = events.filter((e) => e.dir === "up"), dn = events.filter((e) => e.dir === "down");
      byDir = { up: r(up.filter((e) => e.status === "reverted").length, up.length),
                down: r(dn.filter((e) => e.status === "reverted").length, dn.length) };
    }

    let byVol = null;
    if (sc.by_volatility_bucket) {
      const k = sc.volatility_buckets | 0;
      const empty = sc.record_empty_scores ? 0 : NaN;
      const vols = events.map((e) => e.start_vol).filter(Number.isFinite).sort((a, b) => a - b);
      byVol = {};
      if (!vols.length) for (let i = 0; i < k; i++) byVol["bucket_" + i] = empty;
      else {
        const cuts = [];
        for (let i = 1; i < k; i++) cuts.push(quantileLinear(vols, i / k));
        const tot = new Array(k).fill(0), rev = new Array(k).fill(0);
        for (const e of events) {
          if (!Number.isFinite(e.start_vol)) continue;
          let b = 0; while (b < cuts.length && cuts[b] <= e.start_vol) b++;
          if (b >= k) b = k - 1;
          tot[b]++; if (e.status === "reverted") rev[b]++;
        }
        for (let i = 0; i < k; i++) byVol["bucket_" + i] = tot[i] ? rev[i] / tot[i] : empty;
      }
    }

    let sharpe = null;
    if (sc.compute_sharpe) {
      const rets = events.filter((e) => e.start_price !== 0 && Number.isFinite(e.end_price) && Number.isFinite(e.start_price))
        .map((e) => (e.dir === "up" ? 1 : -1) * (e.end_price - e.start_price) / e.start_price);
      if (rets.length >= 2) {
        const m = rets.reduce((a, b) => a + b, 0) / rets.length;
        const sd = Math.sqrt(rets.reduce((a, b) => a + (b - m) ** 2, 0) / (rets.length - 1));
        sharpe = sd > 0 ? m / sd : NaN;
      } else sharpe = NaN;
    }

    const rr = total ? reverted / total : 0;
    let score;
    if (total === 0 && !sc.record_empty_scores) score = NaN;
    else switch (sc.score_metric) {
      case "reversion_rate": score = rr; break;
      case "direction": score = byDir ? meanFinite(Object.values(byDir)) : NaN; break;
      case "volatility_bucket": score = byVol ? meanFinite(Object.values(byVol)) : NaN; break;
      case "sharpe": score = sharpe ?? NaN; break;
      default: {
        const c = [rr];
        if (byDir) c.push(meanFinite(Object.values(byDir)));
        if (byVol) c.push(meanFinite(Object.values(byVol)));
        if (sharpe !== null) c.push(sharpe);
        score = meanFinite(c);
      }
    }
    return { score, total, reverted, failed, expired, sharpe, byDir, byVol, events };
  }

  // ------------------------------------------------------------------- engine
  function runEngine(cfg, comps, prices, returns, trace) {
    const T = prices.length, eng = cfg.engine, minBars = cfg.data.min_bars_required;
    const { mean: M, vol: V } = comps, priceVol = comps.volUnit === "price";
    M.reset(); V.reset();
    let active = [];
    const events = [];
    const close = (ev, status, t, dur, maxAbs, p) => events.push({
      dir: ev.dir, status, s: ev.s, e: t, dur, start_z: ev.z, max_abs_z: maxAbs,
      start_price: ev.p, end_price: p, start_vol: ev.vol,
    });
    for (let t = 0; t < T; t++) {
      const p = prices[t];
      if (!(eng.freeze_mean_on_event && active.length)) M.update(p);
      if (priceVol) { if (!(eng.freeze_volatility_on_event && active.length)) V.update(p); }
      else if (t >= 1 && !(eng.freeze_volatility_on_event && active.length)) V.update(returns[t - 1]);

      if (t + 1 < minBars || !M.isReady() || !V.isReady()) continue;
      const mean = M.value, vol = V.value;
      if (!Number.isFinite(mean) || !Number.isFinite(vol) || vol <= 0) continue;
      const z = (p - mean) / vol;
      if (!Number.isFinite(z)) continue;
      if (trace) { trace.mean[t] = mean; trace.vol[t] = vol; trace.z[t] = z; }

      if (active.length) {
        const still = [];
        for (const ev of active) {
          const dur = t - ev.s, maxAbs = Math.max(ev.maxAbs, Math.abs(z));
          if (comps.isReverted(z)) { close(ev, "reverted", t, dur, maxAbs, p); continue; }
          if (comps.isFailed(dur, z)) { close(ev, "failed", t, dur, maxAbs, p); continue; }
          ev.maxAbs = maxAbs; still.push(ev);
        }
        active = still;
      }
      if (active.length < eng.max_active_events && (eng.allow_overlapping_events || !active.length)) {
        const d = comps.detect(p, mean, vol);
        if (d) active.push({ dir: d > 0 ? "up" : "down", s: t, p, z, vol, maxAbs: Math.abs(z) });
      }
    }
    for (const ev of active) close(ev, "expired", T - 1, T - 1 - ev.s, ev.maxAbs, prices[T - 1]);
    return scoreEvents(events, cfg.scoring);
  }

  // --------------------------------------------------------------- backtester
  function runBacktest(cfg, comps, cols, numIdx, denIdx, trace) {
    const bt = cfg.backtest, T = cols[0].length;
    const numLeg = numIdx.map((j) => cols[j]), denLeg = denIdx.map((j) => cols[j]);
    const ratio = ratioSeries(cols, numIdx, denIdx, T);
    const sigMode = bt.strategy.params.signal_series;
    const signal = sigMode === "log_ratio" ? ratio.map((r) => Math.log(Math.max(r, 1e-12))) : ratio;
    const priceVol = comps.volUnit === "price";
    let sigRet = null;
    if (!priceVol) {
      if (sigMode === "log_ratio") { sigRet = new Float64Array(T - 1); for (let t = 1; t < T; t++) sigRet[t - 1] = signal[t] - signal[t - 1]; }
      else sigRet = returnsOf(ratio, cfg.data.returns_mode);
    }
    const { mean: M, vol: V } = comps;
    M.reset(); V.reset();
    const bps = (bt.costs.commission_bps || 0) + (bt.costs.slippage_bps || 0);
    const cost = (n) => Math.abs(n) * (bps / 10000);
    const minBars = cfg.data.min_bars_required, eng = cfg.engine;

    let cash = bt.initial_cash, holding = null;
    const trades = [], eqI = [], eqV = [];
    const legPx = (leg, t) => (leg === "num" ? numLeg : denLeg).map((c) => c[t]);
    const equity = (t) => {
      if (!holding) return cash;
      const px = legPx(holding.leg, t); let s = cash;
      for (let i = 0; i < px.length; i++) s += holding.qty[i] * px[i];
      return s;
    };
    const sell = (t) => {
      const px = legPx(holding.leg, t);
      let proceeds = 0, gross = 0, pnl = 0;
      for (let i = 0; i < px.length; i++) {
        const v = holding.qty[i] * px[i];
        proceeds += v; gross += Math.abs(v); pnl += holding.qty[i] * (px[i] - holding.entryPx[i]);
      }
      const c = cost(gross);
      cash += proceeds - c;
      const costs = holding.entryCost + c;
      trades.push({ leg: holding.leg, dir: holding.leg === "num" ? "up" : "down", s: holding.s, e: t, dur: t - holding.s,
        gross_entry: holding.gross, gross_exit: gross, pnl, costs, net: pnl - costs });
      holding = null;
    };
    const buy = (t, leg) => {
      const px = legPx(leg, t), eq = cash, c = cost(eq), invest = eq - c;
      if (invest <= 0 || px.some((x) => x <= 0)) return;
      const per = invest / px.length;
      holding = { leg, s: t, entryPx: px, qty: px.map((x) => per / x), gross: invest, entryCost: c };
      cash = 0;
    };

    for (let t = 0; t < T; t++) {
      const s = signal[t];
      if (!(eng.freeze_mean_on_event && holding)) M.update(s);
      if (!(eng.freeze_volatility_on_event && holding)) {
        if (priceVol) V.update(s); else if (t >= 1) V.update(sigRet[t - 1]);
      }
      if (t + 1 < minBars || !M.isReady() || !V.isReady()) continue;
      eqI.push(t); eqV.push(equity(t));
      const mean = M.value, vol = V.value;
      if (!Number.isFinite(mean) || !Number.isFinite(vol) || vol <= 0) continue;
      const z = (s - mean) / vol;
      if (!Number.isFinite(z)) continue;
      if (trace) { trace.mean[t] = mean; trace.vol[t] = vol; trace.z[t] = z; }
      const d = comps.detect(s, mean, vol);
      let tgt = d === 0 ? null : d < 0 ? "den" : "num";
      if (!holding) { buy(t, tgt || "num"); continue; }
      if (tgt && tgt !== holding.leg) { sell(t); buy(t, tgt); }
    }
    if (holding) { sell(T - 1); if (eqV.length) { eqI[eqI.length - 1] = T - 1; eqV[eqV.length - 1] = cash; } }
    return { initial_cash: bt.initial_cash, final_equity: cash, total_return: cash / bt.initial_cash - 1, trades, equity: { i: eqI, v: eqV } };
  }

  // ------------------------------------------------------------------ universe
  function combinations(n, k) {
    const out = [], c = [];
    (function rec(start) {
      if (c.length === k) { out.push(c.slice()); return; }
      for (let i = start; i < n; i++) { c.push(i); rec(i + 1); c.pop(); }
    })(0);
    return out;
  }
  const overlaps = (a, b) => a.some((x) => b.includes(x));

  function iterJobs(N, ru) {
    const libN = combinations(N, ru.k_num), libD = ru.k_num === ru.k_den ? libN : combinations(N, ru.k_den);
    const jobs = [], max = ru.max_jobs ?? Infinity;
    if (ru.k_num === ru.k_den && ru.unordered_if_equal_k) {
      for (let i = 0; i < libN.length - 1 && jobs.length < max; i++)
        for (let j = i + 1; j < libN.length && jobs.length < max; j++)
          if (!(ru.disallow_overlap && overlaps(libN[i], libN[j]))) jobs.push([i, j]);
    } else {
      for (let i = 0; i < libN.length && jobs.length < max; i++)
        for (let j = 0; j < libD.length && jobs.length < max; j++)
          if (!(ru.disallow_overlap && overlaps(libN[i], libD[j]))) jobs.push([i, j]);
    }
    return { libN, libD, jobs };
  }

  /** Normalize each column by its first value (RatioUniverse(normalize_by_first=True)). */
  function normalizeCols(cols) {
    return cols.map((c) => { const b = c[0], o = new Float64Array(c.length); for (let t = 0; t < c.length; t++) o[t] = c[t] / b; return o; });
  }

  /**
   * Scan the whole ratio universe with `cfg`, in chunks so the page stays responsive.
   * `symbolsMask` (optional) restricts the universe to a subset of panel columns.
   */
  async function scanUniverse(cfg, panel, { onProgress, symbolsMask, signal } = {}) {
    const keep = panel.symbols.map((_, j) => j).filter((j) => !symbolsMask || symbolsMask[j]);
    const raw = keep.map((j) => panel.close[j]);
    const norm = normalizeCols(raw);
    const T = raw[0].length;
    const { libN, libD, jobs } = iterJobs(keep.length, cfg.ratio_universe);
    const comps = buildComponents(cfg);
    const priceVol = comps.volUnit === "price";
    if (!priceVol && cfg.data.returns_mode === "none") throw new Error("volatility_unit is 'returns' but returns_mode is 'none'");
    const scores = new Float64Array(jobs.length);
    const nEvents = new Int32Array(jobs.length);
    const CHUNK = 60;
    for (let a = 0; a < jobs.length; a += CHUNK) {
      if (signal && signal.aborted) throw new DOMException("aborted", "AbortError");
      for (let q = a; q < Math.min(a + CHUNK, jobs.length); q++) {
        const [i, j] = jobs[q];
        const r = ratioSeries(norm, libN[i], libD[j], T);
        const res = runEngine(cfg, comps, r, priceVol ? null : returnsOf(r, cfg.data.returns_mode));
        scores[q] = res.score; nEvents[q] = res.total;
      }
      onProgress && onProgress(Math.min(a + CHUNK, jobs.length) / jobs.length);
      await new Promise((res) => setTimeout(res, 0));
    }
    // TopKRanker semantics: keep first-seen on ties, then sort descending (stable).
    const k = cfg.visualization.top_k || 10;
    const order = [];
    for (let q = 0; q < jobs.length; q++) if (Number.isFinite(scores[q])) order.push(q);
    order.sort((x, y) => scores[y] - scores[x] || x - y);
    const top = order.slice(0, k).map((q, r) => {
      const [i, j] = jobs[q];
      const numIdx = libN[i].map((c) => keep[c]), denIdx = libD[j].map((c) => keep[c]);
      const ratio = ratioSeries(norm, libN[i], libD[j], T);
      const eng = runEngine(cfg, comps, ratio, priceVol ? null : returnsOf(ratio, cfg.data.returns_mode));
      const backtest = cfg.backtest && cfg.backtest.enabled ? runBacktest(cfg, comps, panel.close, numIdx, denIdx) : null;
      return { rank: r + 1, q, num_idx: numIdx, den_idx: denIdx, num: numIdx.map((c) => panel.symbols[c]),
        den: denIdx.map((c) => panel.symbols[c]), score: scores[q], engine: eng, backtest };
    });
    return { jobs, scores, nEvents, top, keep };
  }

  // ------------------------------------------------------------------ metrics
  /** Performance statistics of a backtest equity curve + trade list (252 bars/yr). */
  function metrics(bt) {
    const v = bt.equity.v, n = v.length;
    const out = { total_return: bt.total_return, trades: bt.trades.length };
    if (n < 2) return out;
    let peak = v[0], mdd = 0;
    const rets = [];
    for (let t = 0; t < n; t++) {
      if (v[t] > peak) peak = v[t];
      mdd = Math.min(mdd, v[t] / peak - 1);
      if (t) rets.push(v[t] / v[t - 1] - 1);
    }
    const m = rets.reduce((a, b) => a + b, 0) / rets.length;
    const sd = Math.sqrt(rets.reduce((a, b) => a + (b - m) ** 2, 0) / (rets.length - 1));
    const years = (n - 1) / 252;
    const wins = bt.trades.filter((t) => t.net > 0);
    const grossWin = wins.reduce((a, t) => a + t.net, 0);
    const grossLoss = -bt.trades.filter((t) => t.net <= 0).reduce((a, t) => a + t.net, 0);
    const numBars = bt.trades.filter((t) => t.leg === "num").reduce((a, t) => a + t.dur, 0);
    const allBars = bt.trades.reduce((a, t) => a + t.dur, 0);
    return Object.assign(out, {
      cagr: Math.pow(bt.final_equity / bt.initial_cash, 1 / years) - 1,
      max_dd: mdd,
      vol: sd * Math.sqrt(252),
      sharpe: sd > 0 ? (m / sd) * Math.sqrt(252) : NaN,
      win_rate: bt.trades.length ? wins.length / bt.trades.length : NaN,
      profit_factor: grossLoss > 0 ? grossWin / grossLoss : NaN,
      avg_hold: bt.trades.length ? allBars / bt.trades.length : NaN,
      num_share: allBars ? numBars / allBars : NaN,
      costs: bt.trades.reduce((a, t) => a + t.costs, 0),
      years,
    });
  }

  root.mrscore = { buildComponents, runEngine, runBacktest, scanUniverse, ratioSeries, returnsOf, normalizeCols, metrics };
})(window);
