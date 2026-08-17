"""Validate or rebuild the typed HNSW cache from authoritative SQLite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import hnswlib

from .embedder import EMBEDDING_DIMENSION, EMBEDDING_SPACE_ID
from .index_rebuild import authoritative_rows, rebuild


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pair(db_path: str, index_path: str) -> tuple[bool, str]:
    index_file = Path(index_path)
    map_file = Path(index_path + ".id_map.json")
    expected = {str(ref) for ref, _ in authoritative_rows(db_path)}

    if (
        not index_file.is_file()
        or index_file.is_symlink()
        or not map_file.is_file()
        or map_file.is_symlink()
    ):
        return False, "missing or non-regular pair"

    try:
        data = json.loads(map_file.read_text(encoding="utf-8"))
        if data.get("version") != 3 or not isinstance(data.get("refs"), dict):
            return False, "legacy or malformed typed map"
        if (
            data.get("embedding_space") != EMBEDDING_SPACE_ID
            or data.get("dimension") != EMBEDDING_DIMENSION
        ):
            return False, "embedding-space mismatch"
        if data.get("index_sha256") != _sha256(index_file):
            return False, "mixed index/map generation"
        if set(data["refs"]) != expected:
            return False, "typed map incomplete versus SQLite"

        labels = {int(value) for value in data["refs"].values()}
        if len(labels) != len(data["refs"]):
            return False, "duplicate internal labels"

        index = hnswlib.Index(space="cosine", dim=EMBEDDING_DIMENSION)
        index.load_index(
            str(index_file),
            max_elements=max(1, len(expected)),
        )
        if (
            int(index.get_current_count()) != len(expected)
            or set(map(int, index.get_ids_list())) != labels
        ):
            return False, "index count or labels mismatch"
        return True, "complete"
    except Exception as exc:
        return False, f"invalid pair: {type(exc).__name__}"


async def ensure_index(db_path: str, index_path: str, embed) -> dict:
    valid, reason = validate_pair(db_path, index_path)
    if valid:
        return {
            "action": "reused",
            "reason": reason,
            "count": len(authoritative_rows(db_path)),
        }

    result = await rebuild(db_path, index_path, embed)
    valid, after_reason = validate_pair(db_path, index_path)
    if not valid:
        raise RuntimeError(
            f"rebuilt typed index failed validation: {after_reason}"
        )
    return {
        "action": "rebuilt",
        "reason": reason,
        "count": result["count"],
    }
