from __future__ import annotations

from typing import Any, Mapping


class StreamContentNormalizer:
    """Stateful pass-through normalizer for streamed backend content."""

    def feed(self, text: str) -> str:
        return str(text or "")

    def finish(self) -> str:
        return ""


class ModelBackendAdapter:
    """Compatibility boundary between Kven II and a model/backend pair."""

    adapter_id = "base"

    def matches(
        self,
        *,
        backend_model: str,
        backend_url: str,
    ) -> bool:
        return False

    def prepare_request(
        self,
        payload: Mapping[str, Any],
        *,
        phase: str,
    ) -> dict[str, Any]:
        return dict(payload)

    def normalize_complete_content(
        self,
        content: str,
        *,
        phase: str,
    ) -> str:
        return content

    def create_stream_content_normalizer(
        self,
        *,
        phase: str,
        thinking_enabled: bool,
    ) -> StreamContentNormalizer:
        return StreamContentNormalizer()

    def forbidden_stream_markers(
        self,
        *,
        phase: str,
    ) -> tuple[str, ...]:
        return ()
