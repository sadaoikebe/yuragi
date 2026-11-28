"""The management tools' line to the broker for status, restart and keymap reload.

On Windows the broker listens on \\\\.\\pipe\\yuragi-ime-<user SID>-<session>; on macOS
the input program does, on a Unix domain socket (SOCKET_PATH; docs/MACOS.md). Elsewhere
there is no broker. These functions connect and say hello as a TIP would. A retry
restarts the engine; a keymap reload keeps its sessions. Nothing here starts a broker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import time

HELLO = {"op": "hello", "proto": 1}
SOCKET_PATH = Path.home() / "Library" / "Application Support" / "yuragi-ime" / "broker.sock"


def pipe_address() -> str:
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Declared: undeclared, ctypes takes the pseudo handle (HANDLE)-1 as a 32-bit int
    # and passes 0xFFFFFFFF, which OpenProcessToken rejects (ERROR_INVALID_HANDLE).
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(wintypes.LPWSTR)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken")
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation")
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid_pointer), ctypes.byref(text)):
            raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW")
        sid = text.value
        kernel32.LocalFree(text)
    finally:
        kernel32.CloseHandle(token)
    session = wintypes.DWORD()
    kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session))
    return rf"\\.\pipe\yuragi-ime-{sid}-{session.value}"


class _Connection:
    def __init__(self, address: str, timeout: float):
        import _winapi
        import msvcrt
        self.timeout = timeout
        self.file = open(address, "r+b", buffering=0)  # FileNotFoundError: no broker
        self.handle = msvcrt.get_osfhandle(self.file.fileno())
        self.peek = _winapi.PeekNamedPipe
        self.buffer = b""

    def send(self, msg: dict) -> None:
        self.file.write((json.dumps(msg) + "\n").encode("utf-8"))

    def read_line(self, seq: int | None = None) -> dict | None:
        """Read one reply within the timeout, skipping events when waiting for a seq."""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                reply = json.loads(line)
                if isinstance(reply, dict) and (seq is None or reply.get("seq") == seq):
                    return reply
                continue
            available, _ = self.peek(self.handle)
            if available:
                chunk = self.file.read(min(4096, available))
                if not chunk:
                    return None
                self.buffer += chunk
            else:
                time.sleep(0.005)
        return None

    def close(self) -> None:
        self.file.close()


class _SocketConnection:
    def __init__(self, address: str, timeout: float):
        self.timeout = timeout
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.settimeout(timeout)
            self.socket.connect(address)  # OSError: no input program
        except OSError:
            self.socket.close()
            raise
        self.buffer = b""

    def send(self, msg: dict) -> None:
        self.socket.sendall((json.dumps(msg) + "\n").encode("utf-8"))

    def read_line(self, seq: int | None = None) -> dict | None:
        """As _Connection.read_line."""
        deadline = time.monotonic() + self.timeout
        while True:
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                reply = json.loads(line)
                if isinstance(reply, dict) and (seq is None or reply.get("seq") == seq):
                    return reply
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.socket.settimeout(remaining)
            try:
                chunk = self.socket.recv(4096)
            except TimeoutError:
                return None
            if not chunk:
                return None
            self.buffer += chunk

    def close(self) -> None:
        self.socket.close()


def _connect(address: str | None, timeout: float) -> _Connection | _SocketConnection | None:
    try:
        if sys.platform == "darwin":
            return _SocketConnection(address or str(SOCKET_PATH), timeout)
        if os.name != "nt":
            return None  # no broker
        return _Connection(address or pipe_address(), timeout)
    except OSError:
        return None  # no broker: not running for this user


def status(address: str | None = None, timeout: float = 1.0) -> dict | None:
    """{"state": ready|starting|down|..., "warnings": [...]}; None when no broker answers."""
    connection = _connect(address, timeout)
    if connection is None:
        return None
    try:
        connection.send(HELLO)
        reply = connection.read_line()
    except OSError:
        return None
    finally:
        connection.close()
    if reply is None:
        return None
    return {"state": reply.get("state"), "warnings": reply.get("warnings", [])}


def retry(address: str | None = None, timeout: float = 1.0) -> bool:
    """Ask the broker to start the engine again; False when no broker answers."""
    connection = _connect(address, timeout)
    if connection is None:
        return False
    try:
        connection.send(HELLO)
        if connection.read_line() is None:
            return False
        connection.send({"op": "retry"})
        return True
    except OSError:
        return False
    finally:
        connection.close()


def reload_keymap(address: str | None = None, timeout: float = 1.0) -> dict | None:
    connection = _connect(address, timeout)
    if connection is None:
        return None
    try:
        connection.send(HELLO)
        if connection.read_line() is None:
            return None
        connection.send({"op": "reload_keymap", "seq": 1})
        return connection.read_line(seq=1)
    except (OSError, ValueError):
        return None
    finally:
        connection.close()


def last_stop(logs: Path) -> dict | None:
    """The last stop the broker told the user about (logs/notices.log), with its time."""
    path = Path(logs) / "notices.log"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            notice = json.loads(line)
        except ValueError:
            continue
        if "stopped" in notice:
            return notice
    return None
