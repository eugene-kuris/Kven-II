"""Completely invented infrastructure evidence; no production fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kven_public.infra_reference import Observation, Snapshot, canonical, digest, export, replay


def obs(object_id="device-amber", value="online", *, prop="status", proof="sample-a"):
    return Observation("DEVICE", object_id, prop, value, f"example:{proof}", digest(proof))


def snap(time, *observations, coverage="COMPLETE", source="example-source", scope="zone-a"):
    return Snapshot(source, scope, time, coverage, observations)


T0 = "2030-01-01T10:00:00Z"
T1 = "2030-01-01T10:01:00Z"
T2 = "2030-01-01T10:02:00Z"


class InfraReferenceTests(unittest.TestCase):
    def test_typed_provenance_and_replay_are_deterministic(self):
        events = (snap(T0, obs(), obs("device-blue")),)
        first = export(events, as_of=T0)
        self.assertEqual(first, export(events, as_of=T0))
        self.assertEqual(first, export((snap(T0, obs("device-blue"), obs()),), as_of=T0))
        result = json.loads(first)
        self.assertEqual(len(result["history"]), 2)
        self.assertTrue(all(record["verification_evidence"][0]["evidence_sha256"]
                            for record in result["history"]))
        self.assertTrue(all(record["current_state_proof"] for record in result["current"]))

    def test_same_scope_repeat_is_reverified_not_semantic_drift(self):
        result = replay((snap(T0, obs()), snap(T1, obs(proof="sample-b"))), as_of=T1)
        self.assertEqual(result["deltas"][1]["changed"], [])
        self.assertEqual(result["deltas"][1]["reverified"], [canonical(["example-source", "zone-a", "DEVICE", "device-amber", "status"])])
        self.assertEqual(result["history"][0]["observed_at"], T0)
        self.assertEqual(result["history"][0]["last_verified_at"], T1)
        self.assertEqual(len(result["history"][0]["verification_evidence"]), 2)

    def test_new_fact_supersedes_old_with_both_provenance_chains(self):
        result = replay((snap(T0, obs()), snap(T1, obs(value="offline", proof="sample-b"))), as_of=T1)
        self.assertEqual(len(result["history"]), 2)
        old = next(item for item in result["history"] if item["value"] == "online")
        new = next(item for item in result["history"] if item["value"] == "offline")
        self.assertEqual(old["superseded_by"], new["fact_id"])
        self.assertEqual(len(result["deltas"][1]["changed"]), 1)

    def test_conflicting_current_evidence_is_unresolved_not_chosen(self):
        result = replay((snap(T0, obs(value="online"), obs(value="offline", proof="sample-b")),), as_of=T0)
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(len(result["current"]), 2)
        self.assertTrue(all(not fact["current_state_proof"] for fact in result["current"]))
        self.assertTrue(all(fact["status"] == "conflicted" for fact in result["current"]))

    def test_partial_reobservation_cannot_resolve_earlier_conflict(self):
        """A partial sample cannot invalidate a competing earlier proof."""
        events = (
            snap(T0, obs(value="online", proof="a"),
                 obs(value="offline", proof="b")),
            snap(T1, obs(value="online", proof="c"), coverage="PARTIAL"),
        )
        result = replay(events, as_of=T1)
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(len(result["current"]), 2)
        self.assertEqual(result["deltas"][1]["removed"], [])
        self.assertEqual(result["deltas"][1]["changed"], [])
        self.assertEqual(len(result["deltas"][1]["unknown"]), 1)
        self.assertEqual(len(result["deltas"][1]["conflicts"]), 1)
        self.assertTrue(all(not fact["current_state_proof"] for fact in result["current"]))
        historical = {fact["value"]: fact for fact in result["history"]}
        self.assertIsNone(historical["offline"]["superseded_by"])
        self.assertEqual(historical["offline"]["last_verified_at"], T0)
        self.assertEqual(historical["online"]["last_verified_at"], T1)

    def test_complete_reobservation_can_resolve_prior_scope_conflict(self):
        events = (
            snap(T0, obs(value="online", proof="a"),
                 obs(value="offline", proof="b")),
            snap(T1, obs(value="online", proof="c"), coverage="COMPLETE"),
        )
        result = replay(events, as_of=T1)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(len(result["current"]), 1)
        self.assertTrue(result["current"][0]["current_state_proof"])
        history = {fact["value"]: fact for fact in result["history"]}
        self.assertEqual(history["offline"]["superseded_by"], history["online"]["fact_id"])

    def test_complete_scope_removes_only_missing_own_scope(self):
        events = (snap(T0, obs()), snap(T0, obs("device-gold"), source="example-other"),
                  snap(T1, coverage="COMPLETE"))
        result = replay(events, as_of=T1)
        self.assertEqual(len(result["deltas"][-1]["removed"]), 1)
        self.assertEqual(len(result["current"]), 1)
        self.assertEqual(result["current"][0]["status"], "historical_only")
        self.assertTrue(any(fact["removed_at"] == T1 for fact in result["history"]))

    def test_partial_absence_never_removes_and_only_seen_fact_freshens(self):
        events = (snap(T0, obs(), obs("device-blue")),
                  snap(T1, obs(proof="sample-b"), coverage="PARTIAL"))
        result = replay(events, as_of=T1)
        self.assertEqual(result["deltas"][-1]["removed"], [])
        self.assertEqual(len(result["deltas"][-1]["unknown"]), 1)
        by_id = {r["native_id"]: r for r in result["history"]}
        self.assertEqual(by_id["device-amber"]["last_verified_at"], T1)
        self.assertEqual(by_id["device-blue"]["last_verified_at"], T0)
        self.assertEqual(sum(r["current_state_proof"] for r in result["current"]), 1)

    def test_failed_collection_proves_neither_absence_nor_freshness(self):
        result = replay((snap(T0, obs()), snap(T1, coverage="FAILED")), as_of=T1)
        self.assertEqual(result["deltas"][-1]["removed"], [])
        self.assertEqual(len(result["deltas"][-1]["unknown"]), 1)
        self.assertEqual(len(result["current"]), 1)
        self.assertFalse(result["current"][0]["current_state_proof"])
        self.assertEqual(result["current"][0]["status"], "historical_only")

    def test_stale_is_not_current_without_new_evidence(self):
        result = replay((snap(T0, obs()),), as_of=T2)
        self.assertFalse(result["current"][0]["current_state_proof"])
        self.assertEqual(result["history"][0]["last_verified_at"], T0)

    def test_scope_isolation_and_stable_native_identity(self):
        events = (snap(T0, obs(), source="alpha", scope="east"),
                  snap(T0, obs(value="offline"), source="alpha", scope="west"),
                  snap(T1, coverage="COMPLETE", source="alpha", scope="east"))
        result = replay(events, as_of=T1)
        self.assertEqual(len(result["deltas"][-1]["removed"]), 1)
        self.assertEqual(len(result["current"]), 1)
        self.assertIn('west', result["current"][0]["key"])

    def test_invalid_evidence_digest_fails_closed(self):
        bad = Observation("DEVICE", "device-amber", "status", "online", "example:bad", "not-a-sha")
        with self.assertRaises(ValueError):
            replay((snap(T0, bad),), as_of=T0)

    def test_failed_snapshot_cannot_smuggle_observations(self):
        with self.assertRaises(ValueError):
            replay((snap(T0, obs(), coverage="FAILED"),), as_of=T0)

    def test_time_must_be_monotonic_and_explicit(self):
        with self.assertRaises(ValueError):
            replay((snap(T1, obs()), snap(T0, obs())), as_of=T2)
        with self.assertRaises(ValueError):
            replay((snap(T0, obs()),), as_of="2030-01-01T10:00:00")

    def test_multiple_corroborating_proofs_are_one_current_value(self):
        result = replay((snap(T0, obs(proof="proof-a"), obs(proof="proof-b")),), as_of=T0)
        self.assertEqual(len(result["history"]), 1)
        self.assertEqual(len(result["current"]), 1)
        self.assertEqual(len(result["history"][0]["verification_evidence"]), 2)
        self.assertEqual(result["conflicts"], [])

    def test_duplicate_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            replay((snap(T0, obs(), obs()),), as_of=T0)

    def test_synthetic_authority_cannot_be_supplied_by_caller(self):
        record = obs()
        self.assertEqual(record.encode()["authority_class"], "synthetic_observation")
        with self.assertRaises(TypeError):
            Observation("DEVICE", "device-amber", "status", "online",
                        "example:proof", digest("proof"), authority_class="trusted_live")

    def test_replay_rejects_forged_snapshot_encoder(self):
        class Impostor:
            def encode(self):
                payload = snap(T0, obs()).encode()
                payload["observations"][0]["authority_class"] = "trusted_live"
                return payload
        with self.assertRaises(ValueError):
            replay((Impostor(),), as_of=T0)

    def test_replay_rejects_subclass_overridden_snapshot_encoder(self):
        class ForgedSnapshot(Snapshot):
            def encode(self):
                payload = super().encode()
                payload["observations"][0]["authority_class"] = "trusted_live"
                return payload
        with self.assertRaises(ValueError):
            replay((ForgedSnapshot("example-source", "zone-a", T0, "COMPLETE", (obs(),)),), as_of=T0)

    def test_snapshot_rejects_subclass_overridden_observation_encoder(self):
        class ForgedObservation(Observation):
            def encode(self):
                payload = super().encode()
                payload["authority_class"] = "trusted_live"
                return payload
        with self.assertRaises(ValueError):
            snap(T0, ForgedObservation("DEVICE", "device-amber", "status", "online",
                                       "example:proof", digest("proof")))

    def test_snapshot_tuple_fields_resist_object_setattr(self):
        event = snap(T0, obs())
        for payload in ([obs()], (object(),), (obs(), object())):
            with self.subTest(payload=str(type(payload))):
                with self.assertRaises(AttributeError):
                    object.__setattr__(event, "observations", payload)
        self.assertEqual(len(replay((event,), as_of=T0)["current"]), 1)

    def test_observation_value_cannot_be_forged_after_construction(self):
        record = obs(value={"state": ["online"]})
        event = snap(T0, record)
        original = export((event,), as_of=T0)
        for field in ("value_json", "kind", "native_id", "property",
                      "evidence_ref", "evidence_sha256"):
            with self.subTest(field=field):
                with self.assertRaises(AttributeError):
                    object.__setattr__(record, field, "forged")
        self.assertEqual(export((event,), as_of=T0), original)

    def test_record_cannot_acquire_mutable_instance_dict(self):
        record, event = obs(), snap(T0, obs())
        self.assertFalse(hasattr(record, "__dict__"))
        self.assertFalse(hasattr(event, "__dict__"))
        for obj in (record, event):
            with self.assertRaises(AttributeError):
                object.__setattr__(obj, "injected", "fake")

    def test_source_metadata_cannot_change_after_construction(self):
        event = snap(T0, obs())
        for field in ("source_id", "scope", "collected_at", "coverage"):
            with self.subTest(field=field):
                with self.assertRaises(AttributeError):
                    object.__setattr__(event, field, "forged")
        self.assertEqual(event.source_id, "example-source")

    def test_replay_rejects_mutable_snapshot_sequence(self):
        with self.assertRaises(ValueError):
            replay([snap(T0, obs())], as_of=T0)

    def test_mutating_caller_value_cannot_change_snapshot_or_export(self):
        value = {"state": ["online", {"label": "original"}]}
        record = obs(value=value)
        events = (snap(T0, record),)
        original = export(events, as_of=T0)
        value["state"][0] = "offline"
        value["state"][1]["label"] = "mutated"
        value["state"].append("extra")
        self.assertEqual(export(events, as_of=T0), original)
        self.assertEqual(record.encode()["value"], {"state": ["online", {"label": "original"}]})
        encoded = record.encode()
        encoded["value"]["state"][0] = "tampered"
        self.assertEqual(export(events, as_of=T0), original)

    def test_snapshot_observations_must_be_immutable_tuple(self):
        with self.assertRaises(ValueError):
            Snapshot("example-source", "zone-a", T0, "COMPLETE", [obs()])

    def test_collected_at_rejects_overridden_replace_string(self):
        class ShiftingTime(str):
            def replace(self, *args, **kwargs):
                return T2  # Not the timestamp held in the underlying str.
        bad_time = ShiftingTime(T0)
        with self.assertRaises(ValueError):
            snap(bad_time, obs())
        # Also exercise the replay/encode boundary by bypassing __new__.
        forged = tuple.__new__(Snapshot, ("example-source", "zone-a", bad_time, "COMPLETE", (obs(),)))
        with self.assertRaises(ValueError):
            replay((forged,), as_of=T2)
        with self.assertRaises(ValueError):
            forged.encode()

    def test_coverage_rejects_overridden_equality_string(self):
        class SpoofCoverage(str):
            def __eq__(self, other):
                return True
            __hash__ = str.__hash__
        spoofed = SpoofCoverage("FAILED")
        with self.assertRaises(ValueError):
            snap(T0, obs(), coverage=spoofed)
        forged = tuple.__new__(Snapshot, ("example-source", "zone-a", T0, spoofed, (obs(),)))
        with self.assertRaises(ValueError):
            replay((forged,), as_of=T0)
        with self.assertRaises(ValueError):
            forged.encode()

    def test_as_of_rejects_str_subclass_and_fake_parser(self):
        class FakeAsOf(str):
            def replace(self, *args, **kwargs):
                return T0
        for malformed in (FakeAsOf(T1), object()):
            with self.subTest(type=type(malformed).__name__):
                with self.assertRaises(ValueError):
                    replay((snap(T0, obs()),), as_of=malformed)
        # Valid exact UTC timestamps still work.
        self.assertEqual(len(replay((snap(T0, obs()),), as_of=T0)["current"]), 1)

    def test_observation_rejects_polymorphic_identity_strings(self):
        class ForgedId(str):
            def __hash__(self):
                return hash("spoofed")
        with self.assertRaises(ValueError):
            Observation(ForgedId("DEVICE"), "device-amber", "status", "online",
                        "example:proof", digest("proof"))
        bad = tuple.__new__(Observation, ("DEVICE", "device-amber", "status", '"online"',
                                         "example:proof", ForgedId(digest("proof"))))
        with self.assertRaises(ValueError):
            replay((snap(T0, bad),), as_of=T0)


    def test_value_json_tuple_graft_malformed_and_noncanonical_are_rejected(self):
        original = obs()
        valid = original.value_json
        bad_payloads = (["online"], {"x": "y"}, object(), "not-json", "{ \"b\":2, \"a\":1 }",
                        "{\"x\":1,\"x\":2}", "NaN", " 1.0", "true ")
        for forged_payload in bad_payloads:
            with self.subTest(payload=repr(forged_payload)):
                forged = tuple.__new__(Observation, (
                    original.kind, original.native_id, original.property,
                    forged_payload, original.evidence_ref, original.evidence_sha256))
                with self.assertRaises(ValueError):
                    forged.encode()
                with self.assertRaises(ValueError):
                    replay((snap(T0, forged),), as_of=T0)
        self.assertEqual(original.value_json, valid)

    def test_value_json_str_subclass_overrides_are_rejected(self):
        class VolatileJSON(str):
            def __str__(self):
                return '"forged"'
            def replace(self, *args, **kwargs):
                return '"forged"'
        original = obs()
        forged = tuple.__new__(Observation, (original.kind, original.native_id,
            original.property, VolatileJSON(original.value_json),
            original.evidence_ref, original.evidence_sha256))
        with self.assertRaises(ValueError):
            replay((snap(T0, forged),), as_of=T0)

    def test_snapshot_subclass_tuple_graft_rejected_by_replay(self):
        class RogueSnapshot(Snapshot):
            def encode(self):
                raise AssertionError("must never invoke polymorphic encoder")
        forged = tuple.__new__(RogueSnapshot, (
            "example-source", "zone-a", T0, "COMPLETE", (obs(),)))
        with self.assertRaises(ValueError):
            replay((forged,), as_of=T0)
        with self.assertRaises(ValueError):
            Snapshot.encode(forged)

    def test_observation_subclass_tuple_graft_rejected_by_snapshot_encoder(self):
        class RogueObservation(Observation):
            def encode(self):
                raise AssertionError("must never invoke polymorphic encoder")
        src = obs()
        forged = tuple.__new__(RogueObservation, (
            src.kind, src.native_id, src.property, src.value_json,
            src.evidence_ref, src.evidence_sha256))
        with self.assertRaises(ValueError):
            snap(T0, forged)
        raw = tuple.__new__(Snapshot, (
            "example-source", "zone-a", T0, "COMPLETE", (forged,)))
        with self.assertRaises(ValueError):
            replay((raw,), as_of=T0)

    def test_replay_is_derived_and_does_not_mutate_input(self):
        record = obs()
        events = (snap(T0, record),)
        old = canonical(events[0].encode())
        self.assertEqual(export(events, as_of=T0), export(events, as_of=T0))
        self.assertEqual(canonical(events[0].encode()), old)


if __name__ == "__main__":
    unittest.main()
