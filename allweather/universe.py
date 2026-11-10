"""The All-Weather universe: 22 asset classes in six sleeves, plus T-bills as cash.

Each asset has a US-listed proxy with a long history (used for the gauges and the backtest) and a
UCITS ETF / ETP that a European investor can buy. Base weights are the static all-weather mix the
gauges tilt; they sum to 100.

Macro sensitivities (`beta`) say how each asset tends to react to the six macro factors in
engine.macro_factors(); they come from economic reasoning (the growth/inflation quadrants behind
all-weather portfolios), not from fitting returns:

    G  growth strong / improving          I  inflation high / rising
    S  financial stress high / rising     R  interest rates falling
    U  US dollar strengthening            Y  real yields falling
"""

CASH = {"id": "BIL", "name": "US T-bills", "proxy": "BIL", "ucits": "IB01.L",
        "ucits_name": "iShares $ Treasury Bond 0-1yr UCITS ETF (Acc)"}
CASH_FALLBACK = "SHY"   # holds the cash share until BIL has a year of history (BIL listed May 2007)

SLEEVES = ["Treasuries", "Credit & inflation", "Equity regions", "US sectors", "Real assets", "Crypto"]

_S = 9 / 7  # the US-sector sleeve's 9% split over seven sectors

# id, name, sleeve, proxy (Yahoo), ucits (Yahoo), ucits name, base weight %, macro betas
ASSETS = [
    ("SHY", "Treasuries 1-3y", "Treasuries", "SHY", "IBTA.L", "iShares $ Treasury Bond 1-3yr UCITS ETF (Acc)", 5, "bond:short"),
    ("IEF", "Treasuries 7-10y", "Treasuries", "IEF", "CBU0.L", "iShares $ Treasury Bond 7-10yr UCITS ETF (Acc)", 15, "bond:mid"),
    ("TLT", "Treasuries 20y+", "Treasuries", "TLT", "IDTL.L", "iShares $ Treasury Bond 20+yr UCITS ETF (Dist)", 15, "bond:long"),
    ("TIP", "Inflation-linked (TIPS)", "Credit & inflation", "TIP", "IDTP.L", "iShares $ TIPS UCITS ETF (Acc)", 7,
     {"I": 1, "G": -0.3, "Y": 0.7}),
    ("LQD", "Investment-grade corporates", "Credit & inflation", "LQD", "LQDE.L", "iShares $ Corp Bond UCITS ETF (Dist)", 4,
     {"G": -0.2, "I": -0.7, "S": -0.5, "R": 0.8}),
    ("HYG", "High-yield corporates", "Credit & inflation", "HYG", "IHYU.L", "iShares $ High Yield Corp Bond UCITS ETF (Dist)", 4,
     {"G": 0.8, "I": -0.3, "S": -1, "R": 0.3}),
    ("SPY", "US large caps", "Equity regions", "SPY", "CSPX.L", "iShares Core S&P 500 UCITS ETF (Acc)", 9,
     {"G": 1, "I": -0.5, "S": -1, "R": 0.3}),
    ("VGK", "Europe", "Equity regions", "VGK", "IMAE.AS", "iShares Core MSCI Europe UCITS ETF (Acc)", 6,
     {"G": 1, "I": -0.3, "S": -1, "U": -0.5}),
    ("EEM", "Emerging markets", "Equity regions", "EEM", "EIMI.L", "iShares Core MSCI EM IMI UCITS ETF (Acc)", 6,
     {"G": 1, "I": 0.3, "S": -1, "U": -1}),
    ("XLK", "Technology", "US sectors", "XLK", "IUIT.L", "iShares S&P 500 Information Technology Sector UCITS ETF", _S,
     {"G": 0.7, "I": -0.5, "S": -0.7, "R": 0.7}),
    ("XLF", "Financials", "US sectors", "XLF", "IUFS.L", "iShares S&P 500 Financials Sector UCITS ETF", _S,
     {"G": 1, "S": -1, "R": -0.4}),
    ("XLE", "Energy", "US sectors", "XLE", "IUES.L", "iShares S&P 500 Energy Sector UCITS ETF", _S,
     {"G": 0.5, "I": 1, "S": -0.5, "U": -0.3}),
    ("XLV", "Health care", "US sectors", "XLV", "IUHC.L", "iShares S&P 500 Health Care Sector UCITS ETF", _S,
     {"G": -0.3, "I": -0.3, "S": 0.4}),
    ("XLU", "Utilities", "US sectors", "XLU", "IUUS.L", "iShares S&P 500 Utilities Sector UCITS ETF", _S,
     {"G": -0.5, "I": -0.3, "S": 0.4, "R": 0.8}),
    ("XLP", "Consumer staples", "US sectors", "XLP", "IUCS.L", "iShares S&P 500 Consumer Staples Sector UCITS ETF", _S,
     {"G": -0.5, "I": -0.2, "S": 0.5}),
    ("XLI", "Industrials", "US sectors", "XLI", "IUIS.L", "iShares S&P 500 Industrials Sector UCITS ETF", _S,
     {"G": 1, "S": -0.8}),
    ("VNQ", "US real estate", "Real assets", "VNQ", "IDUP.L", "iShares US Property Yield UCITS ETF (Dist)", 3,
     {"G": 0.5, "S": -0.7, "R": 0.8}),
    ("GLD", "Gold", "Real assets", "GLD", "IGLN.L", "iShares Physical Gold ETC", 7,
     {"I": 0.6, "S": 0.6, "U": -0.7, "Y": 1}),
    ("SLV", "Silver", "Real assets", "SLV", "ISLN.L", "iShares Physical Silver ETC", 2,
     {"G": 0.5, "I": 0.8, "U": -0.7, "Y": 0.7}),
    ("DBC", "Broad commodities", "Real assets", "DBC", "ICOM.L", "iShares Diversified Commodity Swap UCITS ETF", 5,
     {"G": 0.8, "I": 1, "U": -0.5}),
    ("BTC", "Bitcoin", "Crypto", "BTC-USD", "IB1T.DE", "iShares Bitcoin ETP (not UCITS)", 3,
     {"G": 0.3, "S": -1, "R": 0.5, "U": -0.5}),
]

FIELDS = ("id", "name", "sleeve", "proxy", "ucits", "ucits_name", "base", "beta")
UNIVERSE = [dict(zip(FIELDS, a)) for a in ASSETS]
IDS = [a["id"] for a in UNIVERSE]
BY_ID = {a["id"]: a for a in UNIVERSE}
FIXED_INCOME = {"SHY", "IEF", "TLT", "TIP", "LQD", "HYG"}

# Value component for assets where long-term price reversal is not the right "cheapness" measure.
VALUE_SERIES = {"TIP": "z_real10", "LQD": "z_aaa", "HYG": "z_baa"}   # Treasuries: inside the bond gauges

# Weight caps after tilting (fraction of the portfolio).
MAX_WEIGHT = 0.25
MAX_WEIGHT_BY_ID = {"BTC": 0.06}

assert abs(sum(a["base"] for a in UNIVERSE) - 100) < 1e-9
