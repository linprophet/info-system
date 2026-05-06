"""Load source definitions from topics/<topic>/sources.json files.

Schema (see topics/industry-agi/sources.json for the canonical example).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


HERE = Path(__file__).parent
REPO_ROOT = HERE.parent
TOPICS_DIR = REPO_ROOT / "topics"


VALID_TYPES = {
    "newsletter", "youtube", "podcast", "wechat", "x", "rss",
    "hf-papers", "alphaxiv", "arxiv",  # weekly_paper aggregator types
    "scrape",  # generic HTML scrape: index page + article URL prefix → custom adapter
}
VALID_TIERS = {"S", "A", "B"}


@dataclass
class Group:
    id: str
    name: str
    subtitle: str = ""


@dataclass
class Source:
    id: str
    name: str
    group_id: str
    type: str
    tier: str = "A"
    lang: str = "en"
    rss_url: Optional[str] = None
    youtube_handle: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    rsshub_path: Optional[str] = None
    homepage: Optional[str] = None
    # type=scrape only: list-page URL + article-link prefix used to filter index links
    index_url: Optional[str] = None
    article_url_prefix: Optional[str] = None
    notes: str = ""
    weight: float = 1.0
    topic: str = ""
    disabled: bool = False  # if True, skipped during ingest

    @property
    def has_direct_feed(self) -> bool:
        return bool(self.rss_url) or bool(self.youtube_channel_id) or bool(
            self.youtube_handle
        )


def _load_topic(topic_dir: Path) -> tuple[dict[str, Any], list[Group], list[Source]]:
    sj = topic_dir / "sources.json"
    if not sj.exists():
        return {}, [], []
    data = json.loads(sj.read_text(encoding="utf-8"))
    groups = [
        Group(id=g["id"], name=g["name"], subtitle=g.get("subtitle", ""))
        for g in data.get("groups", [])
    ]
    sources: list[Source] = []
    seen_ids: set[str] = set()
    for raw in data.get("sources", []):
        sid = raw["id"]
        if sid in seen_ids:
            raise ValueError(f"duplicate source id in {sj}: {sid}")
        seen_ids.add(sid)
        if raw["type"] not in VALID_TYPES:
            raise ValueError(f"{sj}:{sid}: bad type {raw['type']!r}")
        if raw.get("tier", "A") not in VALID_TIERS:
            raise ValueError(f"{sj}:{sid}: bad tier {raw.get('tier')!r}")
        sources.append(
            Source(
                id=sid,
                name=raw["name"],
                group_id=raw["group_id"],
                type=raw["type"],
                tier=raw.get("tier", "A"),
                lang=raw.get("lang", "en"),
                rss_url=raw.get("rss_url"),
                youtube_handle=raw.get("youtube_handle"),
                youtube_channel_id=raw.get("youtube_channel_id"),
                rsshub_path=raw.get("rsshub_path"),
                homepage=raw.get("homepage"),
                index_url=raw.get("index_url"),
                article_url_prefix=raw.get("article_url_prefix"),
                notes=raw.get("notes", ""),
                weight=float(raw.get("weight", 1.0)),
                topic=data.get("topic", topic_dir.name),
                disabled=bool(raw.get("disabled", False)),
            )
        )
    return data, groups, sources


def load_topic(topic: str) -> tuple[list[Group], list[Source]]:
    """Load groups + sources from a single topic dir."""
    _, groups, sources = _load_topic(TOPICS_DIR / topic)
    return groups, sources


def load_all_industry_topics() -> tuple[list[Group], list[Source]]:
    """Load every topic dir that has sources.json (NOT scholars.json/orgs.json)."""
    all_groups: list[Group] = []
    all_sources: list[Source] = []
    seen_groups: set[str] = set()
    for td in sorted(TOPICS_DIR.iterdir()):
        if not td.is_dir():
            continue
        if not (td / "sources.json").exists():
            continue
        _, groups, sources = _load_topic(td)
        for g in groups:
            if g.id not in seen_groups:
                all_groups.append(g)
                seen_groups.add(g.id)
        all_sources.extend(sources)
    return all_groups, all_sources
