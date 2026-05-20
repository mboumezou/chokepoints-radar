# Commodity Chokepoint Radar

Streamlit dashboard that aggregates news for major global straits, canals and rerouting corridors, then asks Ollama for an aggregate commodity-market tension score.

## What it does

- Shows a map of key chokepoints.
- Creates one tab per chokepoint.
- Pulls a 30-day news window from GDELT, Google News RSS and curated maritime RSS feeds.
- Sends a capped packet of retained headlines/descriptions to `cogito-2.1:671b-cloud` for aggregate scoring.
- Uses Ollama aggregate scoring only; if the AI call is unavailable, the background refresh reports an error instead of silently creating a heuristic score.
- Adds live marine weather from Open-Meteo.
- Asks the AI for a conservative 0-100 daily tension score, with small weather weight and larger political/logistics context weight.
- Stores chokepoint snapshots in `data_cache/` so restarts reuse the last retained articles.
- Runs scheduled refreshes in a background thread so the Streamlit UI stays usable.
- Recomputes scores and summaries in the background on a rolling 30-minute cadence by default.
- Includes a structural geopolitical risk prior per chokepoint, displayed separately from article-driven logistics/weather signals.

## Run

```powershell
pip install -r requirements.txt
streamlit run app.py
```

Keep the Ollama API key in `ollama.txt`. The app reads it locally and never displays it.
