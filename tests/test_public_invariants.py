from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kven_public.context_window import Message, assemble_context
from kven_public.memory_identity import MemoryRef
from kven_public.memory_reranker import parse_memory_selection_protocol
from kven_public.memory_store import get_connection, init_schema
from kven_public.person_binding import PersonBindingStore, TransportIdentity
from kven_public.model_adapters.registry import resolve_model_adapter
from kven_public.planner_router import PlannerRouterError
from kven_public.trusted_tools import (
    ContinuationState,
    TrustedObservation,
    TrustedToolContinuation,
)


class PublicInvariantTests(unittest.TestCase):
    def test_memory_identity_is_typed(self):
        self.assertNotEqual(MemoryRef("semantic", 7), MemoryRef("episodic", 7))
        self.assertEqual(
            MemoryRef.parse("semantic:7"),
            MemoryRef("semantic", 7),
        )

    def test_sqlite_forces_delete_mode_without_wal_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "memory.db"
            init_schema(db)
            connection = get_connection(db)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA journal_mode").fetchone()[0].lower(),
                    "delete",
                )
                connection.execute(
                    "INSERT INTO semantic_memory(content) VALUES ('probe')"
                )
                connection.commit()
            finally:
                connection.close()
            self.assertFalse(Path(str(db) + "-wal").exists())
            self.assertFalse(Path(str(db) + "-shm").exists())

    def test_reranker_protocol_fails_closed(self):
        self.assertEqual(
            parse_memory_selection_protocol(
                "MEMORY 2,5",
                allowed_ids={2, 5, 9},
                max_items=2,
            ),
            [2, 5],
        )
        with self.assertRaises(PlannerRouterError):
            parse_memory_selection_protocol(
                "MEMORY 2,999",
                allowed_ids={2, 5, 9},
                max_items=2,
            )

    def test_context_compacts_prefix_but_keeps_source_immutable(self):
        history = (
            Message("user", "old " * 80),
            Message("assistant", "older " * 80),
            Message("user", "current question"),
        )
        result = assemble_context(
            history,
            max_tokens=90,
            reserve_tokens=20,
            summarize_prefix=lambda prefix: "earlier discussion",
        )
        self.assertGreater(result.compacted_prefix_count, 0)
        self.assertEqual(history[-1].content, "current question")
        self.assertEqual(result.messages[-1].content, "current question")

    def test_person_binding_is_transport_scoped_and_non_authorizing(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "people.db")
            store = PersonBindingStore(db)
            store.upsert_person("person-a", "Example Person")
            store.bind(
                TransportIdentity("telegram", "account-a", "123"),
                "person-a",
            )
            self.assertEqual(
                store.resolve(
                    TransportIdentity("telegram", "account-a", "123")
                ),
                ("person-a", "Example Person"),
            )
            self.assertIsNone(
                store.resolve(
                    TransportIdentity("telegram", "different-account", "123")
                )
            )

    def test_qwen_adapter_is_narrow(self):
        adapter = resolve_model_adapter(
            backend_model="Qwen3.6-35B-A3B",
            backend_url="http://127.0.0.1:9999",
        )
        normalizer = adapter.create_stream_content_normalizer(
            phase="main",
            thinking_enabled=False,
        )
        self.assertEqual(normalizer.feed("<think>\n"), "")
        self.assertEqual(normalizer.feed("</think>\nVisible"), "Visible")

        second = adapter.create_stream_content_normalizer(
            phase="main",
            thinking_enabled=False,
        )
        self.assertEqual(
            second.feed("<think>private reasoning</think>Visible"),
            "<think>private reasoning</think>Visible",
        )

    def test_tool_observations_require_executor_provenance(self):
        continuation = TrustedToolContinuation(datetime.now(timezone.utc))
        with self.assertRaises(ValueError):
            continuation.accept(
                TrustedObservation("get_time", "ok", {"iso": "example"}, False)
            )
        self.assertEqual(continuation.state, ContinuationState.FAILED)

    def test_web_continuation_allows_one_selected_fetch(self):
        continuation = TrustedToolContinuation(
            datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        continuation.accept(
            TrustedObservation(
                "web_search",
                "ok",
                {"results": [{"url": "https://example.com/source"}]},
                True,
            )
        )
        continuation.accept(
            TrustedObservation(
                "fetch_url",
                "ok",
                {"url": "https://example.com/source", "text": "observed"},
                True,
            )
        )
        context = continuation.finalization_context()
        self.assertEqual(continuation.state, ContinuationState.FINAL)
        self.assertEqual(len(context["observations"]), 2)
        self.assertIn("ordinary semantic answer", context["instruction"])

    def test_web_continuation_rejects_unselected_or_recursive_hops(self):
        continuation = TrustedToolContinuation(datetime.now(timezone.utc))
        continuation.accept(
            TrustedObservation(
                "web_search", "ok", {"results": [{"url": "https://example.com/a"}]}, True
            )
        )
        with self.assertRaises(ValueError):
            continuation.accept(
                TrustedObservation("fetch_url", "ok", {"url": "https://example.com/b"}, True)
            )


if __name__ == "__main__":
    unittest.main()
