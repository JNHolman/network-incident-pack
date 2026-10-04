"""Layer-4 TCP checks with bounded retries and concurrent execution."""

from __future__ import annotations

import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

Connector = Callable[..., object]
Sleeper = Callable[[float], None]
TcpProgressCallback = Callable[[str, int, Optional[Dict[str, object]]], None]


def _error_type(error: BaseException) -> str:
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(error, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError)):
        return "connection_reset"
    if isinstance(error, socket.gaierror):
        return "name_resolution"
    if isinstance(error, OSError):
        return "os_error"
    return "unexpected_error"


def _is_retryable(error: BaseException) -> bool:
    """Retry only failures that can reasonably be transient for a TCP connect."""
    return isinstance(
        error,
        (socket.timeout, TimeoutError, ConnectionResetError, ConnectionAbortedError),
    )


def tcp_check(
    host: str,
    port: int,
    *,
    timeout: float = 3.0,
    max_attempts: int = 2,
    retry_delay: float = 0.2,
    connector: Connector = socket.create_connection,
    sleep: Sleeper = time.sleep,
) -> Dict[str, object]:
    """Attempt one TCP connection, selectively retrying transient failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if timeout <= 0:
        raise ValueError("timeout must be greater than 0")
    if retry_delay < 0:
        raise ValueError("retry_delay cannot be negative")

    started_at = time.perf_counter()
    last_error: BaseException | None = None
    attempts_used = 0

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        try:
            connection = connector((host, port), timeout=timeout)
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            return {
                "host": host,
                "port": port,
                "ok": True,
                "error": "",
                "error_type": "",
                "attempts": attempt,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            }
        except Exception as error:
            last_error = error
            retryable = _is_retryable(error)
            logger.debug(
                "TCP check failed host=%s port=%s attempt=%s/%s type=%s retryable=%s",
                host,
                port,
                attempt,
                max_attempts,
                _error_type(error),
                retryable,
            )
            if not retryable or attempt >= max_attempts:
                break
            if retry_delay:
                sleep(retry_delay * (2 ** (attempt - 1)))

    assert last_error is not None
    return {
        "host": host,
        "port": port,
        "ok": False,
        "error": f"{type(last_error).__name__}: {last_error}",
        "error_type": _error_type(last_error),
        "attempts": attempts_used,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }


def run_tcp_checks(
    host: str,
    ports: Sequence[int],
    *,
    timeout: float = 3.0,
    max_attempts: int = 2,
    retry_delay: float = 0.2,
    max_workers: int = 4,
    progress_callback: Optional[TcpProgressCallback] = None,
) -> List[Dict[str, object]]:
    """Run independent TCP checks concurrently while preserving input port order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if not ports:
        return []

    def check_port(port: int) -> Dict[str, object]:
        if progress_callback is not None:
            progress_callback("started", port, None)
        result = tcp_check(
            host,
            port,
            timeout=timeout,
            max_attempts=max_attempts,
            retry_delay=retry_delay,
        )
        if progress_callback is not None:
            progress_callback("completed", port, result)
        return result

    worker_count = min(max_workers, len(ports))
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="incident-tcp"
    ) as executor:
        return list(executor.map(check_port, ports))
