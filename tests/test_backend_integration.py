import json
import socket
import tempfile
import time
import unittest
from pathlib import Path

from backend.esp32_client import Esp32Client
from backend.parser import encode_ndjson
from backend.robot_backend import RobotBackendServer
from tools.fake_esp32_server import DisconnectFrame, FakeEsp32Server


class BackendIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_directory.name) / "integration.db"
        self.fake_esp32 = FakeEsp32Server().start()
        esp32_client = Esp32Client(ack_timeout=0.2)
        self.backend = RobotBackendServer(
            host="127.0.0.1",
            port=0,
            db_path=self.db_path,
            esp32_client=esp32_client,
        )
        self.backend.start_in_thread()
        self.client = socket.create_connection(self.backend.address, timeout=2.0)
        self.client.settimeout(0.1)
        self.buffer = bytearray()
        self.inbox: list[dict] = []
        self._receive_type("backend_status")
        self._receive_type("esp_status")

    def tearDown(self):
        try:
            self.client.close()
        finally:
            self.backend.shutdown()
            self.fake_esp32.stop()
            self.temp_directory.cleanup()

    def _send(self, message):
        self.client.sendall(encode_ndjson(message))

    def _receive_one(self, deadline):
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for backend message")
            self.client.settimeout(min(0.1, remaining))
            try:
                chunk = self.client.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                self.fail("backend closed the connection")
            self.buffer.extend(chunk)
        raw, _, remaining = self.buffer.partition(b"\n")
        self.buffer = bytearray(remaining)
        return json.loads(raw.decode("utf-8"))

    def _receive_matching(self, predicate, timeout=2.0):
        for index, message in enumerate(self.inbox):
            if predicate(message):
                return self.inbox.pop(index)

        deadline = time.monotonic() + timeout
        while True:
            message = self._receive_one(deadline)
            if predicate(message):
                return message
            self.inbox.append(message)

    def _receive_type(self, expected_type, request_id=None, timeout=2.0):
        return self._receive_matching(
            lambda message: message.get("type") == expected_type
            and (request_id is None or message.get("request_id") == request_id),
            timeout,
        )

    def _connect_esp32(self, request_id="esp-connect"):
        host, port = self.fake_esp32.address
        self._send(
            {
                "type": "esp_connect",
                "ip": host,
                "port": port,
                "request_id": request_id,
            }
        )
        status = self._receive_type("esp_status", request_id)
        self.assertTrue(status["connected"])

    def _send_arm(self, request_id, angles=None, command="MOVE", timeout=2.0):
        self._send(
            {
                "type": "arm_command",
                "command": command,
                "angles": angles or [90, 120, 80, 100],
                "request_id": request_id,
            }
        )
        return self._receive_type("arm_result", request_id, timeout)

    def _receive_agv(self, event, distance=None, timeout=2.0):
        return self._receive_matching(
            lambda message: message.get("type") == "agv_event"
            and message.get("event") == event
            and (distance is None or message.get("distance") == distance),
            timeout,
        )

    def test_scenario_a_typed_and_legacy_ack(self):
        self._connect_esp32()
        typed = self._send_arm("typed")
        self.assertTrue(typed["ack"])
        self.assertEqual(typed["response"], "ARM_ACK,OK")

        self.fake_esp32.set_command_scripts([["OK"]])
        legacy = self._send_arm("legacy", [10, 20, 30, 40])
        self.assertTrue(legacy["ack"])
        self.assertEqual(legacy["response"], "OK")

    def test_scenario_b_agv_before_ack_is_routed_separately(self):
        self.backend.esp32.ack_timeout = 1.0
        self.fake_esp32.set_command_scripts(
            [
                [
                    "AGV,TELEMETRY,54.2,0,1,0,180,180",
                    (0.5, "ARM_ACK,OK"),
                ]
            ]
        )
        self._connect_esp32()
        started_at = time.monotonic()
        self._send(
            {
                "type": "arm_command",
                "command": "MOVE",
                "angles": [90, 120, 80, 100],
                "request_id": "agv-before",
            }
        )
        agv = self._receive_agv("TELEMETRY", 54.2, timeout=0.35)
        agv_elapsed = time.monotonic() - started_at
        result = self._receive_type("arm_result", "agv-before", timeout=1.0)

        self.assertTrue(result["ack"])
        self.assertFalse(agv["logged"])
        self.assertEqual(agv["motor_left"], 180)
        self.assertLess(agv_elapsed, 0.4)

    def test_pending_command_disconnect_releases_wait_immediately(self):
        self.backend.esp32.ack_timeout = 1.0
        self.fake_esp32.set_command_scripts([[DisconnectFrame(delay=0.05)]])
        self._connect_esp32()
        self._send({"type": "mission_start", "request_id": "disconnect-mission"})
        mission_id = self._receive_type(
            "mission_started", "disconnect-mission"
        )["mission_id"]

        started_at = time.monotonic()
        result = self._send_arm("disconnect-pending", timeout=0.6)
        elapsed = time.monotonic() - started_at

        self.assertFalse(result["ack"])
        self.assertIn("connection", result["error"].lower())
        self.assertLess(elapsed, 0.5)
        self.assertFalse(self.backend.esp32.connected)
        self.assertEqual(
            [row["ack"] for row in self.backend.database.get_arm_logs(mission_id)],
            [0],
        )

    def test_ack_without_pending_is_diagnostic_and_not_buffered(self):
        self._connect_esp32()
        self.fake_esp32.send_unsolicited(["ARM_ACK,OK"])
        diagnostic = self._receive_type("esp_diagnostic")
        self.assertEqual(diagnostic["code"], "UNEXPECTED_ARM_ACK")

        self.fake_esp32.set_command_scripts([[]])
        result = self._send_arm("after-unsolicited", timeout=1.0)
        self.assertFalse(result["ack"])
        self.assertIn("ACK timeout", result["error"])

    def test_duplicate_ack_is_discarded_before_next_command(self):
        self.fake_esp32.set_command_scripts(
            [["ARM_ACK,OK", "ARM_ACK,OK"], []]
        )
        self._connect_esp32()

        first = self._send_arm("first-with-duplicate")
        diagnostic = self._receive_type("esp_diagnostic")
        self.assertTrue(first["ack"])
        self.assertEqual(diagnostic["code"], "UNEXPECTED_ARM_ACK")

        second = self._send_arm("after-duplicate", timeout=1.0)
        self.assertFalse(second["ack"])
        self.assertIn("ACK timeout", second["error"])

    def test_scenario_c_agv_frames_before_and_after_ack_are_not_lost(self):
        self.fake_esp32.set_command_scripts(
            [
                [
                    "AGV,TELEMETRY,54.2,0,1,0,180,180",
                    "AGV,TELEMETRY,53.0,0,1,0,180,180",
                    "ARM_ACK,OK",
                    "AGV,TELEMETRY,51.7,0,1,0,180,180",
                ]
            ]
        )
        self._connect_esp32()
        result = self._send_arm("sandwich")
        distances = [
            self._receive_agv("TELEMETRY", distance)["distance"]
            for distance in (54.2, 53.0, 51.7)
        ]

        self.assertTrue(result["ack"])
        self.assertEqual(distances, [54.2, 53.0, 51.7])

    def test_scenario_d_error_ack_and_timeout(self):
        self.fake_esp32.set_command_scripts([["ARM_ACK,ERROR"], []])
        self._connect_esp32()
        self._send({"type": "mission_start", "request_id": "failure-mission"})
        mission_id = self._receive_type(
            "mission_started", "failure-mission"
        )["mission_id"]

        rejected = self._send_arm("error-ack")
        self.assertFalse(rejected["ack"])
        self.assertIn("ARM_ACK,ERROR", rejected["error"])
        self.assertTrue(self.backend.esp32.connected)

        timed_out = self._send_arm("timeout", timeout=1.0)
        self.assertFalse(timed_out["ack"])
        self.assertIn("ACK timeout", timed_out["error"])
        self.assertFalse(self.backend.esp32.connected)
        self.assertEqual(
            [row["ack"] for row in self.backend.database.get_arm_logs(mission_id)],
            [0, 0],
        )

    def test_scenario_e_late_ack_cannot_complete_next_command(self):
        self.backend.esp32.ack_timeout = 0.1
        self.fake_esp32.set_command_scripts([[(0.35, "ARM_ACK,OK")]])
        self._connect_esp32()

        first = self._send_arm("first-timeout", timeout=1.0)
        self.assertFalse(first["ack"])
        self.assertIn("ACK timeout", first["error"])
        self.assertFalse(self.backend.esp32.connected)

        # Let the old server-side connection attempt its late ACK.  The client
        # has reset that TCP connection, so a new command requires reconnect.
        time.sleep(0.4)
        self.fake_esp32.set_command_scripts([["ARM_ACK,OK"]])
        self._connect_esp32("esp-reconnect")
        second = self._send_arm("second-after-reconnect")
        self.assertTrue(second["ack"])
        self.assertEqual(second["response"], "ARM_ACK,OK")
        self.assertEqual(
            self.fake_esp32.received_commands,
            ["90,120,80,100", "90,120,80,100"],
        )

    def test_malformed_frames_do_not_kill_receiver(self):
        self.fake_esp32.set_command_scripts(
            [["GARBAGE", "AGV,UNKNOWN,1,0,0,0,0,0", "ARM_ACK,OK"]]
        )
        self._connect_esp32()
        result = self._send_arm("after-malformed")
        first = self._receive_type("esp_diagnostic")
        second = self._receive_type("esp_diagnostic")

        self.assertTrue(result["ack"])
        self.assertEqual(first["code"], "PROTOCOL_ERROR")
        self.assertEqual(second["code"], "PROTOCOL_ERROR")
        self.assertTrue(self.backend.esp32.receiver_alive)

    def test_mission_routes_two_agv_rows_and_one_arm_row(self):
        self.fake_esp32.set_command_scripts(
            [
                ["AGV,STOP,20.0,0,1,0,0,0", "ARM_ACK,OK"],
                [
                    "AGV,TELEMETRY,54.2,0,1,0,180,180",
                    "AGV,OBSTACLE,14.1,0,1,0,0,0",
                    "ARM_ACK,OK",
                ],
            ]
        )
        self._connect_esp32()

        outside = self._send_arm("outside-mission")
        outside_agv = self._receive_agv("STOP", 20.0)
        self.assertFalse(outside["logged"])
        self.assertFalse(outside_agv["logged"])

        self._send({"type": "mission_start", "request_id": "mission-start"})
        started = self._receive_type("mission_started", "mission-start")
        mission_id = started["mission_id"]

        arm = self._send_arm("mission-arm", command="MOVE")
        telemetry = self._receive_agv("TELEMETRY", 54.2)
        obstacle = self._receive_agv("OBSTACLE", 14.1)
        self.assertTrue(arm["ack"])
        self.assertTrue(arm["logged"])
        self.assertTrue(telemetry["logged"])
        self.assertTrue(obstacle["logged"])

        self._send(
            {
                "type": "mission_end",
                "result": "SUCCESS",
                "request_id": "mission-end",
            }
        )
        self._receive_type("mission_ended", "mission-end")

        mission = self.backend.database.get_mission(mission_id)
        arm_logs = self.backend.database.get_arm_logs(mission_id)
        agv_logs = self.backend.database.get_agv_logs(mission_id)
        self.assertEqual(mission["result"], "SUCCESS")
        self.assertEqual(len(arm_logs), 1)
        self.assertEqual(arm_logs[0]["ack"], 1)
        self.assertEqual([row["event"] for row in agv_logs], ["TELEMETRY", "OBSTACLE"])

    def test_bad_json_and_invalid_angles_return_errors(self):
        self.client.sendall(b"not-json\n")
        self.assertEqual(self._receive_type("error")["code"], "invalid_request")

        self._send(
            {
                "type": "arm_command",
                "command": "MOVE",
                "angles": [90, 90, 181, 90],
                "request_id": "invalid-angles",
            }
        )
        error = self._receive_type("error", "invalid-angles")
        self.assertEqual(error["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
