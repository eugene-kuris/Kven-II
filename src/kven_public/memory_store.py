"""Minimal public form of Kven's authoritative SQLite memory store."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .provenance import dumps as dump_provenance

DEFAULT_DB_PATH = "data/kven-memory.db"


def get_connection(db_path: str | os.PathLike[str] = DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
    if str(mode).lower() != "delete":
        connection.close()
        raise RuntimeError(
            f"Kven-owned SQLite must use DELETE journal mode, got {mode!r}"
        )
    return connection


def init_schema(db_path: str | os.PathLike[str] = DEFAULT_DB_PATH) -> None:
    connection = get_connection(db_path)
    try:
        for table, default_importance, default_decay in (
            ("semantic_memory", 0.5, 0.96),
            ("episodic_memory", 0.3, 0.85),
        ):
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT '{table.split("_")[0]}',
                    importance REAL NOT NULL DEFAULT {default_importance},
                    tags TEXT NOT NULL DEFAULT '[]',
                    epistemic_type TEXT NOT NULL DEFAULT 'Observation',
                    source TEXT NOT NULL DEFAULT 'model_inference',
                    provenance_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    decay_rate REAL NOT NULL DEFAULT {default_decay},
                    deleted INTEGER NOT NULL DEFAULT 0,
                    usage_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        connection.commit()
    finally:
        connection.close()


def insert_memory(
    db_path: str | os.PathLike[str],
    *,
    table: str,
    content: str,
    importance: float,
    tags: str = "[]",
    decay_rate: float,
    epistemic_type: str = "Observation",
    source: str = "model_inference",
    provenance=None,
) -> int:
    if table not in {"semantic_memory", "episodic_memory"}:
        raise ValueError(f"unsupported memory table: {table!r}")
    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            f"""
            INSERT INTO {table}
            (content, importance, tags, decay_rate,
             epistemic_type, source, provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content,
                importance,
                tags,
                decay_rate,
                epistemic_type,
                source,
                dump_provenance(provenance),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()
