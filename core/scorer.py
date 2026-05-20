from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable

import requests

from core.config import Chokepoint
from core.news import Article, parse_datetime


DEFAULT_MODEL = "cogito-2.1:671b-cloud"
DEFAULT_OLLAMA_API_BASE = "https://ollama.com/api"
REQUEST_TIMEOUT_SECONDS = 75


@dataclass(frozen=True)
class ClassifiedArticle:
    article: Article
    relevant: bool
    confidence: float
    severity: int
    impact_tags: tuple[str, ...]
    risk_type: str
    summary: str
    filter_method: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["article"] = self.article.to_dict()
        return payload


@dataclass(frozen=True)
class ChokepointAssessment:
    classified_articles: tuple[ClassifiedArticle, ...]
    tension_score: int
    market_summary: str
    score_rationale: str
    political_context_score: int
    logistics_score: int
    weather_score: int
    assessment_method: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "classified_articles": [item.to_dict() for item in self.classified_articles],
            "tension_score": self.tension_score,
            "market_summary": self.market_summary,
            "score_rationale": self.score_rationale,
            "political_context_score": self.political_context_score,
            "logistics_score": self.logistics_score,
            "weather_score": self.weather_score,
            "assessment_method": self.assessment_method,
            "updated_at": self.updated_at,
        }


def article_from_dict(payload: dict) -> Article:
    return Article(
        id=str(payload.get("id", "")),
        title=str(payload.get("title", "")),
        description=str(payload.get("description", "")),
        url=str(payload.get("url", "")),
        source=str(payload.get("source", "")),
        published_at=str(payload.get("published_at", "")),
        origin=str(payload.get("origin", "")),
        chokepoint=str(payload.get("chokepoint", "")),
    )


def classified_article_from_dict(payload: dict) -> ClassifiedArticle:
    article_payload = payload.get("article", {})
    article = article_from_dict(article_payload if isinstance(article_payload, dict) else {})
    return ClassifiedArticle(
        article=article,
        relevant=bool(payload.get("relevant", False)),
        confidence=safe_float(payload.get("confidence", 0.0), default=0.0),
        severity=clamp_int(payload.get("severity", 0), 0, 5, default=0),
        impact_tags=tuple(str(tag) for tag in payload.get("impact_tags", []) if str(tag).strip()) or ("monitoring",),
        risk_type=str(payload.get("risk_type", "other")),
        summary=str(payload.get("summary", "")),
        filter_method=str(payload.get("filter_method", "unknown")),
    )


def assessment_from_dict(payload: dict) -> ChokepointAssessment:
    items = payload.get("classified_articles", [])
    classified = tuple(
        classified_article_from_dict(item)
        for item in items
        if isinstance(item, dict)
    )
    return ChokepointAssessment(
        classified_articles=classified,
        tension_score=clamp_int(payload.get("tension_score", 0), 0, 100, default=0),
        market_summary=str(payload.get("market_summary", "")),
        score_rationale=str(payload.get("score_rationale", "")),
        political_context_score=clamp_int(payload.get("political_context_score", 0), 0, 100, default=0),
        logistics_score=clamp_int(payload.get("logistics_score", 0), 0, 100, default=0),
        weather_score=clamp_int(payload.get("weather_score", 0), 0, 15, default=0),
        assessment_method=str(payload.get("assessment_method", "unknown")),
        updated_at=str(payload.get("updated_at", "")),
    )


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_int(value: object, lower: int, upper: int, default: int = 0) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(upper, parsed))


