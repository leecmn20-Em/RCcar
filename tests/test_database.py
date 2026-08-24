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
        finally:
            connection.close()
        self.assertTrue({"mission", "arm_log", "agv_log"}.issubset(tables))

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
