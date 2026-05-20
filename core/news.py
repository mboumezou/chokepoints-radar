from __future__ import annotations

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import requests

from core.config import CHOKEPOINTS, CURATED_RSS_FEEDS, GENERAL_TRADE_TERMS, Chokepoint


REQUEST_TIMEOUT_SECONDS = 14


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    description: str
    url: str
    source: str
    published_at: str
    origin: str
    chokepoint: str

    def to_dict(self) -> dict:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_or_blank(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return ""
    return str(value)


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def article_id(url: str, title: str) -> str:
    key = url or title
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", key.lower()).strip("-")
    return normalized[:120] or "article"


def gdelt_query(chokepoint: Chokepoint) -> str:
    aliases = " OR ".join(f'"{alias}"' for alias in chokepoint.aliases)
    core_terms = (
        "shipping OR maritime OR freight OR vessel OR cargo OR commodity OR commodities "
        'OR "raw materials" OR "supply chain" OR port OR congestion OR rerouting '
        "OR disruption OR blockage OR drought OR attack OR security OR sanctions OR storm"
    )
    return f"({aliases}) ({core_terms})"


def google_query(chokepoint: Chokepoint, days: int) -> str:
    aliases = " OR ".join(f'"{alias}"' for alias in chokepoint.aliases[:3])
    return (
        f"({aliases}) "
        '(shipping OR maritime OR freight OR vessel OR cargo OR commodities OR "raw materials" '
        "OR port OR congestion OR rerouting OR disruption OR blockage OR drought OR attack) "
        f"when:{days}d"
    )


def fetch_gdelt_articles(chokepoint: Chokepoint, days: int, max_records: int) -> list[Article]:
    end = utc_now()
    start = end - timedelta(days=days)
    params = {
        "query": gdelt_query(chokepoint),
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "HybridRel",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    response = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    articles: list[Article] = []
    for raw in payload.get("articles", []) or []:
        title = clean_text(raw.get("title"))
        url = raw.get("url", "")
        if not title or not url:
            continue
        published = parse_datetime(raw.get("seendate", ""))
        source = raw.get("domain") or raw.get("sourceCountry") or "GDELT"
        articles.append(
            Article(
                id=article_id(url, title),
                title=title,
                description=clean_text(raw.get("snippet") or raw.get("sourceCollection") or ""),
                url=url,
                source=source,
                published_at=iso_or_blank(published),
                origin="GDELT",
                chokepoint=chokepoint.name,
            )
        )
    return articles


def fetch_google_news_articles(chokepoint: Chokepoint, days: int, max_records: int) -> list[Article]:
    params = {
        "q": google_query(chokepoint, days),
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    response = requests.get(
        "https://news.google.com/rss/search",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)

    articles: list[Article] = []
    for item in root.findall("./channel/item")[:max_records]:
        title = clean_text(item.findtext("title"))
        url = item.findtext("link") or ""
        description = clean_text(item.findtext("description"))
        published = parse_datetime(item.findtext("pubDate") or "")
        source_node = item.find("source")
        source = source_node.text if source_node is not None and source_node.text else "Google News"
        if not title or not url:
            continue
        articles.append(
            Article(
                id=article_id(url, title),
                title=title,
                description=description,
                url=url,
                source=clean_text(source),
                published_at=iso_or_blank(published),
                origin="Google News RSS",
                chokepoint=chokepoint.name,
            )
        )
    return articles


def fetch_curated_feed_articles(days: int, max_per_feed: int = 80) -> list[Article]:
    cutoff = utc_now() - timedelta(days=days)
    articles: list[Article] = []
    for feed_url in CURATED_RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception:
            continue

        channel_title = clean_text(root.findtext("./channel/title")) or urllib.parse.urlparse(feed_url).netloc
        for item in root.findall("./channel/item")[:max_per_feed]:
            title = clean_text(item.findtext("title"))
            url = item.findtext("link") or ""
            description = clean_text(item.findtext("description"))
            published = parse_datetime(item.findtext("pubDate") or "")
            if published and published < cutoff:
                continue
            if not title or not url:
                continue
            articles.append(
                Article(
                    id=article_id(url, title),
                    title=title,
                    description=description,
                    url=url,
                    source=channel_title,
                    published_at=iso_or_blank(published),
                    origin="Curated RSS",
                    chokepoint="",
                )
            )
    return articles


def attach_curated_articles_to_chokepoint(
    chokepoint: Chokepoint, curated_articles: Iterable[Article]
) -> list[Article]:
    aliases = tuple(alias.lower() for alias in chokepoint.aliases)
    trade_terms = tuple(term.lower() for term in GENERAL_TRADE_TERMS)
    matches: list[Article] = []
    for article in curated_articles:
        text = f"{article.title} {article.description}".lower()
        alias_hit = any(alias in text for alias in aliases)
        trade_hit = any(term in text for term in trade_terms)
        if alias_hit and trade_hit:
            matches.append(
                Article(
                    id=article.id,
                    title=article.title,
                    description=article.description,
                    url=article.url,
                    source=article.source,
                    published_at=article.published_at,
                    origin=article.origin,
                    chokepoint=chokepoint.name,
                )
            )
    return matches


def dedupe_articles(articles: Iterable[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        key = article.url.lower().strip() or article.title.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)

    def sort_key(article: Article) -> datetime:
        return parse_datetime(article.published_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)

    return sorted(unique, key=sort_key, reverse=True)


def fetch_articles_for_chokepoint(
    chokepoint: Chokepoint,
    days: int = 30,
    max_records_per_source: int = 45,
    curated_articles: Iterable[Article] = (),
) -> list[Article]:
    articles: list[Article] = []
    for fetcher in (fetch_gdelt_articles, fetch_google_news_articles):
        try:
            articles.extend(fetcher(chokepoint, days=days, max_records=max_records_per_source))
        except Exception:
            continue
    articles.extend(attach_curated_articles_to_chokepoint(chokepoint, curated_articles))
    return dedupe_articles(articles)
