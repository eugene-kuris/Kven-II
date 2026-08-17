"""Versioned, compact provenance envelopes for derived general memory."""

import json

STATES = {"known", "unknown", "not_applicable"}


def known(value):
    if value is None or value == "":
        raise ValueError("known provenance fields require a value")
    return {"state": "known", "value": value}


def unknown():
    return {"state": "unknown"}


def not_applicable():
    return {"state": "not_applicable"}


def validate_envelope(envelope):
    if envelope is None:
        return None
    if not isinstance(envelope, dict) or envelope.get("version") != 1:
        raise ValueError("provenance envelope version must be 1")
    fields = envelope.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("provenance fields must be an object")
    for name, field in fields.items():
        if not isinstance(name, str) or not isinstance(field, dict):
            raise ValueError("invalid provenance field")
        state = field.get("state")
        if state not in STATES:
            raise ValueError(f"invalid provenance state: {state!r}")
        if (state == "known") != ("value" in field):
            raise ValueError("only known provenance fields carry a value")
    return envelope


def dumps(envelope):
    validated = validate_envelope(envelope)
    return None if validated is None else json.dumps(
        validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def loads(value):
    return None if value is None else validate_envelope(json.loads(value))
