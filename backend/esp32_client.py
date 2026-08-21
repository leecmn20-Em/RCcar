"""Backend-owned ESP32 TCP client with one dedicated receive loop."""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.parser import ProtocolError, parse_esp32_line, validate_angles


LOGGER = logging.getLogger(__name__)
Esp32EventHandler = Callable[[dict[str, Any]], None]


class Esp32Error(RuntimeError):
    """Base error for ESP32 connection and command failures."""


class Esp32NotConnectedError(Esp32Error):
    """Raised when a command is attempted without a connection."""


class Esp32TimeoutError(Esp32Error):
    """Raised when the pending Arm command is not acknowledged in time."""


@dataclass(frozen=True)
class ArmSendResult:
    ack: bool
    response: str
    wire_command: str
    error: str | None = None


@dataclass
class _PendingArmCommand:
    event: threading.Event = field(default_factory=threading.Event)
    completed: bool = False
    ack: bool = False
    response: str = ""
    error: str | None = None


class Esp32Client:
    """Own one ESP32 socket and route every received line in one thread.

    Arm sends are serialized because the wire protocol has no request ID.  A
    sender waits on its pending command event, but never reads the socket.
    ``_receiver_loop`` is the sole location that calls ``recv``.
    """

    MAX_LINE_BYTES = 8192
    RECEIVER_POLL_SECONDS = 0.2

    def __init__(
        self,
        connect_timeout: float = 3.0,
        ack_timeout: float = 2.0,
        event_handler: Esp32EventHandler | None = None,
    ):
        self.connect_timeout = connect_timeout
        self.ack_timeout = ack_timeout
        self._event_handler = event_handler

        self._socket: socket.socket | None = None
        self._endpoint: tuple[str, int] | None = None
        self._receiver_thread: threading.Thread | None = None
        self._receiver_stop: threading.Event | None = None
        self._generation = 0
        self._pending: _PendingArmCommand | None = None

        self._state_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._command_lock = threading.Lock()

    def set_event_handler(self, handler: Esp32EventHandler | None) -> None:
        with self._state_lock:
            self._event_handler = handler

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return self._socket is not None

    @property
    def endpoint(self) -> tuple[str, int] | None:
        with self._state_lock:
            return self._endpoint

    @property
    def receiver_alive(self) -> bool:
        with self._state_lock:
            thread = self._receiver_thread
            return bool(thread and thread.is_alive())

    def connect(self, ip: str, port: int) -> None:
        if not isinstance(ip, str) or not ip.strip():
            raise Esp32Error("ESP32 IP must not be empty")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise Esp32Error("ESP32 port must be between 1 and 65535")

        candidate: socket.socket | None = None
        try:
            candidate = socket.create_connection(
                (ip.strip(), port), timeout=self.connect_timeout
            )
            candidate.settimeout(self.RECEIVER_POLL_SECONDS)
        except OSError as error:
            if candidate is not None:
                candidate.close()
            raise Esp32Error(f"ESP32 connection failed: {error}") from error

        self.disconnect()
        with self._state_lock:
            self._generation += 1
            generation = self._generation
            stop_event = threading.Event()
            receiver = threading.Thread(
                target=self._receiver_loop,
                args=(candidate, generation, stop_event),
                name=f"esp32-receiver-{generation}",
                daemon=True,
            )
            self._socket = candidate
            self._endpoint = (ip.strip(), port)
            self._receiver_stop = stop_event
            self._receiver_thread = receiver
            receiver.start()

    def disconnect(self) -> None:
        self._disconnect_current("ESP32 disconnected", notify=False)

    def send_arm_command(self, angles: list[int] | tuple[int, ...]) -> ArmSendResult:
        """Send four angles and wait for receiver-routed ARM_ACK completion."""
        normalized = validate_angles(angles)
        wire_command = ",".join(map(str, normalized))

        with self._command_lock:
            with self._state_lock:
                sock = self._socket
                generation = self._generation
                if sock is None:
                    raise Esp32NotConnectedError("ESP32 is not connected")
                if self._pending is not None:
                    raise Esp32Error("another Arm command is already pending")
                pending = _PendingArmCommand()
                self._pending = pending

            try:
                with self._send_lock:
                    sock.sendall((wire_command + "\n").encode("ascii"))
            except OSError as error:
                message = f"ESP32 communication failed: {error}"
                self._disconnect_generation(generation, message, notify=True)
                raise Esp32Error(message) from error

            if not pending.event.wait(self.ack_timeout):
                timed_out = False
                with self._state_lock:
                    # If the receiver completed at the timeout boundary, use
                    # that result rather than discarding a valid ACK.
                    if not pending.completed and self._pending is pending:
                        self._pending = None
                        pending.completed = True
                        pending.error = (
                            f"ACK timeout after {self.ack_timeout:.1f} seconds"
                        )
                        timed_out = True
                if timed_out:
                    # With no wire request ID, connection reset is the only
                    # reliable barrier against a late ACK completing the next
                    # command.
                    self._disconnect_generation(
                        generation, pending.error or "ACK timeout", notify=True
                    )
                    raise Esp32TimeoutError(pending.error or "ACK timeout")

            return ArmSendResult(
                ack=pending.ack,
                response=pending.response,
                wire_command=wire_command,
                error=pending.error,
            )

    def _receiver_loop(
        self,
        sock: socket.socket,
        generation: int,
        stop_event: threading.Event,
    ) -> None:
        buffer = bytearray()
        connection_error: str | None = None
        try:
            while not stop_event.is_set():
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError as error:
                    if not stop_event.is_set():
                        connection_error = f"ESP32 receive failed: {error}"
                    break

                if not chunk:
                    connection_error = "ESP32 closed the connection"
                    break
                buffer.extend(chunk)

                while b"\n" in buffer:
                    raw_line, _, remaining = buffer.partition(b"\n")
                    buffer = bytearray(remaining)
                    self._route_received_line(raw_line, generation)

                if len(buffer) > self.MAX_LINE_BYTES:
                    self._emit_event(
                        {
                            "system": "DIAGNOSTIC",
                            "type": "FRAME_TOO_LARGE",
                            "message": "ESP32 line exceeded the receive limit",
                            "raw": buffer.decode("utf-8", errors="replace"),
                        }
                    )
                    buffer.clear()
        finally:
            if connection_error is not None:
                self._receiver_connection_lost(sock, generation, connection_error)
            try:
                sock.close()
            except OSError:
                pass

    def _route_received_line(self, raw_line: bytes, generation: int) -> None:
        with self._state_lock:
            if generation != self._generation or self._socket is None:
                return

        raw_text = raw_line.decode("utf-8", errors="replace").strip()
        try:
            parsed = parse_esp32_line(raw_line)
        except ProtocolError as error:
            self._emit_event(
                {
                    "system": "DIAGNOSTIC",
                    "type": "PROTOCOL_ERROR",
                    "message": str(error),
                    "raw": raw_text,
                }
            )
            return

        if parsed["system"] == "ARM":
            with self._state_lock:
                if generation != self._generation or self._socket is None:
                    return
                pending = self._pending
                if pending is not None:
                    self._pending = None
                    pending.completed = True
                    pending.ack = bool(parsed["ok"])
                    pending.response = raw_text
                    if not pending.ack:
                        pending.error = f"ESP32 returned {raw_text}"
                    pending.event.set()
                    return
            self._emit_event(
                {
                    "system": "DIAGNOSTIC",
                    "type": "UNEXPECTED_ARM_ACK",
                    "message": "ARM ACK arrived without a pending command",
                    "raw": raw_text,
                }
            )
            return

        self._emit_event(parsed)

    def _receiver_connection_lost(
        self, sock: socket.socket, generation: int, reason: str
    ) -> None:
        pending: _PendingArmCommand | None = None
        with self._state_lock:
            if generation != self._generation or self._socket is not sock:
                return
            stop_event = self._receiver_stop
            if stop_event is not None:
                stop_event.set()
            self._socket = None
            self._endpoint = None
            self._receiver_stop = None
            self._receiver_thread = None
            pending = self._pending
            self._pending = None
            if pending is not None:
                pending.completed = True
                pending.error = reason
                pending.event.set()
        self._emit_event(
            {
                "system": "CONNECTION",
                "type": "STATUS",
                "connected": False,
                "error": reason,
            }
        )

    def _disconnect_current(self, reason: str, notify: bool) -> None:
        with self._state_lock:
            generation = self._generation
        self._disconnect_generation(generation, reason, notify)

    def _disconnect_generation(
        self, generation: int, reason: str, notify: bool
    ) -> None:
        sock: socket.socket | None = None
        receiver: threading.Thread | None = None
        pending: _PendingArmCommand | None = None
        with self._state_lock:
            if generation != self._generation:
                return
            sock = self._socket
            receiver = self._receiver_thread
            stop_event = self._receiver_stop
            if stop_event is not None:
                stop_event.set()
            self._socket = None
            self._endpoint = None
            self._receiver_thread = None
            self._receiver_stop = None
            pending = self._pending
            self._pending = None
            if pending is not None:
                pending.completed = True
                pending.error = reason
                pending.event.set()

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if receiver is not None and receiver is not threading.current_thread():
            receiver.join(timeout=1.0)
        if notify and sock is not None:
            self._emit_event(
                {
                    "system": "CONNECTION",
                    "type": "STATUS",
                    "connected": False,
                    "error": reason,
                }
            )

    def _emit_event(self, event: dict[str, Any]) -> None:
        with self._state_lock:
            handler = self._event_handler
        if handler is None:
            return
        try:
            handler(event)
        except Exception:
            # A DB/UI routing error must never terminate the sole receiver.
            LOGGER.exception("ESP32 event handler failed for %r", event)
