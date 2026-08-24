"""PyQt5 Robot Arm GUI using the separate localhost backend process."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.backend_client import BackendClient


class RobotArmGUI(QMainWindow):
    """4-axis GUI; all ESP32 and SQLite work is delegated to the backend."""

    DEFAULT_BACKEND_HOST = "127.0.0.1"
    DEFAULT_BACKEND_PORT = 6000
    DEFAULT_ESP32_IP = "192.168.4.1"
    DEFAULT_ESP32_PORT = 5000
    JOINT_NAMES = ("Base", "Shoulder", "Upper Arm", "Fore Arm")
    HOME_ANGLES = (90, 90, 90, 90)

    def __init__(self):
        super().__init__()
        self.backend_connected = False
        self.esp_connected = False
        self.current_mission_id: int | None = None  # display-only backend state
        self._request_sequence = 0
        self._pending_action_request_id: str | None = None

        self.angle_sliders = []
        self.angle_spinboxes = []

        self.action_timer = QTimer(self)
        self.action_timer.setSingleShot(True)
        self.action_timer.timeout.connect(self._send_next_action_step)
        self.action_step = 0
        self.action_running = False

        self.setWindowTitle("Robot Arm Controller - Backend / ESP32 TCP")
        self.resize(1050, 800)
        self._build_ui()
        self._set_backend_ui(False)
        self._set_esp_connected_ui(False)
        self._set_mission_ui(None)
        self.set_angles(self.HOME_ANGLES)

        self.backend_client = BackendClient(
            self.DEFAULT_BACKEND_HOST, self.DEFAULT_BACKEND_PORT, parent=self
        )
        self.backend_client.connected_changed.connect(self._on_backend_connection_changed)
        self.backend_client.message_received.connect(self._handle_backend_message)
        self.backend_client.transport_error.connect(self._handle_backend_transport_error)
        self.backend_client.start()

        self.add_log("프로그램을 시작했습니다.")
        self.add_log(
            "Backend 연결을 기다립니다. 먼저 backend/robot_backend.py를 실행하세요."
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(self._build_connection_group())

        splitter = QSplitter(Qt.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(self._build_manual_control_group())
        left_layout.addStretch(1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.addWidget(self._build_teaching_group())
        right_layout.addWidget(self._build_action_group())

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)
        main_layout.addWidget(self._build_log_group())

    def _build_connection_group(self):
        group = QGroupBox("Backend / ESP32 무선 연결")
        layout = QGridLayout(group)

        self.backend_status = QLabel("● Backend 연결 안 됨")
        self.backend_status.setMinimumWidth(170)
        layout.addWidget(self.backend_status, 0, 0, 1, 2)

        layout.addWidget(QLabel("ESP32 IP"), 0, 2)
        self.ip_input = QLineEdit(self.DEFAULT_ESP32_IP)
        self.ip_input.setPlaceholderText("예: 192.168.4.1")
        layout.addWidget(self.ip_input, 0, 3)

        layout.addWidget(QLabel("Port"), 0, 4)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(self.DEFAULT_ESP32_PORT)
        layout.addWidget(self.port_input, 0, 5)

        self.connect_button = QPushButton("ESP32 연결")
        self.connect_button.clicked.connect(self.connect_esp32)
        layout.addWidget(self.connect_button, 0, 6)

        self.disconnect_button = QPushButton("연결 해제")
        self.disconnect_button.clicked.connect(self.disconnect_esp32)
        layout.addWidget(self.disconnect_button, 0, 7)

        self.connection_status = QLabel("● ESP32 연결 안 됨")
        self.connection_status.setAlignment(Qt.AlignCenter)
        self.connection_status.setMinimumWidth(150)
        layout.addWidget(self.connection_status, 0, 8)

        self.mission_status = QLabel("Mission: 없음")
        layout.addWidget(self.mission_status, 1, 0, 1, 2)

        self.mission_start_button = QPushButton("Mission Start")
        self.mission_start_button.clicked.connect(self.start_mission)
        layout.addWidget(self.mission_start_button, 1, 2, 1, 2)

        layout.addWidget(QLabel("종료 결과"), 1, 4)
        self.mission_result_input = QComboBox()
        self.mission_result_input.addItems(["SUCCESS", "FAILED", "ABORTED"])
        layout.addWidget(self.mission_result_input, 1, 5)

        self.mission_end_button = QPushButton("Mission End")
        self.mission_end_button.clicked.connect(self.end_mission)
        layout.addWidget(self.mission_end_button, 1, 6, 1, 2)
        layout.setColumnStretch(3, 1)
        return group

    def _build_manual_control_group(self):
        group = QGroupBox("로봇팔 수동 제어")
        layout = QGridLayout(group)
        for row, joint_name in enumerate(self.JOINT_NAMES):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 180)
            slider.setSingleStep(1)
            slider.setPageStep(10)
            spinbox = QSpinBox()
            spinbox.setRange(0, 180)
            spinbox.setSuffix("°")
            slider.valueChanged.connect(spinbox.setValue)
            spinbox.valueChanged.connect(slider.setValue)
            self.angle_sliders.append(slider)
            self.angle_spinboxes.append(spinbox)
            layout.addWidget(QLabel(joint_name), row, 0)
            layout.addWidget(slider, row, 1)
            layout.addWidget(spinbox, row, 2)

        button_row = QHBoxLayout()
        self.home_button = QPushButton("Home")
        self.home_button.clicked.connect(self.go_home)
        button_row.addWidget(self.home_button)
        self.send_button = QPushButton("현재 각도 ESP32로 전송")
        self.send_button.clicked.connect(self.send_current_angles)
        button_row.addWidget(self.send_button, 1)
        layout.addLayout(button_row, len(self.JOINT_NAMES), 0, 1, 3)
        layout.setColumnStretch(1, 1)
        return group

    def _build_teaching_group(self):
        group = QGroupBox("Teaching Position")
        layout = QVBoxLayout(group)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("이름"))
        self.position_name_input = QLineEdit()
        self.position_name_input.setPlaceholderText("예: Ready, Arm Down, Push")
        name_row.addWidget(self.position_name_input, 1)
        layout.addLayout(name_row)

        self.position_list = QListWidget()
        self.position_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.position_list.itemDoubleClicked.connect(self.load_selected_position)
        layout.addWidget(self.position_list)

        first_row = QHBoxLayout()
        save_button = QPushButton("현재 자세 저장")
        save_button.clicked.connect(self.save_teaching_position)
        first_row.addWidget(save_button)
        load_button = QPushButton("선택 자세 불러오기")
        load_button.clicked.connect(self.load_selected_position)
        first_row.addWidget(load_button)
        layout.addLayout(first_row)

        second_row = QHBoxLayout()
        send_button = QPushButton("선택 자세 실행")
        send_button.clicked.connect(self.send_selected_position)
        second_row.addWidget(send_button)
        delete_button = QPushButton("선택 자세 삭제")
        delete_button.clicked.connect(self.delete_selected_position)
        second_row.addWidget(delete_button)
        layout.addLayout(second_row)
        return group

    def _build_action_group(self):
        group = QGroupBox("Teaching Action")
        layout = QVBoxLayout(group)
        self.action_list = QListWidget()
        self.action_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.action_list)

        edit_row = QHBoxLayout()
        add_button = QPushButton("선택 자세를 순서에 추가")
        add_button.clicked.connect(self.add_selected_position_to_action)
        edit_row.addWidget(add_button)
        remove_button = QPushButton("단계 삭제")
        remove_button.clicked.connect(self.remove_selected_action_step)
        edit_row.addWidget(remove_button)
        clear_button = QPushButton("전체 지우기")
        clear_button.clicked.connect(self.action_list.clear)
        edit_row.addWidget(clear_button)
        layout.addLayout(edit_row)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("단계 간격"))
        self.action_interval_input = QSpinBox()
        self.action_interval_input.setRange(100, 10000)
        self.action_interval_input.setSingleStep(100)
        self.action_interval_input.setValue(700)
        self.action_interval_input.setSuffix(" ms")
        interval_row.addWidget(self.action_interval_input)
        self.execute_action_button = QPushButton("동작 순서 실행")
        self.execute_action_button.clicked.connect(self.execute_action)
        interval_row.addWidget(self.execute_action_button, 1)
        self.stop_action_button = QPushButton("실행 중지")
        self.stop_action_button.clicked.connect(lambda: self.stop_action())
        self.stop_action_button.setEnabled(False)
        interval_row.addWidget(self.stop_action_button)
        layout.addLayout(interval_row)
        return group

    def _build_log_group(self):
        group = QGroupBox("로그")
        layout = QVBoxLayout(group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.document().setMaximumBlockCount(1000)
        layout.addWidget(self.log_output)
        clear_button = QPushButton("로그 지우기")
        clear_button.clicked.connect(self.log_output.clear)
        layout.addWidget(clear_button, alignment=Qt.AlignRight)
        return group

    # ------------------------------------------------------------------
    # Backend / ESP32 / mission requests
    # ------------------------------------------------------------------
    def _next_request_id(self) -> str:
        self._request_sequence += 1
        return f"gui-{self._request_sequence}"

    def _send_backend(self, message: dict) -> str | None:
        request_id = self._next_request_id()
        message = dict(message)
        message["request_id"] = request_id
        if not self.backend_client.send_message(message):
            self.add_log(
                "Backend가 연결되어 있지 않습니다. Backend 실행 상태를 확인하세요.",
                "ERROR",
            )
            return None
        return request_id

    def connect_esp32(self):
        if self.esp_connected:
            self.add_log("이미 ESP32에 연결되어 있습니다.", "WARN")
            return
        ip = self.ip_input.text().strip()
        if not ip:
            self.add_log("ESP32 IP를 입력하세요.", "ERROR")
            return
        port = self.port_input.value()
        if self._send_backend({"type": "esp_connect", "ip": ip, "port": port}):
            self.add_log(f"Backend에 ESP32 연결 요청: {ip}:{port}")

    def disconnect_esp32(self):
        self.stop_action("ESP32 연결 해제로 Teaching Action을 중지했습니다.")
        if self._send_backend({"type": "esp_disconnect"}):
            self.add_log("Backend에 ESP32 연결 해제를 요청했습니다.")

    def start_mission(self):
        if self.current_mission_id is not None:
            self.add_log("Mission이 이미 진행 중입니다.", "WARN")
            return
        if self._send_backend({"type": "mission_start"}):
            self.add_log("Mission Start 요청을 보냈습니다.")

    def end_mission(self):
        if self.current_mission_id is None:
            self.add_log("종료할 Mission이 없습니다.", "WARN")
            return
        result = self.mission_result_input.currentText()
        if self._send_backend({"type": "mission_end", "result": result}):
            self.add_log(f"Mission End 요청: {result}")

    # ------------------------------------------------------------------
    # Angles and asynchronous ACK handling
    # ------------------------------------------------------------------
    def get_current_angles(self):
        return [spinbox.value() for spinbox in self.angle_spinboxes]

    def set_angles(self, angles):
        if len(angles) != len(self.angle_spinboxes):
            raise ValueError("각도는 반드시 4개여야 합니다.")
        for spinbox, angle in zip(self.angle_spinboxes, angles):
            spinbox.setValue(max(0, min(180, int(angle))))

    def go_home(self):
        self.set_angles(self.HOME_ANGLES)
        self.add_log(f"Home 자세 설정: {list(self.HOME_ANGLES)}")
        if self.esp_connected:
            self.send_angles(self.HOME_ANGLES, "HOME")
        else:
            self.add_log("연결 전이므로 화면의 각도만 Home으로 변경했습니다.", "WARN")

    def send_current_angles(self):
        self.send_angles(self.get_current_angles(), "MOVE")

    def send_angles(self, angles, command="MOVE") -> str | None:
        if not self.esp_connected:
            self.add_log("ESP32가 연결되어 있지 않습니다.", "ERROR")
            return None
        if len(angles) != len(self.JOINT_NAMES):
            self.add_log("전송할 각도는 반드시 4개여야 합니다.", "ERROR")
            return None
        normalized = [max(0, min(180, int(angle))) for angle in angles]
        request_id = self._send_backend(
            {"type": "arm_command", "command": command, "angles": normalized}
        )
        if request_id:
            self.add_log(f"IPC > {command} {normalized}")
        return request_id

    # ------------------------------------------------------------------
    # Teaching Position
    # ------------------------------------------------------------------
    def save_teaching_position(self):
        name = self.position_name_input.text().strip()
        if not name:
            name = f"Position {self.position_list.count() + 1}"
        angles = self.get_current_angles()
        item = self._find_position_by_name(name)
        if item is None:
            item = QListWidgetItem()
            self.position_list.addItem(item)
        item.setData(Qt.UserRole, {"name": name, "angles": angles})
        item.setText(self._format_position_text(name, angles))
        self.position_list.setCurrentItem(item)
        self.position_name_input.clear()
        self.add_log(f"Teaching Position 저장: {name} = {angles}")

    def load_selected_position(self, item=None):
        item = item or self.position_list.currentItem()
        if item is None:
            self.add_log("불러올 Teaching Position을 선택하세요.", "WARN")
            return
        data = item.data(Qt.UserRole)
        self.set_angles(data["angles"])
        self.add_log(f"Teaching Position 불러오기: {data['name']} = {data['angles']}")

    def send_selected_position(self):
        item = self.position_list.currentItem()
        if item is None:
            self.add_log("실행할 Teaching Position을 선택하세요.", "WARN")
            return
        data = item.data(Qt.UserRole)
        self.set_angles(data["angles"])
        self.add_log(f"Teaching Position 실행: {data['name']}")
        self.send_angles(data["angles"], "TEACHING")

    def delete_selected_position(self):
        row = self.position_list.currentRow()
        if row < 0:
            self.add_log("삭제할 Teaching Position을 선택하세요.", "WARN")
            return
        item = self.position_list.takeItem(row)
        self.add_log(f"Teaching Position 삭제: {item.data(Qt.UserRole)['name']}")

    def _find_position_by_name(self, name):
        for index in range(self.position_list.count()):
            item = self.position_list.item(index)
            data = item.data(Qt.UserRole)
            if data and data.get("name") == name:
                return item
        return None

    @staticmethod
    def _format_position_text(name, angles):
        return f"{name}  |  {', '.join(map(str, angles))}"

    # ------------------------------------------------------------------
    # Teaching Action
    # ------------------------------------------------------------------
    def add_selected_position_to_action(self):
        source_item = self.position_list.currentItem()
        if source_item is None:
            self.add_log("동작 순서에 추가할 Teaching Position을 선택하세요.", "WARN")
            return
        source = source_item.data(Qt.UserRole)
        data = {"name": source["name"], "angles": list(source["angles"])}
        item = QListWidgetItem()
        item.setData(Qt.UserRole, data)
        item.setText(
            f"{self.action_list.count() + 1}. "
            f"{self._format_position_text(data['name'], data['angles'])}"
        )
        self.action_list.addItem(item)
        self.add_log(f"동작 순서에 추가: {data['name']}")

    def remove_selected_action_step(self):
        row = self.action_list.currentRow()
        if row < 0:
            self.add_log("삭제할 동작 단계를 선택하세요.", "WARN")
            return
        self.action_list.takeItem(row)
        self._renumber_action_items()
        self.add_log("선택한 동작 단계를 삭제했습니다.")

    def _renumber_action_items(self):
        for index in range(self.action_list.count()):
            item = self.action_list.item(index)
            data = item.data(Qt.UserRole)
            item.setText(
                f"{index + 1}. {self._format_position_text(data['name'], data['angles'])}"
            )

    def execute_action(self):
        if self.action_running:
            self.add_log("Teaching Action이 이미 실행 중입니다.", "WARN")
            return
        if not self.esp_connected:
            self.add_log("Teaching Action 실행 전에 ESP32를 연결하세요.", "ERROR")
            return
        if self.action_list.count() == 0:
            self.add_log("동작 순서가 비어 있습니다.", "WARN")
            return
        self.action_step = 0
        self.action_running = True
        self._pending_action_request_id = None
        self._set_action_running_ui(True)
        self.add_log(f"Teaching Action 시작: 총 {self.action_list.count()}단계")
        self._send_next_action_step()

    def _send_next_action_step(self):
        if not self.action_running or self._pending_action_request_id is not None:
            return
        if self.action_step >= self.action_list.count():
            self.action_running = False
            self._set_action_running_ui(False)
            self.add_log("Teaching Action 실행 완료")
            return
        item = self.action_list.item(self.action_step)
        data = item.data(Qt.UserRole)
        self.set_angles(data["angles"])
        self.add_log(
            f"Action {self.action_step + 1}/{self.action_list.count()}: {data['name']}"
        )
        request_id = self.send_angles(data["angles"], "ACTION")
        if request_id is None:
            self.stop_action("명령 전송 실패로 Teaching Action을 중지했습니다.")
            return
        self._pending_action_request_id = request_id

    def stop_action(self, message="Teaching Action을 중지했습니다."):
        self.action_timer.stop()
        was_running = self.action_running
        self.action_running = False
        self._pending_action_request_id = None
        self._set_action_running_ui(False)
        if was_running:
            self.add_log(message, "WARN")

    def _set_action_running_ui(self, running):
        self.execute_action_button.setEnabled(not running)
        self.stop_action_button.setEnabled(running)

    # ------------------------------------------------------------------
    # Backend events (executed in the Qt main thread via signals)
    # ------------------------------------------------------------------
    def _on_backend_connection_changed(self, connected):
        self.backend_connected = connected
        self._set_backend_ui(connected)
        if connected:
            self.add_log(
                f"Backend 연결됨: {self.DEFAULT_BACKEND_HOST}:{self.DEFAULT_BACKEND_PORT}"
            )
        else:
            self._set_esp_connected_ui(False)
            self.stop_action("Backend 연결 해제로 Teaching Action을 중지했습니다.")
            self.add_log("Backend 연결이 해제되었습니다. 자동 재연결을 시도합니다.", "WARN")

    def _handle_backend_transport_error(self, message):
        self.add_log(message, "ERROR")

    def _handle_backend_message(self, message):
        message_type = message.get("type")
        if message_type == "backend_status":
            self._set_mission_ui(message.get("mission_id"))
            return
        if message_type == "esp_status":
            connected = bool(message.get("connected"))
            self._set_esp_connected_ui(connected)
            if connected:
                self.add_log(
                    f"ESP32 연결 성공: {message.get('ip')}:{message.get('port')}"
                )
            else:
                self.add_log("ESP32 연결 안 됨", "WARN")
            return
        if message_type == "mission_started":
            self._set_mission_ui(message.get("mission_id"))
            self.add_log(f"Mission 시작됨: ID {self.current_mission_id}")
            return
        if message_type == "mission_ended":
            mission_id = message.get("mission_id")
            result = message.get("result")
            self._set_mission_ui(None)
            self.add_log(f"Mission 종료됨: ID {mission_id}, 결과 {result}")
            return
        if message_type == "arm_result":
            self._handle_arm_result(message)
            return
        if message_type == "agv_event":
            # Backend routing is ready; a high-rate AGV dashboard is deferred
            # to the next phase, so telemetry is intentionally not rendered.
            return
        if message_type == "esp_diagnostic":
            self.add_log(
                f"ESP32 protocol 경고 [{message.get('code')}]: "
                f"{message.get('message')}",
                "WARN",
            )
            return
        if message_type == "error":
            self.add_log(
                f"Backend 오류 [{message.get('code', 'error')}]: {message.get('message')}",
                "ERROR",
            )
            if message.get("request_id") == self._pending_action_request_id:
                self.stop_action("Backend 오류로 Teaching Action을 중지했습니다.")
            return
        self.add_log(f"알 수 없는 Backend 이벤트: {message}", "WARN")

    def _handle_arm_result(self, message):
        command = message.get("command")
        wire_command = message.get("wire_command")
        self.add_log(f"ESP32 TX > {wire_command}")
        if message.get("ack"):
            self.add_log(f"ESP32 RX < {message.get('response')} ({command} ACK 완료)")
        else:
            detail = message.get("error") or message.get("response") or "ACK 없음"
            self.add_log(f"ESP32 명령 실패 ({command}): {detail}", "ERROR")
        if not message.get("logged"):
            self.add_log("활성 Mission이 없어 이 Arm 명령은 DB에 저장하지 않았습니다.")

        if message.get("request_id") == self._pending_action_request_id:
            self._pending_action_request_id = None
            if not self.action_running:
                return
            if not message.get("ack"):
                self.stop_action("ACK 확인 실패로 Teaching Action을 중지했습니다.")
                return
            self.action_step += 1
            self.action_timer.start(self.action_interval_input.value())

    def _set_backend_ui(self, connected):
        if connected:
            self.backend_status.setText("● Backend 연결됨")
            self.backend_status.setStyleSheet("color: #14833b; font-weight: bold;")
        else:
            self.backend_status.setText("● Backend 연결 안 됨")
            self.backend_status.setStyleSheet("color: #b3261e; font-weight: bold;")
        self.connect_button.setEnabled(connected and not self.esp_connected)
        self.mission_start_button.setEnabled(
            connected and self.current_mission_id is None
        )
        self.mission_end_button.setEnabled(
            connected and self.current_mission_id is not None
        )

    def _set_esp_connected_ui(self, connected):
        self.esp_connected = connected
        self.connect_button.setEnabled(self.backend_connected and not connected)
        self.disconnect_button.setEnabled(self.backend_connected and connected)
        self.ip_input.setEnabled(not connected)
        self.port_input.setEnabled(not connected)
        if connected:
            self.connection_status.setText("● ESP32 연결됨")
            self.connection_status.setStyleSheet("color: #14833b; font-weight: bold;")
        else:
            self.connection_status.setText("● ESP32 연결 안 됨")
            self.connection_status.setStyleSheet("color: #b3261e; font-weight: bold;")

    def _set_mission_ui(self, mission_id):
        self.current_mission_id = mission_id if isinstance(mission_id, int) else None
        if self.current_mission_id is None:
            self.mission_status.setText("Mission: 없음")
        else:
            self.mission_status.setText(f"Mission: {self.current_mission_id} 진행 중")
        self.mission_start_button.setEnabled(
            self.backend_connected and self.current_mission_id is None
        )
        self.mission_end_button.setEnabled(
            self.backend_connected and self.current_mission_id is not None
        )

    # ------------------------------------------------------------------
    # Log and shutdown
    # ------------------------------------------------------------------
    def add_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] [{level}] {message}")
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        self.action_timer.stop()
        self.backend_client.stop()
        if not self.backend_client.wait(2000):
            self.add_log("Backend client thread 종료를 기다리는 중입니다.", "WARN")
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = RobotArmGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
