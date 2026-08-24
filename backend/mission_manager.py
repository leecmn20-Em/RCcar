"""Backend-only current mission state and mission-scoped logging policy."""

from __future__ import annotations

import threading
from typing import Any

from database.database import DatabaseManager


class MissionError(RuntimeError):
    """Base error for invalid mission state transitions."""


class MissionAlreadyActiveError(MissionError):
    pass


class NoActiveMissionError(MissionError):
    pass


class MissionManager:
    """Keep current_mission_id in the backend, never in the GUI."""

    def __init__(self, database: DatabaseManager):
        self.database = database
        self._current_mission_id: int | None = None
        self._lock = threading.RLock()

    @property
    def current_mission_id(self) -> int | None:
        with self._lock:
            return self._current_mission_id

    def start(self) -> int:
        with self._lock:
            if self._current_mission_id is not None:
                raise MissionAlreadyActiveError(
                    f"mission {self._current_mission_id} is already active"
                )
            self._current_mission_id = self.database.create_mission()
            return self._current_mission_id

    def end(self, result: str) -> int:
        with self._lock:
            if self._current_mission_id is None:
                raise NoActiveMissionError("there is no active mission")
            mission_id = self._current_mission_id
            self.database.end_mission(mission_id, result)
            self._current_mission_id = None
            return mission_id

    def log_arm_if_active(
        self, command: str, angles: list[int], ack: bool
    ) -> int | None:
        """Log a real ESP32 send attempt only when a mission is active."""
        with self._lock:
            if self._current_mission_id is None:
                return None
            self.database.insert_arm_log(
                mission_id=self._current_mission_id,
                command=command,
                angles=angles,
                ack=ack,
            )
            return self._current_mission_id

    def log_agv_if_active(self, event: dict[str, Any]) -> int | None:
        with self._lock:
            if self._current_mission_id is None:
                return None
            self.database.insert_agv_log(self._current_mission_id, event)
            return self._current_mission_id
