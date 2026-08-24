"""Compatibility launcher for the backend-based Robot Arm GUI.

The original direct ESP32 socket implementation was moved out of the GUI.
Run the backend first, then this file or ``gui/robot_gui.py``.
"""

from gui.robot_gui import RobotArmGUI, main

__all__ = ["RobotArmGUI", "main"]


if __name__ == "__main__":
    main()
