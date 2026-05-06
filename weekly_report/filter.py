"""Stage 2: LLM-based filter.

Reads items/<week>.jsonl, sends batches to DeepSeek with the filter prompt,
attaches `score`, `theme`, `oneliner` to each item, writes to
filtered/<week>.jsonl. Idempotent — safe to re-run; will overwrite output.

Heuristic pre-pass (cheap, no LLM): drops obvious noise BEFORE paying for tokens:
- YouTube /shorts/ URLs (almost always noise)
- empty title / link items
- items with paywall stub summaries < 30 chars

Then the LLM scores everything that survived the heuristic pre-pass.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from .llm import CostTracker, chat_json
from .sources import Source
from .storage import (
    FILTERED_DIR,
    ITEMS_DIR,
    append_jsonl,
    read_jsonl,
)


log = logging.getLogger(__name__)


HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "filter.md"


# ---------- heuristic pre-filter ----------


_SHORTS_RE = re.compile(r"youtube\.com/shorts/", re.IGNORECASE)


@dataclass
class HeuristicResult:
    keep: bool
    reason: str  # empty if keep=True; else why dropped


def heuristic_prefilter(item: dict) -> HeuristicResult:
    url = item.get("url") or ""
    title = (item.get("title") or "").strip()
    summary = (item.get("summary") or "").strip()

    if not url or not title:
        return HeuristicResult(False, "empty url/title")
    if _SHORTS_RE.search(url):
        return HeuristicResult(False, "youtube short")
    if title.lower().startswith(("trailer:", "preview:")):
        return HeuristicResult(False, "trailer")
    return HeuristicResult(True, "")


# ---------- LLM batch ----------


# Items per LLM call. DeepSeek context is 64K; ~25 items × ~600 input tokens
# = ~15K input + ~3K output, comfortably under and keeps each call <30s.
BATCH_SIZE = 25

# Truncate per-item summary so prompt stays small
SUMMARY_TRUNC = 600


def _item_for_prompt(item: dict, source: Optional[Source]) -> dict:
    return {
        "id": item["id"],
        "source_id": item["source_id"],
        "source_name": source.name if source else item["source_id"],
        "source_tier": item.get("source_tier", "A"),
        "source_lang": item.get("source_lang", "en"),
        "title": item.get("title", "")[:200],
        "summary": (item.get("summary") or "")[:SUMMARY_TRUNC],
        "url": item.get("url", ""),
    }


def _build_user_msg(batch: list[dict]) -> str:
    return (
        "Score the following items.\n\n"
        f"```json\n{json.dumps(batch, ensure_ascii=False, indent=2)}\n```"
    )


VALID_TRACKS = {"tech", "industry", "noise"}


def filter_batch(
    batch: list[dict], system_prompt: str, tracker: CostTracker
) -> dict[str, dict]:
    """Send one batch to LLM. Returns mapping id -> {track, score, theme, oneliner}."""
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
        track = str(r.get("track", "noise"))
        if track not in VALID_TRACKS:
            track = "noise"
        score = float(r.get("score", 0.0))
        # Force noise -> score 0 for consistency
        if track == "noise":
            score = 0.0
        by_id[str(rid)] = {
            "track": track,
            "score": score,
            "theme": str(r.get("theme", "noise")),
            "oneliner": str(r.get("oneliner", "")).strip(),
        }
    return by_id


# ---------- main entry ----------


def filter_week(
    week_id: str,
    items: list[dict],
    sources: list[Source],
    *,
    keep_threshold: float = 0.5,
    show_progress: bool = True,
) -> tuple[list[dict], CostTracker]:
    """Filter `items` for this week, return enriched list (all items, with score
    fields attached + `kept: bool`) and a CostTracker."""

    src_by_id = {s.id: s for s in sources}
    tracker = CostTracker()
    system = PROMPT_PATH.read_text(encoding="utf-8")

    # heuristic pre-pass
    survivors: list[dict] = []
    pre_dropped: list[dict] = []
    for it in items:
        h = heuristic_prefilter(it)
        if h.keep:
            survivors.append(it)
        else:
            it = dict(it)
            it.update(
                {
                    "track": "noise",
                    "score": 0.0,
                    "theme": "noise",
                    "oneliner": "",
                    "kept": False,
                    "drop_reason": f"heuristic:{h.reason}",
                }
            )
            pre_dropped.append(it)

    if show_progress:
        print(
            f"[filter] week={week_id} input={len(items)} survived_heuristic={len(survivors)} "
            f"pre_dropped={len(pre_dropped)}",
            flush=True,
        )

    # LLM scoring in batches
    enriched: list[dict] = []
    for i in range(0, len(survivors), BATCH_SIZE):
        batch_raw = survivors[i : i + BATCH_SIZE]
        batch_prompt = [_item_for_prompt(it, src_by_id.get(it["source_id"])) for it in batch_raw]
        if show_progress:
            print(
                f"  [filter] batch {i // BATCH_SIZE + 1}/"
                f"{(len(survivors) + BATCH_SIZE - 1) // BATCH_SIZE}  "
                f"({len(batch_raw)} items)…",
                flush=True,
            )
        scores = filter_batch(batch_prompt, system, tracker)
        for it in batch_raw:
            sc = scores.get(it["id"])
            it = dict(it)
            if sc is None:
                it.update(
                    {
                        "track": "noise",
                        "score": 0.0,
                        "theme": "noise",
                        "oneliner": "",
                        "kept": False,
                        "drop_reason": "llm:no-score-returned",
                    }
                )
            else:
                kept = (
                    sc["track"] != "noise"
                    and sc["score"] >= keep_threshold
                )
                drop_reason = ""
                if not kept:
                    if sc["track"] == "noise":
                        drop_reason = "llm:track=noise"
                    else:
                        drop_reason = f"llm:score={sc['score']:.2f}"
                it.update(
                    {
                        "track": sc["track"],
                        "score": sc["score"],
                        "theme": sc["theme"],
                        "oneliner": sc["oneliner"],
                        "kept": kept,
                        "drop_reason": drop_reason,
                    }
                )
            enriched.append(it)

    if show_progress:
        n_kept = sum(1 for it in enriched if it.get("kept"))
        n_tech = sum(1 for it in enriched if it.get("kept") and it.get("track") == "tech")
        n_industry = sum(
            1 for it in enriched if it.get("kept") and it.get("track") == "industry"
        )
        print(
            f"[filter] llm-scored={len(enriched)} kept={n_kept} "
            f"(tech={n_tech} industry={n_industry}) "
            f"({n_kept / max(len(items), 1):.0%} of input) · {tracker.summary()}",
            flush=True,
        )

    # combine, sort by published_at desc
    all_out = enriched + pre_dropped
    all_out.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_out, tracker


def write_filtered(week_id: str, items: list[dict]) -> Path:
    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    path = FILTERED_DIR / f"{week_id}.jsonl"
    if path.exists():
        path.unlink()  # filter is overwriting per run, not appending
    append_jsonl(path, items)
    return path
