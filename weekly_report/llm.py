"""DeepSeek API client wrapper.

DeepSeek is OpenAI-compatible. We use the openai SDK with a custom base_url.

Provides:
- chat_json(prompt, ...): force-JSON-mode chat completion with retry
- chat_text(prompt, ...): plain text chat completion with retry
- estimate_cost(usage, model): rough $ from token usage

Reads from env (loaded via python-dotenv if .env present):
    DEEPSEEK_API_KEY        — required
    DEEPSEEK_BASE_URL       — default https://api.deepseek.com
    DEEPSEEK_MODEL_FILTER   — default deepseek-v4-pro
    DEEPSEEK_MODEL_SYNTH    — default deepseek-v4-pro
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import APIError, OpenAI, RateLimitError


HERE = Path(__file__).parent
REPO_ROOT = HERE.parent

# Load .env at import time so callers don't have to.
load_dotenv(REPO_ROOT / ".env")

log = logging.getLogger(__name__)


# DeepSeek pricing (per 1M tokens, USD, cache-miss rates). Source: deepseek.com/pricing.
# v4-pro: $0.435 in / $0.87 out (75% off list through 2026-05-31; list is $1.74/$3.48)
# v4-flash: cheaper preview-tier alternative
# Values are approximations — used only for run-cost telemetry.
PRICING = {
    "deepseek-v4-pro":   {"input": 0.435, "output": 0.87},
    "deepseek-v4-flash": {"input": 0.075, "output": 0.30},
    "deepseek-chat":     {"input": 0.27,  "output": 1.10},
    "deepseek-reasoner": {"input": 0.55,  "output": 2.19},
}

DEFAULT_MODEL = "deepseek-v4-pro"


@dataclass
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_s: float

    @property
    def cost_usd(self) -> float:
        p = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        return (
            self.input_tokens / 1_000_000 * p["input"]
            + self.output_tokens / 1_000_000 * p["output"]
        )


class CostTracker:
    """Aggregate token usage across multiple LLM calls in a single pipeline run."""

    def __init__(self) -> None:
        self.calls: list[LLMUsage] = []

    def add(self, u: LLMUsage) -> None:
        self.calls.append(u)

    @property
    def total_input(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_cost(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_elapsed(self) -> float:
        return sum(c.elapsed_s for c in self.calls)

    def summary(self) -> str:
        return (
            f"{len(self.calls)} call(s) · "
            f"in={self.total_input} out={self.total_output} tokens · "
            f"${self.total_cost:.4f} · {self.total_elapsed:.1f}s"
        )


# ---------- client ----------


def _client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. Put it in .env or export it."
        )
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)


def model_filter() -> str:
    return os.environ.get("DEEPSEEK_MODEL_FILTER", DEFAULT_MODEL)


def model_synth() -> str:
    return os.environ.get("DEEPSEEK_MODEL_SYNTH", DEFAULT_MODEL)


# ---------- core call with retry ----------


def _call(
    *,
    model: str,
    system: str,
    user: str,
    response_format: Optional[dict[str, Any]] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    max_retries: int = 4,
    tracker: Optional[CostTracker] = None,
) -> tuple[str, LLMUsage]:
    cli = _client()
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
    }
    if response_format:
        kwargs["response_format"] = response_format
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    delay = 2.0
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        t0 = time.perf_counter()
        try:
            resp = cli.chat.completions.create(**kwargs)
            elapsed = time.perf_counter() - t0
            content = resp.choices[0].message.content or ""
            usage = LLMUsage(
                model=model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                elapsed_s=elapsed,
            )
            if tracker is not None:
                tracker.add(usage)
            return content, usage
        except RateLimitError as e:
            last_exc = e
            log.warning(
                "rate limit (attempt %d/%d), sleeping %.1fs", attempt + 1, max_retries, delay
            )
        except APIError as e:
            last_exc = e
            log.warning(
                "api error (attempt %d/%d): %s", attempt + 1, max_retries, e
            )
        except Exception as e:
            last_exc = e
            log.warning("call error (attempt %d/%d): %s", attempt + 1, max_retries, e)
        time.sleep(delay)
        delay = min(delay * 2, 30.0)
    raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_exc}")


def chat_text(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    tracker: Optional[CostTracker] = None,
) -> tuple[str, LLMUsage]:
    return _call(
        model=model or model_synth(),
        system=system,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
        tracker=tracker,
    )


def chat_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    tracker: Optional[CostTracker] = None,
) -> tuple[Any, LLMUsage]:
    """Forces JSON mode. Returns parsed JSON (object or list)."""
    raw, usage = _call(
        model=model or model_filter(),
        system=system,
        user=user,
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=max_tokens,
        tracker=tracker,
    )
    try:
        return json.loads(raw), usage
    except json.JSONDecodeError as e:
        # Defensive: sometimes models wrap JSON in ```...``` despite mode.
        raw_stripped = raw.strip()
        if raw_stripped.startswith("```"):
            raw_stripped = raw_stripped.strip("`").lstrip("json").strip()
            try:
                return json.loads(raw_stripped), usage
            except Exception:
                pass
        raise RuntimeError(f"LLM did not return valid JSON: {e}\n--- raw ---\n{raw[:500]}")
