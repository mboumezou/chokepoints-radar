from __future__ import annotations

import streamlit as st
import yfinance as yf

# Tickers directly relevant to chokepoint commodity flows
INDICES = [
    ("Brent Crude",    "BZ=F",  "$/bbl",    "energy"),
    ("Natural Gas",    "NG=F",  "$/MMBtu",  "energy"),
    ("Wheat",          "ZW=F",  "¢/bu",     "agri"),
    ("Copper",         "HG=F",  "$/lb",     "metals"),
    ("Dry Bulk (BDRY)","BDRY",  "$",        "shipping"),
]


@st.cache_data(ttl=3600)
def fetch_market_snapshot() -> list[dict]:
    tickers = [t for _, t, _, _ in INDICES]
    try:
        raw = yf.download(tickers, period="5d", auto_adjust=True, progress=False)
        close = raw["Close"] if "Close" in raw.columns else raw
    except Exception:
        return []

    results = []
    for name, ticker, unit, category in INDICES:
        try:
            series = close[ticker].dropna()
            if series.empty:
                continue
            last = round(float(series.iloc[-1]), 2)
            prev = round(float(series.iloc[-2]), 2) if len(series) >= 2 else last
            change_pct = round((last - prev) / prev * 100, 2) if prev else 0.0
            results.append({
                "name": name,
                "ticker": ticker,
                "price": last,
                "change_pct": change_pct,
                "unit": unit,
                "category": category,
            })
        except Exception:
            continue
    return results
