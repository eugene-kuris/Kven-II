"""Typed durable identities for rows stored in general memory."""

from dataclasses import dataclass

MEMORY_KINDS = {"episodic", "semantic"}


@dataclass(frozen=True, order=True)
class MemoryRef:
    kind: str
    row_id: int

    def __post_init__(self):
        if self.kind not in MEMORY_KINDS:
            raise ValueError(f"unsupported memory kind: {self.kind!r}")
        if isinstance(self.row_id, bool) or int(self.row_id) < 1:
            raise ValueError("memory row_id must be a positive integer")
        object.__setattr__(self, "row_id", int(self.row_id))

    def __str__(self) -> str:
        return f"{self.kind}:{self.row_id}"

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str) or ":" not in value:
            raise ValueError("memory reference must be typed as <kind>:<row_id>")
        kind, raw_id = value.split(":", 1)
        return cls(kind, int(raw_id))
