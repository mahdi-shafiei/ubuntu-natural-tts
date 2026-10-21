"""Shared test doubles."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from natural_tts.config import KokoroSettings, Paths, PiperSettings, Settings
from natural_tts.system import Result

OK = Result(0, b"", b"")


@dataclass
class Call:
    """One recorded invocation of a runner."""

    argv: tuple[str, ...]
    stdin: bytes | None
    timeout: float | None


@dataclass
class RecordingRunner:
    """A ``Runner`` that records calls and answers via ``respond``."""

    respond: Callable[[tuple[str, ...]], Result] = lambda argv: OK
    calls: list[Call] = field(default_factory=list)

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes | None = None,
        timeout: float | None = None,
    ) -> Result:
        call = Call(tuple(argv), stdin, timeout)
        self.calls.append(call)
        return self.respond(call.argv)

    @property
    def argvs(self) -> list[tuple[str, ...]]:
        return [c.argv for c in self.calls]


def make_settings(
    tmp_path: Any,
    piper: PiperSettings | None = None,
    kokoro: KokoroSettings | None = None,
) -> Settings:
    """Settings rooted in a temporary home and runtime directory."""
    paths = Paths.from_env(
        {"XDG_RUNTIME_DIR": str(tmp_path / "run")}, home=tmp_path
    )
    return Settings(
        paths=paths,
        piper=piper or PiperSettings(),
        kokoro=kokoro or KokoroSettings(),
    )


def unused_port() -> int:
    """A localhost TCP port with nothing listening on it."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LocalHTTPServer:
    """A threaded localhost HTTP server answering every request alike."""

    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "json": json.loads(raw) if raw else None,
                    }
                )
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, *args: object) -> None:
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self._httpd.server_address[1])
        threading.Thread(
            target=self._httpd.serve_forever, args=(0.05,), daemon=True
        ).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> LocalHTTPServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
