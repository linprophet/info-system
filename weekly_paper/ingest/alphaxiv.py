r"""alphaxiv 7-day trending ingest.

URL: https://www.alphaxiv.org/  (Explore 页 = 默认 7-day trending list)

alphaxiv 用 Next.js App Router + RSC（React Server Components）渲染。论文数据嵌在
`<script class="$tsr" id="$tsr-stream-barrier">…</script>` 流里，格式是 JS 对象字面量
（不是纯 JSON），包含 `$R[N]={…}` 形式的引用赋值。

我们做的：
1. 找 `trendingPapers:` 数组体（用 brace/bracket 平衡走到对应 `]`）。
2. 从中切出 paper-level 对象（`$R[N]={id:"…",paper_group_id:"…"`），跳过嵌套的
   author / metrics 子对象。
3. 把 JS 对象字面量转 JSON：去掉所有 `$R[N]=` 引用前缀 + 给未加引号的 key 补引号；
   字符串值本身已是 JSON 兼容形式（标准 \" \\ \uXXXX 都能被 json.loads 解析）。
4. 每篇 paper 抽 title / abstract / paper_summary.summary / universal_paper_id / authors
   / organization_info / metrics / publication_date 构造 Item。

URL 用 `https://www.alphaxiv.org/abs/<universal_paper_id>`，对 arxiv 论文（ID 形如
`2604.25917`）和 alphaxiv slug 论文（如 `on-policy-distillation`）都通用。

date 处理沿用 hf_papers 思路：信任 alphaxiv 的"最近 7 天热门"编辑判断，把早于本周一的
publication_date clamp 到周一，让 filter_in_week 不会把仍在 trending 的旧论文丢掉。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any, Optional

from weekly_report.items import INLINE_TEXT_MAX_CHARS, Item, url_hash
from weekly_report.sources import Source
from weekly_report.storage import SourceState, utc_now_iso, week_bounds


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


def _walk_balanced(s: str, start: int, open_ch: str, close_ch: str) -> int:
    """从 `start`（指向 `open_ch` 之后那一位）走到平衡的 `close_ch`，返回其后一位。

    遇到字符串字面量（"…"）时跳过。返回 close 的下一位；若到末尾仍未平衡返回 len(s)。
    """
    depth = 1
    i = start
    in_str = False
    esc = False
    while i < len(s) and depth > 0:
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
        i += 1
    return i


def _js_object_to_json(blob: str) -> str:
    """把 JS 对象字面量字符串转成 JSON。

    操作：
    1. 去掉所有 `$R[<N>]=` 引用赋值前缀。
    2. 给未加引号的 property name 补双引号（identifier 后紧跟 `:` 且前面是 `{` 或 `,`）。

    字符串内部不做修改，依靠状态机识别。
    """
    blob = re.sub(r"\$R\[\d+\]=", "", blob)
    out: list[str] = []
    i = 0
    n = len(blob)
    in_str = False
    esc = False
    while i < n:
        c = blob[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        # potential unquoted property name?
        if c.isalpha() or c == "_":
            # only if previous non-space is `{` or `,`
            j = len(out) - 1
            while j >= 0 and out[j] in " \t\n\r":
                j -= 1
            if j >= 0 and out[j] in "{,":
                k = i
                while k < n and (blob[k].isalnum() or blob[k] == "_"):
                    k += 1
                kk = k
                while kk < n and blob[kk] in " \t\n\r":
                    kk += 1
                if kk < n and blob[kk] == ":":
                    out.append('"')
                    out.append(blob[i:k])
                    out.append('"')
                    i = k
                    continue
        out.append(c)
        i += 1
    return "".join(out)


def _extract_trending_papers(html_body: str) -> list[dict]:
    """从 alphaxiv home page HTML 抽出 trending paper 列表。"""
    m = re.search(r"trendingPapers:(?:\$R\[\d+\]=)?\[", html_body)
    if not m:
        return []
    arr_start = m.end()
    arr_end = _walk_balanced(html_body, arr_start, "[", "]") - 1
    arr_body = html_body[arr_start:arr_end]

    # paper-level: `$R[N]={id:"<uuid>",paper_group_id:"…"`（排除 full_authors 子对象）
    head_re = re.compile(r'\$R\[\d+\]=\{id:"[0-9a-f-]{20,}",paper_group_id:"')
    papers: list[dict] = []
    for hm in head_re.finditer(arr_body):
        st = hm.start()
        # advance to the actual `{`
        while st < len(arr_body) and arr_body[st] != "{":
            st += 1
        en = _walk_balanced(arr_body, st + 1, "{", "}")
        blob = arr_body[st:en]
        try:
            obj = json.loads(_js_object_to_json(blob))
        except json.JSONDecodeError as e:
            log.warning("alphaxiv paper JSON decode err: %s", e)
            continue
        papers.append(obj)
    return papers


def _to_iso_aware(dt_str: str) -> str:
    """alphaxiv publication_date 像 `2026-05-01T17:51:38.000Z`，已是 ISO + tz。"""
    if not dt_str:
        return ""
    s = dt_str.strip()
    # `Z` 后缀是 UTC，把 `Z` 换成 `+00:00` 让 fromisoformat 接受
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return s


def _paper_url(p: dict) -> str:
    pid = p.get("universal_paper_id") or p.get("paper_group_id") or p.get("id")
    if not pid:
        return ""
    return f"https://www.alphaxiv.org/abs/{pid}"


def _paper_to_item(
    source: Source,
    p: dict,
    *,
    week_id: Optional[str] = None,
) -> Optional[Item]:
    title = (p.get("title") or "").strip()
    url = _paper_url(p)
    if not title or not url:
        return None

    abstract = (p.get("abstract") or "").strip()
    summary_blob = ((p.get("paper_summary") or {}).get("summary") or "").strip()
    # 优先用 paper_summary（人/AI 总结，更紧凑），回退 abstract 前段
    summary_short = (summary_blob or abstract)[: INLINE_TEXT_MAX_CHARS // 4]
    raw = abstract if abstract and len(abstract) <= INLINE_TEXT_MAX_CHARS else ""

    pub_at = _to_iso_aware(p.get("publication_date") or p.get("first_publication_date") or "")
    # 若日期早于本周一，clamp 到周一（保留时区/时间尾巴）—— 信任 alphaxiv 的 "trending" 编辑判断
    if week_id and pub_at:
        try:
            ws, _ = week_bounds(week_id)
            ws_str = ws.date().isoformat()
            if pub_at[:10] < ws_str:
                tail = pub_at[10:] if len(pub_at) > 10 else "T00:00:00+00:00"
                pub_at = ws_str + tail
        except Exception:
            pass

    authors = list(p.get("authors") or [])

    tags: list[str] = ["paper", "alphaxiv-trending"]
    for o in p.get("organization_info") or []:
        name = o.get("name") if isinstance(o, dict) else None
        if name:
            tags.append(f"alphaxiv-org:{name}")
    metrics = p.get("metrics") or {}
    visits = (metrics.get("visits_count") or {}).get("last_7_days")
    if isinstance(visits, int):
        tags.append(f"alphaxiv-v7d:{visits}")
    votes = metrics.get("public_total_votes")
    if isinstance(votes, int):
        tags.append(f"alphaxiv-votes:{votes}")
    # arxiv topics（cs.CV / cs.LG / cs.RO …）有助于 LLM 分类
    for t in (p.get("topics") or [])[:8]:
        if isinstance(t, str):
            tags.append(f"topic:{t}")
    gh = p.get("github_url")
    if isinstance(gh, str) and gh:
        tags.append(f"github:{gh}")
        gh_stars = p.get("github_stars")
        if isinstance(gh_stars, int):
            tags.append(f"github-stars:{gh_stars}")

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
    )


def _trending_score(p: dict) -> tuple[int, int]:
    """排序键：先 visits_count.last_7_days 降序，再 public_total_votes 降序。"""
    metrics = p.get("metrics") or {}
    visits = (metrics.get("visits_count") or {}).get("last_7_days") or 0
    votes = metrics.get("public_total_votes") or 0
    return (-int(visits), -int(votes))


def ingest_alphaxiv(
    source: Source,
    state: SourceState,
    *,
    week_id: Optional[str] = None,
    top_n: int = 30,
) -> tuple[list[Item], str]:
    """抓 alphaxiv 7-day trending，按 last_7_days visits 降序取 top_n。

    Returns (items, status). status: 'ok' | 'fail'.
    """
    url = "https://www.alphaxiv.org/"
    try:
        body = _fetch(url)
    except Exception as e:
        log.warning("alphaxiv fetch fail: %s", e)
        state.last_error = f"fetch: {type(e).__name__}: {e}"
        return [], "fail"

    papers = _extract_trending_papers(body)
    if not papers:
        state.last_error = "parse: no trendingPapers block"
        return [], "fail"

    papers.sort(key=_trending_score)
    items: list[Item] = []
    for p in papers[:top_n]:
        try:
            it = _paper_to_item(source, p, week_id=week_id)
            if it:
                items.append(it)
        except Exception as ex:
            log.warning("alphaxiv entry err: %s", ex)

    state.last_error = ""
    return items, "ok"
