#!/usr/bin/env python3
"""Build subscription feeds (OPML / JSON / Markdown) for each topic.

Project layout (one folder per topic):

    info_system/
    ├── generate_feeds.py
    └── topics/
        ├── image-generation/
        │   ├── scholars.json
        │   ├── orgs.json          # optional
        │   └── out/               # generated artifacts
        ├── video-generation/
        ├── world-model/
        ├── agent-rl/
        ├── vla-embodied/
        ├── vlm-llm-posttrain/
        └── agent-harness/

Usage:
    python generate_feeds.py                          # all topics, default RSSHub
    python generate_feeds.py --topic vla-embodied     # one topic
    python generate_feeds.py --instance http://localhost:1200
    python generate_feeds.py --report-only            # only coverage reports
    python generate_feeds.py --merge                  # also write a combined OPML at out/all.opml

Outputs (per topic, into topics/<topic>/out/):
    feeds.opml              # universal RSS reader import
    feeds-x.json            # follow-builders compatible X handle list
    feeds-scholars.json     # Google Scholar profile list (only if scholars.json present)
    feeds-orgs.json         # Org list (only if orgs.json present)
    feeds-flat.tsv          # one wide table for Excel/Numbers
    coverage-report.md      # field coverage + missing checklist
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote


HERE = Path(__file__).parent
TOPICS_DIR = HERE / "topics"
COMBINED_OUT = HERE / "out"


# ---------- IO ----------


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def discover_topics(topics_dir: Path) -> list[Path]:
    """Return sorted list of topic dirs that contain scholars.json or orgs.json."""
    if not topics_dir.exists():
        return []
    out: list[Path] = []
    for p in sorted(topics_dir.iterdir()):
        if not p.is_dir():
            continue
        if (p / "scholars.json").exists() or (p / "orgs.json").exists():
            out.append(p)
    return out


# ---------- URL builders ----------


def build_scholar_urls(scholar: dict[str, Any], instance: str) -> dict[str, str | None]:
    sid = scholar.get("scholar_id")
    handle = scholar.get("x_handle")
    return {
        "scholar_html": (
            f"https://scholar.google.com/citations?user={sid}&hl=en" if sid else None
        ),
        "scholar_rss": f"{instance}/google/citations/{sid}" if sid else None,
        "x_html": f"https://x.com/{handle}" if handle else None,
        "x_rss": (
            f"{instance}/twitter/user/{handle}?excludeReplies=1&includeRts=0"
            if handle
            else None
        ),
        "x_rss_alt_nitter": (
            f"https://nitter.privacydev.net/{handle}/rss" if handle else None
        ),
        "github_html": (
            f"https://github.com/{scholar['github']}" if scholar.get("github") else None
        ),
        "search_hint_scholar": (
            f"https://www.google.com/search?q={quote(scholar['name'] + ' Google Scholar')}"
            if not sid
            else None
        ),
        "search_hint_x": (
            f"https://x.com/search?q={quote(scholar['name'])}&src=typed_query&f=user"
            if not handle
            else None
        ),
    }


def build_org_urls(org: dict[str, Any], instance: str) -> dict[str, str | None]:
    handle = org.get("x_handle")
    blog_rss = org.get("blog_rss")
    gh_org = org.get("github_org")
    hf_org = org.get("huggingface_org")
    return {
        "x_html": f"https://x.com/{handle}" if handle else None,
        "x_rss": (
            f"{instance}/twitter/user/{handle}?excludeReplies=1&includeRts=0"
            if handle
            else None
        ),
        "x_rss_alt_nitter": (
            f"https://nitter.privacydev.net/{handle}/rss" if handle else None
        ),
        "blog_rss": blog_rss,
        # GitHub organization activity feed (公开事件，含新 repo / star / commit)
        "github_org_html": f"https://github.com/{gh_org}" if gh_org else None,
        "github_org_rss": f"https://github.com/{gh_org}.atom" if gh_org else None,
        # Hugging Face org papers feed via RSSHub
        "hf_org_html": f"https://huggingface.co/{hf_org}" if hf_org else None,
        "hf_org_rss": (
            f"{instance}/huggingface/papers/{hf_org}" if hf_org else None
        ),
        "search_hint_x": (
            f"https://x.com/search?q={quote(org['name'])}&src=typed_query&f=user"
            if not handle
            else None
        ),
    }


# ---------- OPML ----------


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def opml_outline(title: str, xml_url: str, html_url: str) -> str:
    return (
        f'    <outline type="rss" text="{esc(title)}" title="{esc(title)}" '
        f'xmlUrl="{esc(xml_url)}" htmlUrl="{esc(html_url)}" />'
    )


def write_opml(data: dict[str, Any], instance: str, out: Path) -> int:
    """Write a per-topic OPML containing every available feed.

    Returns the number of feed entries written (used for stats).
    """
    groups = {g["id"]: g for g in data.get("groups", [])}
    bucket: dict[str, list[str]] = {gid: [] for gid in groups}

    # ---- scholars ----
    for s in data.get("scholars", []) or []:
        urls = build_scholar_urls(s, instance)
        gid = s["group_id"]
        if urls["scholar_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{s['name']} · Scholar",
                    urls["scholar_rss"],
                    urls["scholar_html"] or "",
                )
            )
        if urls["x_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{s['name']} · X (@{s['x_handle']})",
                    urls["x_rss"],
                    urls["x_html"] or "",
                )
            )

    # ---- orgs ----
    for o in data.get("orgs", []) or []:
        urls = build_org_urls(o, instance)
        gid = o["group_id"]
        if urls["blog_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{o['name']} · Blog",
                    urls["blog_rss"],
                    o.get("homepage") or "",
                )
            )
        if urls["x_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{o['name']} · X (@{o['x_handle']})",
                    urls["x_rss"],
                    urls["x_html"] or "",
                )
            )
        if urls["github_org_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{o['name']} · GitHub org",
                    urls["github_org_rss"],
                    urls["github_org_html"] or "",
                )
            )
        if urls["hf_org_rss"]:
            bucket.setdefault(gid, []).append(
                opml_outline(
                    f"{o['name']} · HuggingFace papers",
                    urls["hf_org_rss"],
                    urls["hf_org_html"] or "",
                )
            )

    feed_count = sum(len(v) for v in bucket.values())

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "<head>",
        f"<title>{esc(data.get('title', 'feeds'))} · {esc(data.get('topic', ''))}</title>",
        f"<dateCreated>{esc(data.get('updated_at', ''))}</dateCreated>",
        "</head>",
        "<body>",
    ]
    for gid, group in groups.items():
        feeds = bucket.get(gid, [])
        lines.append(
            f'  <outline text="{esc(group["name"])}" title="{esc(group["name"])}">'
        )
        lines.extend(feeds)
        lines.append("  </outline>")
    lines += ["</body>", "</opml>", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return feed_count


# ---------- Per-source JSON dumps ----------


def write_x_feed(data: dict[str, Any], out: Path) -> int:
    """follow-builders compatible: combined X handle list (scholars + orgs)."""
    handles: list[dict[str, str]] = []
    for s in data.get("scholars", []) or []:
        if s.get("x_handle"):
            handles.append(
                {
                    "name": s["name"],
                    "kind": "scholar",
                    "handle": s["x_handle"],
                    "url": f"https://x.com/{s['x_handle']}",
                    "group_id": s["group_id"],
                }
            )
    for o in data.get("orgs", []) or []:
        if o.get("x_handle"):
            handles.append(
                {
                    "name": o["name"],
                    "kind": "org",
                    "handle": o["x_handle"],
                    "url": f"https://x.com/{o['x_handle']}",
                    "group_id": o["group_id"],
                }
            )
    out.write_text(
        json.dumps(
            {"sources": handles, "count": len(handles)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return len(handles)


def write_scholar_feed(data: dict[str, Any], instance: str, out: Path) -> int:
    items: list[dict[str, str]] = []
    for s in data.get("scholars", []) or []:
        sid = s.get("scholar_id")
        if not sid:
            continue
        items.append(
            {
                "name": s["name"],
                "scholar_id": sid,
                "html_url": f"https://scholar.google.com/citations?user={sid}&hl=en",
                "rss_url": f"{instance}/google/citations/{sid}",
                "group_id": s["group_id"],
            }
        )
    out.write_text(
        json.dumps(
            {"sources": items, "count": len(items)}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return len(items)


def write_orgs_feed(data: dict[str, Any], instance: str, out: Path) -> int:
    items: list[dict[str, Any]] = []
    for o in data.get("orgs", []) or []:
        urls = build_org_urls(o, instance)
        items.append(
            {
                "name": o["name"],
                "group_id": o["group_id"],
                "homepage": o.get("homepage"),
                "key_works": o.get("key_works"),
                "x": urls["x_rss"],
                "blog": urls["blog_rss"],
                "github": urls["github_org_rss"],
                "huggingface": urls["hf_org_rss"],
            }
        )
    out.write_text(
        json.dumps(
            {"sources": items, "count": len(items)}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return len(items)


def write_flat_tsv(data: dict[str, Any], instance: str, out: Path) -> None:
    """Wide table: one row per scholar AND per org."""
    cols = [
        "kind",
        "group",
        "name",
        "affiliation_or_key_works",
        "scholar_html",
        "scholar_rss",
        "x_html",
        "x_rss",
        "blog_rss",
        "github_html",
        "github_org_rss",
        "huggingface_html",
        "homepage",
    ]
    lines = ["\t".join(cols)]
    groups = {g["id"]: g["name"] for g in data.get("groups", [])}

    for s in data.get("scholars", []) or []:
        u = build_scholar_urls(s, instance)
        lines.append(
            "\t".join(
                [
                    "scholar",
                    groups.get(s["group_id"], s["group_id"]),
                    s["name"],
                    s.get("affiliation", "") or "",
                    u["scholar_html"] or "",
                    u["scholar_rss"] or "",
                    u["x_html"] or "",
                    u["x_rss"] or "",
                    "",
                    u["github_html"] or "",
                    "",
                    "",
                    s.get("homepage") or "",
                ]
            )
        )
    for o in data.get("orgs", []) or []:
        u = build_org_urls(o, instance)
        lines.append(
            "\t".join(
                [
                    "org",
                    groups.get(o["group_id"], o["group_id"]),
                    o["name"],
                    o.get("key_works", "") or "",
                    "",
                    "",
                    u["x_html"] or "",
                    u["x_rss"] or "",
                    u["blog_rss"] or "",
                    "",
                    u["github_org_rss"] or "",
                    u["hf_org_html"] or "",
                    o.get("homepage") or "",
                ]
            )
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- Coverage report ----------


def write_report(data: dict[str, Any], out: Path) -> dict[str, Any]:
    scholars = data.get("scholars", []) or []
    orgs = data.get("orgs", []) or []

    s_total = len(scholars)
    s_have_scholar = sum(1 for s in scholars if s.get("scholar_id"))
    s_have_x = sum(1 for s in scholars if s.get("x_handle"))
    s_have_either = sum(
        1 for s in scholars if s.get("scholar_id") or s.get("x_handle")
    )
    s_verified = sum(1 for s in scholars if s.get("verified"))

    o_total = len(orgs)
    o_have_x = sum(1 for o in orgs if o.get("x_handle"))
    o_have_blog = sum(1 for o in orgs if o.get("blog_rss"))
    o_have_gh = sum(1 for o in orgs if o.get("github_org"))
    o_have_hf = sum(1 for o in orgs if o.get("huggingface_org"))
    o_have_any = sum(
        1
        for o in orgs
        if o.get("x_handle")
        or o.get("blog_rss")
        or o.get("github_org")
        or o.get("huggingface_org")
    )

    md: list[str] = []
    md.append(f"# Coverage Report · {data.get('topic', '')}\n")
    md.append(f"Updated: {data.get('updated_at', '')}\n")

    if s_total:
        md.append("## Scholars\n")
        md.append(f"- Total: **{s_total}**")
        md.append(
            f"- 有 Google Scholar ID: **{s_have_scholar}** "
            f"({s_have_scholar / s_total:.0%})"
        )
        md.append(f"- 有 X handle: **{s_have_x}** ({s_have_x / s_total:.0%})")
        md.append(
            f"- 至少一个可订阅 source: **{s_have_either}** "
            f"({s_have_either / s_total:.0%})"
        )
        md.append(f"- 已 verified: **{s_verified}** ({s_verified / s_total:.0%})\n")

        missing_both = [
            s for s in scholars if not s.get("scholar_id") and not s.get("x_handle")
        ]
        md.append("### 完全缺失的 scholar（既没 Scholar 也没 X）\n")
        if missing_both:
            for s in missing_both:
                q = quote(s["name"])
                md.append(
                    f"- **{s['name']}** ({s['group_id']}, {s.get('affiliation', '')}) — "
                    f"[Search Scholar](https://www.google.com/search?q={q}+Google+Scholar) · "
                    f"[Search X](https://x.com/search?q={q}&f=user)"
                )
        else:
            md.append("（无）")
        md.append("")

    if o_total:
        md.append("## Orgs\n")
        md.append(f"- Total: **{o_total}**")
        md.append(f"- 有 X handle: **{o_have_x}** ({o_have_x / o_total:.0%})")
        md.append(f"- 有 Blog RSS: **{o_have_blog}** ({o_have_blog / o_total:.0%})")
        md.append(f"- 有 GitHub org: **{o_have_gh}** ({o_have_gh / o_total:.0%})")
        md.append(f"- 有 HuggingFace org: **{o_have_hf}** ({o_have_hf / o_total:.0%})")
        md.append(
            f"- 至少一个可订阅 source: **{o_have_any}** ({o_have_any / o_total:.0%})\n"
        )

        missing = [
            o
            for o in orgs
            if not (
                o.get("x_handle")
                or o.get("blog_rss")
                or o.get("github_org")
                or o.get("huggingface_org")
            )
        ]
        md.append("### 完全缺失的 org（任何 source 都没有）\n")
        if missing:
            for o in missing:
                q = quote(o["name"])
                md.append(
                    f"- **{o['name']}** ({o['group_id']}) — "
                    f"[Google](https://www.google.com/search?q={q}) · "
                    f"[X user search](https://x.com/search?q={q}&f=user)"
                )
        else:
            md.append("（无）")
        md.append("")

    out.write_text("\n".join(md), encoding="utf-8")
    return {
        "scholars_total": s_total,
        "scholars_either": s_have_either,
        "orgs_total": o_total,
        "orgs_any": o_have_any,
    }


# ---------- Per-topic driver ----------


def merge_topic_data(topic_dir: Path) -> dict[str, Any]:
    """Load scholars.json and orgs.json (if present) into a unified dict."""
    sj = topic_dir / "scholars.json"
    oj = topic_dir / "orgs.json"
    base: dict[str, Any] = {
        "topic": topic_dir.name,
        "title": topic_dir.name,
        "updated_at": "",
        "groups": [],
        "scholars": [],
        "orgs": [],
    }
    if sj.exists():
        d = load(sj)
        base["topic"] = d.get("topic", base["topic"])
        base["title"] = d.get("title", base["title"])
        base["updated_at"] = d.get("updated_at", base["updated_at"])
        base["groups"].extend(d.get("groups", []))
        base["scholars"].extend(d.get("scholars", []))
    if oj.exists():
        d = load(oj)
        if not base["topic"] or base["topic"] == topic_dir.name:
            base["topic"] = d.get("topic", base["topic"])
        if base["title"] == topic_dir.name:
            base["title"] = d.get("title", base["title"])
        if not base["updated_at"]:
            base["updated_at"] = d.get("updated_at", "")
        # de-dup groups by id
        seen = {g["id"] for g in base["groups"]}
        for g in d.get("groups", []):
            if g["id"] not in seen:
                base["groups"].append(g)
                seen.add(g["id"])
        base["orgs"].extend(d.get("orgs", []))
    return base


def process_topic(topic_dir: Path, instance: str, report_only: bool) -> dict[str, Any]:
    data = merge_topic_data(topic_dir)
    out_dir = topic_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = write_report(data, out_dir / "coverage-report.md")
    line = (
        f"[{topic_dir.name}] scholars={stats['scholars_total']} "
        f"({stats['scholars_either']} subscribable) · "
        f"orgs={stats['orgs_total']} ({stats['orgs_any']} subscribable)"
    )

    if report_only:
        print(line)
        return stats

    feed_count = write_opml(data, instance, out_dir / "feeds.opml")
    x_count = write_x_feed(data, out_dir / "feeds-x.json")
    sc_count = write_scholar_feed(data, instance, out_dir / "feeds-scholars.json")
    org_count = write_orgs_feed(data, instance, out_dir / "feeds-orgs.json")
    write_flat_tsv(data, instance, out_dir / "feeds-flat.tsv")
    print(
        f"{line} → opml={feed_count} feeds, x={x_count}, scholars={sc_count}, orgs={org_count}"
    )
    return stats


def write_combined_opml(topic_dirs: list[Path], instance: str, out: Path) -> None:
    """Merge every topic's feeds into one OPML, with topic as the top-level folder."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "<head>",
        "<title>info_system · all topics</title>",
        "</head>",
        "<body>",
    ]
    for td in topic_dirs:
        data = merge_topic_data(td)
        lines.append(
            f'  <outline text="{esc(data.get("title", td.name))}" '
            f'title="{esc(data.get("title", td.name))}">'
        )
        # 把每个 topic 的 group 作为二级 folder 放进来
        groups = {g["id"]: g for g in data.get("groups", [])}
        bucket: dict[str, list[str]] = {gid: [] for gid in groups}
        for s in data.get("scholars", []) or []:
            urls = build_scholar_urls(s, instance)
            gid = s["group_id"]
            if urls["scholar_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{s['name']} · Scholar",
                        urls["scholar_rss"],
                        urls["scholar_html"] or "",
                    )
                )
            if urls["x_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{s['name']} · X (@{s['x_handle']})",
                        urls["x_rss"],
                        urls["x_html"] or "",
                    )
                )
        for o in data.get("orgs", []) or []:
            urls = build_org_urls(o, instance)
            gid = o["group_id"]
            if urls["blog_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{o['name']} · Blog",
                        urls["blog_rss"],
                        o.get("homepage") or "",
                    )
                )
            if urls["x_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{o['name']} · X (@{o['x_handle']})",
                        urls["x_rss"],
                        urls["x_html"] or "",
                    )
                )
            if urls["github_org_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{o['name']} · GitHub org",
                        urls["github_org_rss"],
                        urls["github_org_html"] or "",
                    )
                )
            if urls["hf_org_rss"]:
                bucket.setdefault(gid, []).append(
                    opml_outline(
                        f"{o['name']} · HuggingFace papers",
                        urls["hf_org_rss"],
                        urls["hf_org_html"] or "",
                    )
                )
        for gid, group in groups.items():
            feeds = bucket.get(gid, [])
            lines.append(
                f'    <outline text="{esc(group["name"])}" title="{esc(group["name"])}">'
            )
            for f in feeds:
                lines.append("  " + f)
            lines.append("    </outline>")
        lines.append("  </outline>")
    lines += ["</body>", "</opml>", ""]
    out.write_text("\n".join(lines), encoding="utf-8")


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="只处理某个 topic（topics/<topic>/），不传则处理全部",
    )
    parser.add_argument(
        "--topics-dir",
        type=Path,
        default=TOPICS_DIR,
        help=f"topic 根目录（默认 {TOPICS_DIR}）",
    )
    parser.add_argument(
        "--instance",
        type=str,
        default="https://rsshub.app",
        help="RSSHub 实例 base URL（生产建议自建，例：http://localhost:1200）",
    )
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="额外生成一份 out/all.opml（聚合所有 topic）",
    )
    args = parser.parse_args()

    topic_dirs = discover_topics(args.topics_dir)
    if args.topic:
        match = [d for d in topic_dirs if d.name == args.topic]
        if not match:
            available = ", ".join(d.name for d in topic_dirs) or "(none)"
            print(
                f"topic not found: {args.topic}\navailable: {available}",
                file=sys.stderr,
            )
            return 2
        topic_dirs = match

    if not topic_dirs:
        print(
            f"no topics with scholars.json or orgs.json found under {args.topics_dir}",
            file=sys.stderr,
        )
        return 2

    print(f"[info] processing {len(topic_dirs)} topic(s) via instance={args.instance}")
    for td in topic_dirs:
        process_topic(td, args.instance, args.report_only)

    if args.merge and not args.report_only:
        COMBINED_OUT.mkdir(parents=True, exist_ok=True)
        write_combined_opml(topic_dirs, args.instance, COMBINED_OUT / "all.opml")
        print(f"[ok] wrote combined OPML to {COMBINED_OUT / 'all.opml'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
