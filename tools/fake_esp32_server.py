"""Development-only ESP32 server with scripted multiplexed response frames."""

from __future__ import annotations

import argparse
import socket
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class DisconnectFrame:
    """Script action that closes the active TCP client after an optional delay."""

    delay: float = 0.0


ScheduledFrame = str | tuple[float, str] | DisconnectFrame


MODE_SCRIPTS: dict[str, list[ScheduledFrame]] = {
    "ack": ["ARM_ACK,OK"],
    "legacy": ["OK"],
    "agv-before-ack": [
        "AGV,TELEMETRY,54.2,0,1,0,95.25,97.50",
        "ARM_ACK,OK",
    ],
    "sandwich": [
        "AGV,TELEMETRY,54.2,0,1,0,95.25,97.50",
        "AGV,TELEMETRY,53.0,0,1,0,96.10,96.85",
        "ARM_ACK,OK",
        "AGV,TELEMETRY,51.7,0,1,0,94.75,98.20",
    ],
    "error": ["ARM_ACK,ERROR"],
    "timeout": [],
}


class FakeEsp32Server:
    """Accept Arm CSV lines and emit one configurable frame script per line."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        response: str = "ARM_ACK,OK",
        command_scripts: Iterable[Iterable[ScheduledFrame]] | None = None,
    ):
        self.host = host
        self.port = port
        self.response = response
        self.received_commands: list[str] = []
        self.sent_frames: list[str] = []
        self._command_scripts: deque[list[ScheduledFrame]] = deque(
            [list(script) for script in (command_scripts or [])]
        )
        self._script_lock = threading.Lock()
        self._client_send_lock = threading.Lock()
        self._active_client_lock = threading.Lock()
        self._active_client: socket.socket | None = None
        self._active_client_event = threading.Event()
        self._listener: socket.socket | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._listener is None:
            return self.host, self.port
        address = self._listener.getsockname()
        return str(address[0]), int(address[1])

    def set_command_scripts(
        self, scripts: Iterable[Iterable[ScheduledFrame]]
    ) -> None:
        with self._script_lock:
            self._command_scripts = deque([list(script) for script in scripts])

    def start(self) -> "FakeEsp32Server":
        self._thread = threading.Thread(
            target=self.serve_forever, name="fake-esp32", daemon=True
        )
        self._thread.start()
        if not self._ready_event.wait(2.0):
            raise RuntimeError("fake ESP32 did not start")
        return self

    def send_unsolicited(
        self, frames: Iterable[ScheduledFrame], timeout: float = 1.0
    ) -> bool:
        """Send frames without waiting for an Arm command from the backend."""
        if not self._active_client_event.wait(timeout):
            raise TimeoutError("fake ESP32 has no active TCP client")
        with self._active_client_lock:
            client = self._active_client
        if client is None:
            raise ConnectionError("fake ESP32 client disconnected")
        return self._send_script(client, frames)

    def serve_forever(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(2)
        listener.settimeout(0.2)
        self._listener = listener
        self._ready_event.set()
        print(f"Fake ESP32 listening on {self.address[0]}:{self.address[1]}", flush=True)
        try:
            while not self._stop_event.is_set():
                try:
                    client, _ = listener.accept()
                except socket.timeout:
                    continue
                with client:
                    self._set_active_client(client)
                    try:
                        client.settimeout(0.2)
                        buffer = bytearray()
                        keep_connection = True
                        while keep_connection and not self._stop_event.is_set():
                            try:
                                chunk = client.recv(1024)
                            except socket.timeout:
                                continue
                            except OSError:
                                break
                            if not chunk:
                                break
                            buffer.extend(chunk)
                            while b"\n" in buffer:
                                raw, _, remaining = buffer.partition(b"\n")
                                buffer = bytearray(remaining)
                                command = raw.decode(
                                    "utf-8", errors="replace"
                                ).strip()
                                self.received_commands.append(command)
                                print(f"RX < {command}", flush=True)
                                if not self._send_script(
                                    client, self._next_script()
                                ):
                                    keep_connection = False
                                    break
                    finally:
                        self._clear_active_client(client)
        finally:
            listener.close()
            self._listener = None

    def _next_script(self) -> list[ScheduledFrame]:
        with self._script_lock:
            if self._command_scripts:
                return self._command_scripts.popleft()
        return [self.response]

    def _send_script(
        self, client: socket.socket, script: Iterable[ScheduledFrame]
    ) -> bool:
        for item in script:
            if isinstance(item, DisconnectFrame):
                if item.delay > 0 and self._stop_event.wait(item.delay):
                    return False
                with self._client_send_lock:
                    try:
                        client.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                self.sent_frames.append("<DISCONNECT>")
                print("TX > <DISCONNECT>", flush=True)
                return False
            if isinstance(item, tuple):
                delay, frame = item
            else:
                delay, frame = 0.0, item
            if delay > 0 and self._stop_event.wait(delay):
                return False
            with self._client_send_lock:
                try:
                    client.sendall((frame + "\n").encode("utf-8"))
                except OSError:
                    return False
            self.sent_frames.append(frame)
            print(f"TX > {frame}", flush=True)
        return True

    def _set_active_client(self, client: socket.socket) -> None:
        with self._active_client_lock:
            self._active_client = client
            self._active_client_event.set()

    def _clear_active_client(self, client: socket.socket) -> None:
        with self._active_client_lock:
            if self._active_client is client:
                self._active_client = None
                self._active_client_event.clear()

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener is not None:
            try:
                with socket.create_connection(self.address, timeout=0.2):
                    pass
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def __enter__(self) -> "FakeEsp32Server":
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--mode", choices=sorted(MODE_SCRIPTS), default="ack")
    parser.add_argument(
        "--response",
        help="single fallback response; overrides --mode for the first command",
    )
    args = parser.parse_args()
    script = [args.response] if args.response is not None else MODE_SCRIPTS[args.mode]
    server = FakeEsp32Server(
        args.host, args.port, command_scripts=[script]
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
