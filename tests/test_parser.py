import unittest

from backend.parser import (
    ProtocolError,
    decode_ndjson_line,
    encode_ndjson,
    parse_esp32_line,
    validate_angles,
)


class ParserTests(unittest.TestCase):
    def test_legacy_arm_ack(self):
        self.assertEqual(
            parse_esp32_line("OK\n"),
            {"system": "ARM", "type": "ACK", "ok": True},
        )

    def test_typed_arm_ack_ok(self):
        self.assertEqual(
            parse_esp32_line(bytearray(b"ARM_ACK,OK")),
            {"system": "ARM", "type": "ACK", "ok": True},
        )

    def test_typed_arm_ack_error(self):
        self.assertEqual(
            parse_esp32_line("ARM_ACK,ERROR"),
            {"system": "ARM", "type": "ACK", "ok": False},
        )

    def test_agv_telemetry(self):
        parsed = parse_esp32_line("AGV,TELEMETRY,54.2,0,1,0,95.25,97.5")
        self.assertEqual(
            parsed,
            {
                "system": "AGV",
                "event": "TELEMETRY",
                "distance": 54.2,
                "left_ir": 0,
                "center_ir": 1,
                "right_ir": 0,
                "left_rpm": 95.25,
                "right_rpm": 97.5,
            },
        )

    def test_agv_wrong_field_count(self):
        with self.assertRaises(ProtocolError):
            parse_esp32_line("AGV,TELEMETRY,54.2,0,1")

    def test_agv_obstacle_and_stop(self):
        for event in ("OBSTACLE", "STOP"):
            with self.subTest(event=event):
                parsed = parse_esp32_line(
                    f"AGV,{event},14.1,0,1,0,12.34,56.78"
                )
                self.assertEqual(parsed["system"], "AGV")
                self.assertEqual(parsed["event"], event)
                self.assertEqual(parsed["distance"], 14.1)
                self.assertEqual(parsed["left_rpm"], 12.34)
                self.assertEqual(parsed["right_rpm"], 56.78)

    def test_agv_destination_has_no_invented_sensor_values(self):
        self.assertEqual(
            parse_esp32_line("AGV,DEST"),
            {
                "system": "AGV",
                "event": "DEST",
                "distance": None,
                "left_ir": None,
                "center_ir": None,
                "right_ir": None,
                "left_rpm": None,
                "right_rpm": None,
            },
        )

    def test_agv_numeric_conversion_error(self):
        with self.assertRaisesRegex(ProtocolError, "numeric"):
            parse_esp32_line("AGV,TELEMETRY,far,0,1,0,95.25,97.5")

    def test_agv_rpm_must_be_finite_and_nonnegative(self):
        invalid_pairs = (
            ("-0.01", "10.0"),
            ("10.0", "-0.01"),
            ("nan", "10.0"),
            ("10.0", "inf"),
            ("10.0", "-inf"),
        )
        for left_rpm, right_rpm in invalid_pairs:
            with self.subTest(left_rpm=left_rpm, right_rpm=right_rpm):
                with self.assertRaises(ProtocolError):
                    parse_esp32_line(
                        "AGV,TELEMETRY,54.2,0,1,0,"
                        f"{left_rpm},{right_rpm}"
                    )

    def test_unknown_esp32_message(self):
        for message in ("", "AGV", "MAYBE"):
            with self.subTest(message=message), self.assertRaises(ProtocolError):
                parse_esp32_line(message)

    def test_malformed_arm_ack(self):
        for message in ("ARM_ACK", "ARM_ACK,WHAT", "ARM_ACK,OK,EXTRA"):
            with self.subTest(message=message), self.assertRaises(ProtocolError):
                parse_esp32_line(message)

    def test_unknown_agv_event(self):
        with self.assertRaises(ProtocolError):
            parse_esp32_line("AGV,UNKNOWN,1,0,0,0,0,0")

    def test_ndjson_round_trip(self):
        message = {"type": "arm_command", "angles": [90, 120, 80, 100]}
        encoded = encode_ndjson(message)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(decode_ndjson_line(encoded), message)

    def test_invalid_json(self):
        with self.assertRaises(ProtocolError):
            decode_ndjson_line("not-json")

    def test_angle_validation(self):
        self.assertEqual(validate_angles([0, 90, 180, 1]), [0, 90, 180, 1])
        for invalid in ([90, 90, 90], [90, 181, 90, 90], [90, 1.5, 90, 90]):
            with self.subTest(invalid=invalid), self.assertRaises(ProtocolError):
                validate_angles(invalid)


if __name__ == "__main__":
    unittest.main()
