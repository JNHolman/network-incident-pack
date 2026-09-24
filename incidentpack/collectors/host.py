"""Concurrent execution of independent host-side evidence commands."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import List, Sequence

from incidentpack.runner import CommandResult, run_command


def run_host_commands(
    commands: Sequence[Sequence[str]],
    *,
    timeout: int,
    max_workers: int = 4,
) -> List[CommandResult]:
    """Run host commands concurrently while preserving the configured command order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if not commands:
        return []

    worker_count = min(max_workers, len(commands))
    runner = partial(run_command, timeout=timeout)
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="incident-cmd"
    ) as executor:
        return list(executor.map(runner, commands))
