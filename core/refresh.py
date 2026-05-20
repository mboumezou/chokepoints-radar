from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from core.scorer import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_API_BASE,
    ChokepointAssessment,
    assess_chokepoint_with_ai,
    read_ollama_api_key,
)
from core.config import CHOKEPOINTS, Chokepoint
from core.news import (
    Article,
    attach_curated_articles_to_chokepoint,
    dedupe_articles,
    fetch_brave_news_articles,
    fetch_curated_feed_articles,
    fetch_google_news_articles,
    read_brave_api_key,
)
from core.cache import (
    ChokepointSnapshot,
    days_since_last_article,
    load_snapshot,
    make_snapshot,
    merge_and_trim_articles,
    save_snapshot,
)
from core.weather import fetch_marine_weather, fetch_wind_weather


def default_settings() -> dict:
    return {
        "days": 30,
        "max_records": 15,
        "max_stored_articles": 80,
        "max_ai_articles": 15,
        "curated_feed_limit": 100,
        "model": DEFAULT_MODEL,
        "api_base": DEFAULT_OLLAMA_API_BASE,
        "use_ai": True,
    }


def normalize_settings(settings: dict) -> dict:
    merged = default_settings()
    merged.update(settings)
    return merged


def risk_label(score: int) -> tuple[str, str]:
    if score >= 65:
        return "High", "risk-high"
    if score >= 35:
        return "Medium", "risk-medium"
    return "Low", "risk-low"


def classify_for_snapshot(
    chokepoint: Chokepoint,
    articles: list[Article],
    weather: dict,
    settings: dict,
    api_key: str,
) -> ChokepointAssessment:
    settings = normalize_settings(settings)
    if settings["use_ai"] and api_key:
        return assess_chokepoint_with_ai(
            chokepoint,
            articles=articles[: settings["max_ai_articles"]],
            api_key=api_key,
            weather=weather,
            model=settings["model"],
            api_base=settings["api_base"],
            max_articles=settings["max_ai_articles"],
        )
    raise RuntimeError("Ollama aggregate scoring is required, but no Ollama API key is available.")


def refresh_chokepoint_snapshot(
    chokepoint: Chokepoint,
    settings: dict,
    curated_articles: list[Article],
    api_key: str,
    brave_api_key: str,
    existing: ChokepointSnapshot | None,
    emit: Callable[[str], None],
) -> ChokepointSnapshot:
    settings = normalize_settings(settings)
    refresh_days = days_since_last_article(existing, default_days=settings["days"], max_days=settings["days"])
    existing_articles = existing.articles if existing else []
    n = settings["max_records"]

    # ── Article fetching ──────────────────────────────────────────────────
    emit(f"{chokepoint.name}: window = last {refresh_days} day(s), {n} records/source.")

    emit(f"{chokepoint.name}: [1/3] querying Brave News Search…")
    brave_articles: list[Article] = []
    try:
        brave_articles = fetch_brave_news_articles(chokepoint, api_key=brave_api_key, count=n)
        emit(f"{chokepoint.name}: Brave News → {len(brave_articles)} articles.")
    except Exception as exc:
        emit(f"{chokepoint.name}: Brave News error — {exc}.")

    emit(f"{chokepoint.name}: [2/3] querying Google News RSS…")
    google_articles: list[Article] = []
    try:
        google_articles = fetch_google_news_articles(chokepoint, days=refresh_days, max_records=n)
        emit(f"{chokepoint.name}: Google News → {len(google_articles)} articles.")
    except Exception as exc:
        emit(f"{chokepoint.name}: Google News error — {exc}.")

    emit(f"{chokepoint.name}: [3/3] matching curated RSS pool ({len(curated_articles)} articles across {len(set(a.source for a in curated_articles))} feeds)…")
    curated_matched = attach_curated_articles_to_chokepoint(chokepoint, curated_articles)
    emit(f"{chokepoint.name}: curated RSS → {len(curated_matched)} matched.")

    fetched_articles = dedupe_articles([*brave_articles, *google_articles, *curated_matched])
    emit(f"{chokepoint.name}: {len(fetched_articles)} unique after dedup (Brave + Google + RSS).")

    merged_articles = merge_and_trim_articles(
        existing_articles,
        fetched_articles,
        max_age_days=settings["days"],
        max_articles=settings["max_stored_articles"],
    )
    existing_ids = {article.id for article in existing_articles}
    new_count = sum(1 for article in merged_articles if article.id not in existing_ids)
    emit(
        f"{chokepoint.name}: {new_count} new articles → {len(merged_articles)} total retained in cache "
        f"(max {settings['max_stored_articles']}, window {settings['days']}d)."
    )

    # ── Weather ──────────────────────────────────────────────────────────
    emit(f"{chokepoint.name}: fetching weather — trying marine API…")
    weather: dict = {}
    try:
        weather = fetch_marine_weather(chokepoint)
        wave = weather.get("wave_height")
        wind = weather.get("wind_speed")
        emit(
            f"{chokepoint.name}: weather OK (marine) — "
            f"waves {wave if wave is not None else 'N/A'} {weather.get('wave_height_unit','m')}, "
            f"wind {wind if wind is not None else 'N/A'} {weather.get('wind_speed_unit','km/h')}."
        )
    except Exception as marine_exc:
        emit(f"{chokepoint.name}: marine API failed ({marine_exc}) — trying wind-only fallback…")
        try:
            weather = fetch_wind_weather(chokepoint)
            wind = weather.get("wind_speed")
            emit(
                f"{chokepoint.name}: weather OK (wind-only) — "
                f"wind {wind if wind is not None else 'N/A'} {weather.get('wind_speed_unit','km/h')}."
            )
        except Exception as wind_exc:
            emit(f"{chokepoint.name}: weather unavailable — {wind_exc}.")

    if not weather and existing and existing.weather:
        weather = existing.weather
        emit(f"{chokepoint.name}: live weather unavailable, keeping cached data.")

    # ── AI scoring ───────────────────────────────────────────────────────
    ai_input_count = min(len(merged_articles), settings["max_ai_articles"])
    emit(
        f"{chokepoint.name}: sending {ai_input_count} articles to Ollama "
        f"({settings['model']}) — timeout {75}s…"
    )
    assessment = classify_for_snapshot(
        chokepoint,
        articles=merged_articles,
        weather=weather,
        settings=settings,
        api_key=api_key,
    )
    emit(f"{chokepoint.name}: Ollama response received, parsing score…")

    snapshot = make_snapshot(chokepoint, merged_articles, assessment, weather)
    save_snapshot(snapshot)
    emit(
        f"{chokepoint.name}: DONE — score={assessment.tension_score}/100 "
        f"(political={assessment.political_context_score}, logistics={assessment.logistics_score}, "
        f"weather={assessment.weather_score}) via {assessment.assessment_method}."
    )
    return snapshot


