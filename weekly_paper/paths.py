"""weekly_paper 自己的数据目录布局（与 weekly_report/data/ 平级独立）。"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
STATE_DIR = DATA_DIR / "state"
ITEMS_DIR = DATA_DIR / "items"
FILTERED_DIR = DATA_DIR / "filtered"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = DATA_DIR / "reports"


def ensure_data_dirs() -> None:
    for d in (STATE_DIR, ITEMS_DIR, FILTERED_DIR, CACHE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# 7 个 topic + noise 兜底
TOPICS = (
    "agent-harness",
    "agent-rl",
    "image-generation",
    "video-generation",
    "vla-embodied",
    "vlm-llm-posttrain",
    "world-model",
)

VALID_TOPIC_TAGS = set(TOPICS) | {"cross", "noise"}
