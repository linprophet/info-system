"""JSONL/JSON 持久化：原子写入、SeenIndex 去重、week-id 工具。

设计原则（见 README）：
- JSONL append-only；每个 stage 一份独立文件，方便人工 review / git diff
- 大字段（transcript/全文）外置到 cache/，主 jsonl 只放路径
- state/ 目录小文件，commit 进 git；items/filtered/clusters/cache gitignore
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
STATE_DIR = DATA_DIR / "state"
ITEMS_DIR = DATA_DIR / "items"
FILTERED_DIR = DATA_DIR / "filtered"
CLUSTERS_DIR = DATA_DIR / "clusters"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = DATA_DIR / "reports"


def ensure_data_dirs() -> None:
    for d in (STATE_DIR, ITEMS_DIR, FILTERED_DIR, CLUSTERS_DIR, CACHE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------- week ids ----------


def iso_week_id(d: date | datetime | None = None) -> str:
    """ISO 8601 week id, e.g. 2026-W18 (Monday-anchored)."""
    if d is None:
        d = datetime.now(timezone.utc).date()
    if isinstance(d, datetime):
        d = d.date()
    y, w, _ = d.isocalendar()
    return f"{y:04d}-W{w:02d}"


def week_bounds(week_id: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a given ISO week id like '2026-W18'.

    start = Monday 00:00:00 UTC, end = next Monday 00:00:00 UTC (exclusive).
    """
    y, w = week_id.split("-W")
    # ISO week 1 is the week containing the first Thursday of the year.
    jan4 = date(int(y), 1, 4)
    jan4_dow = jan4.isocalendar()[2]  # 1..7 (Mon..Sun)
    week1_mon = jan4 - timedelta(days=jan4_dow - 1)
    start_date = week1_mon + timedelta(weeks=int(w) - 1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


# ---------- atomic JSON / JSONL helpers ----------


def _default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(f"not serializable: {type(o)}")


def write_json_atomic(path: Path, obj: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, default=_default)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def append_jsonl(path: Path, items: Iterable[dict]) -> int:
    """Append items to a jsonl file, one per line. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False, default=_default) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


# ---------- SeenIndex (cross-week dedup) ----------


@dataclass
class SeenEntry:
    url_hash: str
    source_id: str
    first_seen_at: str  # ISO timestamp


class SeenIndex:
    """Append-only set of url hashes to dedupe across weeks.

    On startup loads the whole file into memory (set lookup O(1)). Writes are
    append-only and immediately fsynced. At ~25万 entries the file is ~10MB
    and load is sub-second; we'll shard by year if it ever grows past that.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._mem: set[str] = set()
        if path.exists():
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._mem.add(json.loads(line)["url_hash"])
                    except Exception:
                        continue
        self._fp = path.open("a", encoding="utf-8")

    def __contains__(self, h: str) -> bool:
        return h in self._mem

    def __len__(self) -> int:
        return len(self._mem)

    def add(self, url_hash: str, source_id: str) -> bool:
        """Add a hash. Returns True if it was new (and persisted), False if already seen."""
        if url_hash in self._mem:
            return False
        self._mem.add(url_hash)
        entry = SeenEntry(
            url_hash=url_hash,
            source_id=source_id,
            first_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        self._fp.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        self._fp.flush()
        return True

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass

    def __enter__(self) -> "SeenIndex":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ---------- per-source pipeline state ----------


@dataclass
class SourceState:
    source_id: str
    last_run_at: str = ""
    last_run_status: str = ""  # "ok" | "fail" | "partial"
    last_seen_at: str = ""  # most recent item.published_at we've ingested
    last_seen_url: str = ""
    last_error: str = ""
    consecutive_failures: int = 0
    youtube_channel_id: str = ""  # cached after first resolve
    items_ingested_total: int = 0
    extras: dict = field(default_factory=dict)


class StateFile:
    """Wraps state/sources.json. Always writes atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path
        raw = read_json(path, default={}) or {}
        self._state: dict[str, SourceState] = {
            sid: SourceState(**v) for sid, v in raw.items()
        }

    def get(self, source_id: str) -> SourceState:
        if source_id not in self._state:
            self._state[source_id] = SourceState(source_id=source_id)
        return self._state[source_id]

    def set(self, state: SourceState) -> None:
        self._state[state.source_id] = state

    def all(self) -> list[SourceState]:
        return list(self._state.values())

    def save(self) -> None:
        write_json_atomic(self.path, {sid: asdict(s) for sid, s in self._state.items()})


# ---------- timing util ----------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def perf() -> float:
    return time.perf_counter()
