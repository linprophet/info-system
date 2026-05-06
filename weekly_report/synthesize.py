"""Stage 3: LLM synthesis. Take filtered items (kept=True) and write the
final markdown weekly report.

Two tracks:
- `tech` -> reports/<week>-tech.md, using prompts/synthesize-tech.md
- `industry` -> reports/<week>-industry.md, using prompts/synthesize-industry.md

Single LLM call per track (kept items typically ≤ 50 each, fits comfortably
in DeepSeek context).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .compose import _parse_iso
from .llm import CostTracker, chat_text
from .sources import Source
from .storage import REPORTS_DIR, week_bounds


HERE = Path(__file__).parent
PROMPT_DIR = HERE / "prompts"

PROMPT_PATHS = {
    "tech": PROMPT_DIR / "synthesize-tech.md",
    "industry": PROMPT_DIR / "synthesize-industry.md",
}

# Per-item character budget in synth payload — keep prompt manageable
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
        "score": round(item.get("score", 0.0), 2),
        "theme": item.get("theme", ""),
        "oneliner": item.get("oneliner", ""),
        "duration_sec": item.get("duration_sec", 0),
    }


def synthesize_week(
    week_id: str,
    items: list[dict],
    sources: list[Source],
    *,
    track: str = "tech",
    show_progress: bool = True,
) -> tuple[str, CostTracker]:
    """Generate the final markdown weekly report for one track ('tech' or 'industry').

    Expects items already filtered (with track + score + kept fields). Only items
    matching `track` AND kept=True are sent to LLM. Items in the OTHER kept track
    are reported as 'diverted' rather than 'dropped'.
    """
    if track not in PROMPT_PATHS:
        raise ValueError(f"unknown track: {track!r}, must be one of {list(PROMPT_PATHS)}")

    src_by_id = {s.id: s for s in sources}
    in_track = [it for it in items if it.get("kept") and it.get("track") == track]
    other_track = "industry" if track == "tech" else "tech"
    diverted = [
        it for it in items if it.get("kept") and it.get("track") == other_track
    ]
    dropped = [it for it in items if not it.get("kept")]
    n_heur = sum(
        1 for it in dropped if (it.get("drop_reason") or "").startswith("heuristic:")
    )
    n_llm = len(dropped) - n_heur

    if not in_track:
        raise RuntimeError(
            f"no kept items in track={track!r} for {week_id} — "
            "lower --threshold or check filter output"
        )

    in_track.sort(key=lambda x: -x.get("score", 0.0))

    payload = [_item_for_synth(it, src_by_id.get(it["source_id"])) for it in in_track]
    start, end = week_bounds(week_id)
    distinct_sources = len({it["source_id"] for it in in_track})

    system = PROMPT_PATHS[track].read_text(encoding="utf-8")
    diverted_var = "N_INDUSTRY" if track == "tech" else "N_TECH"
    user = (
        f"WEEK_ID: {week_id}\n"
        f"DATE_FROM: {start.date()}\n"
        f"DATE_TO: {(end.date())}\n"
        f"N_ITEMS: {len(in_track)}\n"
        f"N_SOURCES: {distinct_sources}\n"
        f"N_DROPPED: {len(dropped)}  (= {n_heur} heuristic + {n_llm} LLM-low-score/noise)\n"
        f"{diverted_var}: {len(diverted)}  (kept items diverted to the other track)\n\n"
        f"Use N_DROPPED and {diverted_var} verbatim in the '🗑️ 已分流 / 过滤' section.\n\n"
        f"Items (sorted by score desc):\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )

    if show_progress:
        print(
            f"[synth/{track}] week={week_id} kept_items={len(in_track)} "
            f"sources={distinct_sources}…",
            flush=True,
        )

    tracker = CostTracker()
    md, _ = chat_text(system, user, temperature=0.3, tracker=tracker)

    if show_progress:
        print(f"[synth/{track}] {tracker.summary()}", flush=True)

    return md.strip() + "\n", tracker


def write_report(week_id: str, md: str, track: str = "tech") -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{week_id}-{track}.md"
    path.write_text(md, encoding="utf-8")
    return path
