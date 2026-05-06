#!/usr/bin/env python3
"""Verify every org's source URLs and update the `verified` field.

Strategy (per source kind):
- X handle:    https://publish.twitter.com/oembed?url=https://twitter.com/{h}
               (oembed correctly returns 404 for non-existent handles, 200 otherwise.
               Probing https://x.com/{h} directly is useless because X returns 403
               to all unauthenticated traffic.)
- Blog RSS:    GET the URL itself, expect 200.
- GitHub org:  GET https://github.com/{org}.atom, expect 200 + valid atom body.
- HF org:      GET https://huggingface.co/{org}, expect 200.
- Homepage:    informational only, never affects verified flag.

An org is auto-flagged verified=true iff every declared, non-homepage source
returned ok. Otherwise it is "partial" (some ok) or "fail" (none ok).

Writes:
- topics/<topic>/out/verify-report.md       (always)
- topics/<topic>/orgs.json                  (in-place: verified + verify_notes,
                                             unless --dry-run)

Usage:
    python verify_feeds.py                       # all topics, 8 workers
    python verify_feeds.py --topic vla-embodied
    python verify_feeds.py --dry-run             # report only
    python verify_feeds.py --workers 16
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


HERE = Path(__file__).parent
TOPICS_DIR = HERE / "topics"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 12.0


# ---------- HTTP probe ----------


@dataclass
class Probe:
    label: str
    url: str
    ok: bool = False
    status: int | None = None
    error: str | None = None
    elapsed_ms: int = 0


def probe(url: str, label: str) -> Probe:
    """Return a Probe. Tries HEAD then falls back to GET if needed."""
    p = Probe(label=label, url=url)
    if not url:
        p.error = "empty url"
        return p

    t0 = time.perf_counter()
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                p.status = resp.status
                p.ok = resp.status in (200, 301, 302, 304)
                p.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return p
        except urllib.error.HTTPError as e:
            # Some sites refuse HEAD (405); fall through to GET on the next iteration.
            if e.code == 405 and method == "HEAD":
                continue
            p.status = e.code
            p.ok = e.code in (301, 302, 304)
            p.error = f"HTTP {e.code}"
            p.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return p
        except urllib.error.URLError as e:
            if method == "HEAD":
                # Try GET in case server is hostile to HEAD
                continue
            p.error = f"URLError: {e.reason}"
            p.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return p
        except Exception as e:  # noqa: BLE001
            if method == "HEAD":
                continue
            p.error = f"{type(e).__name__}: {e}"
            p.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return p
    p.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return p


# ---------- per-org plan ----------


"""Why X probes do NOT count toward `verified`:

