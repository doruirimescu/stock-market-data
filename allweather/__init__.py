"""All-Weather gauges: buy/sell gauges for 22 asset classes and a gauge-tilted all-weather allocation.

    allweather/universe.py          the assets, sleeves, base weights and macro sensitivities
    allweather/data.py              Yahoo prices + FRED macro, cached in generated/allweather/cache/
    allweather/engine.py            gauges and allocation (pure pandas, shared by the page and the backtest)
    allweather/build.py             daily build -> docs/data/allweather.js
    allweather/tradelab_strategy.py the tradelab vector strategy (backtest)
    allweather/export_backtest.py   tradelab run dirs -> docs/data/allweather_backtest.js
"""
