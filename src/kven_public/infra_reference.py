"""Synthetic, pure-Python infrastructure evidence/replay reference.

This is *not* the deployed private collector, a production state store, or a
connector. Inputs are tuple-backed immutable records with canonicalized nested values.
The module is illustrative, not an authorization/security boundary.
The result can be rebuilt from the ordered synthetic input snapshots.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal


Coverage = Literal["COMPLETE", "PARTIAL", "FAILED"]


def canonical(value: Any) -> str:
    """Deterministic UTF-8 JSON; never interpret input as commands or authority."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _instant(value: str) -> datetime:
    # Do not execute overridden str.replace() from untrusted subclasses.
    if type(value) is not str:
        raise ValueError("timestamp must be an exact str")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid observation timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware observation timestamp required")
    return parsed.astimezone(timezone.utc)


class Observation(namedtuple("_ObservationFields", "kind native_id property value_json evidence_ref evidence_sha256")):
    """Tuple-backed record: fields cannot be changed via object.__setattr__."""

    __slots__ = ()

    def __new__(cls, kind: str, native_id: str, property: str, value: Any,
                evidence_ref: str, evidence_sha256: str):
        if cls is not Observation:
            raise ValueError("only exact synthetic Observation records are supported")
        if not all(type(item) is str and item for item in (
            kind, native_id, property, evidence_ref, evidence_sha256
        )):
            raise ValueError("observation identifiers and evidence must be exact strings")
        return super().__new__(cls, kind, native_id, property, canonical(value),
                               evidence_ref, evidence_sha256)

    def encode(self) -> dict[str, Any]:
        if type(self) is not Observation:
            raise ValueError("unexpected observation type")
        if not all(type(x) is str and x for x in (
            self.kind, self.native_id, self.property, self.evidence_ref,
        )):
            raise ValueError("typed identity and evidence reference are required")
        if (type(self.evidence_sha256) is not str or len(self.evidence_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in self.evidence_sha256)):
            raise ValueError("evidence SHA256 must be a lowercase 64-hex digest")
        # Even tuple-backed records can be fabricated via tuple.__new__.
        # Reject non-string, non-JSON, or noncanonical value payloads before replay.
        if type(self.value_json) is not str:
            raise ValueError("stored observation JSON must be an exact str")
        try:
            value = json.loads(self.value_json)
            if canonical(value) != self.value_json:
                raise ValueError("observation JSON is not canonical")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid canonical observation JSON") from exc
        return {"kind": self.kind, "native_id": self.native_id,
                "property": self.property, "value": value,
                "evidence_ref": self.evidence_ref,
                "evidence_sha256": self.evidence_sha256,
                "authority_class": "synthetic_observation"}


class Snapshot(namedtuple("_SnapshotFields", "source_id scope collected_at coverage observations")):
    """Tuple-backed snapshot, rejecting mutable observation containers."""

    __slots__ = ()

    def __new__(cls, source_id: str, scope: str, collected_at: str,
                coverage: Coverage, observations: tuple[Observation, ...] = ()):
        if cls is not Snapshot:
            raise ValueError("only exact synthetic Snapshot records are supported")
        if not all(type(item) is str for item in (source_id, scope, collected_at, coverage)):
            raise ValueError("snapshot metadata must contain exact immutable strings")
        if type(observations) is not tuple or any(type(item) is not Observation for item in observations):
            raise ValueError("snapshot observations must be a tuple of exact Observation records")
        return super().__new__(cls, source_id, scope, collected_at, coverage, observations)

    @staticmethod
    def _require_exact_members(snapshot: "Snapshot") -> None:
        if (type(snapshot) is not Snapshot or type(snapshot.observations) is not tuple or
                any(type(item) is not Observation for item in snapshot.observations)):
            raise ValueError("synthetic snapshot requires exact immutable input types")

    def encode(self) -> dict[str, Any]:
        Snapshot._require_exact_members(self)
        if type(self.source_id) is not str or not self.source_id or type(self.scope) is not str or not self.scope:
            raise ValueError("source and declared scope are required")
        if type(self.collected_at) is not str or type(self.coverage) is not str:
            raise ValueError("snapshot timestamp and coverage require exact str values")
        _instant(self.collected_at)
        if self.coverage not in ("COMPLETE", "PARTIAL", "FAILED"):
            raise ValueError("invalid coverage")
        if self.coverage == "FAILED" and self.observations:
            raise ValueError("FAILED coverage cannot attest any observations")
        observations = sorted((Observation.encode(item) for item in self.observations), key=canonical)
        if len({canonical(item) for item in observations}) != len(observations):
            raise ValueError("duplicate immutable observation")
        keys = [(item["kind"], item["native_id"], item["property"], item["evidence_ref"])
                for item in observations]
        if len(keys) != len(set(keys)):
            raise ValueError("one evidence reference cannot attest contradictory values")
        return {"source_id": self.source_id, "scope": self.scope,
                "collected_at": self.collected_at, "coverage": self.coverage,
                "observations": observations}


