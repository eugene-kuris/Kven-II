"""Representative token-budgeted conversation context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class ContextAssembly:
    messages: tuple[Message, ...]
    compacted_prefix_count: int
    estimated_tokens: int


def default_token_estimate(text: str) -> int:
    """Cheap conservative estimate when a model tokenizer is not injected."""
    value = str(text or "")
    return max(1, (len(value) + 2) // 3)


def assemble_context(
    history: Iterable[Message],
    *,
    max_tokens: int,
    reserve_tokens: int,
    summarize_prefix: Callable[[tuple[Message, ...]], str],
    token_count: Callable[[str], int] = default_token_estimate,
) -> ContextAssembly:
    """
    Preserve recent dialogue verbatim and compact only the older prefix.

    Source history is supplied by the caller and is never mutated or deleted.
    """
    messages = tuple(history)
    usable = int(max_tokens) - int(reserve_tokens)
    if usable < 1:
        raise ValueError("reserve_tokens leaves no usable context budget")

    def message_cost(message: Message) -> int:
        return token_count(message.role) + token_count(message.content) + 4

    total = sum(message_cost(message) for message in messages)
    if total <= usable:
        return ContextAssembly(messages, 0, total)

    kept_reversed = []
    kept_cost = 0
    split = len(messages)

    for index in range(len(messages) - 1, -1, -1):
        cost = message_cost(messages[index])
        if kept_reversed and kept_cost + cost > usable:
            break
        kept_reversed.append(messages[index])
        kept_cost += cost
        split = index

    prefix = messages[:split]
    recent = tuple(reversed(kept_reversed))

    if not prefix:
        return ContextAssembly(recent, 0, kept_cost)

    summary = str(summarize_prefix(prefix) or "").strip()
    if not summary:
        raise ValueError("prefix summarizer returned an empty summary")

    summary_message = Message(
        role="system",
        content=(
            "Earlier conversation summary (derived from retained source "
            f"history):\n{summary}"
        ),
    )

    while recent and (
        message_cost(summary_message)
        + sum(message_cost(item) for item in recent)
        > usable
    ):
        recent = recent[1:]

    final = (summary_message, *recent)
    final_cost = sum(message_cost(item) for item in final)
    if final_cost > usable:
        raise ValueError("summary alone exceeds the usable context budget")

    return ContextAssembly(
        messages=final,
        compacted_prefix_count=len(prefix),
        estimated_tokens=final_cost,
    )
