"""Non-blocking PyQt transport for the localhost NDJSON backend."""

from __future__ import annotations

import json
import queue
import socket
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from backend.parser import encode_ndjson


class BackendClient(QThread):
    """Own the GUI-side localhost socket outside the Qt main thread."""

    connected_changed = pyqtSignal(bool)
    message_received = pyqtSignal(object)
    transport_error = pyqtSignal(str)

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6000,
        reconnect_interval: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.reconnect_interval = reconnect_interval
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._outbox: queue.Queue[dict] = queue.Queue()
        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected_event.is_set()

    def send_message(self, message: dict) -> bool:
        if not self.connected:
            return False
        self._outbox.put(dict(message))
        return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._socket_lock:
            active_socket = self._socket
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_connection()
            except OSError as error:
                if not self._stop_event.is_set():
                    message = f"Backend 연결 실패: {error}"
                    if message != self._last_error:
                        self.transport_error.emit(message)
                        self._last_error = message
            finally:
                self._mark_disconnected()
                self._discard_pending_messages()

            if not self._stop_event.is_set():
                self._stop_event.wait(self.reconnect_interval)

    def _run_connection(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=1.0)
        sock.settimeout(0.1)
        with self._socket_lock:
            self._socket = sock
        self._connected_event.set()
        self.connected_changed.emit(True)
        self._last_error = None
        buffer = bytearray()

        try:
            while not self._stop_event.is_set():
                self._flush_outbox(sock)
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    raise ConnectionError("Backend가 연결을 종료했습니다.")
                buffer.extend(chunk)
                if len(buffer) > 1024 * 1024:
                    raise ConnectionError("Backend 메시지가 너무 큽니다.")

                while b"\n" in buffer:
                    raw_line, _, remaining = buffer.partition(b"\n")
                    buffer = bytearray(remaining)
                    try:
                        message = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        self.transport_error.emit(f"Backend JSON 해석 실패: {error}")
                        continue
                    if isinstance(message, dict):
                        self.message_received.emit(message)
                    else:
                        self.transport_error.emit("Backend 메시지가 JSON object가 아닙니다.")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _flush_outbox(self, sock: socket.socket) -> None:
        while True:
            try:
                message = self._outbox.get_nowait()
            except queue.Empty:
                return
            sock.sendall(encode_ndjson(message))

    def _mark_disconnected(self) -> None:
        was_connected = self._connected_event.is_set()
        self._connected_event.clear()
        with self._socket_lock:
            self._socket = None
        if was_connected:
            self.connected_changed.emit(False)

    def _discard_pending_messages(self) -> None:
        while True:
            try:
                self._outbox.get_nowait()
            except queue.Empty:
                return
