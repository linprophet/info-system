"""CLI entry for weekly_report.

Commands:
    ingest      fetch all sources -> items/<week>.jsonl       (no LLM)
    preview     items/<week>.jsonl -> reports/<week>-preview.md (no LLM)
    filter      items/<week>.jsonl -> filtered/<week>.jsonl    (LLM, cheap)
    synth       filtered/<week>.jsonl -> reports/<week>.md     (LLM, strong)
    report      filter + synth in one go
    status      show per-source pipeline state

Each stage's output is a checkpoint — re-running synth doesn't re-run filter,
re-running filter doesn't re-run ingest. Pipeline state under weekly_report/data/.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .compose import compose_preview_md, filter_in_week, write_preview
from .filter import filter_week, write_filtered
from .ingest.rss import ingest_source
from .ingest.web_scrape import ingest_scrape
from .items import Item
from .sources import Source, load_all_industry_topics, load_topic
from .storage import (
    FILTERED_DIR,
    ITEMS_DIR,
    REPORTS_DIR,
    STATE_DIR,
    SeenIndex,
    StateFile,
    append_jsonl,
    ensure_data_dirs,
    iso_week_id,
    perf,
    read_jsonl,
    utc_now_iso,
)
from .synthesize import synthesize_week, write_report


log = logging.getLogger("weekly_report")


# ---------- helpers ----------


def _load_sources(topic: Optional[str]) -> list[Source]:
    if topic:
        _, sources = load_topic(topic)
    else:
        _, sources = load_all_industry_topics()
    return sources


def _load_groups(topic: Optional[str]):
    from .sources import load_all_industry_topics, load_topic

    if topic:
        groups, _ = load_topic(topic)
    else:
        groups, _ = load_all_industry_topics()
    return groups


# ---------- ingest ----------


def cmd_ingest(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    sources = _load_sources(args.topic)
    if args.source:
        sources = [s for s in sources if s.id == args.source]
        if not sources:
            print(f"source not found: {args.source}", file=sys.stderr)
            return 2

    n_disabled = sum(1 for s in sources if s.disabled)
    sources = [s for s in sources if not s.disabled]
    if n_disabled and not args.source:
        print(f"[ingest] skipping {n_disabled} disabled source(s)", flush=True)

    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    state = StateFile(STATE_DIR / "sources.json")
    seen = SeenIndex(STATE_DIR / "seen.jsonl")

    print(
        f"[ingest] week={week_id} sources={len(sources)} "
        f"items_path={items_path.relative_to(items_path.parent.parent.parent)} "
        f"workers={args.workers}",
        flush=True,
    )

    total_new = 0
    total_dup = 0
    total_errs = 0

    def work(s: Source) -> tuple[Source, list[Item], str, float]:
        st = state.get(s.id)
        st.last_run_at = utc_now_iso()
        t0 = perf()
        if s.type == "scrape":
            items, status = ingest_scrape(s, st)
        else:
            items, status = ingest_source(s, st)
        elapsed = perf() - t0
        st.last_run_status = status
        if status == "fail":
            st.consecutive_failures += 1
        elif status == "ok":
            st.consecutive_failures = 0
        return s, items, status, elapsed

    # fetches in parallel; writes serialized below
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(work, sources))

    new_items_buf: list[dict] = []
    for s, items, status, elapsed in results:
        st = state.get(s.id)
        new = 0
        dup = 0
        for it in items:
            if it.id in seen:
                dup += 1
                continue
            seen.add(it.id, s.id)
            new_items_buf.append(it.to_dict())
            new += 1
            if it.published_at and it.published_at > st.last_seen_at:
                st.last_seen_at = it.published_at
                st.last_seen_url = it.url
        st.items_ingested_total += new

        total_new += new
        total_dup += dup
        if status not in ("ok", "skip:no-feed-url"):
            total_errs += 1

        emoji = {"ok": "✓", "fail": "✗"}.get(status, "·")
        if status == "skip:no-feed-url":
            note = "(no rss yet — Step 2)"
        elif status == "fail":
            note = f"FAIL {st.last_error[:80]}"
        else:
            note = f"+{new} new / {dup} dup / {len(items)} fetched"
        print(
            f"  {emoji} {s.id:30s}  {note:55s}  ({elapsed * 1000:5.0f}ms)",
            flush=True,
        )

    if new_items_buf:
        n_written = append_jsonl(items_path, new_items_buf)
        print(
            f"\n[ingest] wrote {n_written} new items to {items_path}", flush=True
        )

    state.save()
    seen.close()

    print(
        f"\n[ingest] summary: +{total_new} new, {total_dup} dup-skip, "
        f"{total_errs} errors, {len(seen)} total seen URLs",
        flush=True,
    )
    return 0


# ---------- preview ----------


def cmd_preview(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    if not items_path.exists():
        print(
            f"no items file: {items_path}\n"
            f"hint: run `python -m weekly_report.run ingest --week {week_id}` first",
            file=sys.stderr,
        )
        return 2

    sources = _load_sources(args.topic)
    groups = _load_groups(args.topic)

    raw = list(read_jsonl(items_path))
    in_window = filter_in_week(raw, week_id) if not args.all_items else raw

    print(
        f"[preview] week={week_id} items_in_file={len(raw)} in_window={len(in_window)}",
        flush=True,
    )

    md = compose_preview_md(week_id, in_window, sources, groups)
    out = write_preview(week_id, md)
    print(f"[preview] wrote {out}", flush=True)
    return 0


# ---------- filter (LLM stage 2) ----------


def cmd_filter(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    if not items_path.exists():
        print(
            f"no items file: {items_path}\n"
            f"hint: run `python -m weekly_report.run ingest --week {week_id}` first",
            file=sys.stderr,
        )
        return 2

    sources = _load_sources(args.topic)
    raw = list(read_jsonl(items_path))
    in_window = filter_in_week(raw, week_id)
    if not in_window:
        print(f"no items in week {week_id}", file=sys.stderr)
        return 2

    enriched, _ = filter_week(
        week_id,
        in_window,
        sources,
        keep_threshold=args.threshold,
    )
    out_path = write_filtered(week_id, enriched)
    n_kept = sum(1 for it in enriched if it.get("kept"))
    print(
        f"[filter] wrote {len(enriched)} items ({n_kept} kept) to {out_path}",
        flush=True,
    )
    return 0


# ---------- synth (LLM stage 3) ----------


def _resolve_tracks(arg: str) -> list[str]:
    if arg == "both":
        return ["tech", "industry"]
    return [arg]


def cmd_synth(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    filtered_path = FILTERED_DIR / f"{week_id}.jsonl"
    if not filtered_path.exists():
        print(
            f"no filtered file: {filtered_path}\n"
            f"hint: run `python -m weekly_report.run filter --week {week_id}` first",
            file=sys.stderr,
        )
        return 2

    sources = _load_sources(args.topic)
    items = list(read_jsonl(filtered_path))

    total_cost = 0.0
    for track in _resolve_tracks(args.track):
        try:
            md, t = synthesize_week(week_id, items, sources, track=track)
        except RuntimeError as e:
            print(f"[synth/{track}] skipped: {e}", flush=True)
            continue
        out = write_report(week_id, md, track=track)
        print(f"[synth/{track}] wrote {out} ({len(md)} chars)", flush=True)
        total_cost += t.total_cost
    print(f"[synth] grand total cost: ${total_cost:.4f}", flush=True)
    return 0


# ---------- report (filter + synth in one shot) ----------


def cmd_report(args: argparse.Namespace) -> int:
    """End-to-end (assuming ingest already done): filter then synthesize."""
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    if not items_path.exists():
        print(
            f"no items file: {items_path}\nhint: run `ingest` first",
            file=sys.stderr,
        )
        return 2

    sources = _load_sources(args.topic)
    raw = list(read_jsonl(items_path))
    in_window = filter_in_week(raw, week_id)
    if not in_window:
        print(f"no items in week {week_id}", file=sys.stderr)
        return 2

    enriched, t1 = filter_week(
        week_id, in_window, sources, keep_threshold=args.threshold
    )
    write_filtered(week_id, enriched)

    total_cost = t1.total_cost
    total_in = t1.total_input
    total_out = t1.total_output

    for track in _resolve_tracks(args.track):
        try:
            md, t2 = synthesize_week(week_id, enriched, sources, track=track)
        except RuntimeError as e:
            print(f"[report/{track}] skipped: {e}", flush=True)
            continue
        out = write_report(week_id, md, track=track)
        print(f"[report/{track}] wrote {out}", flush=True)
        total_cost += t2.total_cost
        total_in += t2.total_input
        total_out += t2.total_output

    print(
        f"\n[report] grand total: in={total_in} out={total_out} tokens · ${total_cost:.4f}",
        flush=True,
    )
    return 0


# ---------- status ----------


def cmd_status(args: argparse.Namespace) -> int:
    state = StateFile(STATE_DIR / "sources.json")
    sources = {s.id: s for s in _load_sources(args.topic)}
    rows = []
    for st in state.all():
        s = sources.get(st.source_id)
        if not s:
            continue
        rows.append(
            (
                s.tier,
                s.name,
                st.last_run_status or "—",
                st.last_seen_at[:10] if st.last_seen_at else "—",
                st.items_ingested_total,
                st.consecutive_failures,
            )
        )
    rows.sort(key=lambda r: ({"S": 0, "A": 1, "B": 2}.get(r[0], 9), r[1]))

    print(
        f"{'TIER':4s}  {'SOURCE':35s}  {'STATUS':10s}  {'LAST SEEN':12s}  {'TOTAL':>6s}  {'FAILS':>6s}"
    )
    print("-" * 90)
    for tier, name, status, last_seen, total, fails in rows:
        print(
            f"{tier:4s}  {name[:35]:35s}  {status:10s}  {last_seen:12s}  {total:>6d}  {fails:>6d}"
        )
    return 0


# ---------- main ----------


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="weekly_report — fetch sources and compose weekly preview/report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="fetch all sources for a week into items/<week>.jsonl")
    pi.add_argument("--week", help="ISO week id, e.g. 2026-W18 (default: current)")
    pi.add_argument("--topic", help="only this topic (default: all)")
    pi.add_argument("--source", help="only this source id (for debugging)")
    pi.add_argument("--workers", type=int, default=8)
    pi.set_defaults(func=cmd_ingest)

    pp = sub.add_parser("preview", help="compose markdown preview for a week (no LLM)")
    pp.add_argument("--week", help="ISO week id (default: current)")
    pp.add_argument("--topic", help="only this topic (default: all)")
    pp.add_argument(
        "--all-items",
        action="store_true",
        help="don't filter to the week window (include all items in the file)",
    )
    pp.set_defaults(func=cmd_preview)

    pf = sub.add_parser("filter", help="LLM-score items -> filtered/<week>.jsonl")
    pf.add_argument("--week", help="ISO week id (default: current)")
    pf.add_argument("--topic", help="only this topic (default: all)")
    pf.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="keep items with score >= threshold (default 0.5)",
    )
    pf.set_defaults(func=cmd_filter)

    pn = sub.add_parser("synth", help="synthesize final markdown from filtered/<week>.jsonl")
    pn.add_argument("--week", help="ISO week id (default: current)")
    pn.add_argument("--topic", help="only this topic (default: all)")
    pn.add_argument(
        "--track",
        choices=["tech", "industry", "both"],
        default="both",
        help="which report(s) to write (default: both)",
    )
    pn.set_defaults(func=cmd_synth)

    pr = sub.add_parser("report", help="filter + synth end-to-end")
    pr.add_argument("--week", help="ISO week id (default: current)")
    pr.add_argument("--topic", help="only this topic (default: all)")
    pr.add_argument("--threshold", type=float, default=0.5)
    pr.add_argument(
        "--track",
        choices=["tech", "industry", "both"],
        default="both",
        help="which report(s) to write (default: both)",
    )
    pr.set_defaults(func=cmd_report)

    ps = sub.add_parser("status", help="show per-source pipeline state")
    ps.add_argument("--topic", help="only this topic (default: all)")
    ps.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
