"""Local Unix-socket messaging between the hotkey commands and the daemon.

The protocol is one UTF-8 message per connection: the client writes the
text and closes its sending side; the server reads until end-of-stream.
"""

from __future__ import annotations

import contextlib
import os
import socket
import stat
from pathlib import Path
from types import TracebackType

# A message starting with NUL can never come from selected text.
STOP_MESSAGE = "\x00STOP"
# Upper bound on one message (~1 MiB of text, i.e. a long article).
MAX_MESSAGE_BYTES = 1 << 20
_RECV_CHUNK = 65536


class DaemonNotRunningError(ConnectionError):
    """Raised when nothing is listening on the daemon socket."""


def _ensure_private_dir(path: Path) -> None:
    """Create ``path`` as a 0700 directory owned by the current user.

    Raises:
        PermissionError: if the directory exists but belongs to someone else
            (relevant for the /tmp fallback location).
    """
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid():
        raise PermissionError(f"{path} is owned by another user")
    if stat.S_IMODE(info.st_mode) != 0o700:
        path.chmod(0o700)


class MessageServer:
    """Listening end of the daemon socket (a context manager)."""

    def __init__(self, path: Path) -> None:
        """Prepare a server for ``path``; the socket is bound on enter."""
        self.path = path
        self._sock: socket.socket | None = None

    def __enter__(self) -> MessageServer:
        """Bind a private socket, replacing any stale one."""
        _ensure_private_dir(self.path.parent)
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        self.path.chmod(0o600)
        sock.listen()
        self._sock = sock
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close and remove the socket."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    def receive(self) -> str:
        """Block until one message arrives and return it.

        Messages longer than ``MAX_MESSAGE_BYTES`` are truncated; invalid
        UTF-8 is replaced rather than rejected.
        """
        if self._sock is None:
            raise RuntimeError("MessageServer used outside its context")
        conn, _ = self._sock.accept()
        with conn:
            data = bytearray()
            while len(data) < MAX_MESSAGE_BYTES:
                chunk = conn.recv(_RECV_CHUNK)
                if not chunk:
                    break
                data += chunk
        return bytes(data[:MAX_MESSAGE_BYTES]).decode("utf-8", "replace")


def send_message(path: Path, message: str) -> None:
    """Send one message to the daemon listening on ``path``.

    Raises:
        DaemonNotRunningError: if no daemon is listening.
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise DaemonNotRunningError(
                f"the Kokoro daemon is not running or still starting "
                f"(no socket at {path})"
            ) from exc
        # The server stops reading at MAX_MESSAGE_BYTES and may close early.
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            sock.sendall(message.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
