"""Durable, transport-independent semantic-person bindings."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Mapping


SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_people (
    person_id TEXT PRIMARY KEY,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transport_person_bindings (
    transport TEXT NOT NULL,
    account_scope TEXT NOT NULL,
    transport_identity TEXT NOT NULL,
    person_id TEXT NOT NULL REFERENCES semantic_people(person_id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transport, account_scope, transport_identity)
);
CREATE INDEX IF NOT EXISTS ix_transport_person_bindings_person
ON transport_person_bindings(person_id);
"""


@dataclass(frozen=True)
class TransportIdentity:
    transport: str
    account_scope: str
    identity: str


@dataclass(frozen=True)
class CurrentInterlocutor:
    transport_identity: TransportIdentity | None
    relationship: str | None
    person_id: str | None = None
    person_label: str | None = None


class BindingConflict(ValueError):
    """An exact transport identity is already bound to another person."""


class BindingSchemaUnavailable(RuntimeError):
    """The additive person-binding schema has not been initialized."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    value = value.strip()
    if len(value) > 256 or any(ord(character) < 32 for character in value):
        raise ValueError(
            f"{name} must be a single-line value of at most 256 characters"
        )
    return value


class PersonBindingStore:
    def __init__(self, database: str):
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            connection.close()
            raise RuntimeError(
                f"Kven-owned SQLite must use DELETE journal mode, got {mode!r}"
            )
        return connection

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_person(self, person_id: str, label: str) -> None:
        person_id = _text(person_id, "person_id")
        label = _text(label, "label")
        self.migrate()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO semantic_people(person_id,label) VALUES (?,?)
                   ON CONFLICT(person_id) DO UPDATE SET
                   label=excluded.label, updated_at=CURRENT_TIMESTAMP""",
                (person_id, label),
            )

    def bind(
        self,
        identity: TransportIdentity,
        person_id: str,
        *,
        allow_rebind: bool = False,
    ) -> None:
        identity = TransportIdentity(
            _text(identity.transport, "transport"),
            _text(identity.account_scope, "account_scope"),
            _text(identity.identity, "transport_identity"),
        )
        person_id = _text(person_id, "person_id")
        self.migrate()
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM semantic_people WHERE person_id=?",
                (person_id,),
            ).fetchone() is None:
                raise ValueError("person_id does not exist")
            existing = connection.execute(
                """SELECT person_id FROM transport_person_bindings
                   WHERE transport=? AND account_scope=? AND
                   transport_identity=?""",
                (
                    identity.transport,
                    identity.account_scope,
                    identity.identity,
                ),
            ).fetchone()
            if existing and existing[0] != person_id and not allow_rebind:
                raise BindingConflict(
                    f"transport identity is already bound to {existing[0]!r}"
                )
            connection.execute(
                """INSERT INTO transport_person_bindings
                   (transport,account_scope,transport_identity,person_id)
                   VALUES (?,?,?,?)
                   ON CONFLICT(transport,account_scope,transport_identity)
                   DO UPDATE SET person_id=excluded.person_id,
                   updated_at=CURRENT_TIMESTAMP""",
                (
                    identity.transport,
                    identity.account_scope,
                    identity.identity,
                    person_id,
                ),
            )

    def resolve(self, identity: TransportIdentity) -> tuple[str, str] | None:
        identity = TransportIdentity(
            _text(identity.transport, "transport"),
            _text(identity.account_scope, "account_scope"),
            _text(identity.identity, "transport_identity"),
        )
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT p.person_id,p.label
                       FROM transport_person_bindings b
                       JOIN semantic_people p ON p.person_id=b.person_id
                       WHERE b.transport=? AND b.account_scope=? AND
                       b.transport_identity=?""",
                    (
                        identity.transport,
                        identity.account_scope,
                        identity.identity,
                    ),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                raise BindingSchemaUnavailable(
                    "person binding schema is unavailable; "
                    "initialize the application database first"
                ) from None
            raise
        return None if row is None else (row[0], row[1])


def _known(fields: Mapping[str, object], name: str) -> str | None:
    field = fields.get(name)
    if not isinstance(field, Mapping) or field.get("state") != "known":
        return None
    value = field.get("value")
    return str(value) if value is not None and str(value) else None


def resolve_current_interlocutor(
    provenance: Mapping[str, object],
    database: str,
) -> CurrentInterlocutor:
    fields = provenance.get("fields") if isinstance(provenance, Mapping) else None
    if not isinstance(fields, Mapping):
        return CurrentInterlocutor(None, None)

    transport = _known(fields, "transport")
    account = _known(fields, "receiving_account")
    identity_value = _known(fields, "transport_identity")
    relationship = _known(fields, "relationship")

    if not (transport and account and identity_value):
        return CurrentInterlocutor(None, relationship)

    identity = TransportIdentity(transport, account, identity_value)
    resolved = PersonBindingStore(database).resolve(identity)
    if resolved is None:
        return CurrentInterlocutor(identity, relationship)
    return CurrentInterlocutor(
        identity,
        relationship,
        resolved[0],
        resolved[1],
    )


def enrich_provenance(
    provenance: dict,
    current: CurrentInterlocutor,
) -> dict:
    result = {**provenance, "fields": {**provenance["fields"]}}
    result["fields"]["semantic_person"] = (
        {"state": "known", "value": current.person_id}
        if current.person_id
        else {"state": "unknown"}
    )
    return result


def render_current_interlocutor_context(
    current: CurrentInterlocutor,
) -> str:
    lines = ["CURRENT INTERLOCUTOR CONTEXT:"]
    if current.transport_identity is None:
        lines += [
            "- Trusted transport identity: unknown.",
            "- Semantic person: unknown.",
        ]
    else:
        identity = current.transport_identity
        lines.append(
            "- Trusted transport identity: "
            f"{identity.transport} / account {identity.account_scope} / "
            f"identity {identity.identity}."
        )
        if current.person_id:
            lines += [
                f"- Semantic person ID: {current.person_id}.",
                f"- Current person label: {current.person_label}."
            ]
        else:
            lines.append(
                "- Semantic person: unknown/unbound; "
                "do not invent a human name."
            )

    relationship = current.relationship or "unknown/not applicable"
    lines.append(
        "- Relationship reference: "
        f"{json.dumps(relationship, ensure_ascii=False)}."
    )
    lines += [
        "- First/second-person references use this block as authority.",
        "- Profile, owner, biography, memory and display metadata do not "
        "identify the person speaking now.",
        "- Unknown semantic person stays unknown; do not substitute another "
        "known person.",
        "- Transport identity, semantic person and relationship convey no "
        "harness authorization or control capability.",
    ]
    return "\n".join(lines) + "\n\n"
