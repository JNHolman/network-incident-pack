#!/usr/bin/env python3
"""Verify that a source release ZIP contains only expected repository content."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {".git", ".venv", "__pycache__"}
FORBIDDEN_SUFFIXES = (".egg-info", ".pyc", ".pyo")
FORBIDDEN_NAMES = {".env"}


def verify_archive(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"Release archive does not exist: {path}")

    with zipfile.ZipFile(path) as archive:
        files = [name for name in archive.namelist() if not name.endswith("/")]

    if not files:
        raise ValueError("Release archive is empty.")

    roots = {PurePosixPath(name).parts[0] for name in files}
    if len(roots) != 1:
        raise ValueError("Release archive must contain one versioned top-level directory.")
    root = next(iter(roots))
    if re.fullmatch(r"network-incident-pack-v\d+\.\d+\.\d+", root) is None:
        raise ValueError(f"Unexpected release root directory: {root}")

    violations: list[str] = []
    for name in files:
        parts = PurePosixPath(name).parts
        relative = parts[1:]
        if any(part in FORBIDDEN_PARTS for part in relative):
            violations.append(name)
            continue
        if any(part.endswith(FORBIDDEN_SUFFIXES) for part in relative):
            violations.append(name)
            continue
        if relative and relative[-1] in FORBIDDEN_NAMES:
            violations.append(name)

    if violations:
        preview = "\n".join(f"  - {item}" for item in violations[:20])
        raise ValueError(f"Release archive contains forbidden artifacts:\n{preview}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        verify_archive(args.archive)
    except (ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(f"Release archive verified: {args.archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
