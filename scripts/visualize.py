#!/usr/bin/env python3
"""
Render an AlphaSpread valuations JSON file to an interactive Plotly bar chart
(HTML). Structure mirrors the reference python-trading `visualize.py`:

    - x-axis : ticker symbols
    - y-axis : valuation score (signed %: + = undervalued, - = overvalued)
    - colour : red if Overvalued, green otherwise
    - sorted : by solvency score (ascending), then valuation score
    - hover  : company name, ticker, valuation, intrinsic value, solvency

Input JSON is a dict keyed by symbol, each value a record with at least:
    symbol, company, valuation_type, valuation_score, solvency_score
(as produced by alphaspread_index.py).

Usage:
    python visualize.py nasdaq100_valuations.json
    python visualize.py sp500_valuations.json -o chart.html --title "S&P 500"
"""

import argparse
import json
import sys


def prepare_data(data):
    """Sort records by (solvency asc, valuation score) and split into columns."""
    rows = {}
    for rec in data.values():
        if rec.get("error"):
            continue
        sym = rec.get("symbol")
        if not sym:
            continue
        rows[sym] = rec

    ordered = sorted(
        rows.values(),
        key=lambda r: (r.get("solvency_score") if r.get("solvency_score") is not None else 0,
                       r.get("valuation_score") if r.get("valuation_score") is not None else 0),
    )
    return ordered


def compute_summary(records):
    """Equal-weight aggregate stats across all valued stocks."""
    scores = [r.get("valuation_score") for r in records
              if r.get("valuation_score") is not None]
    solv = [r.get("solvency_score") for r in records
            if r.get("solvency_score") is not None]
    n_under = sum(1 for r in records if r.get("valuation_type") == "Undervalued")
    n_over = sum(1 for r in records if r.get("valuation_type") == "Overvalued")
    avg_score = sum(scores) / len(scores) if scores else None
    return {
        "n": len(records),
        "n_scored": len(scores),
        "avg_score": avg_score,   # signed %: + undervalued, - overvalued
        "verdict": (None if avg_score is None else
                    ("Undervalued" if avg_score >= 0 else "Overvalued")),
        "n_undervalued": n_under,
        "n_overvalued": n_over,
        "avg_solvency": (sum(solv) / len(solv) if solv else None),
    }


