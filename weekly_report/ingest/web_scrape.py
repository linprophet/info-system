"""Generic SSR-blog scraper for sources that don't expose RSS.

Targets blogs where:
- the index page (`source.index_url`) lists articles with `<a href="<prefix><slug>">`
  patterns (`source.article_url_prefix` filters which links are articles), and
- each article page has standard `og:title` / `og:description` meta tags + a
  publication date in one of several common patterns.

Used initially for Anthropic Engineering and Claude blog (both Next.js SSR sites
without public RSS).

Strategy:
1. Fetch index_url → extract unique article slugs matching article_url_prefix.
2. For each article (in parallel, capped), fetch its HTML and pull:
   - title  ← <meta property="og:title"> (fallback: <title>)
   - summary ← <meta property="og:description">
   - published_at ← first matching pattern from PARSE_DATE_PATTERNS, parsed via
     a tolerant multi-format parser, normalized to UTC ISO 8601.
3. Build Item per article. Authors=[], duration=0.

Article URLs that fail to yield a date are kept (with `published_at=""`) and
will be dropped by `filter_in_week`. We log a `last_error_per_slug` summary on
the SourceState for debugging.
"""

from __future__ import annotations

import concurrent.futures as cf
import html
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
ARTICLE_FETCH_WORKERS = 6
MAX_ARTICLES_PER_RUN = 60  # safety cap so a misconfigured prefix can't ddos


class _PermissiveRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow 308 too (older Python's default handler stops at 308)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code == 308:
            return super().redirect_request(req, fp, 301, msg, headers, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_PermissiveRedirectHandler())


def _fetch(url: str) -> tuple[str, str]:
    """Fetch url, follow redirects (incl. 308). Returns (final_url, body)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with _OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
        final_url = resp.geturl()
        body = resp.read().decode("utf-8", errors="ignore")
    return final_url, body


def _meta_content(html_body: str, *, prop: Optional[str] = None, name: Optional[str] = None) -> str:
    """Pull a <meta property=... content="..."> or <meta name=... content="..."> value.

    Robust to:
    - attribute ordering (some sites put `content=` first)
    - unquoted attribute values (Webflow-minified HTML uses `property=og:title`)
    """
    # Attribute-value pattern that accepts both `"..."` and unquoted (terminated
    # on whitespace, '>', '/', or another attribute char).
    val_pat = r"""(?:"([^"]*)"|'([^']*)'|([^\s>/]*))"""
    target = prop or name or ""
    if not target:
        return ""
    attr = "property" if prop else "name"
    # case 1: <meta ... attr=target ... content="..." ...>
    m = re.search(
        rf"<meta[^>]+{attr}\s*=\s*(?:\"{re.escape(target)}\"|'{re.escape(target)}'|{re.escape(target)})[^>]+content\s*=\s*{val_pat}",
        html_body,
    )
    if m:
        return html.unescape(next((g for g in m.groups() if g is not None), ""))
    # case 2: <meta ... content="..." ... attr=target ...>
    m = re.search(
        rf"<meta[^>]+content\s*=\s*{val_pat}[^>]+{attr}\s*=\s*(?:\"{re.escape(target)}\"|'{re.escape(target)}'|{re.escape(target)}(?=[\s>/]))",
        html_body,
    )
    if m:
        return html.unescape(next((g for g in m.groups() if g is not None), ""))
    return ""


