"""Explicit Qwen3-Embedding-8B adapter for Kven memory retrieval."""

from __future__ import annotations

import math
import os
from typing import Any

import httpx

EMBEDDING_DIMENSION = 4096
EMBEDDING_SPACE_ID = "qwen3-embedding-8b-q8_0:kven-memory-v1"
EMBEDDING_MODEL_NAME = os.getenv(
    "KVEN_EMBEDDING_MODEL",
    "Qwen3-Embedding-8B-Q8_0.gguf",
)
EMBEDDING_URL = os.getenv(
    "KVEN_EMBEDDING_URL",
    "http://127.0.0.1:8081/v1/embeddings",
)
EMBEDDING_TIMEOUT_SECONDS = float(
    os.getenv("KVEN_EMBEDDING_TIMEOUT_SECONDS", "10")
)
QUERY_INSTRUCTION = (
    "Given a memory-retrieval query for a persistent personal AI, retrieve "
    "the passage that most directly and truthfully answers the query. Prefer "
    "the correct subject, entity, project and modality over semantically "
    "similar but unrelated passages."
)


class EmbeddingResponseError(RuntimeError):
    """The embedder returned an unusable or cross-space vector."""


def _input_text(text: str, input_type: str) -> str:
    value = str(text or "").strip()
    if not value:
        raise ValueError("embedding input must not be empty")
    if input_type == "document":
        return value
    if input_type == "query":
        return f"Instruct: {QUERY_INSTRUCTION}\nQuery: {value}"
    raise ValueError(f"unsupported embedding input_type: {input_type!r}")


def _validated_vector(payload: Any) -> list[float]:
    try:
        vector = payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EmbeddingResponseError(
            "embedding response has no data[0].embedding"
        ) from exc
    if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSION:
        size = len(vector) if isinstance(vector, list) else None
        raise EmbeddingResponseError(
            f"embedding dimension mismatch: got={size}, "
            f"expected={EMBEDDING_DIMENSION}"
        )
    result = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in result):
        raise EmbeddingResponseError("embedding contains non-finite values")
    return result


def get_embedding_sync(
    text: str,
    normalize_embeddings: bool = True,
    *,
    input_type: str = "document",
) -> list[float]:
    if not normalize_embeddings:
        raise ValueError(
            "the Qwen retrieval space requires normalized embeddings"
        )
    response = httpx.post(
        EMBEDDING_URL,
        json={
            "model": EMBEDDING_MODEL_NAME,
            "input": _input_text(text, input_type),
        },
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _validated_vector(response.json())


async def get_embedding(
    text: str,
    normalize_embeddings: bool = True,
    *,
    input_type: str = "document",
) -> list[float]:
    if not normalize_embeddings:
        raise ValueError(
            "the Qwen retrieval space requires normalized embeddings"
        )
    async with httpx.AsyncClient(
        timeout=EMBEDDING_TIMEOUT_SECONDS
    ) as client:
        response = await client.post(
            EMBEDDING_URL,
            json={
                "model": EMBEDDING_MODEL_NAME,
                "input": _input_text(text, input_type),
            },
        )
    response.raise_for_status()
    return _validated_vector(response.json())