The publish.twitter.com/oembed endpoint sometimes returns 404 for *real,
public* handles (e.g. @lovable_dev, @roo_code) — empirically it appears to
404 for accounts that have disabled oEmbed, or have low engagement. Direct
GET on https://x.com/{handle} always returns 403 to unauthenticated traffic.
So we cannot reliably auto-verify X. We still probe it for an informational
signal in verify_notes, but verified=true is decided ONLY by the always-
reliable backbones: GitHub atom + Blog RSS + HF org.
"""

VERIFIABLE_LABELS = {"GitHub atom", "Blog RSS", "HF org"}


@dataclass
class OrgResult:
    name: str
    group_id: str
    probes: list[Probe] = field(default_factory=list)

    @property
    def verifiable_probes(self) -> list[Probe]:
        return [p for p in self.probes if p.label in VERIFIABLE_LABELS]

    @property
    def declared_verifiable(self) -> int:
        return len(self.verifiable_probes)

    @property
    def ok_verifiable(self) -> int:
        return sum(1 for p in self.verifiable_probes if p.ok)

    @property
    def x_probe(self) -> Probe | None:
        for p in self.probes:
            if p.label == "X":
                return p
        return None

    @property
    def verified(self) -> bool:
        return (
            self.declared_verifiable > 0
            and self.ok_verifiable == self.declared_verifiable
        )

    @property
    def status_emoji(self) -> str:
        # ⚪ = no verifiable backbone declared (only X / homepage)
        if self.declared_verifiable == 0:
            return "⚪"
        if self.ok_verifiable == 0:
            return "❌"
        if self.verified:
            return "✅"
        return "⚠️"


def plan_probes(org: dict[str, Any]) -> list[tuple[str, str]]:
    """Return list of (label, url) probes for one org.

    label semantics: any label that isn't "Homepage" counts toward verified.
    """
    out: list[tuple[str, str]] = []
    if org.get("x_handle"):
        out.append(
            (
                "X",
                f"https://publish.twitter.com/oembed?url=https://twitter.com/"
                f"{org['x_handle']}",
            )
        )
    if org.get("blog_rss"):
        out.append(("Blog RSS", org["blog_rss"]))
    if org.get("github_org"):
        out.append(("GitHub atom", f"https://github.com/{org['github_org']}.atom"))
    if org.get("huggingface_org"):
        out.append(("HF org", f"https://huggingface.co/{org['huggingface_org']}"))
    if org.get("homepage"):
        out.append(("Homepage", org["homepage"]))
    return out


def verify_org(org: dict[str, Any]) -> OrgResult:
    res = OrgResult(name=org["name"], group_id=org.get("group_id", ""))
    for label, url in plan_probes(org):
        res.probes.append(probe(url, label))
    return res


# ---------- topic driver ----------


def verify_topic(
    topic_dir: Path, workers: int, dry_run: bool
) -> tuple[list[OrgResult], dict[str, Any] | None]:
    oj = topic_dir / "orgs.json"
    if not oj.exists():
        return [], None

    data = json.loads(oj.read_text(encoding="utf-8"))
    orgs = data.get("orgs", [])
    if not orgs:
        return [], data

    print(f"[{topic_dir.name}] verifying {len(orgs)} orgs ...", flush=True)

    results: list[OrgResult] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(verify_org, orgs):
            results.append(r)
            print(
                f"  {r.status_emoji} {r.name}  ({r.ok_sources}/{r.declared_sources} sources ok)",
                flush=True,
            )

    write_topic_report(topic_dir, results)

    if not dry_run:
        by_name = {r.name: r for r in results}
        for org in orgs:
            r = by_name.get(org["name"])
            if not r:
                continue
            org["verified"] = r.verified

            parts: list[str] = []
            failed_v = [
                f"{p.label}({p.status or p.error})"
                for p in r.verifiable_probes
                if not p.ok
            ]
            if r.verified:
                parts.append("backbone OK")
            elif r.ok_verifiable == 0 and r.declared_verifiable > 0:
                parts.append("backbone all FAIL")
            elif failed_v:
                parts.append("backbone partial: " + ", ".join(failed_v))
            elif r.declared_verifiable == 0:
                parts.append("no backbone declared (X-only org)")

            xp = r.x_probe
            if xp is not None:
                if xp.ok:
                    parts.append("X oembed ok")
                else:
                    parts.append(
                        f"X oembed {xp.status or xp.error} "
                        "(handle may still be real — oembed unreliable)"
                    )
            org["verify_notes"] = "auto 2026-05-03 · " + " · ".join(parts)
        oj.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  → wrote back to {oj.relative_to(HERE)}", flush=True)

    return results, data


def write_topic_report(topic_dir: Path, results: list[OrgResult]) -> None:
    out_dir = topic_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "verify-report.md"

    total = len(results)
    verified = sum(1 for r in results if r.verified)
    partial = sum(
        1
        for r in results
        if 0 < r.ok_verifiable < r.declared_verifiable
    )
    fail = sum(
        1 for r in results if r.declared_verifiable > 0 and r.ok_verifiable == 0
    )
    no_backbone = sum(1 for r in results if r.declared_verifiable == 0)

    md: list[str] = []
    md.append(f"# Verify Report · {topic_dir.name}\n")
    md.append(
        "Verified=true iff every declared backbone source "
        "(GitHub atom / Blog RSS / HF org) returned 200/301/302/304. "
        "X handles are probed via publish.twitter.com/oembed but treated as "
        "informational only (oembed is unreliable).\n"
    )
    md.append("## Summary\n")
    md.append(f"- Total orgs: **{total}**")
    md.append(f"- ✅ Verified (all backbone sources ok): **{verified}**")
    md.append(f"- ⚠️ Partial (some backbone sources fail): **{partial}**")
    md.append(f"- ❌ All backbone sources unreachable: **{fail}**")
    md.append(
        f"- ⚪ No backbone declared (only X / homepage): **{no_backbone}**\n"
    )

    md.append("## Per-org\n")
    md.append("| Status | Org | Backbone OK | X oembed | Failures |")
    md.append("| --- | --- | --- | --- | --- |")
    for r in results:
        failures = [
            f"{p.label}({p.status or p.error})"
            for p in r.verifiable_probes
            if not p.ok
        ]
        xp = r.x_probe
        x_cell = "—" if xp is None else ("✓" if xp.ok else f"✗{xp.status or ''}")
        md.append(
            f"| {r.status_emoji} | {r.name} | "
            f"{r.ok_verifiable}/{r.declared_verifiable} | {x_cell} | "
            f"{', '.join(failures) if failures else '—'} |"
        )
    md.append("")

    md.append("## Detail\n")
    for r in results:
        md.append(f"### {r.status_emoji} {r.name}")
        for p in r.probes:
            mark = "✓" if p.ok else "✗"
            extra = (
                f"HTTP {p.status}"
                if p.status
                else (p.error or "?")
            )
            md.append(f"- {mark} **{p.label}** — `{p.url}` · {extra} · {p.elapsed_ms}ms")
        md.append("")
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"  → wrote {out.relative_to(HERE)}", flush=True)


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--topic", type=str, default=None)
    parser.add_argument("--topics-dir", type=Path, default=TOPICS_DIR)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成 verify-report.md，不修改 orgs.json",
    )
    parser.add_argument(
        "--rsshub",
        type=str,
        default="https://rsshub.app",
        help="同时探测一下 RSSHub 实例的 HF papers / X 路由是否可用",
    )
    args = parser.parse_args()

    # Pre-flight: probe the RSSHub instance once for the HF papers + X routes,
    # so the user knows whether the public instance can actually serve them.
    print(f"[rsshub-preflight] probing {args.rsshub} ...", flush=True)
    for label, path in [
        ("HF papers", "/huggingface/papers/google"),
        ("X user", "/twitter/user/openai"),
    ]:
        p = probe(f"{args.rsshub}{path}", label)
        emoji = "✓" if p.ok else "✗"
        print(
            f"  {emoji} {label}: HTTP {p.status or p.error} ({p.elapsed_ms}ms)",
            flush=True,
        )
    print()

    if not args.topics_dir.exists():
        print(f"topics dir not found: {args.topics_dir}", file=sys.stderr)
        return 2

    topic_dirs = [
        p
        for p in sorted(args.topics_dir.iterdir())
        if p.is_dir() and (p / "orgs.json").exists()
    ]
    if args.topic:
        topic_dirs = [p for p in topic_dirs if p.name == args.topic]
        if not topic_dirs:
            print(f"topic not found: {args.topic}", file=sys.stderr)
            return 2

    grand_total = 0
    grand_verified = 0
    grand_partial = 0
    grand_fail = 0
    grand_no_backbone = 0
    for td in topic_dirs:
        results, _ = verify_topic(td, workers=args.workers, dry_run=args.dry_run)
        grand_total += len(results)
        grand_verified += sum(1 for r in results if r.verified)
        grand_partial += sum(
            1 for r in results if 0 < r.ok_verifiable < r.declared_verifiable
        )
        grand_fail += sum(
            1 for r in results if r.declared_verifiable > 0 and r.ok_verifiable == 0
        )
        grand_no_backbone += sum(
            1 for r in results if r.declared_verifiable == 0
        )

    print()
    print(
        f"[grand] orgs={grand_total} ✅verified={grand_verified} "
        f"⚠️partial={grand_partial} ❌fail={grand_fail} "
        f"⚪x-only={grand_no_backbone}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
