"""Safe output-path selection and atomic per-file report writing."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .markdown import build_markdown
from .schema import sanitize_report, validate_report


def sanitize_filename_component(value: str, default: str = "host") -> str:
    """Return a filesystem-safe filename component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    cleaned = cleaned.strip(".-_")
    return cleaned or default


def choose_output_base(out_dir: str, host: str, timestamp: Optional[str] = None) -> str:
    """Return a unique output base path, adding a numeric suffix if needed."""
    stamp = timestamp or dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_host = sanitize_filename_component(host)
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    base_name = f"incident_pack_{safe_host}_{stamp}"
    candidate = directory / base_name
    suffix = 1
    while candidate.with_suffix(".json").exists() or candidate.with_suffix(".md").exists():
        candidate = directory / f"{base_name}_{suffix:02d}"
        suffix += 1
    return str(candidate)


def _atomic_write_text(path: Path, content: str) -> None:
    """Replace one output atomically so interrupted writes do not leave partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def write_outputs(
    evidence: Mapping[str, Any], out_dir: str, md_max_lines: int
) -> Dict[str, str]:
    """Validate and atomically write JSON and Markdown report files."""
    safe_evidence = sanitize_report(evidence)
    validate_report(safe_evidence)
    meta = safe_evidence["meta"]
    host = str(meta.get("host", "host")) if isinstance(meta, Mapping) else "host"
    base = choose_output_base(out_dir, host)
    json_path = Path(f"{base}.json")
    md_path = Path(f"{base}.md")

    json_text = json.dumps(safe_evidence, indent=2, sort_keys=False) + "\n"
    markdown_text = build_markdown(dict(safe_evidence), md_max_lines=md_max_lines)

    _atomic_write_text(json_path, json_text)
    _atomic_write_text(md_path, markdown_text)

    return {"json": str(json_path), "md": str(md_path)}