def refresh_targets(
    target_names: list[str],
    settings: dict,
    emit: Callable[[str], None],
    cold_start_names: set[str] | None = None,
) -> None:
    settings = normalize_settings(settings)
    targets = [cp for cp in CHOKEPOINTS if cp.name in set(target_names)]
    if not targets:
        emit("No refresh target selected.")
        return

    api_key = read_ollama_api_key() if settings["use_ai"] else ""
    brave_api_key = read_brave_api_key()
    if brave_api_key:
        emit("Brave News API key loaded.")
    else:
        emit("Brave News API key not found — Brave source skipped.")

    emit(
        f"Fetching curated maritime RSS feeds: last {settings['days']} day(s), "
        f"{settings['curated_feed_limit']} items/feed."
    )
    curated = fetch_curated_feed_articles(
        days=settings["days"],
        max_per_feed=settings["curated_feed_limit"],
    )
    emit(f"Curated RSS pool loaded: {len(curated)} articles before chokepoint matching.")

    for index, chokepoint in enumerate(targets, start=1):
        emit(f"[{index}/{len(targets)}] Refresh target: {chokepoint.name}.")
        existing = load_snapshot(chokepoint)
        try:
            refresh_chokepoint_snapshot(
                chokepoint,
                settings=settings,
                curated_articles=curated,
                api_key=api_key,
                brave_api_key=brave_api_key,
                existing=existing,
                emit=emit,
            )
        except Exception as exc:
            emit(f"{chokepoint.name}: ERROR — {exc}. Continuing with next target.")


def load_cached_dashboard_data() -> tuple[pd.DataFrame, dict[str, ChokepointSnapshot], list[Chokepoint]]:
    snapshots: dict[str, ChokepointSnapshot] = {}
    missing: list[Chokepoint] = []
    rows: list[dict] = []
    for chokepoint in CHOKEPOINTS:
        snapshot = load_snapshot(chokepoint)
        if snapshot is None:
            missing.append(chokepoint)
        else:
            snapshots[chokepoint.name] = snapshot
        rows.append(snapshot_to_row(chokepoint, snapshot))
    return pd.DataFrame(rows), snapshots, missing


def snapshot_to_row(chokepoint: Chokepoint, snapshot: ChokepointSnapshot | None) -> dict:
    assessment = snapshot.assessment if snapshot else None
    score = assessment.tension_score if assessment else 0
    risk, _ = risk_label(score)
    relevant_count = (
        sum(1 for item in assessment.classified_articles if item.relevant)
        if assessment
        else 0
    )
    return {
        "name": chokepoint.name,
        "kind": chokepoint.kind,
        "latitude": chokepoint.latitude,
        "longitude": chokepoint.longitude,
        "score": score,
        "risk": risk,
        "news_count": relevant_count,
        "raw_count": len(snapshot.articles) if snapshot else 0,
        "updated_at": snapshot.updated_at if snapshot else "",
    }
