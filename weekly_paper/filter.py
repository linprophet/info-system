"""weekly_paper · LLM filter (topic classifier + relevance score).

直接复用 weekly_report.filter 的 batching / heuristic 框架，但：
- 系统 prompt 改为 prompts/filter.md（7 topic + noise 分类）
- 输出字段从 {track, score, theme, oneliner} 改为 {topic, score, oneliner}
- kept = (topic != 'noise') and (score >= keep_threshold)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from weekly_report.filter import (
    SUMMARY_TRUNC,
    BATCH_SIZE,
    heuristic_prefilter,
    _build_user_msg,
)
from weekly_report.llm import CostTracker, chat_json
from weekly_report.sources import Source
from weekly_report.storage import append_jsonl

from .paths import FILTERED_DIR, VALID_TOPIC_TAGS


log = logging.getLogger(__name__)


HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "filter.md"


def filter_batch(
    batch: list[dict], system_prompt: str, tracker: CostTracker
) -> dict[str, dict]:
    """Send one batch to LLM. Returns mapping id -> {topic, score, oneliner}."""
    user = _build_user_msg(batch)
    out, _ = chat_json(system_prompt, user, tracker=tracker)
    items = out.get("items") if isinstance(out, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(
            f"LLM returned unexpected shape (no items list). top-level keys: "
            f"{list(out.keys()) if isinstance(out, dict) else type(out).__name__}"
        )
    by_id: dict[str, dict] = {}
    for r in items:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if rid is None:
            continue
        topic = str(r.get("topic", "noise"))
        if topic not in VALID_TOPIC_TAGS:
            topic = "noise"
        score = float(r.get("score", 0.0))
        if topic == "noise":
            score = 0.0
        by_id[str(rid)] = {
            "topic": topic,
            "score": score,
            "oneliner": str(r.get("oneliner", "")).strip(),
        }
    return by_id


def _item_for_filter(item: dict, source: Optional[Source]) -> dict:
    return {
        "id": item["id"],
        "source_id": item["source_id"],
        "source_name": source.name if source else item["source_id"],
        "source_tier": item.get("source_tier", "A"),
        "source_lang": item.get("source_lang", "en"),
        "source_topic": (source.topic if source else "") or "cross",
        "title": item.get("title", "")[:200],
        "url": item.get("url", ""),
        "published_at": item.get("published_at", "")[:10],
        "summary": (item.get("summary") or "")[:SUMMARY_TRUNC],
        "tags": item.get("tags", [])[:6],
        "duration_sec": item.get("duration_sec", 0),
    }


def filter_week(
    week_id: str,
    items: list[dict],
    sources: list[Source],
    *,
    keep_threshold: float = 0.5,
    show_progress: bool = True,
) -> tuple[list[dict], CostTracker]:
    """For one week's items, run heuristic + LLM topic classifier. Returns enriched list."""
    src_by_id = {s.id: s for s in sources}

    # heuristic pre-pass
    survivors: list[dict] = []
    pre_dropped: list[dict] = []
    for it in items:
        h = heuristic_prefilter(it)
        if h.keep:
            survivors.append(it)
        else:
            it = dict(it)
            it.update({
                "topic": "noise",
                "score": 0.0,
                "oneliner": "",
                "kept": False,
                "drop_reason": f"heuristic:{h.reason}",
            })
            pre_dropped.append(it)

    if show_progress:
        print(
            f"[filter] week={week_id} input={len(items)} survived_heuristic="
            f"{len(survivors)} pre_dropped={len(pre_dropped)}",
            flush=True,
        )

    system = PROMPT_PATH.read_text(encoding="utf-8")
    tracker = CostTracker()
    enriched: list[dict] = list(pre_dropped)

    n_batches = (len(survivors) + BATCH_SIZE - 1) // BATCH_SIZE
    for bi in range(n_batches):
        batch_raw = survivors[bi * BATCH_SIZE: (bi + 1) * BATCH_SIZE]
        batch_prompt = [_item_for_filter(it, src_by_id.get(it["source_id"])) for it in batch_raw]
        if show_progress:
            print(
                f"  [filter] batch {bi + 1}/{n_batches}  ({len(batch_raw)} items)…",
                flush=True,
            )
        scores = filter_batch(batch_prompt, system, tracker)
        for it in batch_raw:
            sc = scores.get(it["id"])
            it = dict(it)
            if sc is None:
                it.update({
                    "topic": "noise",
                    "score": 0.0,
                    "oneliner": "",
                    "kept": False,
                    "drop_reason": "llm:no-score-returned",
                })
            else:
                kept = (sc["topic"] != "noise") and (sc["score"] >= keep_threshold)
                drop_reason = ""
                if not kept:
                    if sc["topic"] == "noise":
                        drop_reason = "llm:topic=noise"
                    else:
                        drop_reason = f"llm:score={sc['score']:.2f}"
                it.update({
                    "topic": sc["topic"],
                    "score": sc["score"],
                    "oneliner": sc["oneliner"],
                    "kept": kept,
                    "drop_reason": drop_reason,
                })
            enriched.append(it)

    if show_progress:
        n_kept = sum(1 for it in enriched if it.get("kept"))
        from collections import Counter
        topic_counts = Counter(it.get("topic") for it in enriched if it.get("kept"))
        topics_str = " ".join(f"{t}={n}" for t, n in topic_counts.most_common())
        print(
            f"[filter] llm-scored={len(enriched)} kept={n_kept} ({topics_str}) "
            f"({n_kept / max(len(items), 1):.0%} of input) · {tracker.summary()}",
            flush=True,
        )

    return enriched, tracker


def write_filtered(week_id: str, items: list[dict]) -> Path:
    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    path = FILTERED_DIR / f"{week_id}.jsonl"
    if path.exists():
        path.unlink()
    append_jsonl(path, items)
    return path
