"""Thread-safe SQLite schema and persistence operations for robot missions."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mission (
    mission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    result TEXT
);

CREATE TABLE IF NOT EXISTS arm_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    command TEXT NOT NULL,
    base INTEGER,
    shoulder INTEGER,
    upper INTEGER,
    forearm INTEGER,
    ack INTEGER,
    FOREIGN KEY(mission_id) REFERENCES mission(mission_id)
);

CREATE TABLE IF NOT EXISTS agv_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    distance REAL,
    left_ir INTEGER,
    center_ir INTEGER,
    right_ir INTEGER,
    motor_left INTEGER,
    motor_right INTEGER,
    FOREIGN KEY(mission_id) REFERENCES mission(mission_id)
);

CREATE INDEX IF NOT EXISTS idx_arm_log_mission_timestamp
    ON arm_log(mission_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_agv_log_mission_timestamp
    ON agv_log(mission_id, timestamp);
"""


class DatabaseManager:
    """Own the backend's one SQLite connection and serialize its use."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.path), check_same_thread=False, timeout=5.0
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(SCHEMA_SQL)
            self._connection.commit()

    @staticmethod
    def timestamp() -> str:
        return datetime.now().astimezone().isoformat(timespec="milliseconds")

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def create_mission(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO mission(start_time) VALUES (?)", (self.timestamp(),)
            )
            return int(cursor.lastrowid)

    def end_mission(self, mission_id: int, result: str) -> None:
        if not isinstance(result, str) or not result.strip():
            raise ValueError("mission result must not be empty")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE mission
                   SET end_time = ?, result = ?
                 WHERE mission_id = ? AND end_time IS NULL
                """,
                (self.timestamp(), result.strip(), mission_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"active mission {mission_id} was not found")

    def insert_arm_log(
        self, mission_id: int, command: str, angles: list[int], ack: bool
    ) -> int:
        if len(angles) != 4:
            raise ValueError("arm log requires exactly four angles")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO arm_log(
                    mission_id, timestamp, command,
                    base, shoulder, upper, forearm, ack
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    self.timestamp(),
                    command,
                    *angles,
                    int(bool(ack)),
                ),
            )
            return int(cursor.lastrowid)

    def insert_agv_log(self, mission_id: int, event: dict[str, Any]) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO agv_log(
                    mission_id, timestamp, event, distance,
                    left_ir, center_ir, right_ir, motor_left, motor_right
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    self.timestamp(),
                    event["event"],
                    event.get("distance"),
                    event.get("left_ir"),
                    event.get("center_ir"),
                    event.get("right_ir"),
                    event.get("motor_left"),
                    event.get("motor_right"),
                ),
            )
            return int(cursor.lastrowid)

    def get_mission(self, mission_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(
                "SELECT * FROM mission WHERE mission_id = ?", (mission_id,)
            ).fetchone()

    def get_arm_logs(self, mission_id: int) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._connection.execute(
                    "SELECT * FROM arm_log WHERE mission_id = ? ORDER BY id",
                    (mission_id,),
                ).fetchall()
            )

    def get_agv_logs(self, mission_id: int) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._connection.execute(
                    "SELECT * FROM agv_log WHERE mission_id = ? ORDER BY id",
                    (mission_id,),
                ).fetchall()
            )

    def foreign_keys_enabled(self) -> bool:
        with self._lock:
            row = self._connection.execute("PRAGMA foreign_keys").fetchone()
            return bool(row[0])

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
