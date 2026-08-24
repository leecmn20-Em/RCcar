import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.mission_manager import (
    MissionAlreadyActiveError,
    MissionManager,
    NoActiveMissionError,
)
from database.database import DatabaseManager


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_directory.name) / "test.db"
        self.database = DatabaseManager(self.db_path)
        self.missions = MissionManager(self.database)

    def tearDown(self):
        self.database.close()
        self.temp_directory.cleanup()

    def test_schema_and_foreign_keys(self):
        self.assertTrue(self.database.foreign_keys_enabled())
        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            agv_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(agv_log)")
            }
        finally:
            connection.close()
        self.assertTrue({"mission", "arm_log", "agv_log"}.issubset(tables))
        self.assertTrue(
            {
                "motor_left",
                "motor_right",
                "left_rpm",
                "right_rpm",
            }.issubset(agv_columns)
        )

    def test_agv_log_preserves_decimal_rpm_without_writing_legacy_duty(self):
        mission_id = self.missions.start()
        self.database.insert_agv_log(
            mission_id,
            {
                "event": "TELEMETRY",
                "distance": 54.2,
                "left_ir": 0,
                "center_ir": 1,
                "right_ir": 0,
                "left_rpm": 95.25,
                "right_rpm": 97.5,
            },
        )

        row = self.database.get_agv_logs(mission_id)[0]
        self.assertEqual(row["left_rpm"], 95.25)
        self.assertEqual(row["right_rpm"], 97.5)
        self.assertIsNone(row["motor_left"])
        self.assertIsNone(row["motor_right"])

    def test_legacy_agv_schema_migration_preserves_existing_duty_row(self):
        legacy_path = Path(self.temp_directory.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                """
                CREATE TABLE mission (
                    mission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    result TEXT
                );
                CREATE TABLE arm_log (
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
                CREATE TABLE agv_log (
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
                INSERT INTO mission(mission_id, start_time)
                VALUES (1, '2026-08-24T10:00:00+09:00');
                INSERT INTO agv_log(
                    mission_id, timestamp, event, distance,
                    left_ir, center_ir, right_ir, motor_left, motor_right
                ) VALUES (
                    1, '2026-08-24T10:00:01+09:00', 'TELEMETRY', 54.2,
                    0, 1, 0, 255, 120
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        migrated = DatabaseManager(legacy_path)
        try:
            row = migrated.get_agv_logs(1)[0]
            self.assertTrue({"left_rpm", "right_rpm"}.issubset(row.keys()))
            self.assertEqual(row["motor_left"], 255)
            self.assertEqual(row["motor_right"], 120)
            self.assertIsNone(row["left_rpm"])
            self.assertIsNone(row["right_rpm"])
        finally:
            migrated.close()

    def test_mission_start_log_and_end(self):
        mission_id = self.missions.start()
        logged_id = self.missions.log_arm_if_active(
            "HOME", [90, 90, 90, 90], True
        )
        self.assertEqual(logged_id, mission_id)
        self.assertEqual(len(self.database.get_arm_logs(mission_id)), 1)

        ended_id = self.missions.end("SUCCESS")
        self.assertEqual(ended_id, mission_id)
        mission = self.database.get_mission(mission_id)
        self.assertIsNotNone(mission["end_time"])
        self.assertEqual(mission["result"], "SUCCESS")

    def test_no_mission_means_no_arm_log(self):
        self.assertIsNone(
            self.missions.log_arm_if_active("MOVE", [90, 90, 90, 90], True)
        )

    def test_mission_state_errors(self):
        with self.assertRaises(NoActiveMissionError):
            self.missions.end("SUCCESS")
        self.missions.start()
        with self.assertRaises(MissionAlreadyActiveError):
            self.missions.start()

    def test_arm_log_foreign_key(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.insert_arm_log(999, "MOVE", [1, 2, 3, 4], False)


if __name__ == "__main__":
    unittest.main()
