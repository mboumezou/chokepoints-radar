from __future__ import annotations

from datetime import datetime, timezone
from html import escape

import pandas as pd
import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    st_folium = None

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

import requests
import streamlit.components.v1 as components

from core.scorer import DEFAULT_MODEL, DEFAULT_OLLAMA_API_BASE, ClassifiedArticle
from core.config import CHOKEPOINTS, Chokepoint
from core.news import parse_datetime, read_brave_api_key
from core.scheduler import get_refresh_status, is_refresh_running, schedule_background_refresh
from core.cache import ChokepointSnapshot, clear_persistent_cache
from core.refresh import load_cached_dashboard_data
from core.market import fetch_market_snapshot


st.set_page_config(
    page_title="Commodity Chokepoint Radar",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


CSS = """
<style>
    .main .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1500px; }
    h1, h2, h3 { letter-spacing: 0; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 800; }
    [data-testid="stMetricLabel"] { color: #64748b; font-size: 0.82rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
    [data-testid="stMetricDelta"] { font-size: 0.85rem; }

    /* ── Hero ── */
    .hero {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 1.1rem;
        gap: 1rem;
    }
    .hero-left {}
    .hero-title {
        font-size: 1.85rem;
        line-height: 1.1;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.2rem;
    }
    .hero-subtitle {
        color: #64748b;
        font-size: 0.92rem;
        margin-bottom: 0;
    }
    .hero-badge {
        border-radius: 999px;
        padding: 0.22rem 0.75rem;
        font-size: 0.78rem;
        font-weight: 700;
        border: 1.5px solid;
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        margin-top: 0.5rem;
    }
    .badge-running {
        color: #1d4ed8;
        background: #eff6ff;
        border-color: #93c5fd;
        animation: pulse 1.8s ease-in-out infinite;
    }
    .badge-idle   { color: #166534; background: #f0fdf4; border-color: #86efac; }
    .badge-error  { color: #b91c1c; background: #fef2f2; border-color: #fca5a5; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.55} }

    /* ── Panels ── */
    .panel {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #ffffff;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.06);
    }
    .compact-panel {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.75rem 0.9rem;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    }

    /* ── Score panel ── */
    .score-panel {
        border-radius: 10px;
        padding: 1.2rem 1.3rem;
        color: #ffffff;
        min-height: 168px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .score-high   { background: linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%); }
    .score-medium { background: linear-gradient(135deg, #78350f 0%, #f59e0b 100%); }
    .score-low    { background: linear-gradient(135deg, #14532d 0%, #22c55e 100%); }
    .score-value  { font-size: 3.2rem; font-weight: 800; line-height: 1; }
    .score-label  { font-size: 0.82rem; opacity: 0.85; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .score-risk   { font-size: 1.1rem; font-weight: 800; letter-spacing: 0.02em; }

    /* ── Summary box ── */
    .summary-box {
        border-left: 4px solid #3b82f6;
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.2rem;
        min-height: 168px;
    }
    .summary-title {
        color: #1e293b;
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.6rem;
    }
    .summary-line {
        color: #334155;
        margin: 0.3rem 0;
        line-height: 1.5;
        font-size: 0.92rem;
    }
    .summary-rationale {
        color: #64748b;
        font-size: 0.78rem;
        margin-top: 0.65rem;
        font-style: italic;
    }

    /* ── Component bars ── */
    .component-label {
        display: flex;
        justify-content: space-between;
        gap: 0.8rem;
        color: #475569;
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.4rem;
    }
    .bar-track {
        width: 100%;
        height: 8px;
        background: #e2e8f0;
        border-radius: 999px;
        overflow: hidden;
    }
    .bar-fill {
        height: 8px;
        border-radius: 999px;
        background: linear-gradient(90deg, #3b82f6, #6366f1);
        transition: width 0.3s ease;
    }

    /* ── Weather cards ── */
    .weather-card {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #ffffff;
        padding: 0.9rem 1rem;
        min-height: 108px;
        box-shadow: 0 1px 3px rgba(15,23,42,0.05);
        transition: box-shadow 0.2s;
    }
    .weather-card:hover { box-shadow: 0 4px 8px rgba(15,23,42,0.1); }
    .weather-label {
        color: #64748b;
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.45rem;
    }
    .weather-value {
        color: #0f172a;
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .weather-foot {
        color: #94a3b8;
        font-size: 0.75rem;
        margin-top: 0.35rem;
    }

    /* ── Ops log ── */
    .ops-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.5rem;
    }
    .ops-title {
        font-weight: 800;
        color: #0f172a;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .ops-log {
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        background: #0f172a;
        color: #93c5fd;
        padding: 0.85rem;
        min-height: 400px;
        max-height: 400px;
        overflow-y: auto;
        font-family: "Cascadia Code", Consolas, "Courier New", monospace;
        font-size: 0.77rem;
        line-height: 1.45;
        white-space: pre-wrap;
    }

    /* ── Status pills ── */
    .status-pill {
        border-radius: 999px;
        padding: 0.1rem 0.5rem;
        font-size: 0.72rem;
        font-weight: 700;
        border: 1px solid #cbd5e1;
        color: #334155;
        background: #f8fafc;
    }
    .status-running { color: #1d4ed8; background: #eff6ff; border-color: #bfdbfe; }
    .status-error   { color: #b91c1c; background: #fef2f2; border-color: #fecaca; }
    .status-idle    { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }

    /* ── Article cards ── */
    .article-card {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        margin: 0.6rem 0;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
        transition: box-shadow 0.2s, border-color 0.2s;
    }
    .article-card:hover { box-shadow: 0 4px 10px rgba(15,23,42,0.08); border-color: #94a3b8; }
    .article-meta {
        color: #94a3b8;
        font-size: 0.78rem;
        margin-bottom: 0.3rem;
    }
    .article-title {
        font-weight: 700;
        font-size: 0.97rem;
        margin-bottom: 0.3rem;
        line-height: 1.35;
    }
    .article-title a { color: #1e40af; text-decoration: none; }
    .article-title a:hover { text-decoration: underline; }
    .article-desc { color: #475569; font-size: 0.85rem; line-height: 1.4; margin-bottom: 0.4rem; }

    /* ── Pills/tags ── */
    .pill {
        display: inline-block;
        border: 1px solid #e2e8f0;
        border-radius: 999px;
        padding: 0.08rem 0.45rem;
        margin: 0.06rem;
        font-size: 0.72rem;
        color: #475569;
        background: #f8fafc;
        font-weight: 600;
    }
    .pill-security   { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
    .pill-weather    { background: #eff6ff; border-color: #bfdbfe; color: #1e40af; }
    .pill-congestion { background: #fffbeb; border-color: #fde68a; color: #92400e; }
    .pill-energy     { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }

    /* ── Risk colors (text) ── */
    .risk-low    { color: #16a34a; font-weight: 700; }
    .risk-medium { color: #d97706; font-weight: 700; }
    .risk-high   { color: #dc2626; font-weight: 700; }

    /* ── Section titles ── */
    .section-title {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748b;
        margin-bottom: 0.5rem;
    }

    /* ── Market index cards ── */
    .index-card {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #ffffff;
        padding: 0.75rem 0.9rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.05);
    }
    .index-name  { color: #64748b; font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
    .index-price { color: #0f172a; font-size: 1.3rem; font-weight: 800; line-height: 1.1; margin: 0.2rem 0; }
    .index-unit  { color: #94a3b8; font-size: 0.72rem; }
    .index-up    { color: #16a34a; font-size: 0.8rem; font-weight: 700; }
    .index-down  { color: #dc2626; font-size: 0.8rem; font-weight: 700; }
    .index-flat  { color: #94a3b8; font-size: 0.8rem; font-weight: 700; }
</style>
"""


FIXED_SETTINGS = {
    "days": 30,
    "max_records": 25,
    "max_stored_articles": 120,
}


# ─── Helpers ────────────────────────────────────────────────────────────────

def risk_label(score: int) -> tuple[str, str]:
    if score >= 65:
        return "High", "risk-high"
    if score >= 35:
        return "Medium", "risk-medium"
    return "Low", "risk-low"


def risk_tone(score: int) -> str:
    if score >= 65:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def format_age(published_at: str) -> str:
    published = parse_datetime(published_at)
    if not published:
        return "date unavailable"
    delta = datetime.now(timezone.utc) - published
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "< 1h ago"
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def format_timestamp(value: str | None) -> str:
    parsed = parse_datetime(value or "")
    if not parsed:
        return "Unavailable"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def weather_condition_label(code: object) -> str:
    if not isinstance(code, (int, float)):
        return "Unavailable"
    c = int(code)
    if c == 0:
        return "Clear sky"
    if c in {1, 2, 3}:
        return "Partly cloudy"
    if c in {45, 48}:
        return "Fog"
    if c in {51, 53, 55, 56, 57}:
        return "Drizzle"
    if c in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "Rain"
    if c in {71, 73, 75, 77, 85, 86}:
        return "Snow"
    if c in {95, 96, 99}:
        return "Thunderstorm"
    return f"Code {c}"


def value_or_dash(value: object, unit: str) -> str:
    if value is None:
        return "N/A"
    return f"{value} {unit}"


def summary_lines(summary: str) -> list[str]:
    text = (summary or "No rolling summary available yet.").strip()
    parts = [p.strip() for p in text.replace("\n", " ").split(". ") if p.strip()]
    if not parts:
        return [text]
    lines: list[str] = []
    for part in parts[:4]:
        line = part if part.endswith(".") else f"{part}."
        lines.append(line)
    return lines


def pill_class(tag: str) -> str:
    mapping = {
        "security": "pill-security",
        "weather": "pill-weather",
        "congestion": "pill-congestion",
        "energy": "pill-energy",
    }
    return mapping.get(tag, "")


# ─── UI Components ───────────────────────────────────────────────────────────

def render_component_bar(label: str, value: int, maximum: int = 100) -> None:
    safe_value = max(0, min(maximum, int(value or 0)))
    width = int(round((safe_value / maximum) * 100)) if maximum else 0
    st.markdown(
        f"""
        <div class="compact-panel">
            <div class="component-label">
                <span>{escape(label)}</span>
                <span>{safe_value}/{maximum}</span>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:{width}%;"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_weather_card(label: str, value: str, foot: str = "") -> None:
    st.markdown(
        f"""
        <div class="weather-card">
            <div class="weather-label">{escape(label)}</div>
            <div class="weather-value">{escape(value)}</div>
            <div class="weather-foot">{escape(foot)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_panel(score: int, updated_at: str) -> None:
    tone = risk_tone(score)
    risk, _ = risk_label(score)
    st.markdown(
        f"""
        <div class="score-panel score-{tone}">
            <div>
                <div class="score-label">Tension score</div>
                <div class="score-value">{int(score)}</div>
                <div class="score-label">/ 100</div>
            </div>
            <div>
                <div class="score-risk">{escape(risk)} risk</div>
                <div class="score-label" style="margin-top:0.2rem;">Updated {escape(format_timestamp(updated_at))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_summary_box(chokepoint: Chokepoint, summary: str, rationale: str) -> None:
    lines = "".join(
        f'<div class="summary-line">{escape(line)}</div>'
        for line in summary_lines(summary)
    )
    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-title">Situation summary</div>
            {lines}
            <div class="summary-rationale">{escape(rationale or chokepoint.baseline_risk_note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_map(summary_df: pd.DataFrame, selected_name: str) -> str:
    if folium is None or st_folium is None:
        st.dataframe(
            summary_df[["name", "kind", "score", "risk", "news_count"]],
            use_container_width=True,
            hide_index=True,
        )
        return selected_name

    m = folium.Map(location=[20, 25], zoom_start=2, tiles="CartoDB positron")

    for _, row in summary_df.iterrows():
        score = row["score"]
        if score >= 65:
            color, fill_color = "#dc2626", "#ef4444"
        elif score >= 35:
            color, fill_color = "#d97706", "#f59e0b"
        else:
            color, fill_color = "#16a34a", "#22c55e"

        radius = 10 + min(12, score // 8)
        popup_html = (
            f"<b>{row['name']}</b><br>"
            f"Score: <b>{score}/100</b> — {row['risk']} risk<br>"
            f"AI inputs: {row['news_count']} articles"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=radius,
            tooltip=row["name"],
            popup=folium.Popup(popup_html, max_width=200),
            color=color,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.78,
            weight=2,
        ).add_to(m)

    result = st_folium(m, height=420, use_container_width=True, returned_objects=["last_object_clicked_tooltip"])
    clicked = result.get("last_object_clicked_tooltip") if result else None
    if clicked and clicked in set(summary_df["name"]):
        return clicked
    return selected_name


def render_article_card(item: ClassifiedArticle) -> None:
    article = item.article
    tags_html = "".join(
        f'<span class="pill {pill_class(str(tag))}">{escape(str(tag))}</span>'
        for tag in item.impact_tags
    )
    title = escape(article.title)
    source = escape(article.source)
    origin = escape(article.origin)
    desc = escape((item.summary or article.description or "")[:200])
    url = escape(article.url, quote=True)
    age = format_age(article.published_at)
    st.markdown(
        f"""
        <div class="article-card">
            <div class="article-meta">{source} &middot; {origin} &middot; {age}</div>
            <div class="article-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
            <div class="article-desc">{desc}</div>
            <div>{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_controls() -> dict:
    with st.sidebar:
        st.markdown("### Commodity Chokepoint Radar")
        st.caption(f"{len(CHOKEPOINTS)} chokepoints monitored")
        st.divider()

        st.markdown("**Scoring**")
        max_ai_articles = st.slider("Articles sent to AI", min_value=5, max_value=50, value=20, step=5)
        st.caption("Takes effect after next refresh.")
        rolling_minutes = st.slider("Refresh interval (min)", min_value=10, max_value=60, value=30, step=5)
        auto_refresh = st.toggle("Auto-refresh", value=True)

        st.divider()
        st.markdown("**Selection**")
        selected = st.selectbox("Chokepoint", [cp.name for cp in CHOKEPOINTS], index=0, label_visibility="collapsed")
        force_selected = st.button("Force refresh now", use_container_width=True)

        model = DEFAULT_MODEL
        api_base = DEFAULT_OLLAMA_API_BASE
        with st.expander("Advanced"):
            model = st.text_input("Model", value=DEFAULT_MODEL)
            api_base = st.text_input("API base URL", value=DEFAULT_OLLAMA_API_BASE)
            st.caption("Fixed: 30d lookback · 15 records/source · 80 cached articles/chokepoint")

        st.divider()
        if st.button("Clear disk cache", use_container_width=True):
            st.cache_data.clear()
            clear_persistent_cache()
            st.rerun()

    return {
        **FIXED_SETTINGS,
        "max_ai_articles": max_ai_articles,
        "auto_refresh": auto_refresh,
        "refresh_seconds": rolling_minutes * 60,
        "model": model,
        "api_base": api_base,
        "use_ai": True,
        "selected": selected,
        "force_selected": force_selected,
    }


def render_log_window(status: dict) -> None:
    running = bool(status.get("running")) if status else False
    has_error = bool(status.get("error")) if status else False
    status_class = "status-error" if has_error else "status-running" if running else "status-idle"
    status_text = "Error" if has_error else "Running" if running else "Idle"
    logs = status.get("logs", []) if status else []
    if not logs:
        message = status.get("message", "Waiting for first background refresh.") if status else "Waiting for first background refresh."
        logs = [message]
    target_line = ", ".join(status.get("targets", []) or []) if status else "—"
    updated = format_timestamp(status.get("updated_at", "")) if status else "Unavailable"
    body = "\n".join(str(line) for line in logs[-120:])
    st.markdown(
        f"""
        <div class="ops-header">
            <span class="ops-title">Refresh log</span>
            <span class="status-pill {status_class}">{status_text}</span>
        </div>
        <div class="weather-foot" style="margin-bottom:0.4rem; color:#64748b; font-size:0.78rem;">
            Targets: {escape(target_line)} &nbsp;·&nbsp; Last update: {escape(updated)}
        </div>
        <div class="ops-log">{escape(body)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_market_overview(summary_df: pd.DataFrame, snapshots: dict[str, ChokepointSnapshot]) -> None:
    if summary_df.empty:
        return
    high_count = int((summary_df["score"] >= 65).sum())
    medium_count = int(((summary_df["score"] >= 35) & (summary_df["score"] < 65)).sum())
    low_count = int((summary_df["score"] < 35).sum())
    top_row = summary_df.sort_values("score", ascending=False).iloc[0]
    refreshed_count = len(snapshots)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Highest tension", f"{int(top_row['score'])}/100", top_row["name"])
    m2.metric("High risk", high_count, "chokepoints")
    m3.metric("Medium risk", medium_count, "chokepoints")
    m4.metric("Snapshots cached", f"{refreshed_count}/{len(CHOKEPOINTS)}")


def render_chokepoint_view(
    chokepoint: Chokepoint,
    snapshot: ChokepointSnapshot | None,
) -> None:
    if snapshot is None:
        st.subheader(chokepoint.name)
        st.info("No cached data yet. A background refresh will fill it shortly.")
        return

    assessment = snapshot.assessment
    score_inputs = sorted(
        assessment.classified_articles,
        key=lambda x: parse_datetime(x.article.published_at) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    raw_articles = snapshot.articles
    weather = snapshot.weather
    score = assessment.tension_score
    risk, risk_class = risk_label(score)

    st.subheader(chokepoint.name)
    st.caption(chokepoint.strategic_note)

    score_col, summary_col = st.columns([1, 2.2])
    with score_col:
        render_score_panel(score, snapshot.updated_at)
    with summary_col:
        render_summary_box(chokepoint, assessment.market_summary, assessment.score_rationale)

    st.markdown('<div class="section-title" style="margin-top:0.9rem;">Score components</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_component_bar("Structural risk", chokepoint.baseline_political_risk)
    with c2:
        render_component_bar("Political context", assessment.political_context_score)
    with c3:
        render_component_bar("Logistics", assessment.logistics_score)
    with c4:
        render_component_bar("Weather impact", assessment.weather_score, maximum=15)

    st.markdown('<div class="section-title" style="margin-top:0.9rem;">Live weather</div>', unsafe_allow_html=True)
    w1, w2, w3, w4, w5 = st.columns(5)
    with w1:
        render_weather_card(
            "Sea state",
            value_or_dash(weather.get("wave_height"), weather.get("wave_height_unit", "m")),
            "Wave height",
        )
    with w2:
        render_weather_card(
            "Wind speed",
            value_or_dash(weather.get("wind_speed"), weather.get("wind_speed_unit", "km/h")),
            "10 m",
        )
    with w3:
        render_weather_card(
            "Wind gusts",
            value_or_dash(weather.get("wind_gusts"), weather.get("wind_gusts_unit", "km/h")),
            "10 m gusts",
        )
    with w4:
        render_weather_card(
            "Condition",
            weather_condition_label(weather.get("weather_code")),
            f"WMO code {weather.get('weather_code', 'n/a')}",
        )
    with w5:
        render_weather_card(
            "Weather time",
            format_timestamp(weather.get("time") or weather.get("wind_time")),
            assessment.assessment_method,
        )

    st.markdown(
        f'<div class="section-title" style="margin-top:0.9rem;">News used by the rolling score</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"{len(score_inputs)} articles sent to the scoring model · {len(raw_articles)} total cached articles."
    )
    if not score_inputs:
        st.info("No articles retained yet for this chokepoint.")
    for item in score_inputs:
        render_article_card(item)


def render_refresh_progress(status: dict) -> None:
    """Show a progress bar while a refresh is running."""
    if not status or not status.get("running"):
        return
    targets = status.get("targets") or []
    logs = status.get("logs") or []
    total = len(targets)
    if total == 0:
        return
    # Each finished chokepoint emits a line containing "score=XX/100"
    completed_names = {
        log.split(":")[0].split("|")[-1].strip()
        for log in logs
        if "score=" in log and "/100" in log
    }
    completed = min(len(completed_names), total)
    fraction = completed / total
    current_msg = status.get("message", "Refreshing…")
    label = f"Refreshing {completed}/{total} — {current_msg}"
    st.progress(fraction, text=label)


def render_market_indices() -> None:
    indices = fetch_market_snapshot()
    if not indices:
        return
    st.markdown('<div class="section-title" style="margin-top:0.6rem;">Market indices</div>', unsafe_allow_html=True)
    cols = st.columns(len(indices))
    for col, item in zip(cols, indices):
        chg = item["change_pct"]
        arrow = "▲" if chg > 0 else "▼" if chg < 0 else "—"
        chg_class = "index-up" if chg > 0 else "index-down" if chg < 0 else "index-flat"
        with col:
            st.markdown(
                f"""
                <div class="index-card">
                    <div class="index-name">{escape(item['name'])}</div>
                    <div class="index-price">{item['price']}</div>
                    <div class="index-unit">{escape(item['unit'])}</div>
                    <div class="{chg_class}">{arrow} {abs(chg):.2f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_vessel_tab(chokepoint: Chokepoint) -> None:
    st.markdown(f"### Live vessel traffic — {escape(chokepoint.name)}")
    st.caption(
        f"Lat {chokepoint.latitude:.2f}° · Lon {chokepoint.longitude:.2f}° · "
        "AIS data via VesselFinder (free embed, refreshes automatically)"
    )
    zoom = 8 if chokepoint.kind in ("Canal", "Strait") else 6
    embed_url = (
        f"https://www.vesselfinder.com/aismap"
        f"?zoom={zoom}&lat={chokepoint.latitude}&lon={chokepoint.longitude}"
        f"&width=100%25&height=650&names=true&mmsi=&track=false&fleet=false"
    )
    components.html(
        f'<iframe src="{embed_url}" width="100%" height="660px" '
        f'frameborder="0" style="border-radius:10px; border:1px solid #e2e8f0;"></iframe>',
        height=670,
    )
    mt_url = (
        f"https://www.marinetraffic.com/en/ais/home"
        f"/centerx:{chokepoint.longitude}/centery:{chokepoint.latitude}/zoom:8"
    )
    st.markdown(f"[Open full screen on MarineTraffic]({mt_url})")


WAR_RISK_QUERIES = [
    ("War Risk Premiums",    "maritime war risk insurance premium shipping 2025"),
    ("Red Sea / Houthi",     "Red Sea Houthi war risk shipping insurance premium"),
    ("JWC Hull War Areas",   "JWC joint war committee hull war risk listed areas shipping"),
    ("P&I Club Alerts",      "P&I club maritime security alert war risk notice"),
    ("Strait of Hormuz",     "Strait of Hormuz war risk Iran insurance shipping"),
    ("Cargo Insurance",      "cargo insurance maritime disruption chokepoint premium rate"),
]


def render_war_risk_tab() -> None:
    st.markdown("### War Risk & Maritime Insurance Monitor")
    st.caption("Search live news on war risk premiums, P&I club alerts, JWC area changes and insurance market signals.")

    api_key = read_brave_api_key()
    if not api_key:
        st.warning("Brave API key not configured. Add BRAVE_API_KEY to your secrets.")
        return

    c1, c2 = st.columns([3, 1])
    with c1:
        topic = st.selectbox("Topic", [q[0] for q in WAR_RISK_QUERIES], label_visibility="collapsed")
    with c2:
        search = st.button("Search", use_container_width=True, type="primary")

    query = next(q[1] for q in WAR_RISK_QUERIES if q[0] == topic)
    cache_key = f"war_risk__{topic}"

    if search:
        st.session_state.pop(cache_key, None)

    if search or cache_key in st.session_state:
        if cache_key not in st.session_state:
            with st.spinner(f"Searching: {query}…"):
                try:
                    resp = requests.get(
                        "https://api.search.brave.com/res/v1/news/search",
                        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                        params={"q": query, "count": 20, "search_lang": "en", "country": "us"},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    st.session_state[cache_key] = resp.json().get("results", [])
                except Exception as exc:
                    st.error(f"Search failed: {exc}")
                    return

        results = st.session_state.get(cache_key, [])
        st.caption(f"{len(results)} results · query: *{query}*")
        for item in results:
            title = escape(item.get("title", ""))
            url = escape(item.get("url", ""), quote=True)
            desc = escape((item.get("description") or "")[:300])
            age = escape(item.get("age", ""))
            source = escape((item.get("meta_url") or {}).get("netloc", ""))
            st.markdown(
                f"""
                <div class="article-card">
                    <div class="article-meta">{source} &middot; {age}</div>
                    <div class="article-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
                    <div class="article-desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Select a topic and click Search.")


def render_hero(status: dict) -> None:
    running = bool(status.get("running")) if status else False
    has_error = bool(status.get("error")) if status else False
    badge_class = "badge-error" if has_error else "badge-running" if running else "badge-idle"
    badge_icon = "⚠" if has_error else "●" if running else "●"
    badge_text = "Error" if has_error else "Refreshing…" if running else "Idle"
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-left">
                <div class="hero-title">Commodity Chokepoint Radar</div>
                <div class="hero-subtitle">Rolling AI tension scores · market summaries · weather · live news</div>
                <div class="hero-badge {badge_class}">{badge_icon} {badge_text}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    settings = sidebar_controls()

    auto_refresh_count = None
    if settings["auto_refresh"] and st_autorefresh is not None:
        auto_refresh_count = st_autorefresh(interval=settings["refresh_seconds"] * 1000, key="radar_refresh")

    summary_df, snapshots, missing = load_cached_dashboard_data()
    running_before_schedule = is_refresh_running()
    scheduled = False

    if missing and not running_before_schedule:
        target_names = [cp.name for cp in missing]
        scheduled = schedule_background_refresh(
            target_names,
            settings=settings,
            reason="cold_start",
            cold_start_names=set(target_names),
        )
    elif settings["force_selected"]:
        scheduled = schedule_background_refresh(
            [settings["selected"]],
            settings=settings,
            reason="manual",
        )
    elif settings["auto_refresh"] and auto_refresh_count is not None:
        last_count = st.session_state.get("last_auto_refresh_count")
        if last_count is None:
            st.session_state["last_auto_refresh_count"] = auto_refresh_count
        elif last_count != auto_refresh_count:
            scheduled = schedule_background_refresh(
                [cp.name for cp in CHOKEPOINTS],
                settings=settings,
                reason="scheduled",
            )
            st.session_state["last_auto_refresh_count"] = auto_refresh_count

    status = get_refresh_status()
    if is_refresh_running() and st_autorefresh is not None:
        st_autorefresh(interval=5000, key="worker_status_poll")

    render_hero(status)
    render_refresh_progress(status)

    if missing:
        st.info(
            f"{len(missing)} chokepoint snapshot(s) initializing in the background — "
            "the dashboard will auto-update when ready."
        )

    tab_radar, tab_vessels, tab_war_risk = st.tabs(["Radar", "Live Vessels", "War Risk & Insurance"])

    with tab_radar:
        render_market_overview(summary_df, snapshots)
        render_market_indices()
        st.markdown("<br>", unsafe_allow_html=True)

        map_col, log_col = st.columns([2, 1])
        with map_col:
            selected_name = render_map(summary_df, settings["selected"])
        with log_col:
            render_log_window(status)

        names = [cp.name for cp in CHOKEPOINTS]
        selected_name = st.radio(
            "Chokepoint view",
            names,
            index=names.index(selected_name) if selected_name in names else 0,
            horizontal=True,
            label_visibility="collapsed",
        )
        selected = next(cp for cp in CHOKEPOINTS if cp.name == selected_name)

        top = summary_df.sort_values(["score", "news_count"], ascending=False).head(8)
        st.dataframe(
            top[["name", "kind", "score", "risk", "news_count", "raw_count", "updated_at"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                "news_count": st.column_config.NumberColumn("AI inputs"),
                "raw_count": st.column_config.NumberColumn("Cached"),
                "updated_at": st.column_config.TextColumn("Updated"),
                "name": st.column_config.TextColumn("Chokepoint"),
                "kind": st.column_config.TextColumn("Type"),
                "risk": st.column_config.TextColumn("Risk"),
            },
        )

        st.divider()
        render_chokepoint_view(selected, snapshot=snapshots.get(selected.name))

    with tab_vessels:
        selected_cp = next(
            (cp for cp in CHOKEPOINTS if cp.name == settings["selected"]),
            CHOKEPOINTS[0],
        )
        render_vessel_tab(selected_cp)

    with tab_war_risk:
        render_war_risk_tab()

    st.markdown(
        """
        <div style="margin-top:2.5rem; padding-top:1rem; border-top:1px solid #e2e8f0;
                    text-align:center; color:#94a3b8; font-size:0.78rem;">
            Created by
            <a href="https://www.linkedin.com/in/mohamed-zidane-boumezou-a8a0052ab/"
               target="_blank" rel="noopener"
               style="color:#3b82f6; text-decoration:none; font-weight:600;">
                Mohamed Zidane Boumezou
            </a>
            &nbsp;&middot;&nbsp;
            <a href="mailto:mohamed.boumezou@dauphine.eu"
               style="color:#3b82f6; text-decoration:none;">
                mohamed.boumezou@dauphine.eu
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
