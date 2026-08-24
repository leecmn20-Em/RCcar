"""Parsers and validators for the local IPC and ESP32 line protocols."""

from __future__ import annotations

import json
import math
from typing import Any


class ProtocolError(ValueError):
    """Raised when a received protocol message is malformed or unsupported."""


def encode_ndjson(message: dict[str, Any]) -> bytes:
    """Encode one object as a UTF-8, newline-delimited JSON frame."""
    if not isinstance(message, dict):
        raise ProtocolError("NDJSON message must be a JSON object")
    return (
        json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def decode_ndjson_line(line: bytes | str) -> dict[str, Any]:
    """Decode and minimally validate one NDJSON line (without stream framing)."""
    if isinstance(line, bytes):
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProtocolError("message is not valid UTF-8") from error

    if not line.strip():
        raise ProtocolError("empty JSON message")

    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise ProtocolError(f"invalid JSON: {error.msg}") from error

    if not isinstance(value, dict):
        raise ProtocolError("JSON message must be an object")
    message_type = value.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise ProtocolError("JSON message requires a non-empty 'type'")
    return value


def validate_angles(value: Any) -> list[int]:
    """Return four integer joint angles after validating the 0..180 range."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ProtocolError("angles must contain exactly four values")

    angles: list[int] = []
    for angle in value:
        if isinstance(angle, bool) or not isinstance(angle, int):
            raise ProtocolError("each angle must be an integer")
        if not 0 <= angle <= 180:
            raise ProtocolError("each angle must be between 0 and 180")
        angles.append(angle)
    return angles


def parse_esp32_line(line: bytes | bytearray | str) -> dict[str, Any]:
    """Classify one newline-framed message received from the ESP32.

    ``OK`` remains a transitional alias for ``ARM_ACK,OK``.  AGV events with
    sensor fields use eight CSV columns ending in left/right RPM values, while
    ``AGV,DEST`` intentionally has no invented sensor values and is represented
    with ``None`` fields.
    """
    if isinstance(line, (bytes, bytearray)):
        try:
            line = bytes(line).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProtocolError("ESP32 message is not valid UTF-8") from error

    text = line.strip()
    if not text:
        raise ProtocolError("empty ESP32 message")
    if text == "OK":
        return {"system": "ARM", "type": "ACK", "ok": True}

    fields = [field.strip() for field in text.split(",")]
    if fields[0] == "ARM_ACK":
        if len(fields) != 2:
            raise ProtocolError("ARM_ACK message must contain exactly two CSV fields")
        if fields[1] == "OK":
            return {"system": "ARM", "type": "ACK", "ok": True}
        if fields[1] == "ERROR":
            return {"system": "ARM", "type": "ACK", "ok": False}
        raise ProtocolError(f"unsupported ARM_ACK status: {fields[1]!r}")

    if fields[0] != "AGV":
        raise ProtocolError(f"unsupported ESP32 response: {text!r}")
    if len(fields) < 2 or not fields[1]:
        raise ProtocolError("AGV message requires an event")

    event = fields[1]
    if event == "DEST":
        if len(fields) != 2:
            raise ProtocolError("AGV,DEST must contain exactly two CSV fields")
        return {
            "system": "AGV",
            "event": "DEST",
            "distance": None,
            "left_ir": None,
            "center_ir": None,
            "right_ir": None,
            "left_rpm": None,
            "right_rpm": None,
        }

    supported_events = {"TRACING", "OBSTACLE", "STOP"}
    if event not in supported_events:
        raise ProtocolError(f"unsupported AGV event: {event!r}")
    if len(fields) != 8:
        raise ProtocolError(
            f"AGV,{event} message must contain exactly eight CSV fields"
        )

    try:
        distance = float(fields[2])
        left_ir = int(fields[3])
        center_ir = int(fields[4])
        right_ir = int(fields[5])
        left_rpm = float(fields[6])
        right_rpm = float(fields[7])
    except ValueError as error:
        raise ProtocolError("AGV numeric field conversion failed") from error

    if not math.isfinite(distance):
        raise ProtocolError("AGV distance must be finite")
    if not math.isfinite(left_rpm) or not math.isfinite(right_rpm):
        raise ProtocolError("AGV RPM values must be finite")
    if left_rpm < 0 or right_rpm < 0:
        raise ProtocolError("AGV RPM values must not be negative")

    return {
        "system": "AGV",
        "event": event,
        "distance": distance,
        "left_ir": left_ir,
        "center_ir": center_ir,
        "right_ir": right_ir,
        "left_rpm": left_rpm,
        "right_rpm": right_rpm,
    }
