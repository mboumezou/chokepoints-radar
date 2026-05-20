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

from core.config import CHOKEPOINTS, CHOKEPOINT_CONTEXT_TERMS, CURATED_RSS_FEEDS, GENERAL_TRADE_TERMS, Chokepoint


REQUEST_TIMEOUT_SECONDS = 14
BRAVE_NEWS_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"


def read_brave_api_key(path: str = "brave.tkt") -> str:
    try:
        import streamlit as st
        key = st.secrets.get("BRAVE_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    try:
        return open(path, "r", encoding="utf-8").read().strip().splitlines()[0].strip()
    except OSError:
        return ""


def brave_news_query(chokepoint: Chokepoint) -> str:
    aliases_part = " OR ".join(f'"{alias}"' for alias in chokepoint.aliases[:2])
    return (
        f"({aliases_part}) "
        "(shipping OR maritime OR commodity OR freight OR tanker OR cargo "
        "OR attack OR disruption OR sanctions OR rerouting OR security OR closure)"
    )


def fetch_brave_news_articles(
    chokepoint: Chokepoint,
    api_key: str,
    count: int = 20,
) -> list[Article]:
    if not api_key:
        return []
    response = requests.get(
        BRAVE_NEWS_ENDPOINT,
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        params={"q": brave_news_query(chokepoint), "count": count, "search_lang": "en", "country": "us"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    articles: list[Article] = []
    for item in response.json().get("results", []) or []:
        title = clean_text(item.get("title"))
        url = item.get("url", "")
        if not title or not url:
            continue
        published = parse_datetime(item.get("page_age") or "")
        source = clean_text((item.get("meta_url") or {}).get("netloc") or "Brave News")
        articles.append(Article(
            id=article_id(url, title),
            title=title,
            description=clean_text(item.get("description") or ""),
            url=url,
            source=source,
            published_at=iso_or_blank(published),
            origin="Brave News",
            chokepoint=chokepoint.name,
        ))
    return articles


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


def google_query(chokepoint: Chokepoint, days: int) -> str:
    aliases = " OR ".join(f'"{alias}"' for alias in chokepoint.aliases[:3])
    return (
        f"({aliases}) "
        '(shipping OR maritime OR freight OR vessel OR cargo OR commodities OR "raw materials" '
        "OR port OR congestion OR rerouting OR disruption OR blockage OR drought OR attack) "
        f"when:{days}d"
    )


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
    context_terms = tuple(t.lower() for t in CHOKEPOINT_CONTEXT_TERMS.get(chokepoint.name, ()))
    trade_terms = tuple(term.lower() for term in GENERAL_TRADE_TERMS)
    matches: list[Article] = []
    for article in curated_articles:
        title = article.title.lower()
        full_text = f"{article.title} {article.description}".lower()
        title_alias_hit = any(alias in title for alias in aliases)
        full_alias_hit = any(alias in full_text for alias in aliases)
        context_hit = any(term in full_text for term in context_terms)
        trade_hit = any(term in full_text for term in trade_terms)
        # Accept if: alias in title (strong signal), OR context term hit,
        # OR alias anywhere in text + at least one trade term
        if title_alias_hit or context_hit or (full_alias_hit and trade_hit):
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