# Date parsing — try every pattern that might appear in SSR HTML. First match wins.
# Returned strings get fed into `_parse_date` which accepts ISO and human formats.
DATE_PATTERNS = [
    # standard meta tags
    re.compile(r'<meta[^>]+property\s*=\s*"article:published_time"[^>]+content\s*=\s*"([^"]+)"'),
    re.compile(r'<meta[^>]+content\s*=\s*"([^"]+)"[^>]+property\s*=\s*"article:published_time"'),
    re.compile(r'<meta[^>]+name\s*=\s*"date"[^>]+content\s*=\s*"([^"]+)"'),
    # JSON-LD style (no full parse — just key:"value")
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"datepublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"publishedAt"\s*:\s*"([^"]+)"'),
    # Anthropic-specific text near the title
    re.compile(r'>Published\s*(?:<!--\s*-->\s*)?([A-Z][a-z]+ \d{1,2},\s*\d{4})'),
    re.compile(r'>Updated\s*(?:<!--\s*-->\s*)?([A-Z][a-z]+ \d{1,2},\s*\d{4})'),
    # <time datetime="..."> tags
    re.compile(r'<time[^>]+datetime\s*=\s*"([^"]+)"'),
]


_HUMAN_DATE_FORMATS = [
    "%b %d, %Y",         # "Apr 30, 2026"
    "%B %d, %Y",         # "April 23, 2026"
    "%Y-%m-%d",          # "2024-12-19"
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f",
]


def _parse_date(s: str) -> Optional[datetime]:
    """Best-effort parse for ISO-ish and human-readable dates → tz-aware datetime."""
    if not s:
        return None
    s = s.strip()
    # 1. ISO with offset (e.g. "2026-04-30T17:20:07Z" or "...+00:00")
    iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    # 2. Stripped variants
    for fmt in _HUMAN_DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_published_at(html_body: str) -> str:
    """Return ISO-8601 string with tz offset, or '' if no date found."""
    for pat in DATE_PATTERNS:
        m = pat.search(html_body)
        if not m:
            continue
        dt = _parse_date(m.group(1))
        if dt is not None:
            return dt.astimezone(timezone.utc).isoformat()
    return ""


def _extract_article_slugs(index_html: str, article_prefix: str) -> list[str]:
    """Find unique article slugs in the index page that start with article_prefix.

    Accepts both quoted and unquoted href attributes (e.g. Webflow-minified HTML
    uses `href=https://example.com/...`), and tolerates an optional trailing
    slash on the article URL.
    """
    # Normalize prefix so it works whether caller passed "/blog/" or "https://x/blog/"
    if article_prefix.startswith(("http://", "https://")):
        rel_prefix = re.sub(r"^https?://[^/]+", "", article_prefix)
    else:
        rel_prefix = article_prefix
    if not rel_prefix.startswith("/"):
        rel_prefix = "/" + rel_prefix
    if not rel_prefix.endswith("/"):
        rel_prefix = rel_prefix + "/"

    # Build alternation: <full URL prefix>|<relative prefix>. Both may appear.
    alternatives = [re.escape(rel_prefix)]
    if article_prefix.startswith(("http://", "https://")):
        full_prefix = article_prefix.rstrip("/") + "/"
        alternatives.insert(0, re.escape(full_prefix))
    prefix_pat = "(?:" + "|".join(alternatives) + ")"

    # `("?)` captures " or empty. Backreference \1 then matches the same; for
    # unquoted attrs, the slug terminates on whitespace, `>`, `'`, or `"`.
    slug_re = re.compile(
        rf'href\s*=\s*("?){prefix_pat}([a-z0-9][a-z0-9-]*)/?\1(?=[\s>"\'])',
        re.IGNORECASE,
    )
    seen: set[str] = set()
    slugs: list[str] = []
    for m in slug_re.finditer(index_html):
        s = m.group(2)
        if s in seen:
            continue
        seen.add(s)
        slugs.append(s)
    return slugs


def _absolute_article_url(source: Source, slug: str) -> str:
    base = source.article_url_prefix or source.index_url or ""
    if base.startswith(("http://", "https://")):
        if not base.endswith("/"):
            base = base + "/"
        return base + slug
    # treat as path; use index_url's host
    if source.index_url and source.index_url.startswith(("http://", "https://")):
        host = re.match(r"^(https?://[^/]+)", source.index_url).group(1)
        if not base.startswith("/"):
            base = "/" + base
        if not base.endswith("/"):
            base = base + "/"
        return host + base + slug
    return slug  # fallback (unlikely)


# ---------- summary extraction helpers ----------

# Article-page hero / lede paragraphs (CSS-Modules class names contain a stable
# `Hero`+`summary` substring on Anthropic; Webflow has its own structure).
_HERO_SUMMARY_RE = re.compile(
    r'<p[^>]*class="[^"]*Hero[^"]*summary[^"]*"[^>]*>(.*?)</p>',
    re.DOTALL,
)

# og:description values that are clearly the site default (not per-article).
_GENERIC_DESC_PATTERNS = (
    re.compile(r"^Anthropic is an AI safety", re.IGNORECASE),
    re.compile(r"^Discuss, discover, and read", re.IGNORECASE),
)


def _strip_html_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def _is_generic_description(text: str) -> bool:
    return any(p.search(text or "") for p in _GENERIC_DESC_PATTERNS)


def _extract_summary(html_body: str) -> str:
    """Prefer per-article hero summary; fall back to og:description; skip if generic."""
    m = _HERO_SUMMARY_RE.search(html_body)
    if m:
        text = html.unescape(_strip_html_tags(m.group(1))).strip()
        if text:
            return text
    og = _meta_content(html_body, prop="og:description")
    if og and not _is_generic_description(og):
        return og
    nm = _meta_content(html_body, name="description")
    if nm and not _is_generic_description(nm):
        return nm
    return ""


# Title cleanup: drop trailing site suffixes such as " | Claude", " — Google DeepMind",
# " \ Anthropic". Separators: |, \, ·(00b7), –(2013), —(2014).
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[|\\\u00b7\u2013\u2014]\s*(?:Google\s+DeepMind|DeepMind|Anthropic|Claude|OpenAI|Google)\s*$"
)


def _clean_title(t: str) -> str:
    return _TITLE_SUFFIX_RE.sub("", t).strip()


def _fetch_article(source: Source, slug: str) -> tuple[str, Optional[Item], Optional[str]]:
    """Returns (slug, item_or_None, error_or_None).

    Soft-skips off-domain redirects (e.g. blog post moved to a docs site) by
    returning a None item with a `redirected:` error string — these get logged
    but don't fail the source.
    """
    url = _absolute_article_url(source, slug)
    try:
        final_url, body = _fetch(url)
    except Exception as e:
        return slug, None, f"fetch: {type(e).__name__}: {e}"

    # If a 308/301 took us off the configured article prefix host, skip — it's
    # been moved to docs/ or another site we don't model here.
    expected_host = urllib.parse.urlparse(url).netloc
    final_host = urllib.parse.urlparse(final_url).netloc
    if expected_host != final_host:
        return slug, None, f"redirected off-domain: {url} -> {final_url}"

    raw_title = _meta_content(body, prop="og:title")
    if not raw_title:
        m = re.search(r"<title>([^<]*)</title>", body)
        raw_title = html.unescape(m.group(1).strip()) if m else ""
    title = _clean_title(raw_title)
    if not title:
        return slug, None, "title: missing og:title and <title>"

    summary = _extract_summary(body)
    pub_at = _extract_published_at(body)

    summary_short = summary[: INLINE_TEXT_MAX_CHARS // 4]
    item = Item(
        id=url_hash(final_url),
        source_id=source.id,
        source_type=source.type,
        source_tier=source.tier,
        source_lang=source.lang,
        title=title,
        url=final_url,
        published_at=pub_at,
        fetched_at=utc_now_iso(),
        summary=summary_short,
        raw_text="",
        authors=[],
        tags=["scrape", source.id],
        duration_sec=0,
    )
    return slug, item, None


def ingest_scrape(
    source: Source,
    state: SourceState,
) -> tuple[list[Item], str]:
    """Index → article-page scrape ingest.

    Required source fields: index_url, article_url_prefix.
    """
    if not source.index_url or not source.article_url_prefix:
        state.last_error = "config: type=scrape requires index_url + article_url_prefix"
        return [], "fail"

    try:
        _, index_html = _fetch(source.index_url)
    except Exception as e:
        state.last_error = f"index-fetch: {type(e).__name__}: {e}"
        return [], "fail"

    slugs = _extract_article_slugs(index_html, source.article_url_prefix)
    if not slugs:
        state.last_error = "parse: no article slugs found on index page"
        return [], "fail"

    if len(slugs) > MAX_ARTICLES_PER_RUN:
        log.warning(
            "scrape: %s found %d slugs, capping to %d",
            source.id, len(slugs), MAX_ARTICLES_PER_RUN,
        )
        slugs = slugs[:MAX_ARTICLES_PER_RUN]

    items: list[Item] = []
    errors: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=ARTICLE_FETCH_WORKERS) as ex:
        for slug, item, err in ex.map(lambda s: _fetch_article(source, s), slugs):
            if err:
                errors.append(f"{slug}: {err}")
            elif item:
                items.append(item)

    if errors and not items:
        state.last_error = "all fetches failed: " + "; ".join(errors[:3])
        return [], "fail"

    if errors:
        state.last_error = f"{len(errors)}/{len(slugs)} article fetches failed (e.g. {errors[0]})"
    else:
        state.last_error = ""

    return items, "ok"
