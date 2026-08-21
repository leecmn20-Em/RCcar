"""Local NDJSON backend that owns ESP32 TCP and SQLite access."""

from __future__ import annotations

import argparse
import socket
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.esp32_client import Esp32Client, Esp32Error, Esp32NotConnectedError
from backend.mission_manager import MissionError, MissionManager
from backend.parser import (
    ProtocolError,
    decode_ndjson_line,
    encode_ndjson,
    validate_angles,
)
from database.database import DatabaseManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6000
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "robot_system.db"
SUPPORTED_ARM_COMMANDS = {"MOVE", "HOME", "TEACHING", "ACTION"}
MAX_IPC_BUFFER_BYTES = 1024 * 1024


class RobotBackendServer:
    """Serve GUI clients while keeping ESP32 and DB ownership centralized."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        db_path: str | Path = DEFAULT_DB_PATH,
        esp32_client: Esp32Client | None = None,
    ):
        self.host = host
        self.port = port
        self.database = DatabaseManager(db_path)
        self.missions = MissionManager(self.database)
        self.esp32 = esp32_client or Esp32Client()

        self._listener: socket.socket | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._client_sockets: set[socket.socket] = set()
        self._client_threads: set[threading.Thread] = set()
        self._clients_lock = threading.RLock()
        self._ipc_send_lock = threading.RLock()
        self._serve_thread: threading.Thread | None = None
        self.esp32.set_event_handler(self._handle_esp32_event)

    @property
    def address(self) -> tuple[str, int]:
        if self._listener is None:
            return self.host, self.port
        address = self._listener.getsockname()
        return str(address[0]), int(address[1])

    def start_in_thread(self, timeout: float = 3.0) -> threading.Thread:
        thread = threading.Thread(
            target=self.serve_forever, name="robot-backend", daemon=True
        )
        self._serve_thread = thread
        thread.start()
        if not self._ready_event.wait(timeout):
            raise RuntimeError("backend server did not start in time")
        return thread

    def serve_forever(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
            listener.listen(5)
            listener.settimeout(0.5)
            self._listener = listener
            self._ready_event.set()
            host, port = self.address
            print(f"Robot backend listening on {host}:{port}", flush=True)
            print(f"SQLite database: {self.database.path}", flush=True)

            while not self._stop_event.is_set():
                try:
                    client_socket, address = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    raise

                client_socket.settimeout(0.5)
                thread = threading.Thread(
                    target=self._serve_client,
                    args=(client_socket, address),
                    name=f"gui-client-{address[0]}:{address[1]}",
                    daemon=True,
                )
                with self._clients_lock:
                    self._client_sockets.add(client_socket)
                    self._client_threads.add(thread)
                thread.start()
        finally:
            self._ready_event.set()
            try:
                listener.close()
            except OSError:
                pass
            self._listener = None

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()

        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass

        with self._clients_lock:
            clients = list(self._client_sockets)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()

        self.esp32.disconnect()
        current = threading.current_thread()
        with self._clients_lock:
            client_threads = list(self._client_threads)
        for thread in client_threads:
            if thread is not current:
                thread.join(timeout=1.0)
        if self._serve_thread is not None and self._serve_thread is not current:
            self._serve_thread.join(timeout=1.5)
        self.database.close()

    def _serve_client(
        self, client_socket: socket.socket, address: tuple[str, int]
    ) -> None:
        del address
        buffer = bytearray()
        try:
            self._send(
                client_socket,
                {
                    "type": "backend_status",
                    "connected": True,
                    "mission_id": self.missions.current_mission_id,
                },
            )
            self._send(client_socket, self._esp_status_message())

            while not self._stop_event.is_set():
                try:
                    chunk = client_socket.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > MAX_IPC_BUFFER_BYTES:
                    self._send(
                        client_socket,
                        self._error("IPC receive buffer exceeded 1 MiB", "frame_too_large"),
                    )
                    break

                while b"\n" in buffer:
                    raw_line, _, remaining = buffer.partition(b"\n")
                    buffer = bytearray(remaining)
                    request = None
                    try:
                        request = decode_ndjson_line(raw_line)
                        responses = self.handle_request(request)
                    except ProtocolError as error:
                        request_id = request.get("request_id") if request else None
                        responses = [
                            self._error(str(error), "invalid_request", request_id)
                        ]
                    except sqlite3.Error as error:
                        request_id = request.get("request_id") if request else None
                        responses = [
                            self._error(
                                f"database error: {error}",
                                "database_error",
                                request_id,
                            )
                        ]
                    except Exception as error:
                        request_id = request.get("request_id") if request else None
                        responses = [
                            self._error(
                                f"internal backend error: {error}",
                                "internal_error",
                                request_id,
                            )
                        ]

                    for response in responses:
                        self._send(client_socket, response)
        finally:
            with self._clients_lock:
                self._client_sockets.discard(client_socket)
                self._client_threads.discard(threading.current_thread())
            try:
                client_socket.close()
            except OSError:
                pass

    def handle_request(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        message_type = request["type"]
        request_id = request.get("request_id")

        if message_type == "esp_connect":
            ip = request.get("ip")
            port = request.get("port")
            if not isinstance(ip, str) or not ip.strip():
                raise ProtocolError("esp_connect requires a non-empty ip")
            if isinstance(port, bool) or not isinstance(port, int):
                raise ProtocolError("esp_connect requires an integer port")
            try:
                self.esp32.connect(ip, port)
            except Esp32Error as error:
                return [
                    self._error(str(error), "esp_connect_failed", request_id),
                    self._esp_status_message(request_id),
                ]
            return [self._esp_status_message(request_id)]

        if message_type == "esp_disconnect":
            self.esp32.disconnect()
            return [self._esp_status_message(request_id)]

        if message_type == "mission_start":
            try:
                mission_id = self.missions.start()
            except MissionError as error:
                return [self._error(str(error), "mission_already_active", request_id)]
            return [
                {
                    "type": "mission_started",
                    "mission_id": mission_id,
                    "request_id": request_id,
                }
            ]

        if message_type == "mission_end":
            result = request.get("result")
            if not isinstance(result, str) or not result.strip():
                raise ProtocolError("mission_end requires a non-empty result")
            if len(result.strip()) > 64:
                raise ProtocolError("mission result must be at most 64 characters")
            try:
                mission_id = self.missions.end(result.strip())
            except MissionError as error:
                return [self._error(str(error), "no_active_mission", request_id)]
            return [
                {
                    "type": "mission_ended",
                    "mission_id": mission_id,
                    "result": result.strip(),
                    "request_id": request_id,
                }
            ]

        if message_type == "arm_command":
            return self._handle_arm_command(request, request_id)

        return [
            self._error(
                f"unsupported message type: {message_type!r}",
                "unsupported_type",
                request_id,
            )
        ]

    def _handle_arm_command(
        self, request: dict[str, Any], request_id: Any
    ) -> list[dict[str, Any]]:
        command = request.get("command")
        if not isinstance(command, str):
            raise ProtocolError("arm_command requires a command string")
        command = command.strip().upper()
        if command not in SUPPORTED_ARM_COMMANDS:
            raise ProtocolError(
                f"command must be one of {sorted(SUPPORTED_ARM_COMMANDS)}"
            )
        angles = validate_angles(request.get("angles"))

        ack = False
        response = ""
        wire_command = ",".join(map(str, angles))
        error_message: str | None = None
        attempted = False
        try:
            result = self.esp32.send_arm_command(angles)
            attempted = True
            ack = result.ack
            response = result.response
            wire_command = result.wire_command
            error_message = result.error
        except Esp32NotConnectedError as error:
            error_message = str(error)
        except Esp32Error as error:
            # A connected send that times out or fails is still an attempt and
            # is stored as ack=0 when a mission is active.
            attempted = True
            error_message = str(error)

        logged_mission_id = None
        if attempted:
            logged_mission_id = self.missions.log_arm_if_active(command, angles, ack)

        arm_result: dict[str, Any] = {
            "type": "arm_result",
            "command": command,
            "angles": angles,
            "ack": ack,
            "response": response,
            "wire_command": wire_command,
            "mission_id": logged_mission_id,
            "logged": logged_mission_id is not None,
            "request_id": request_id,
        }
        if error_message:
            arm_result["error"] = error_message
        if attempted and logged_mission_id is None:
            arm_result["note"] = "no active mission; arm attempt was not stored"

        # Connection-loss/timeout status is broadcast by the receiver client
        # callback, so the requesting GUI does not need a duplicate status.
        return [arm_result]

    def _handle_esp32_event(self, event: dict[str, Any]) -> None:
        """Route receiver-thread events without ever reading the socket here."""
        system = event.get("system")
        if system == "AGV":
            try:
                mission_id = self.missions.log_agv_if_active(event)
            except sqlite3.Error as error:
                self._broadcast(
                    self._error(f"database error: {error}", "database_error")
                )
                mission_id = None

            message = {
                "type": "agv_event",
                "event": event["event"],
                "distance": event.get("distance"),
                "left_ir": event.get("left_ir"),
                "center_ir": event.get("center_ir"),
                "right_ir": event.get("right_ir"),
                "motor_left": event.get("motor_left"),
                "motor_right": event.get("motor_right"),
                "mission_id": mission_id,
                "logged": mission_id is not None,
            }
            if mission_id is None:
                message["note"] = "no active mission; AGV event was not stored"
            self._broadcast(message)
            return

        if system == "CONNECTION":
            message = self._esp_status_message()
            if event.get("error"):
                message["error"] = event["error"]
            self._broadcast(message)
            return

        if system == "DIAGNOSTIC":
            print(
                f"ESP32 diagnostic [{event.get('type')}]: {event.get('message')}",
                flush=True,
            )
            self._broadcast(
                {
                    "type": "esp_diagnostic",
                    "code": event.get("type"),
                    "message": event.get("message"),
                    "raw": event.get("raw"),
                }
            )

    def _esp_status_message(self, request_id: Any = None) -> dict[str, Any]:
        endpoint = self.esp32.endpoint
        message: dict[str, Any] = {
            "type": "esp_status",
            "connected": self.esp32.connected,
            "request_id": request_id,
        }
        if endpoint is not None:
            message.update({"ip": endpoint[0], "port": endpoint[1]})
        return message

    @staticmethod
    def _error(
        message: str, code: str, request_id: Any = None
    ) -> dict[str, Any]:
        return {
            "type": "error",
            "message": message,
            "code": code,
            "request_id": request_id,
        }

    def _broadcast(self, message: dict[str, Any]) -> None:
        with self._clients_lock:
            clients = list(self._client_sockets)
        for client_socket in clients:
            self._send(client_socket, message)

    def _send(self, client_socket: socket.socket, message: dict[str, Any]) -> None:
        # Receiver callbacks can broadcast while a client-handler thread sends
        # arm_result.  Serialize complete NDJSON frames to prevent interleaving.
        with self._ipc_send_lock:
            try:
                client_socket.sendall(encode_ndjson(message))
            except OSError:
                pass


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    server = RobotBackendServer(args.host, args.port, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping robot backend...", flush=True)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
