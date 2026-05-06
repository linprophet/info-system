"""HuggingFace Daily Papers ingest（按周抓取）。

URL: https://huggingface.co/papers/week/<week_id>  (e.g. 2026-W18)

页面是 SvelteKit 渲染的 SSR HTML，论文数据嵌在
`<div data-target="DailyPapers" data-props="<HTML-escaped JSON>">` 里。
我们用 `raw_decode` 跳过尾巴上的 HTML，干净拿到 JSON。

Top-level: `dailyPapers: list[paper_wrapper]`，每个 wrapper 含 `paper` 子对象
（id / title / summary / upvotes / authors / publishedAt）。

按 upvotes 取 top N 抽样，避免单周 100+ 论文把 filter 阶段成本打爆。
"""

from __future__ import annotations

import html
import json
import logging
import urllib.request
from typing import Optional

from weekly_report.items import INLINE_TEXT_MAX_CHARS, Item, url_hash
from weekly_report.sources import Source
from weekly_report.storage import SourceState, utc_now_iso


log = logging.getLogger(__name__)


HTTP_TIMEOUT = 25.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _extract_daily_papers_json(html_body: str) -> Optional[list]:
    """Find the DailyPapers SvelteKit hydrator block and extract its JSON."""
    marker = 'data-target="DailyPapers"'
    start = html_body.find(marker)
    if start < 0:
        return None
    props_start = html_body.find('data-props="', start)
    if props_start < 0:
        return None
    props_start += len('data-props="')
    chunk = html.unescape(html_body[props_start: props_start + 1_500_000])
    try:
        obj, _ = json.JSONDecoder().raw_decode(chunk)
    except json.JSONDecodeError as e:
        log.warning("hf-papers JSON decode err: %s", e)
        return None
    return obj.get("dailyPapers") or []


def _wrapper_to_item(source: Source, w: dict, *, week_id: Optional[str] = None) -> Optional[Item]:
    paper = w.get("paper") or {}
    pid = paper.get("id")
    if not pid:
        return None
    title = (w.get("title") or paper.get("title") or "").strip()
    if not title:
        return None
    summary = (w.get("summary") or paper.get("summary") or "").strip()
    summary_short = summary[: INLINE_TEXT_MAX_CHARS // 4]
    raw = summary if len(summary) <= INLINE_TEXT_MAX_CHARS else ""

    # Use HF paper page as canonical URL（包含 abstract、上下投票、作者卡片）
    url = f"https://huggingface.co/papers/{pid}"

    authors_list = paper.get("authors") or []
    authors = [a.get("name") for a in authors_list if isinstance(a, dict) and a.get("name")]

    # 重要：取 wrapper / paper publishedAt 中**较晚**的那个
    # - wrapper.publishedAt = HF 把它加到 daily papers 的日期
    # - paper.publishedAt   = arxiv 提交日期（更准确）
    # 两者经常差 1-2 天；HF 周日加进 W18 页面但 arxiv 在 W18 周一提交的论文，旧实现会用周日日期
    # 导致被 filter_in_week 错误排除（例如 W18 的 Tuna-2 / World-R1）
    w_pub_raw = w.get("publishedAt") or ""
    p_pub_raw = paper.get("publishedAt") or ""
    # 比较只用日期部分（避免某个有 time / tz 而另一个没有时被字符串比较坑）
    if w_pub_raw and p_pub_raw:
        pub_at = w_pub_raw if w_pub_raw[:10] >= p_pub_raw[:10] else p_pub_raw
    else:
        pub_at = w_pub_raw or p_pub_raw or ""
    # 保留原 ISO 字符串（含时区）；如果原本就只有日期没时间，补 T00:00:00+00:00 让 _parse_iso 拿到 tz-aware
    if pub_at and len(pub_at) == 10:
        pub_at = pub_at + "T00:00:00+00:00"

    # 进一步保险：如果 HF 把这篇论文编辑性地放在 week_id 周页面，但日期算出来还在该周之前，
    # 强制 clamp 到该周的周一（信任 HF 的编辑判断）
    if week_id and pub_at:
        from weekly_report.storage import week_bounds
        try:
            ws, _ = week_bounds(week_id)
            ws_str = ws.date().isoformat()
            if pub_at[:10] < ws_str:
                # 保留原始 time/tz 部分；只换日期前缀
                tail = pub_at[10:] if len(pub_at) > 10 else "T00:00:00+00:00"
                pub_at = ws_str + tail
        except Exception:
            pass

    upvotes = w.get("upvotes") or paper.get("upvotes") or 0

    tags = ["paper"]
    org = w.get("organization") or paper.get("organization")
    if org:
        tags.append(f"hf-org:{org}")
    if upvotes:
        tags.append(f"upvotes:{upvotes}")

    return Item(
        id=url_hash(url),
        source_id=source.id,
        source_type=source.type,
        source_tier=source.tier,
        source_lang=source.lang,
        title=title,
        url=url,
        published_at=pub_at,
        fetched_at=utc_now_iso(),
        summary=summary_short,
        raw_text=raw,
        authors=authors,
        tags=tags,
        duration_sec=0,
        # extra: store upvotes in tags for filter heuristic later
    )


def ingest_hf_papers(
    source: Source,
    state: SourceState,
    *,
    week_id: str,
    top_n: int = 50,
) -> tuple[list[Item], str]:
    """抓 HuggingFace 周内 papers，按 upvotes 降序取 top_n。

    Returns (items, status). status: 'ok' | 'fail'.
    """
    url = f"https://huggingface.co/papers/week/{week_id}"
    try:
        body = _fetch(url)
    except Exception as e:
        log.warning("hf-papers fetch fail: %s", e)
        state.last_error = f"fetch: {type(e).__name__}: {e}"
        return [], "fail"

    wrappers = _extract_daily_papers_json(body)
    if wrappers is None:
        state.last_error = "parse: no DailyPapers block"
        return [], "fail"

    # sort by upvotes desc + 取前 top_n
    wrappers.sort(
        key=lambda w: -((w.get("upvotes") or 0) + (w.get("paper", {}).get("upvotes") or 0)),
    )
    items: list[Item] = []
    for w in wrappers[:top_n]:
        try:
            it = _wrapper_to_item(source, w, week_id=week_id)
            if it:
                items.append(it)
        except Exception as ex:
            log.warning("hf-papers entry err: %s", ex)

    state.last_error = ""
    return items, "ok"
