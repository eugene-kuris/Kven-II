#!/usr/bin/env python3
"""Deterministic publication-boundary scan for the public projection."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
DENIED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".journal", ".pem", ".key"}
PATTERNS = {
    "private IPv4 address": re.compile(
        r"\b(?:10\.\d{1,3}(?:\.\d{1,3}){2}|192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "private deployment path": re.compile(r"/(?:opt|agent/data)/kven", re.I),
    "engineering control identity": re.compile(r"kven-root|qwen.*courier", re.I),
    "credential assignment": re.compile(
        r"(?im)^\s*(?:api[_-]?key|token|password|secret|session)\s*=\s*\S+"
    ),
    "private Git remote": re.compile(r"eugene-kuris/kven2(?:\.git)?", re.I),
    "runtime email identity": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
}


def files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and not set(path.relative_to(ROOT).parts) & SKIP_PARTS
    )


def main() -> int:
    violations: list[str] = []
    for path in files():
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in DENIED_SUFFIXES or path.name in {".env", "credentials"}:
            violations.append(f"denied artifact: {relative}")
            continue
        if path.is_symlink():
            violations.append(f"symlink: {relative}")
            continue
        if path.stat().st_size > 1_000_000:
            violations.append(f"large file: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"binary file: {relative}")
            continue
        # The checker necessarily contains its denied regular expressions.
        if relative == Path("scripts/check_publication.py"):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{label}: {relative}:{line}")
    if violations:
        print("PUBLICATION CHECK: FAIL")
        print("\n".join(violations))
        return 1
    print(f"PUBLICATION CHECK: PASS ({len(files())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
