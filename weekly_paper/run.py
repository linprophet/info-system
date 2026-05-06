"""weekly_paper · CLI 入口。

子命令:
    ingest  抓 sources.json + 7 topics 的 verified blog → items/<week>.jsonl
    filter  items -> filtered (LLM topic classifier)
    synth   filtered -> reports/<week>-paper.md
    report  filter + synth 一气呵成
    status  每个源的运行健康度
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from weekly_report.compose import filter_in_week
from weekly_report.ingest.rss import ingest_source
from weekly_report.items import Item
from weekly_report.sources import Source
from weekly_report.storage import (
    SeenIndex,
    SourceState,
    StateFile,
    append_jsonl,
    iso_week_id,
    perf,
    read_jsonl,
    utc_now_iso,
)

from .filter import filter_week, write_filtered
from .ingest.alphaxiv import ingest_alphaxiv
from .ingest.hf_papers import ingest_hf_papers
from .paths import (
    FILTERED_DIR,
    ITEMS_DIR,
    REPORTS_DIR,
    STATE_DIR,
    ensure_data_dirs,
)
from .sources_loader import load_all_paper_sources
from .synthesize import synthesize_week, write_report


log = logging.getLogger("weekly_paper")


def _load_sources(only_topic: Optional[str]) -> list[Source]:
    return load_all_paper_sources(only_topic).sources


def _ingest_one(s: Source, st: SourceState, week_id: str) -> tuple[list[Item], str]:
    """根据 source.type 路由到对应 ingest 适配器。"""
    if s.type == "hf-papers":
        return ingest_hf_papers(s, st, week_id=week_id)
    if s.type == "alphaxiv":
        return ingest_alphaxiv(s, st, week_id=week_id)
    # 默认 RSS / Atom / YouTube
    return ingest_source(s, st)


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
        f"[ingest] week={week_id} sources={len(sources)} workers={args.workers}",
        flush=True,
    )

    total_new = total_dup = total_errs = 0

    def work(s: Source) -> tuple[Source, list[Item], str, float]:
        st = state.get(s.id)
        st.last_run_at = utc_now_iso()
        t0 = perf()
        items, status = _ingest_one(s, st, week_id)
        elapsed = perf() - t0
        st.last_run_status = status
        if status == "fail":
            st.consecutive_failures += 1
        elif status == "ok":
            st.consecutive_failures = 0
        return s, items, status, elapsed

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(work, sources))

    new_items_buf: list[dict] = []
    for s, items, status, elapsed in results:
        st = state.get(s.id)
        new = dup = 0
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
            note = "(no rss yet)"
        elif status == "fail":
            note = f"FAIL {st.last_error[:80]}"
        else:
            note = f"+{new} new / {dup} dup / {len(items)} fetched"
        print(f"  {emoji} {s.id:40s}  {note:55s}  ({elapsed * 1000:5.0f}ms)", flush=True)

    if new_items_buf:
        n_written = append_jsonl(items_path, new_items_buf)
        print(f"\n[ingest] wrote {n_written} new items to {items_path}", flush=True)

    state.save()
    seen.close()

    print(
        f"\n[ingest] summary: +{total_new} new, {total_dup} dup-skip, "
        f"{total_errs} errors, {len(seen)} total seen URLs",
        flush=True,
    )
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    if not items_path.exists():
        print(f"no items file: {items_path}\nhint: run `ingest` first", file=sys.stderr)
        return 2

    sources = _load_sources(args.topic)
    raw = list(read_jsonl(items_path))
    in_window = filter_in_week(raw, week_id)
    if not in_window:
        print(f"no items in week {week_id}", file=sys.stderr)
        return 2

    enriched, _ = filter_week(week_id, in_window, sources, keep_threshold=args.threshold)
    out_path = write_filtered(week_id, enriched)
    n_kept = sum(1 for it in enriched if it.get("kept"))
    print(f"[filter] wrote {len(enriched)} items ({n_kept} kept) to {out_path}", flush=True)
    return 0


def cmd_synth(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    filtered_path = FILTERED_DIR / f"{week_id}.jsonl"
    if not filtered_path.exists():
        print(
            f"no filtered file: {filtered_path}\nhint: run `filter --week {week_id}` first",
            file=sys.stderr,
        )
        return 2

    sources = _load_sources(args.topic)
    items = list(read_jsonl(filtered_path))
    md, t = synthesize_week(week_id, items, sources)
    out = write_report(week_id, md)
    print(f"[synth] wrote {out} ({len(md)} chars) · cost ${t.total_cost:.4f}", flush=True)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """End-to-end (assuming ingest already done): filter then synthesize."""
    ensure_data_dirs()
    week_id = args.week or iso_week_id()
    items_path = ITEMS_DIR / f"{week_id}.jsonl"
    if not items_path.exists():
        print(f"no items file: {items_path}\nhint: run `ingest` first", file=sys.stderr)
        return 2

    sources = _load_sources(args.topic)
    raw = list(read_jsonl(items_path))
    in_window = filter_in_week(raw, week_id)
    if not in_window:
        print(f"no items in week {week_id}", file=sys.stderr)
        return 2

    enriched, t1 = filter_week(week_id, in_window, sources, keep_threshold=args.threshold)
    write_filtered(week_id, enriched)

    md, t2 = synthesize_week(week_id, enriched, sources)
    out = write_report(week_id, md)
    total_cost = t1.total_cost + t2.total_cost
    print(
        f"\n[report] wrote {out}\n"
        f"[report] grand total: in={t1.total_input + t2.total_input} "
        f"out={t1.total_output + t2.total_output} tokens · ${total_cost:.4f}",
        flush=True,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    sources = _load_sources(args.topic)
    state = StateFile(STATE_DIR / "sources.json")
    print(f"{'source':45s}  {'tier':4s} {'topic':18s} {'last_run':24s} {'status':8s} {'fails':5s} {'last_seen':20s}")
    print("-" * 130)
    for s in sources:
        st = state.get(s.id)
        flag = " (disabled)" if s.disabled else ""
        print(
            f"{s.id+flag:45s}  {s.tier:4s} {(s.topic or 'cross'):18s} "
            f"{st.last_run_at[:19] if st.last_run_at else '-':24s} "
            f"{(st.last_run_status or '-'):8s} "
            f"{st.consecutive_failures:5d} "
            f"{st.last_seen_at[:19] if st.last_seen_at else '-':20s}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="weekly_paper")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="抓所有 paper-relevant 源 → items/<week>.jsonl")
    pi.add_argument("--week", help="ISO week id (default: current)")
    pi.add_argument(
        "--topic",
        help="只加载某个 topic 的源 (research-agi / agent-harness / ...)",
    )
    pi.add_argument("--source", help="只抓单个 source id (debug)")
    pi.add_argument("--workers", type=int, default=10)
    pi.set_defaults(func=cmd_ingest)

    pf = sub.add_parser("filter", help="items -> filtered (LLM topic classifier)")
    pf.add_argument("--week")
    pf.add_argument("--topic")
    pf.add_argument("--threshold", type=float, default=0.5)
    pf.set_defaults(func=cmd_filter)

    pn = sub.add_parser("synth", help="filtered -> reports/<week>-paper.md")
    pn.add_argument("--week")
    pn.add_argument("--topic")
    pn.set_defaults(func=cmd_synth)

    pr = sub.add_parser("report", help="filter + synth end-to-end")
    pr.add_argument("--week")
    pr.add_argument("--topic")
    pr.add_argument("--threshold", type=float, default=0.5)
    pr.set_defaults(func=cmd_report)

    ps = sub.add_parser("status", help="show per-source pipeline state")
    ps.add_argument("--topic")
    ps.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
