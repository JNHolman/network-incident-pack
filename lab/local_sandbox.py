"""Small local HTTP/TCP sandbox for live Incident Pack validation."""

from __future__ import annotations

import argparse
import json
import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple


class HealthHandler(BaseHTTPRequestHandler):
    """Serve a predictable HTTP health endpoint without access-log noise."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps({"status": "ok", "service": "incident-pack-sandbox"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class BannerHandler(socketserver.BaseRequestHandler):
    """Return a fixed banner after a real TCP handshake."""

    def handle(self) -> None:
        self.request.sendall(b"incident-pack-sandbox\n")


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@dataclass
class SandboxEnvironment:
    """Running local endpoints used by the live demo."""

    http_server: ThreadingHTTPServer
    tcp_server: ThreadingTCPServer
    refused_port_number: int
    threads: Tuple[threading.Thread, threading.Thread]

    @property
    def host(self) -> str:
        return str(self.http_server.server_address[0])

    @property
    def http_port(self) -> int:
        return int(self.http_server.server_address[1])

    @property
    def tcp_port(self) -> int:
        return int(self.tcp_server.server_address[1])

    @property
    def refused_port(self) -> int:
        return self.refused_port_number

    def close(self) -> None:
        for server in (self.http_server, self.tcp_server):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)


def _find_refused_port(host: str, port: int) -> int:
    """Choose an unused TCP port and release it so connections are refused.

    Keeping a socket bound but not listening is not portable: some macOS
    configurations time out instead of returning ECONNREFUSED. Releasing the
    localhost port makes the intended failure semantics consistent across the
    supported platforms.
    """
    reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reserved.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reserved.bind((host, port))
        return int(reserved.getsockname()[1])
    finally:
        reserved.close()


def start_sandbox(
    host: str = "127.0.0.1",
    http_port: int = 18080,
    tcp_port: int = 18022,
    refused_port: int = 18081,
) -> SandboxEnvironment:
    """Start two listening endpoints and one deliberately refused TCP port."""
    http_server = ThreadingHTTPServer((host, http_port), HealthHandler)
    try:
        tcp_server = ThreadingTCPServer((host, tcp_port), BannerHandler)
    except Exception:
        http_server.server_close()
        raise

    try:
        refused_port_number = _find_refused_port(host, refused_port)
    except Exception:
        http_server.server_close()
        tcp_server.server_close()
        raise

    threads = (
        threading.Thread(target=http_server.serve_forever, name="sandbox-http", daemon=True),
        threading.Thread(target=tcp_server.serve_forever, name="sandbox-tcp", daemon=True),
    )
    for thread in threads:
        thread.start()

    return SandboxEnvironment(
        http_server=http_server,
        tcp_server=tcp_server,
        refused_port_number=refused_port_number,
        threads=threads,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Incident Pack validation endpoints.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=18080)
    parser.add_argument("--tcp-port", type=int, default=18022)
    parser.add_argument("--refused-port", type=int, default=18081)
    args = parser.parse_args()

    sandbox = start_sandbox(args.host, args.http_port, args.tcp_port, args.refused_port)
    print("Incident Pack local sandbox is running")
    print(f"HTTP health: http://{sandbox.host}:{sandbox.http_port}/health")
    print(f"TCP service: {sandbox.host}:{sandbox.tcp_port}")
    print(f"Deliberately refused TCP port: {sandbox.host}:{sandbox.refused_port}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        sandbox.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
