"""The single place where natural-tts runs external programs."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Conventional shell exit codes for "command not found" and "timed out".
EXIT_NOT_FOUND = 127
EXIT_TIMEOUT = 124


@dataclass(frozen=True)
class Result:
    """Outcome of running a program."""

    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def ok(self) -> bool:
        """True if the program exited with status 0."""
        return self.returncode == 0

    @property
    def text(self) -> str:
        """Stdout decoded as UTF-8 (invalid bytes replaced)."""
        return self.stdout.decode("utf-8", "replace")

    def describe(self, argv: Sequence[str]) -> str:
        """One-line failure description for error messages."""
        message = f"{' '.join(argv)} failed (exit {self.returncode})"
        detail = self.stderr.decode("utf-8", "replace").strip()
        return f"{message}: {detail}" if detail else message


_UNSAFE = frozenset(" \t\n'\"\\")


def plain_argument(value: str) -> str:
    """Return ``value`` if it needs no quoting in config files.

    Speech Dispatcher's dotconf strings and systemd's ExecStart each have
    their own quoting rules; refusing whitespace and quotes keeps both safe.

    Raises:
        ValueError: if ``value`` contains whitespace, quotes or backslashes.
    """
    if _UNSAFE.intersection(value):
        raise ValueError(
            f"{value!r} cannot contain whitespace, quotes or backslashes"
        )
    return value


class Runner(Protocol):
    """Signature of ``run``; tests substitute fakes."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes | None = None,
        timeout: float | None = None,
    ) -> Result:
        """Run ``argv``."""
        ...


def run(
    argv: Sequence[str],
    *,
    stdin: bytes | None = None,
    timeout: float | None = None,
) -> Result:
    """Run ``argv`` and capture its output; never raises for failures.

    A missing program yields exit code 127 and a timeout yields 124.
    """
    try:
        proc = subprocess.run(
            list(argv),
            input=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return Result(EXIT_NOT_FOUND, b"", str(exc).encode())
    except subprocess.TimeoutExpired:
        return Result(EXIT_TIMEOUT, b"", b"timed out")
    return Result(proc.returncode, proc.stdout, proc.stderr)
