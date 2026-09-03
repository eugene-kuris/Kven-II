"""Public-safe representative trusted-tool continuation state machine.

This is an adapted, standalone expression of production invariants. It has no
network or runtime coupling: callers supply observations from their executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class ContinuationState(str, Enum):
    READY = "ready"
    SEARCH_OBSERVED = "search_observed"
    FETCH_OBSERVED = "fetch_observed"
    FINAL = "final"
    FAILED = "failed"


@dataclass(frozen=True)
class TrustedObservation:
    tool_name: str
    status: str
    result: Any
    trusted_executor_provenance: bool


@dataclass
class TrustedToolContinuation:
    """Accept trusted observations and permit one bounded search fetch hop."""

    request_time: datetime
    state: ContinuationState = ContinuationState.READY
    observations: list[TrustedObservation] = field(default_factory=list)
    _search_urls: frozenset[str] = frozenset()

    def accept(self, observation: TrustedObservation) -> None:
        if self.state in {ContinuationState.FINAL, ContinuationState.FAILED}:
            raise RuntimeError("continuation is already terminal")
        if not observation.trusted_executor_provenance:
            self.state = ContinuationState.FAILED
            raise ValueError("untrusted tool observations fail closed")
        if observation.status != "ok":
            self.state = ContinuationState.FAILED
            raise ValueError("failed tool observations fail closed")

        if observation.tool_name == "web_search":
            if self.state is not ContinuationState.READY:
                raise ValueError("web search is allowed only as the first hop")
            self._search_urls = frozenset(_result_urls(observation.result))
            self.state = ContinuationState.SEARCH_OBSERVED
        elif observation.tool_name == "fetch_url":
            if self.state is not ContinuationState.SEARCH_OBSERVED:
                raise ValueError("fetch requires one preceding trusted search")
            fetched_url = str((observation.result or {}).get("url", ""))
            if fetched_url not in self._search_urls:
                raise ValueError("fetch URL was not selected from search results")
            self.state = ContinuationState.FETCH_OBSERVED
        elif observation.tool_name == "get_time":
            if self.state is not ContinuationState.READY:
                raise ValueError("time is a terminal single-hop observation")
        else:
            raise ValueError("tool is outside this representative public policy")
        self.observations.append(observation)

    def finalization_context(self) -> dict[str, Any]:
        if not self.observations:
            raise ValueError("a trusted observation is required")
        self.state = ContinuationState.FINAL
        return {
            "trusted_request_time": self.request_time.astimezone().isoformat(),
            "observations": [
                {"tool": item.tool_name, "result": item.result}
                for item in self.observations
            ],
            "instruction": "Render an ordinary semantic answer, not tool protocol JSON.",
        }


def _result_urls(result: Any) -> list[str]:
    rows = result.get("results", []) if isinstance(result, dict) else []
    urls = []
    for row in rows:
        url = str(row.get("url", "")) if isinstance(row, dict) else ""
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(url)
    return urls
