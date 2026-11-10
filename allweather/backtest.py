"""Backtest the All-Weather gauges with tradelab and publish the results to the site.

    python -m allweather.backtest                 # causality check, runs, robustness, export
    python -m allweather.backtest --skip-robust   # just the three runs + export (faster)

tradelab lives in the trading repo (TRADELAB_DIR, default ../trading/Trading/backtest) and runs with its
own venv. Runs land in its runs/ directory (and its trial ledger); this script writes the configs, runs:

    check-causality   gauges config (exit 4 = look-ahead leak; stops here)
    run               gauges (tilt 1), static all-weather (tilt 0), 60/40 (SPY/IEF),
                      and both all-weather versions without Bitcoin
    optimize          tilt x rebalance grid -> deflated Sharpe, PBO, plateau
    walkforward       rolling 4y in-sample / 1y out-of-sample

and then allweather.export_backtest (run with tradelab's venv, which reads parquet) writes
docs/data/allweather_backtest.js.
Refresh the price/FRED cache first (python -m allweather.data, or `mise run allweather`).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .data import CACHE, FRED_FILE, PRICES, proxies

ROOT = Path(__file__).resolve().parent.parent
TRADELAB = Path(os.environ.get("TRADELAB_DIR", ROOT.parent / "trading/Trading/backtest")).resolve()
CONFIGS = CACHE / "tradelab"
START = "2008-01-02"     # first panel day; indicators are warmed up from the price files before it
STATE = CACHE / "tradelab/runs.json"


def config(name, strategy, params, grid=None, robust=True):
    cfg = {
        "config_version": 1,
        "name": f"allweather_{name}",
        "data": {
            "source": "csv", "symbols": proxies(), "start": START, "freq": "1d",
            "options": {"path": str(PRICES / "{symbol}.csv"), "preset": "generic_end"},
            "benchmark": "SPY", "cash": 0.0,
        },
        "strategy": {"name": strategy, "path": str(ROOT / "allweather/tradelab_strategy.py"), "params": params,
                     "warmup_sessions": 0},
        # ETFs: ~5 bp commission/spread + 5 bp slippage per side on traded notional
        "execution": {"fill": "next_open", "commission_bps": 5, "slippage_bps": 5},
        "initial_capital": 10000,
        "seed": 1,
        "robustness": {"bootstrap_n": 1000, "mc_n": 1000, "cost_mults": [0, 1, 2, 3], "objective": "sharpe",
                       "n_jobs": 1, "walkforward": {"is_len": 1000, "oos_len": 250, "scheme": "rolling", "purge": 5}},
        "analytics": {"periods_per_year": 252},
    }
    if grid:
        cfg["strategy"]["grid"] = grid
    path = CONFIGS / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))    # JSON is valid YAML
    return path


def tradelab(*args):
    py = TRADELAB / ".venv/bin/python"
    if not py.exists():
        sys.exit(f"tradelab venv not found at {py} (set TRADELAB_DIR, then `make env` there)")
    print(f"\n$ tradelab {' '.join(map(str, args))}", file=sys.stderr)
    r = subprocess.run([str(py), "-m", "tradelab", *map(str, args)], cwd=TRADELAB)
    latest = (TRADELAB / "runs/LATEST").resolve()
    return r.returncode, latest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-robust", action="store_true", help="skip optimize and walk-forward")
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args()
    if not FRED_FILE.exists():
        sys.exit("No data cache: run `python -m allweather.data` first.")

    grid = {"tilt": [0.0, 0.5, 1.0, 1.5], "rebalance": ["monthly", "weekly"]}
    gauges = config("gauges", "allweather_gauges", {"tilt": 1.0, "rebalance": "monthly"}, grid=grid)
    static = config("static", "allweather_gauges", {"tilt": 0.0, "rebalance": "monthly"})
    sixty = config("sixty_forty", "fixed_weights", {"weights": {"SPY": 0.6, "IEF": 0.4}})
    # Bitcoin's 2017 run lifts both all-weather versions; these show the gauges' edge without it
    gauges_nb = config("gauges_ex_btc", "allweather_gauges", {"tilt": 1.0, "rebalance": "monthly", "exclude": ["BTC"]})
    static_nb = config("static_ex_btc", "allweather_gauges", {"tilt": 0.0, "rebalance": "monthly", "exclude": ["BTC"]})

    # --skip-engine: tradelab's engine self-test runs a perfect-foresight oracle at +-100% in EVERY symbol; on a
    # 22-symbol, 19-year panel its equity overflows float64 and the test reports FAIL for that reason alone.
    # It tests the engine, not the strategy; the strategy checks (prefix invariance, future poison, equity
    # prefix) still run here and again inside every `run`.
    code, _ = tradelab("check-causality", gauges, "--skip-engine")
    if code != 0:
        sys.exit(f"check-causality failed (exit {code}); not publishing results.")

    runs = {}
    for name, cfg in (("gauges", gauges), ("static", static), ("sixty_forty", sixty),
                      ("gauges_ex_btc", gauges_nb), ("static_ex_btc", static_nb)):
        code, d = tradelab("run", cfg)
        if code != 0:
            sys.exit(f"tradelab run {name} failed (exit {code})")
        runs[name] = str(d)
    if not args.skip_robust:
        for cmd in ("optimize", "walkforward"):
            code, d = tradelab(cmd, gauges)
            if code != 0:
                sys.exit(f"tradelab {cmd} failed (exit {code})")
            runs[cmd] = str(d)
    elif STATE.exists():
        old = json.loads(STATE.read_text())
        runs.update({k: v for k, v in old.items() if k in ("optimize", "walkforward") and Path(v).exists()})
    STATE.write_text(json.dumps(runs, indent=2))
    print(json.dumps(runs, indent=2), file=sys.stderr)

    if not args.no_export:
        # tradelab writes parquet; its venv has the reader (pyarrow), this repo's does not need it
        r = subprocess.run([str(TRADELAB / ".venv/bin/python"), "-m", "allweather.export_backtest"], cwd=ROOT)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
