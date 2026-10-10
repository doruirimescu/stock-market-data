/*
 * Dark Plotly defaults for the calculator and loan pages, matching site.css.
 *
 *   SiteChart.colors         palette (accent, positive/teal, negative/orange, ...)
 *   SiteChart.layout(extra)  base layout deep-merged with `extra`
 *   SiteChart.config         Plotly config (responsive, no logo, trimmed mode bar)
 *   SiteChart.rgba(hex, a)   "#rrggbb" -> "rgba(...)"
 */
(function () {
  "use strict";

  const colors = {
    accent: "#4f8cff",
    positive: "#14a088",
    negative: "#dd6a2c",
    positiveInk: "#5fd4bd",
    negativeInk: "#f4a06f",
    text: "#e6edf7",
    muted: "#9fb0cf",
    faint: "#6b80a8",
    grid: "#1f3460",
    surface: "#0f1b33",
    surface2: "#14244a",
    borderStrong: "#2b4680",
    highlight: "#fde68a",
  };
  const FONT = "Inter, system-ui, sans-serif";

  const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);
  function merge(base, extra) {
    const out = { ...base };
    for (const [k, v] of Object.entries(extra || {})) out[k] = isObj(v) && isObj(base[k]) ? merge(base[k], v) : v;
    return out;
  }

  function rgba(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  }

  function layout(extra) {
    return merge(
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: FONT, color: colors.muted, size: 12 },
        margin: { t: 20, r: 20, b: 56, l: 64 },
        hoverlabel: { bgcolor: colors.surface2, bordercolor: colors.borderStrong, font: { color: colors.text, family: FONT } },
        xaxis: { gridcolor: colors.grid, linecolor: colors.grid, zeroline: false },
        yaxis: { gridcolor: colors.grid, linecolor: colors.grid, zeroline: false },
        legend: { orientation: "h", x: 0, y: 1.12, font: { color: colors.muted } },
        hovermode: "closest",
      },
      extra
    );
  }

  const config = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

  window.SiteChart = { colors, layout, config, rgba };
})();