def read_ollama_api_key(path: str = "ollama.txt") -> str:
    # Streamlit Cloud: key stored in st.secrets
    try:
        import streamlit as st
        key = st.secrets.get("OLLAMA_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    # Local dev: key stored in ollama.txt
    try:
        content = open(path, "r", encoding="utf-8").read().strip()
    except OSError:
        return ""
    if not content:
        return ""
    if "=" in content and "\n" not in content:
        _, value = content.split("=", 1)
        return value.strip().strip('"').strip("'")
    return content.splitlines()[0].strip().strip('"').strip("'")


def extract_json_object(text: str) -> dict | list | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = min([idx for idx in (text.find("{"), text.find("[")) if idx >= 0], default=-1)
    if start < 0:
        return None
    end_char = "}" if text[start] == "{" else "]"
    end = text.rfind(end_char)
    if end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def build_prompt(chokepoint: Chokepoint, articles: list[Article], weather: dict | None = None) -> str:
    compact_articles = [
        {
            "id": article.id,
            "title": article.title[:240],
            "description": article.description[:420],
            "source": article.source,
            "published_at": article.published_at,
            "origin": article.origin,
        }
        for article in articles
    ]
    weather = weather or {}
    weather_snapshot = {
        "wave_height": weather.get("wave_height"),
        "wave_height_unit": weather.get("wave_height_unit"),
        "wind_speed": weather.get("wind_speed"),
        "wind_speed_unit": weather.get("wind_speed_unit"),
        "wind_gusts": weather.get("wind_gusts"),
        "wind_gusts_unit": weather.get("wind_gusts_unit"),
        "weather_code": weather.get("weather_code"),
        "updated_at": weather.get("time") or weather.get("wind_time"),
    }
    return f"""
You are a commodity trading market-intelligence analyst. You receive a search-filtered news packet about one maritime chokepoint and produce an accurate aggregate operational tension score.

Chokepoint:
- Name: {chokepoint.name}
- Aliases: {", ".join(chokepoint.aliases)}
- Baseline political risk: {chokepoint.baseline_political_risk}/100
- Baseline risk note: {chokepoint.baseline_risk_note}

Task:
Use the article titles/descriptions as an aggregate signal packet. Do not classify articles one by one. Assume the upstream query already selected chokepoint-related articles, then judge the overall tension level for broad commodity and raw material trading. Do not limit yourself to oil, LNG or coal. Include metals, ores, steel inputs, agriculture, fertilizers, dry bulk, tankers, containers, freight, insurance, security, weather, canal restrictions, port delays and supply chain disruption.

Return strict JSON only with this shape:
{{
  "tension_score": 0,
  "political_context_score": 0,
  "logistics_score": 0,
  "weather_score": 0,
  "market_summary": "2-3 concise sentences for a trader",
  "score_rationale": "one concise sentence"
}}

Scoring guidance:
- tension_score is 0-100 and must reflect current conditions accurately.
- 0-20 = normal background noise, no actionable signal.
- 21-40 = monitoring signal, no clear disruption.
- 41-60 = meaningful operational tension with some confirmed signal.
- 61-80 = high tension: confirmed disruption risk, active incidents, ongoing conflict exposure, recent attacks or closures.
- 81-100 = acute crisis: active conflict impacting the chokepoint, confirmed blockade, sustained attacks, mass rerouting.
- A chokepoint in a warzone with active attacks and confirmed rerouting should score 85-100, not 60-70.
- Give high weight to political/security context, conflict, sanctions, closures, attacks, strikes, accidents, congestion and draft/canal restrictions.
- The baseline political risk reflects structural ongoing exposure — for high-baseline chokepoints (>60) already under active threat, scores below 70 are rarely appropriate.
- Weather is a secondary but visible input: weather_score must be 0-15. Use 0 only when weather data is unavailable or clearly benign.
- Do not double count duplicate headlines. Treat repeated stories as confirmation, not as independent shocks.

Weather snapshot:
{json.dumps(weather_snapshot, ensure_ascii=False)}

Articles:
{json.dumps(compact_articles, ensure_ascii=False)}
""".strip()


def call_ollama_chat(
    prompt: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_OLLAMA_API_BASE,
) -> str:
    base = api_base.rstrip("/")
    endpoint = f"{base}/chat"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "Return valid JSON only. Be accurate and do not invent facts.",
            },
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0},
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code >= 400 and base == DEFAULT_OLLAMA_API_BASE and model.endswith("-cloud"):
        retry_payload = dict(payload)
        retry_payload["model"] = model.removesuffix("-cloud")
        response = requests.post(endpoint, headers=headers, json=retry_payload, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    return (data.get("message") or {}).get("content", "")


def article_score_inputs(articles: Iterable[Article], method: str = "score-input") -> list[ClassifiedArticle]:
    inputs: list[ClassifiedArticle] = []
    for article in articles:
        text = f"{article.title} {article.description}".lower()
        inputs.append(
            ClassifiedArticle(
                article=article,
                relevant=True,
                confidence=1.0,
                severity=0,
                impact_tags=infer_tags(text),
                risk_type=infer_risk_type(text),
                summary=(article.description or article.title)[:240],
                filter_method=method,
            )
        )
    return inputs


def aggregate_keyword_scores(articles: Iterable[Article]) -> tuple[int, int]:
    political = 0.0
    logistics = 0.0
    political_terms = (
        "attack", "missile", "drone", "piracy", "hijack", "war risk",
        "conflict", "military", "sanction", "closed", "closure", "blocked", "blockade",
    )
    logistics_terms = (
        "congestion", "queue", "delay", "rerouting", "reroute", "restriction",
        "draft", "collision", "grounding", "strike", "disruption", "freight",
    )
    for article in list(articles)[:12]:
        text = f"{article.title} {article.description}".lower()
        recency = recency_weight(article.published_at)
        political_hits = sum(1 for term in political_terms if term in text)
        logistics_hits = sum(1 for term in logistics_terms if term in text)
        political += min(18, political_hits * 6) * recency
        logistics += min(14, logistics_hits * 4) * recency
    return int(min(100, round(political))), int(min(100, round(logistics)))


def weather_score_from_snapshot(weather: dict | None) -> int:
    if not weather:
        return 0
    wave = weather.get("wave_height")
    wind = weather.get("wind_speed")
    gusts = weather.get("wind_gusts")
    weather_code = weather.get("weather_code")
    score = 0
    if isinstance(wave, (int, float)):
        if wave >= 6:
            score = max(score, 15)
        elif wave >= 4:
            score = max(score, 10)
        elif wave >= 2.5:
            score = max(score, 5)
        elif wave >= 1.5:
            score = max(score, 2)
    if isinstance(wind, (int, float)):
        if wind >= 60:
            score = max(score, 9)
        elif wind >= 40:
            score = max(score, 5)
        elif wind >= 25:
            score = max(score, 2)
    if isinstance(gusts, (int, float)):
        if gusts >= 80:
            score = max(score, 12)
        elif gusts >= 55:
            score = max(score, 8)
        elif gusts >= 35:
            score = max(score, 4)
        elif gusts >= 25:
            score = max(score, 1)
    if isinstance(weather_code, (int, float)):
        code = int(weather_code)
        if code in {95, 96, 99}:
            score = max(score, 10)
        elif code in {65, 66, 67, 80, 81, 82}:
            score = max(score, 5)
        elif code in {45, 48, 51, 53, 55, 61, 63}:
            score = max(score, 3)
    return min(15, score)


def heuristic_assessment(
    chokepoint: Chokepoint,
    articles: Iterable[Article],
    weather: dict | None = None,
) -> ChokepointAssessment:
    article_list = list(articles)
    classified = tuple(article_score_inputs(article_list, method="score-input"))
    political_signal, logistics_signal = aggregate_keyword_scores(article_list)
    baseline_floor = int(round(chokepoint.baseline_political_risk * 0.90))
    political_score = int(min(90, max(baseline_floor, political_signal)))
    logistics_score = int(min(70, logistics_signal))
    weather_score = weather_score_from_snapshot(weather)
    total = min(100, political_score + int(logistics_score * 0.55) + weather_score)
    rationale = "Conservative aggregate fallback score from structural risk, retained headlines, recency and weather."
    if not article_list:
        rationale = "No retained articles yet; score is driven by structural risk and live weather only."
    summary = (
        "The rolling score is driven by the retained news packet, structural chokepoint risk and live weather. "
        "No model summary is available because the heuristic fallback was used."
    )
    return ChokepointAssessment(
        classified_articles=classified,
        tension_score=total,
        market_summary=summary,
        score_rationale=rationale,
        political_context_score=political_score,
        logistics_score=logistics_score,
        weather_score=weather_score,
        assessment_method="heuristic",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def infer_tags(text: str) -> tuple[str, ...]:
    tag_terms = {
        "freight": ("freight", "shipping", "vessel", "cargo", "rerouting", "port"),
        "energy": ("oil", "gas", "lng", "tanker", "fuel"),
        "metals": ("iron ore", "steel", "scrap", "copper", "nickel", "aluminium", "aluminum", "bauxite"),
        "agri": ("grain", "wheat", "corn", "soybean", "sugar", "palm oil"),
        "fertilizers": ("fertilizer", "phosphate", "potash", "ammonia"),
        "security": ("attack", "missile", "drone", "piracy", "hijack", "war risk"),
        "weather": ("storm", "drought", "wind", "wave", "weather"),
        "congestion": ("congestion", "queue", "delay", "restriction", "draft"),
    }
    tags = [tag for tag, terms in tag_terms.items() if any(term in text for term in terms)]
    return tuple(tags[:5] or ("monitoring",))


def infer_risk_type(text: str) -> str:
    buckets = {
        "security": ("attack", "missile", "drone", "piracy", "hijack", "security", "war risk"),
        "weather": ("storm", "drought", "weather", "wind", "wave"),
        "congestion": ("congestion", "queue", "delay", "restriction", "draft", "rerouting"),
        "policy": ("sanction", "tariff", "policy", "regulation", "ban"),
        "accident": ("collision", "grounding", "accident", "explosion"),
        "market": ("price", "rate", "freight", "premium", "insurance"),
    }
    for risk_type, terms in buckets.items():
        if any(term in text for term in terms):
            return risk_type
    return "other"


def recency_weight(published_at: str) -> float:
    published = parse_datetime(published_at)
    if not published:
        return 0.65
    age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    return max(0.25, math.exp(-age_hours / 168))


def assess_chokepoint_with_ai(
    chokepoint: Chokepoint,
    articles: list[Article],
    api_key: str,
    weather: dict | None = None,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_OLLAMA_API_BASE,
    max_articles: int = 12,
) -> ChokepointAssessment:
    target_articles = articles[:max_articles]
    if not api_key:
        raise RuntimeError("Ollama aggregate scoring requires an Ollama API key.")

    prompt = build_prompt(chokepoint, target_articles, weather=weather)
    raw = call_ollama_chat(prompt, api_key=api_key, model=model, api_base=api_base)
    parsed = extract_json_object(raw)
    parsed = parsed if isinstance(parsed, dict) else {}
    output = article_score_inputs(target_articles, method="score-input")
    fallback_assessment = heuristic_assessment(chokepoint, target_articles, weather=weather)
    tension = clamp_int(parsed.get("tension_score"), 0, 100, default=fallback_assessment.tension_score)
    observed_weather_score = weather_score_from_snapshot(weather)
    weather_score = clamp_int(parsed.get("weather_score"), 0, 15, default=observed_weather_score)
    weather_score = max(weather_score, observed_weather_score)
    baseline_floor = int(round(chokepoint.baseline_political_risk * 0.95))
    political_score = clamp_int(parsed.get("political_context_score"), 0, 100, default=fallback_assessment.political_context_score)
    political_score = max(political_score, baseline_floor)
    logistics_score = clamp_int(parsed.get("logistics_score"), 0, 100, default=fallback_assessment.logistics_score)
    # No upper cap on the floor — for warzone chokepoints the floor can push tension above 85
    tension = min(100, max(tension, baseline_floor + min(logistics_score, 15) + min(weather_score, 8)))
    return ChokepointAssessment(
        classified_articles=tuple(output),
        tension_score=tension,
        market_summary=str(parsed.get("market_summary") or fallback_assessment.market_summary)[:420],
        score_rationale=str(parsed.get("score_rationale") or "AI conservative assessment from retained headlines and descriptions.")[:280]
        or fallback_assessment.score_rationale,
        political_context_score=political_score,
        logistics_score=logistics_score,
        weather_score=weather_score,
        assessment_method="ollama-aggregate",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
