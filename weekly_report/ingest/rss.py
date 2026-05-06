"""RSS / Atom / YouTube ingest adapter.

For each Source, returns a list of Item dicts. Uses feedparser (lenient
parser that handles both RSS and Atom).

YouTube channels: if `youtube_channel_id` is missing but `youtube_handle`
is present, we resolve handle -> channel_id by scraping the channel page
once and caching back into state (so future runs skip the resolve).
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import feedparser

from ..items import INLINE_TEXT_MAX_CHARS, Item, url_hash
from ..sources import Source
from ..storage import SourceState, utc_now_iso


log = logging.getLogger(__name__)


HTTP_TIMEOUT = 20.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ---------- YouTube handle -> channel_id ----------


YT_HANDLE_PATTERNS = [
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{20,})"'),
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{20,})"'),
    re.compile(
        r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{20,})"'
    ),
    re.compile(r'"externalChannelId"\s*:\s*"(UC[\w-]{20,})"'),
]


def resolve_youtube_channel_id(handle: str) -> Optional[str]:
    """Scrape https://www.youtube.com/@<handle> and extract channel_id.

    Returns None if extraction fails (don't raise — caller decides).
    """
    handle = handle.lstrip("@")
    encoded = urllib.parse.quote(handle, safe="")
    url = f"https://www.youtube.com/@{encoded}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.warning("yt resolve fail for @%s: %s", handle, e)
        return None
    for pat in YT_HANDLE_PATTERNS:
        m = pat.search(body)
        if m:
            return m.group(1)
    return None


def youtube_rss_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


# ---------- feed -> items ----------


def _parse_dt(entry: dict) -> str:
    """Pick the best timestamp from a feedparser entry. Returns ISO UTC string."""
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        v = entry.get(k)
        if v:
            try:
                return datetime(*v[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return ""


_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _clean_html(s: str) -> str:
    if not s:
        return ""
    s = _HTML_TAG.sub(" ", s)
    s = html.unescape(s)
    return _WHITESPACE.sub(" ", s).strip()


def _entry_to_item(source: Source, entry: dict) -> Optional[Item]:
    url = entry.get("link") or entry.get("id") or ""
    if not url:
        return None
    title = _clean_html(entry.get("title", "")).strip() or "(untitled)"

    # Try to grab a body / summary
    body_html = ""
    if "content" in entry and entry["content"]:
        body_html = entry["content"][0].get("value", "")
    if not body_html:
        body_html = entry.get("summary", "") or entry.get("description", "") or ""
    body = _clean_html(body_html)
    summary = body[: INLINE_TEXT_MAX_CHARS // 4]
    raw_text = body if len(body) <= INLINE_TEXT_MAX_CHARS else ""

    # Authors
    authors: list[str] = []
    if "authors" in entry:
        authors = [a.get("name", "") for a in entry["authors"] if a.get("name")]
    elif entry.get("author"):
        authors = [str(entry["author"])]

    # Tags
    tags: list[str] = []
    for t in entry.get("tags") or []:
        term = (t.get("term") or "").strip() if isinstance(t, dict) else str(t)
        if term:
            tags.append(term)

    # Duration (yt:duration in YouTube feeds, itunes_duration in podcasts)
    duration = 0
    if entry.get("itunes_duration"):
        try:
            parts = [int(p) for p in str(entry["itunes_duration"]).split(":")]
            while len(parts) < 3:
                parts.insert(0, 0)
            duration = parts[0] * 3600 + parts[1] * 60 + parts[2]
        except Exception:
            pass

    return Item(
        id=url_hash(url),
        source_id=source.id,
        source_type=source.type,
        source_tier=source.tier,
        source_lang=source.lang,
        title=title,
        url=url,
        published_at=_parse_dt(entry),
        fetched_at=utc_now_iso(),
        summary=summary,
        raw_text=raw_text,
        authors=authors,
        tags=tags,
        duration_sec=duration,
    )


# ---------- public adapter ----------


def fetch_url(url: str) -> Optional[bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def determine_feed_url(source: Source, state: SourceState) -> Optional[str]:
    """Return the actual URL to GET for this source, resolving YouTube handles
    if needed. Mutates `state.youtube_channel_id` if a fresh resolve happens."""
    if source.rss_url:
        return source.rss_url
    if source.type == "youtube":
        cid = source.youtube_channel_id or state.youtube_channel_id
        if not cid and source.youtube_handle:
            cid = resolve_youtube_channel_id(source.youtube_handle)
            if cid:
                state.youtube_channel_id = cid
        if cid:
            return youtube_rss_url(cid)
    if source.rsshub_path:
        # Defer until we wire up RSSHub instance config
        return None
    return None


def ingest_source(source: Source, state: SourceState) -> tuple[list[Item], str]:
    """Fetch + parse one source. Returns (items, status).

    status is one of: 'ok' | 'fail' | 'skip:no-feed-url'
    """
    feed_url = determine_feed_url(source, state)
    if not feed_url:
        return [], "skip:no-feed-url"

    try:
        raw = fetch_url(feed_url)
    except Exception as e:
        log.warning("fetch fail %s: %s", source.id, e)
        state.last_error = f"fetch: {type(e).__name__}: {e}"
        return [], "fail"

    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        log.warning("parse fail %s: %s", source.id, parsed.bozo_exception)
        state.last_error = f"parse: {parsed.bozo_exception}"
        return [], "fail"

    items: list[Item] = []
    for e in parsed.entries:
        try:
            it = _entry_to_item(source, e)
            if it:
                items.append(it)
        except Exception as ex:
            log.warning("entry parse skip %s: %s", source.id, ex)

    state.last_error = ""
    return items, "ok"
