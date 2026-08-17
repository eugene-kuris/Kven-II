"""Narrow planner client and strict single-line protocol helpers."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

PLANNER_MODEL = os.getenv(
    "KVEN_PLANNER_MODEL",
    "Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf",
)
PLANNER_URL = os.getenv(
    "KVEN_PLANNER_URL",
    "http://127.0.0.1:8080/v1/chat/completions",
)
DEFAULT_TIMEOUT_SECONDS = 20.0


class PlannerRouterError(RuntimeError):
    """Planner routing failed or returned an invalid result."""


def single_protocol_line(text: str) -> str:
    lines = [
        line.strip()
        for line in str(text or "").splitlines()
        if line.strip()
    ]
    if len(lines) != 1:
        raise PlannerRouterError(
            "planner did not return exactly one protocol line"
        )
    return lines[0]


async def post_planner_text(
    prompt: str,
    *,
    max_tokens: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": PLANNER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
        "stop": ["\n"],
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_format": "none",
    }

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(PLANNER_URL, json=payload)
    elapsed = time.perf_counter() - started

    response.raise_for_status()
    data = response.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}

    return str(message.get("content") or ""), {
        "elapsed_seconds": round(elapsed, 3),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }
