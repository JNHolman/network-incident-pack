"""Concurrent execution of independent host-side evidence commands."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, List, Optional, Sequence

from incidentpack.runner import CommandResult, run_command

HostProgressCallback = Callable[
    [str, Sequence[str], Optional[CommandResult]],
    None,
]


def run_host_commands(
    commands: Sequence[Sequence[str]],
    *,
    timeout: int,
    max_workers: int = 4,
    progress_callback: Optional[HostProgressCallback] = None,
) -> List[CommandResult]:
    """Run host commands concurrently while preserving the configured command order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if not commands:
        return []

    def run_one(command: Sequence[str]) -> CommandResult:
        if progress_callback is not None:
            progress_callback("started", command, None)
        result = run_command(command, timeout=timeout)
        if progress_callback is not None:
            progress_callback("completed", command, result)
        return result

    worker_count = min(max_workers, len(commands))
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="incident-cmd"
    ) as executor:
        return list(executor.map(run_one, commands))
