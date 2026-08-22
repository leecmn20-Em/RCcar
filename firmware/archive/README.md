# Recovered Robot Arm source

`arms_20260819_original.ino` recovers the source from Git commit
`0c65aeae587293f91c1ed09b065e4ceb98cfc7aa` (2026-08-19). It was deleted by
commit `c86db7556077666aac7afeb66ce7abd542e57332`.

This is reference material, not flash-ready firmware. It contains the historical
pin mapping `base=3`, `shoulder=5`, `forearm=6`, `upperarm=9`, parses colon-delimited
serial input, and forces the shoulder PWM to 70 degrees in every loop. Do not flash
it without first reconciling those details with the actual controller and wiring.

The maintained SoftAP/TCP integration lives in
`../robot_arm_esp32/robot_arm_esp32.ino`.
