# Commodity Chokepoint Radar

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)
![Focus](https://img.shields.io/badge/Focus-Commodities%20%7C%20Geopolitics-1F6F8B)

A real-time decision-support dashboard for monitoring disruption risk across the world's main maritime chokepoints. It combines news, weather, market context and LLM-assisted scoring in a single Streamlit interface.

## Coverage

The dashboard monitors Suez, Panama, Hormuz, Bab el-Mandeb, Malacca, Gibraltar and the Cape of Good Hope rerouting corridor.

## Core features

- Interactive map and one analytical view per chokepoint.
- Rolling 30-day news aggregation from GDELT, Google News and curated maritime feeds.
- Article filtering, deduplication and source-aware retention.
- Live marine weather from Open-Meteo.
- Commodity-market context and structural geopolitical priors.
- Conservative 0–100 tension scoring through an Ollama-hosted language model.
- Persistent snapshots and non-blocking background refreshes.
- Explicit error reporting when an upstream source or the scoring model is unavailable.

## Data pipeline

```text
News feeds + GDELT + weather + market data
                  ↓
       normalize, filter, deduplicate
                  ↓
    chokepoint-level evidence packet
                  ↓
      LLM score + rationale + cache
                  ↓
          Streamlit dashboard
```

## Repository structure

```text
.
├── app.py               # Streamlit interface
├── core/
│   ├── config.py        # Chokepoints, aliases and source configuration
│   ├── news.py          # News collection and normalization
│   ├── weather.py       # Marine weather retrieval
│   ├── scorer.py        # LLM scoring contract
│   ├── refresh.py       # End-to-end refresh workflow
│   ├── scheduler.py     # Background scheduling
│   └── cache.py         # Persistent snapshots
└── requirements.txt
```

## Run locally

```bash
python -m venv .venv
pip install -r requirements.txt
streamlit run app.py
```

Store credentials locally in `ollama.txt` and, if used, `brave.tkt`. Both filenames are excluded by `.gitignore` and must never be committed.

## Design choices

The system separates structural geopolitical risk from the current article-driven signal. The LLM receives a capped, traceable evidence packet and returns an aggregate score; it does not silently fall back to an opaque heuristic when scoring fails.

## Scope and limitations

This is a research and monitoring tool, not a trading signal. News availability, source latency, model judgement and incomplete real-time logistics data can materially affect the displayed score.

## Author

Mohamed Boumezou — Finance student at Université Paris Dauphine–PSL  
[LinkedIn](https://www.linkedin.com/in/mohamed-boumezou-a8a0052ab/)
