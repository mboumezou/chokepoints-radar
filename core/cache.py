from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from core.scorer import ChokepointAssessment, assessment_from_dict
from core.config import Chokepoint
from core.news import Article, dedupe_articles, parse_datetime


DATA_CACHE_DIR = Path("data_cache")
SNAPSHOT_DIR = DATA_CACHE_DIR / "chokepoints"
STATE_PATH = DATA_CACHE_DIR / "state.json"
REFRESH_STATUS_PATH = DATA_CACHE_DIR / "refresh_status.json"
CACHE_SCHEMA_VERSION = 5


@dataclass
class ChokepointSnapshot:
    name: str
    articles: list[Article]
    assessment: ChokepointAssessment
    weather: dict
    updated_at: str
    last_article_at: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_cache_dirs() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "chokepoint"


def snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / f"{slugify(name)}.json"


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


def load_snapshot(chokepoint: Chokepoint) -> ChokepointSnapshot | None:
    path = snapshot_path(chokepoint.name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None

    articles_payload = payload.get("articles", [])
    articles = [
        article_from_dict(item)
        for item in articles_payload
        if isinstance(item, dict)
    ]
    assessment_payload = payload.get("assessment", {})
    if not isinstance(assessment_payload, dict):
        return None
    assessment = assessment_from_dict(assessment_payload)
    return ChokepointSnapshot(
        name=chokepoint.name,
        articles=articles,
        assessment=assessment,
        weather=payload.get("weather", {}) if isinstance(payload.get("weather", {}), dict) else {},
        updated_at=str(payload.get("updated_at", "")),
        last_article_at=str(payload.get("last_article_at", "")),
    )


def save_snapshot(snapshot: ChokepointSnapshot) -> None:
    ensure_cache_dirs()
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "name": snapshot.name,
        "updated_at": snapshot.updated_at,
        "last_article_at": snapshot.last_article_at,
        "articles": [article.to_dict() for article in snapshot.articles],
        "assessment": snapshot.assessment.to_dict(),
        "weather": snapshot.weather,
    }
    snapshot_path(snapshot.name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_snapshot(
    chokepoint: Chokepoint,
    articles: list[Article],
    assessment: ChokepointAssessment,
    weather: dict,
) -> ChokepointSnapshot:
    return ChokepointSnapshot(
        name=chokepoint.name,
        articles=articles,
        assessment=assessment,
        weather=weather,
        updated_at=utc_now().isoformat(),
        last_article_at=latest_article_timestamp(articles),
    )


def latest_article_timestamp(articles: Iterable[Article]) -> str:
    latest: datetime | None = None
    for article in articles:
        published = parse_datetime(article.published_at)
        if published and (latest is None or published > latest):
            latest = published
    return latest.isoformat() if latest else ""


def days_since_last_article(snapshot: ChokepointSnapshot | None, default_days: int, max_days: int) -> int:
    if snapshot is None or not snapshot.last_article_at:
        return min(default_days, max_days)
    latest = parse_datetime(snapshot.last_article_at)
    if not latest:
        return min(default_days, max_days)
    age_days = max(1, int((utc_now() - latest).total_seconds() // 86400) + 1)
    return max(1, min(max_days, age_days))


def merge_and_trim_articles(
    existing: Iterable[Article],
    incoming: Iterable[Article],
    max_age_days: int,
    max_articles: int,
) -> list[Article]:
    cutoff = utc_now() - timedelta(days=max_age_days)
    merged = dedupe_articles([*existing, *incoming])
    retained: list[Article] = []
    for article in merged:
        published = parse_datetime(article.published_at)
        if published and published < cutoff:
            continue
        retained.append(article)
        if len(retained) >= max_articles:
            break
    return retained


def next_rotation_index(total: int) -> int:
    ensure_cache_dirs()
    state = load_state()
    index = int(state.get("next_rotation_index", 0)) if isinstance(state.get("next_rotation_index", 0), int) else 0
    state["next_rotation_index"] = (index + 1) % max(total, 1)
    save_state(state)
    return index % max(total, 1)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(payload: dict) -> None:
    ensure_cache_dirs()
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_refresh_status() -> dict:
    if not REFRESH_STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(REFRESH_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_refresh_status(payload: dict) -> None:
    ensure_cache_dirs()
    REFRESH_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_persistent_cache() -> None:
    if not DATA_CACHE_DIR.exists():
        return
    shutil.rmtree(DATA_CACHE_DIR, ignore_errors=True)
