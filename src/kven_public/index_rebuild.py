"""Offline typed-index reconstruction from authoritative SQLite memory rows."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile

import hnswlib
import numpy as np

from .embedder import EMBEDDING_DIMENSION, EMBEDDING_SPACE_ID
from .memory_identity import MemoryRef


def authoritative_rows(db_path):
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = []
        for kind in ("episodic", "semantic"):
            rows.extend(
                (MemoryRef(kind, row[0]), row[1])
                for row in connection.execute(
                    f"SELECT id, content FROM {kind}_memory "
                    "WHERE deleted = 0 ORDER BY id"
                )
            )
        return rows
    finally:
        connection.close()


async def rebuild(db_path, index_path, embed):
    rows = authoritative_rows(db_path)
    expected = {str(ref) for ref, _ in rows}
    destination = os.path.dirname(index_path) or "."
    os.makedirs(destination, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".typed-memory-rebuild-", dir=destination
    ) as staging:
        staged_index = os.path.join(staging, "hnsw_index.bin")
        staged_map = staged_index + ".id_map.json"

        index = hnswlib.Index(space="cosine", dim=EMBEDDING_DIMENSION)
        index.init_index(
            max_elements=max(1, len(rows)),
            ef_construction=200,
            M=16,
        )

        mapping = {}
        for label, (ref, content) in enumerate(rows, 1):
            vector = np.asarray(await embed(content), dtype=np.float32)
            if vector.shape != (EMBEDDING_DIMENSION,):
                raise ValueError(
                    f"invalid embedding shape for {ref}: {vector.shape}"
                )
            index.add_items(
                vector.reshape(1, -1),
                np.asarray([label], dtype=np.int64),
            )
            mapping[str(ref)] = label

        index.save_index(staged_index)

        digest = hashlib.sha256()
        with open(staged_index, "rb") as binary:
            for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                digest.update(chunk)

        with open(staged_map, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 3,
                    "embedding_space": EMBEDDING_SPACE_ID,
                    "dimension": EMBEDDING_DIMENSION,
                    "index_sha256": digest.hexdigest(),
                    "refs": mapping,
                },
                handle,
                sort_keys=True,
            )
            handle.flush()
            os.fsync(handle.fileno())

        if set(mapping) != expected or index.get_current_count() != len(expected):
            raise RuntimeError("typed rebuild completeness validation failed")

        os.replace(staged_index, index_path)
        os.replace(staged_map, index_path + ".id_map.json")

    return {"count": len(expected), "refs": sorted(expected)}
