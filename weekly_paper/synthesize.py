"""weekly_paper · LLM synthesize stage.

Input: filtered/<week>.jsonl，items 已带 topic + score + oneliner + kept。
Output: reports/<week>-paper.md (Markdown)，按 7 个 topic 分区，每区一段编辑视角 +
若干条目要点 + 长读 + 编辑总观察。

只用 1 次 LLM 调用：把所有 kept items 一次性丢给 DeepSeek，让它生成完整 markdown。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from weekly_report.compose import _parse_iso  # 仅用于 typing 兼容
from weekly_report.llm import CostTracker, chat_text
from weekly_report.sources import Source
from weekly_report.storage import week_bounds

from .paths import REPORTS_DIR


HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "synthesize.md"

SUMMARY_TRUNC_SYNTH = 800


def _item_for_synth(item: dict, source: Optional[Source]) -> dict:
    return {
        "id": item["id"],
        "source_id": item["source_id"],
        "source_name": source.name if source else item["source_id"],
        "source_tier": item.get("source_tier", "A"),
        "source_lang": item.get("source_lang", "en"),
        "title": item.get("title", "")[:200],
        "url": item.get("url", ""),
        "published_at": item.get("published_at", "")[:10],
        "summary": (item.get("summary") or "")[:SUMMARY_TRUNC_SYNTH],
        "authors": item.get("authors", [])[:8],
        "tags": item.get("tags", [])[:6],
        "score": round(item.get("score", 0.0), 2),
        "topic": item.get("topic", "noise"),
        "oneliner": item.get("oneliner", ""),
    }


def synthesize_week(
    week_id: str,
    items: list[dict],
    sources: list[Source],
    *,
    show_progress: bool = True,
) -> tuple[str, CostTracker]:
    """Generate the final paper-focused weekly markdown."""
    src_by_id = {s.id: s for s in sources}
    kept = [it for it in items if it.get("kept")]
    dropped = [it for it in items if not it.get("kept")]
    n_heur = sum(
        1 for it in dropped if (it.get("drop_reason") or "").startswith("heuristic:")
    )
    n_llm = len(dropped) - n_heur

    if not kept:
        raise RuntimeError(
            f"no kept items for {week_id} — run filter first or lower threshold"
        )

    # 排序：先按 topic（按 paths.TOPICS 顺序），再每 topic 内按 score 降序
    from .paths import TOPICS
    topic_order = {t: i for i, t in enumerate(TOPICS)}
    kept.sort(key=lambda x: (topic_order.get(x.get("topic"), 99), -x.get("score", 0.0)))

    # group counts for prompt context
    from collections import Counter
    topic_counts = Counter(it.get("topic") for it in kept)

    payload = [_item_for_synth(it, src_by_id.get(it["source_id"])) for it in kept]
    start, end = week_bounds(week_id)
    distinct_sources = len({it["source_id"] for it in kept})

    system = PROMPT_PATH.read_text(encoding="utf-8")

    topic_breakdown = "\n".join(
        f"- {t}: {topic_counts.get(t, 0)}" for t in TOPICS if topic_counts.get(t, 0) > 0
    )

    user = (
        f"WEEK_ID: {week_id}\n"
        f"DATE_FROM: {start.date()}\n"
        f"DATE_TO: {end.date()}\n"
        f"N_ITEMS: {len(kept)}\n"
        f"N_SOURCES: {distinct_sources}\n"
        f"N_DROPPED: {len(dropped)}  (= {n_heur} heuristic + {n_llm} LLM-low-score/noise)\n\n"
        f"Items by topic:\n{topic_breakdown}\n\n"
        f"In the '🗑️ 已过滤' section, use the N_DROPPED value verbatim.\n\n"
        f"Items (sorted by topic then score desc):\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )

    if show_progress:
        print(
            f"[synth] week={week_id} kept_items={len(kept)} sources={distinct_sources}…",
            flush=True,
        )

    tracker = CostTracker()
    md, _ = chat_text(system, user, temperature=0.3, tracker=tracker)

    if show_progress:
        print(f"[synth] {tracker.summary()}", flush=True)

    return md.strip() + "\n", tracker


def write_report(week_id: str, md: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{week_id}-paper.md"
    path.write_text(md, encoding="utf-8")
    return path
