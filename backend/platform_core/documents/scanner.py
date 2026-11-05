"""Malware scanner interface (DEC-053 AV-A: ClamAV in an isolated container on the same server).

* :class:`ClamdScanner` - the production adapter: clamd ``INSTREAM`` over TCP (``ALEEKHAN_CLAMD_HOST`` /
  ``ALEEKHAN_CLAMD_PORT``) or a unix socket (``ALEEKHAN_CLAMD_SOCKET``). Unreachable / protocol error ->
  ``DependencyUnavailable``: the revision stays QUARANTINED (never auto-CLEAN). Only a signature *name* is
  kept
  as the finding (never file content).
* :class:`FakeScannerForTests` - a deterministic TEST DOUBLE, clearly named; flags the EICAR test string and
  refuses to start outside ALEEKHAN_ENV dev/test. It is never presented as a real scanner.
* :func:`configured_scanner` - the scanner for this deployment (ClamAV if configured, else ``None`` = no
  scan).
"""

from __future__ import annotations

import re
import socket
import struct
from dataclasses import dataclass
from typing import Final, Protocol

from django.conf import settings

from platform_core.engine.errors import DependencyUnavailable, EngineContractError

CHUNK: Final = 64 * 1024
EICAR_MARKER: Final = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
_FINDING_RE: Final = re.compile(r"[^A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class ScanVerdict:
    clean: bool
    finding: str  # signature name / machine code only, '' when clean
    scanner_version: str


class Scanner(Protocol):
    def scan(self, data: bytes) -> ScanVerdict: ...


def _safe_finding(text: str) -> str:
    return _FINDING_RE.sub("_", text.strip())[:200] or "UNKNOWN_FINDING"


class ClamdScanner:
    def __init__(
        self, *, host: str = "", port: int = 3310, unix_socket: str = "", timeout: float = 30.0
    ) -> None:
        if not host and not unix_socket:
            raise EngineContractError("ClamdScanner needs a host or a unix socket")
        self.host, self.port, self.unix_socket, self.timeout = host, port, unix_socket, timeout

    def _connect(self) -> socket.socket:
        try:
            if self.unix_socket:
                family = getattr(socket, "AF_UNIX", None)
                if family is None:
                    raise DependencyUnavailable("unix sockets are not available on this platform")
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect(self.unix_socket)
                return sock
            return socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError:
            raise DependencyUnavailable("the malware scanner is not reachable") from None

    def _command(self, payload: bytes) -> bytes:
        with self._connect() as sock:
            sock.sendall(payload)
            return self._read_reply(sock)

    @staticmethod
    def _read_reply(sock: socket.socket) -> bytes:
        parts: list[bytes] = []
        try:
            while True:
                buf = sock.recv(4096)
                if not buf:
                    break
                parts.append(buf)
                if buf.endswith(b"\0"):
                    break
        except OSError:
            raise DependencyUnavailable("the malware scanner did not answer") from None
        return b"".join(parts).rstrip(b"\0").strip()

    def version(self) -> str:
        return self._command(b"zVERSION\0").decode("utf-8", "replace")[:64]

    def scan(self, data: bytes) -> ScanVerdict:
        version = self.version()
        with self._connect() as sock:
            try:
                sock.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), CHUNK):
                    chunk = data[i : i + CHUNK]
                    sock.sendall(struct.pack(">I", len(chunk)) + chunk)
                sock.sendall(struct.pack(">I", 0))
            except OSError:
                raise DependencyUnavailable("the malware scanner connection failed") from None
            reply = self._read_reply(sock).decode("utf-8", "replace")
        # "stream: OK" | "stream: <Signature> FOUND" | "INSTREAM size limit exceeded. ERROR" | "... ERROR"
        if reply.endswith("OK") and "FOUND" not in reply:
            return ScanVerdict(True, "", version)
        if reply.endswith("FOUND"):
            name = reply.split(":", 1)[-1].rsplit("FOUND", 1)[0]
            return ScanVerdict(False, _safe_finding(name), version)
        if "size limit" in reply.lower():
            return ScanVerdict(False, "SCANNER_SIZE_LIMIT", version)
        raise DependencyUnavailable("the malware scanner returned an error")


class FakeScannerForTests:
    """TEST DOUBLE (not a malware scanner): flags the EICAR test string and an explicit test marker."""

    version = "fake-scanner-for-tests/1"

    def __init__(self, *, extra_markers: tuple[bytes, ...] = (), unavailable: bool = False) -> None:
        if getattr(settings, "ALEEKHAN_ENV", "") not in {"dev", "test"}:
            raise EngineContractError("FakeScannerForTests is a test double (dev/test only)")
        self.markers = (EICAR_MARKER, *extra_markers)
        self.unavailable = unavailable
        self.calls = 0

    def scan(self, data: bytes) -> ScanVerdict:
        self.calls += 1
        if self.unavailable:
            raise DependencyUnavailable("fake scanner configured as unavailable")
        if any(m in data for m in self.markers):
            return ScanVerdict(False, "Eicar-Test-Signature", self.version)
        return ScanVerdict(True, "", self.version)


def configured_scanner() -> Scanner | None:
    host = getattr(settings, "ALEEKHAN_CLAMD_HOST", "")
    path = getattr(settings, "ALEEKHAN_CLAMD_SOCKET", "")
    if not host and not path:
        return None
    return ClamdScanner(
        host=host,
        port=int(getattr(settings, "ALEEKHAN_CLAMD_PORT", 3310)),
        unix_socket=path,
        timeout=float(getattr(settings, "ALEEKHAN_CLAMD_TIMEOUT_SECONDS", 30)),
    )
