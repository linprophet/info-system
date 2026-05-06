"""Canonical item schema shared across stages.

One item = one piece of content (article, podcast episode, video, post).
Stored as one JSON object per line in items/<week>.jsonl.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# Tracking params we strip during normalization (don't change content identity)
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
    "_hsenc",
    "_hsmi",
    "hsCtaTracking",
    "feature",  # youtube
    "si",  # youtube share id
    "pp",  # youtube
}


def url_hash(url: str) -> str:
    """Stable short hash for url-based dedup. Normalizes:
    - lowercase scheme + netloc (path/query stay case-sensitive)
    - drop fragment
    - drop tracking params (utm_*, fbclid, youtube si/pp/feature, ...)
    - sort remaining query params (?b=2&a=1 -> ?a=1&b=2)
    - strip trailing slash from path

    Critically: KEEP meaningful query params like ?v= for youtube videos.
    """
    if not url:
        return ""
    try:
        sp = urlsplit(url.strip())
    except Exception:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    scheme = sp.scheme.lower() or "http"
    netloc = sp.netloc.lower()
    path = sp.path.rstrip("/") if sp.path != "/" else "/"

    # filter + sort query
    pairs = [
        (k, v) for k, v in parse_qsl(sp.query, keep_blank_values=False)
        if k not in _TRACKING_PARAMS
    ]
    pairs.sort()
    query = urlencode(pairs)

    norm = urlunsplit((scheme, netloc, path, query, ""))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


@dataclass
class Item:
    id: str  # = url_hash(url) typically
    source_id: str
    source_type: str  # newsletter | youtube | podcast | wechat | x | rss
    source_tier: str
    source_lang: str
    title: str
    url: str
    published_at: str  # ISO timestamp, UTC
    fetched_at: str  # ISO timestamp, UTC
    summary: str = ""  # short blurb from feed (NOT LLM-generated)
    raw_text: str = ""  # full text if cheap to inline (substack post body)
    raw_text_ref: str = ""  # path to cache/ file if too big to inline
    transcript_ref: str = ""  # path to cache/transcripts/<id>.json (later)
    duration_sec: int = 0  # for audio/video
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Heuristic preview length we keep inline in the JSONL
INLINE_TEXT_MAX_CHARS = 8000
