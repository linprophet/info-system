"""加载 weekly_paper 的全部源。

两类来源拼起来：

1. **聚合源**（aggregator）：来自 `topics/research-agi/sources.json`。
   覆盖 HF papers weekly / dair_ai newsletter / arxiv categories 等多 lab 横跨源。
   每条带 `topic_tag = "cross"` —— 留给 LLM 在 filter 阶段再分配到具体 topic。

2. **Lab 官方 blog**（per-topic）：从 7 个 topic 的 `orgs.json` 自动展开。
   只取 `verified=true` + 有 `blog_rss` 的 org，每 org 生成 1 个 Source。
   `topic_tag` 自动等于 org 的 parent topic 目录名。

X handle / GitHub org activity / HF org papers 等暂不接入：公共 RSSHub 不可用，
且对 paper 追踪噪声大于信号。后续接 self-hosted RSSHub 或 GitHub releases.atom 时再加。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from weekly_report.sources import REPO_ROOT, Source, _load_topic, load_topic


TOPICS_DIR = REPO_ROOT / "topics"
RESEARCH_AGI_DIR = TOPICS_DIR / "research-agi"


# orgs.json -> Source 转换的 topic 目录列表（与 paths.TOPICS 对齐）
ORG_TOPICS = (
    "agent-harness",
    "agent-rl",
    "image-generation",
    "video-generation",
    "vla-embodied",
    "vlm-llm-posttrain",
    "world-model",
)


def _slugify(s: str) -> str:
    """org name -> kebab-case id 片段。'Physical Intelligence (PI)' -> 'physical-intelligence-pi'."""
    out = []
    prev_dash = True
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def _collect_org_blogs(only_topic: Optional[str]) -> dict[str, dict]:
    """扫 7 个 topic 的 orgs.json，按 blog_rss URL 聚合。

    返回 {url -> {org_name, topics:[t1,t2,...], homepage, group_id}}。
    """
    by_url: dict[str, dict] = {}
    for t in ORG_TOPICS:
        if only_topic and only_topic != t:
            continue
        f = TOPICS_DIR / t / "orgs.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for org in data.get("orgs", []):
            blog = org.get("blog_rss")
            if not blog:
                continue
            entry = by_url.setdefault(
                blog,
                {
                    "name": org["name"],
                    "topics": [],
                    "homepage": org.get("homepage"),
                    "group_id": org.get("group_id", "ORGS"),
                    "notes": org.get("notes", "")[:200],
                },
            )
            if t not in entry["topics"]:
                entry["topics"].append(t)
            # 当首个 org 是非 verified 时也保留；后面如果遇到 verified 同 URL 的，可以更新名字
            if org.get("verified") and org["name"] != entry["name"]:
                # 用更具代表性的（短的）名字
                if len(org["name"]) < len(entry["name"]):
                    entry["name"] = org["name"]
    return by_url


@dataclass
class PaperSourceBundle:
    """所有源的组装结果。"""
    sources: list[Source] = field(default_factory=list)
    by_topic: dict[str, list[Source]] = field(default_factory=dict)


def load_all_paper_sources(only_topic: Optional[str] = None) -> PaperSourceBundle:
    """加载全部 weekly_paper 源。

    only_topic: 若指定，只加载该 topic 的源；'research-agi' 表示只 aggregator，
                'agent-harness' 等表示只该 topic 的 lab blogs。
    """
    bundle = PaperSourceBundle()
    seen_ids: set[str] = set()

    def add(src: Source) -> None:
        if src.id in seen_ids:
            return
        seen_ids.add(src.id)
        bundle.sources.append(src)
        bundle.by_topic.setdefault(src.topic or "cross", []).append(src)

    # 1) aggregator (research-agi/sources.json)
    if only_topic in (None, "research-agi"):
        if (RESEARCH_AGI_DIR / "sources.json").exists():
            _, _, srcs = _load_topic(RESEARCH_AGI_DIR)
            for s in srcs:
                # aggregator 默认 topic="cross"
                s.topic = "cross"
                add(s)

    # 2) 7 topics 的 lab blog（按 URL 去重，跨 topic 的 → topic="cross"）
    blog_map = _collect_org_blogs(only_topic)
    for url, entry in blog_map.items():
        topics = entry["topics"]
        # 跨多 topic 的（OpenAI / Anthropic / DeepMind / HuggingFace blog） → cross
        # 单 topic 的 → 该 topic
        primary_topic = topics[0] if len(topics) == 1 else "cross"
        slug = _slugify(entry["name"])
        sid = f"blog-{slug}"
        # tier: 出现在 ≥3 个 topic 的算"S 级跨域核心"，否则 A
        tier = "S" if len(topics) >= 3 else "A"
        notes = entry["notes"]
        if len(topics) > 1:
            notes = f"cross-topic ({', '.join(topics)}); " + notes
        add(
            Source(
                id=sid,
                name=f"{entry['name']} · Blog",
                group_id=entry["group_id"],
                type="newsletter",
                tier=tier,
                lang="en",
                rss_url=url,
                homepage=entry.get("homepage"),
                notes=notes,
                topic=primary_topic,
            )
        )

    return bundle