def _key(source_id: str, scope: str, item: dict[str, Any]) -> tuple[str, ...]:
    return source_id, scope, item["kind"], item["native_id"], item["property"]


def _tag(key: tuple[str, ...]) -> str:
    return canonical(key)


def replay(snapshots: tuple[Snapshot, ...], *, as_of: str) -> dict[str, Any]:
    """Rebuild a derived projection from ordered tuple-backed snapshots.

    No access to networks, secrets, disks, or system time. `as_of` is supplied by
    the caller; it is NOT proof of current infrastructure state. An absent fact
    is removed only under COMPLETE coverage of its own source/scope.
    """
    if type(snapshots) is not tuple or any(type(item) is not Snapshot for item in snapshots):
        raise ValueError("replay requires a tuple of exact synthetic Snapshot records")
    reference_time = _instant(as_of)
    active: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    history: list[dict[str, Any]] = []
    latest: dict[tuple[str, str], dict[str, str]] = {}
    deltas: list[dict[str, Any]] = []
    for snapshot in snapshots:
        # Re-check exact nested types before taking the encoded evidence.
        # Do not trust constructor-only validation of a possibly grafted object.
        Snapshot._require_exact_members(snapshot)
        # Never trust an arbitrary duck-typed encode() as source authority.
        run = Snapshot.encode(snapshot)
        for item in run["observations"]:
            item["authority_class"] = "synthetic_observation"
        timestamp = _instant(run["collected_at"])
        if timestamp > reference_time:
            raise ValueError("snapshot cannot be observed in the future")
        origin = (run["source_id"], run["scope"])
        prior = latest.get(origin)
        if prior and timestamp < _instant(prior["collected_at"]):
            raise ValueError("snapshot order regresses within source/scope")
        latest[origin] = {"coverage": run["coverage"], "collected_at": run["collected_at"]}
        seen: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for obs in run["observations"]:
            seen.setdefault(_key(*origin, obs), []).append(obs)
        delta: dict[str, Any] = {"bundle_sha256": digest(run), "source_id": origin[0],
                                 "scope": origin[1], "coverage": run["coverage"],
                                 "added": [], "changed": [], "removed": [],
                                 "reverified": [], "unknown": [], "conflicts": []}
        for key in sorted(seen):
            previous = active.get(key, [])
            incoming = seen[key]
            old_values = {canonical(record["value"]) for record in previous}
            new_values = {canonical(item["value"]) for item in incoming}
            # PARTIAL coverage cannot disprove a competing value that was not
            # re-observed. Preserve unresolved alternatives until COMPLETE
            # scope coverage or an explicit authority resolution exists.
            unresolved_absence = (run["coverage"] == "PARTIAL" and
                                  len(old_values) > 1 and
                                  bool(old_values - new_values))
            if not previous:
                delta["added"].append(_tag(key))
            elif old_values != new_values and not (
                    unresolved_absence and new_values.issubset(old_values)):
                delta["changed"].append(_tag(key))
            else:
                delta["reverified"].append(_tag(key))
            new_active = []
            for item in incoming:
                existing = next((record for record in previous + new_active
                                 if canonical(record["value"]) == canonical(item["value"])), None)
                proof = {"verified_at": run["collected_at"],
                         "evidence_ref": item["evidence_ref"],
                         "evidence_sha256": item["evidence_sha256"],
                         "authority_class": "synthetic_observation"}
                if existing is not None:
                    if proof not in existing["verification_evidence"]:
                        existing["verification_evidence"].append(proof)
                    existing["last_verified_at"] = run["collected_at"]
                    if existing not in new_active:
                        new_active.append(existing)
                else:
                    fact_id = digest({"key": key, "value": item["value"],
                                      "observed_at": run["collected_at"],
                                      "evidence": proof})
                    fact = {"fact_id": fact_id, "source_id": origin[0], "scope": origin[1],
                            "kind": item["kind"], "native_id": item["native_id"],
                            "property": item["property"], "value": item["value"],
                            "observed_at": run["collected_at"],
                            "last_verified_at": run["collected_at"],
                            "verification_evidence": [proof],
                            "superseded_by": None, "removed_at": None}
                    history.append(fact)
                    new_active.append(fact)
            for old in previous:
                if old not in new_active:
                    if unresolved_absence:
                        new_active.append(old)
                    else:
                        # Multiple simultaneous successors are a conflict, not an
                        # arbitrary winner or implicit authority upgrade.
                        old["superseded_by"] = (new_active[0]["fact_id"] if len(new_active) == 1 else None)
            if unresolved_absence:
                delta["unknown"].append(_tag(key))
            if len({canonical(record["value"]) for record in new_active}) > 1:
                delta["conflicts"].append(_tag(key))
            active[key] = new_active
        for key in sorted(active):
            if key[:2] != origin or key in seen or not active[key]:
                continue
            if run["coverage"] == "COMPLETE":
                delta["removed"].append(_tag(key))
                for record in active[key]:
                    record["removed_at"] = run["collected_at"]
                active[key] = []
            else:
                delta["unknown"].append(_tag(key))
        deltas.append(delta)
    current = []
    conflicts = []
    for key in sorted(active):
        live = active[key]
        if not live:
            continue
        collection = latest[key[:2]]
        conflicted = len({canonical(item["value"]) for item in live}) > 1
        if conflicted:
            conflicts.append({"key": _tag(key), "fact_ids": sorted(item["fact_id"] for item in live),
                              "status": "unresolved"})
        for fact in live:
            last_verified = _instant(fact["last_verified_at"])
            # A historical record does not become fresh because unrelated facts
            # were collected. Failed coverage never certifies current state.
            is_current = (collection["coverage"] != "FAILED" and
                          last_verified == _instant(collection["collected_at"]) and
                          last_verified == reference_time and not conflicted)
            current.append({"fact_id": fact["fact_id"], "key": _tag(key),
                            "value": fact["value"], "last_verified_at": fact["last_verified_at"],
                            "status": ("conflicted" if conflicted else
                                       "verified_at_as_of" if is_current else "historical_only"),
                            "current_state_proof": is_current})
    return {"schema": "infra-reference/1", "as_of": as_of,
            "latest_coverage": [{"source_id": source, "scope": scope, **value}
                                for (source, scope), value in sorted(latest.items())],
            "history": sorted(history, key=lambda x: x["fact_id"]),
            "current": current, "conflicts": conflicts, "deltas": deltas}


def export(snapshots: tuple[Snapshot, ...], *, as_of: str) -> str:
    """Reproducible canonical export; no mutable source evidence is modified."""
    return canonical(replay(snapshots, as_of=as_of)) + "\n"