def _build_figure(records, title="Stock Analysis"):
    """Build (but don't write) the Plotly figure shared by HTML and PNG output."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    symbols = [r["symbol"] for r in records]
    scores = [r.get("valuation_score") for r in records]
    solvencies = [r.get("solvency_score") for r in records]
    vtypes = [r.get("valuation_type") for r in records]
    companies = [r.get("company") or r["symbol"] for r in records]
    intrinsics = [r.get("intrinsic_value") for r in records]
    prices = [r.get("current_price_approx") for r in records]

    colors = ["#d62728" if vt == "Overvalued" else "#2ca02c" for vt in vtypes]

    # Per-bar hover detail (customdata columns): company, verdict, IV, price, solvency
    def fmt(v, pre=""):
        return f"{pre}{v:,.2f}" if isinstance(v, (int, float)) else "n/a"

    customdata = [
        [companies[i],
         (f"{vtypes[i]} by {abs(scores[i]):.0f}%" if scores[i] is not None and vtypes[i] else "n/a"),
         fmt(intrinsics[i]),
         fmt(prices[i]),
         (solvencies[i] if solvencies[i] is not None else "n/a")]
        for i in range(len(records))
    ]

    hovertemplate = (
        "<b>%{customdata[0]}</b> (%{x})<br>"
        "Valuation: %{customdata[1]}<br>"
        "Valuation score: %{y:.0f}%<br>"
        "Intrinsic value: %{customdata[2]}<br>"
        "Current price: ~%{customdata[3]}<br>"
        "Solvency: %{customdata[4]}/100<extra></extra>"
    )

    fig = make_subplots(rows=1, cols=1, subplot_titles=(title,),
                        specs=[[{"type": "xy"}]])
    fig.add_trace(
        go.Bar(
            x=symbols,
            y=scores,
            marker_color=colors,
            customdata=customdata,
            hovertemplate=hovertemplate,
            showlegend=False,   # the red/green meaning is carried by the two legend proxies below
        ),
        row=1, col=1,
    )

    n = len(records)
    fig.update_layout(
        title_text=f"{title} — AlphaSpread Valuation ({n} stocks)",
        template="plotly_white",
        bargap=0.15,
        height=760,
        margin=dict(l=60, r=30, t=90, b=120),
    )
    fig.update_xaxes(title_text="Ticker (sorted by solvency ↑)",
                     tickangle=-90, tickfont=dict(size=9))
    fig.update_yaxes(title_text="Valuation score  (+ undervalued / − overvalued, %)",
                     zeroline=True, zerolinewidth=2, zerolinecolor="#888")

    # Legend proxy: two invisible traces so the red/green meaning is documented.
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color="#2ca02c",
                         name="Undervalued", showlegend=True))
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color="#d62728",
                         name="Overvalued", showlegend=True))
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1))

    # --- Equal-weight summary: mean valuation across all stocks ---
    s = compute_summary(records)
    if s["avg_score"] is not None:
        avg = s["avg_score"]
        avg_color = "#2ca02c" if avg >= 0 else "#d62728"
        # Dashed line at the average, drawn across the whole chart.
        fig.add_hline(
            y=avg, line_dash="dash", line_color=avg_color, line_width=2,
            annotation_text=f"equal-weight avg {avg:+.1f}%",
            annotation_position="top left",
            annotation_font=dict(color=avg_color, size=12),
        )
        avg_solv = (f"{s['avg_solvency']:.0f}/100"
                    if s["avg_solvency"] is not None else "n/a")
        box = (
            f"<b>Equal-weight summary — {s['n_scored']} stocks</b><br>"
            f"Average: <b style='color:{avg_color}'>"
            f"{s['verdict']} by {abs(avg):.1f}%</b><br>"
            f"Undervalued: {s['n_undervalued']}  ·  "
            f"Overvalued: {s['n_overvalued']}<br>"
            f"Average solvency: {avg_solv}"
        )
        fig.add_annotation(
            xref="paper", yref="paper", x=0.005, y=0.99,
            xanchor="left", yanchor="top", align="left",
            text=box, showarrow=False,
            font=dict(size=12, color="#222"),
            bordercolor="#bbb", borderwidth=1, borderpad=8,
            bgcolor="rgba(255,255,255,0.88)",
        )

    return fig


def plot_bars(records, out_path, title="Stock Analysis"):
    """Write the interactive HTML chart."""
    fig = _build_figure(records, title=title)
    fig.write_html(out_path, include_plotlyjs=True, full_html=True)
    return out_path


def plot_png(records, out_path, title="Stock Analysis", scale=2, width=1600, height=800):
    """Write a static PNG image of the same chart.

    Requires the `kaleido` package (``pip install kaleido``); Plotly uses it as
    the static-image engine. Raises if it's unavailable so the caller can warn.
    """
    fig = _build_figure(records, title=title)
    fig.write_image(out_path, format="png", scale=scale, width=width, height=height)
    return out_path


def build_html(data, out_path, title="Stock Analysis"):
    """Convenience: take a loaded results dict and write the HTML chart."""
    records = prepare_data(data)
    if not records:
        raise RuntimeError("No valid records to visualize.")
    return plot_bars(records, out_path, title=title)


def build_png(data, out_path, title="Stock Analysis"):
    """Convenience: take a loaded results dict and write a static PNG chart."""
    records = prepare_data(data)
    if not records:
        raise RuntimeError("No valid records to visualize.")
    return plot_png(records, out_path, title=title)


def main():
    import common
    common.force_utf8_stdout()
    ap = argparse.ArgumentParser(description="Render AlphaSpread valuations to HTML.")
    ap.add_argument("json_file", help="Valuations JSON (dict keyed by symbol).")
    ap.add_argument("-o", "--output", help="Output HTML path.")
    ap.add_argument("--title", default="Stock Analysis", help="Chart title.")
    args = ap.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = args.output or (args.json_file.rsplit(".", 1)[0] + ".html")
    try:
        build_html(data, out, title=args.title)
    except Exception as e:  # noqa: BLE001
        print(f"[x] {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[✓] Wrote chart -> {out}")


if __name__ == "__main__":
    main()
