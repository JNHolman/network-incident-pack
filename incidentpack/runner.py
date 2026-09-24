"""Command execution helpers for host-side incident evidence collection."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Optional, Sequence, TypedDict


logger = logging.getLogger(__name__)


class CommandResult(TypedDict):
    """Structured result returned for every attempted operating-system command."""

    cmd: str
    rc: Optional[int]
    ok: bool
    stdout: str
    stderr: str
    error_type: str
    timed_out: bool
    duration_ms: float


def _as_text(value: object) -> str:
    """Normalize subprocess output to stripped text, including timeout partial output."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip()
    return str(value).strip()


def _result(
    *,
    cmd_text: str,
    rc: Optional[int],
    stdout: str,
    stderr: str,
    error_type: str,
    timed_out: bool,
    started_at: float,
) -> CommandResult:
    """Build one consistent command-result schema for success and failure paths."""
    return {
        "cmd": cmd_text,
        "rc": rc,
        "ok": rc == 0 and not error_type,
        "stdout": stdout,
        "stderr": stderr,
        "error_type": error_type,
        "timed_out": timed_out,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }


def run_command(cmd: Sequence[str], timeout: int) -> CommandResult:
    """
    Run one command and convert execution outcomes into structured evidence.

    Known operational failures are classified explicitly. A final defensive
    exception boundary remains so one broken collector does not abort the
    entire incident pack.
    """
    cmd_list = list(cmd)
    cmd_text = " ".join(cmd_list)
    started_at = time.perf_counter()
    logger.debug("Running command: %s (timeout=%ss)", cmd_text, timeout)

    try:
        completed = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        error_type = "" if completed.returncode == 0 else "nonzero_exit"
        result = _result(
            cmd_text=cmd_text,
            rc=completed.returncode,
            stdout=_as_text(completed.stdout),
            stderr=_as_text(completed.stderr),
            error_type=error_type,
            timed_out=False,
            started_at=started_at,
        )
        if result["ok"]:
            logger.debug(
                "Command completed: %s rc=%s duration_ms=%s",
                cmd_text,
                result["rc"],
                result["duration_ms"],
            )
        else:
            logger.info("Command returned non-zero: %s rc=%s", cmd_text, result["rc"])
        return result

    except subprocess.TimeoutExpired as error:
        message = f"Command timed out after {timeout}s"
        stderr = _as_text(error.stderr)
        if stderr:
            stderr = f"{stderr}\n{message}"
        else:
            stderr = message
        logger.warning("Command timed out: %s after %ss", cmd_text, timeout)
        return _result(
            cmd_text=cmd_text,
            rc=None,
            stdout=_as_text(error.stdout),
            stderr=stderr,
            error_type="timeout",
            timed_out=True,
            started_at=started_at,
        )

    except FileNotFoundError as error:
        logger.warning("Command not found: %s", cmd_list[0] if cmd_list else "<empty>")
        return _result(
            cmd_text=cmd_text,
            rc=None,
            stdout="",
            stderr=f"FileNotFoundError: {error}",
            error_type="command_not_found",
            timed_out=False,
            started_at=started_at,
        )

    except OSError as error:
        logger.warning("OS error running command %s: %s", cmd_text, error)
        return _result(
            cmd_text=cmd_text,
            rc=None,
            stdout="",
            stderr=f"{type(error).__name__}: {error}",
            error_type="os_error",
            timed_out=False,
            started_at=started_at,
        )

    except Exception as error:  # Defensive boundary: preserve incident collection.
        logger.exception("Unexpected command runner failure: %s", cmd_text)
        return _result(
            cmd_text=cmd_text,
            rc=None,
            stdout="",
            stderr=f"{type(error).__name__}: {error}",
            error_type="unexpected_error",
            timed_out=False,
            started_at=started_at,
        )
