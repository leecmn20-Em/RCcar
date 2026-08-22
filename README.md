# Robot Arm GUI / Backend

기존 PyQt5 Robot Arm GUI의 사용법과 PC → ESP32 각도 protocol을 유지하면서, PC 프로그램을 GUI / Backend / SQLite 책임으로 분리한 구조입니다. ESP32 → Backend 응답은 multiplexing을 위해 typed ACK인 `ARM_ACK,OK`를 사용합니다.

## 구조

```text
PyQt GUI
    │
    │ localhost TCP, NDJSON (127.0.0.1:6000)
    ▼
Python Backend
    ├── ESP32 Client
    ├── Parser
    ├── Mission Manager
    └── Database Manager
           │
           ▼
         SQLite (data/robot_system.db)
    │
    │ Wi-Fi TCP (기본 192.168.4.1:5000)
    ▼
ESP32 SoftAP / TCP Server
    │
    │ 향후 UART
    ▼
Arduino Uno / AGV
```

GUI는 ESP32와 SQLite에 직접 접근하지 않습니다. Backend 프로세스 하나만 ESP32 TCP socket과 SQLite connection을 소유합니다.

## 파일 역할

```text
backend/
  robot_backend.py     localhost IPC server와 요청 처리
  esp32_client.py      ESP32 연결, Arm 송신, 단일 receiver와 pending ACK
  parser.py            NDJSON, 각도, ARM ACK/AGV message 분류
  mission_manager.py   current_mission_id와 mission-scoped log 정책
database/
  database.py          schema 생성과 SQLite 쓰기/조회
gui/
  robot_gui.py         기존 Robot Arm UI와 Backend event 처리
  backend_client.py    QThread 기반 비동기 localhost IPC client
data/
  robot_system.db      Backend 첫 실행 때 자동 생성
tools/
  fake_esp32_server.py 개발/테스트용 multiplexing server
tests/
  test_parser.py
  test_database.py
  test_backend_integration.py
firmware/
  archive/arms_20260819_original.ino  Git 이력에서 복원한 원본 보존본
  robot_arm_esp32/robot_arm_esp32.ino Servo + SoftAP/TCP 통합 firmware
robotArm_tcp.py        기존 실행명을 보존한 GUI 호환 launcher
softAP_tcp.cpp         기존 SoftAP 흐름 + typed ARM ACK 응답
```

## 실제 Servo firmware 주의

Git 이력의 `0c65aea` 커밋에서 삭제 전 `ino/arms.ino`를 찾아 `firmware/archive/arms_20260819_original.ino`로 소스 내용을 복원했습니다. 이 코드는 4축 Servo와 Home `90,90,90,90`을 포함하지만, colon 구분 Serial 명령을 사용하고 매 loop마다 Shoulder를 70도로 강제하는 시험 코드도 남아 있어 그대로 flash하면 안 됩니다.

과거 핀은 `base=3`, `shoulder=5`, `forearm=6`, `upperarm=9`였습니다. 현재 AGV 코드는 Arduino Uno 대상으로 설정되어 있고, classic ESP32에서는 GPIO 6과 9가 flash에 연결되는 경우가 많으므로 이 핀 배치를 실제 ESP32 배선으로 간주하지 않습니다.

`firmware/robot_arm_esp32/robot_arm_esp32.ino`에는 다음 동작을 통합했습니다.

- SoftAP `RobotArm_Team3` / TCP 5000
- `base,shoulder,upper,forearm\n` 네 각도의 엄격한 0..180 검증
- 네 Servo target 적용 후 명령당 정확히 한 번 `ARM_ACK,OK`
- 잘못된 형식, 범위 또는 과대 frame에는 `ARM_ACK,ERROR`

안전을 위해 통합 firmware의 네 `ROBOT_ARM_*_PIN`은 `-1`로 두었고 핀 확정 전에는 compile이 중단됩니다. 실제 배선과 Servo 별 안전 각도 범위를 확인한 후 설정해야 합니다. `softAP_tcp.cpp`는 Servo/PWM 제어가 없는 네트워크 참고 코드로 유지합니다.

## 설치

프로젝트 root에서 실행합니다.

```powershell
python -m pip install -r requirements.txt
```

Python 표준 라이브러리 외 GUI에서 PyQt5를 사용합니다.

## 실제 장비 실행 순서

1. `firmware/robot_arm_esp32/robot_arm_esp32.ino`의 네 Servo pin을 실제 배선에 맞게 설정하고 compile/flash합니다.
2. 전원을 인가하기 전에 네 Servo의 90도 Home 위치가 기구적으로 안전한지 확인합니다.
3. PC를 ESP32 SoftAP Wi-Fi에 연결합니다.
4. 터미널 1에서 Backend를 실행합니다.

```powershell
python backend/robot_backend.py
```

5. 터미널 2에서 GUI를 실행합니다.

```powershell
python gui/robot_gui.py
```

기존 명령도 호환됩니다.

```powershell
python robotArm_tcp.py
```

기본값은 다음과 같습니다.

- GUI ↔ Backend: `127.0.0.1:6000`
- Backend ↔ ESP32: `192.168.4.1:5000`
- SQLite: `data/robot_system.db`

Backend 설정은 필요할 때 바꿀 수 있습니다.

```powershell
python backend/robot_backend.py --host 127.0.0.1 --port 6000 --db data/robot_system.db
```

GUI를 Backend보다 먼저 실행해도 종료되지 않으며 1초 간격으로 Backend에 자동 재연결합니다.

## 명령 흐름

GUI와 Backend 사이의 모든 frame은 UTF-8 JSON 한 줄과 `\n` delimiter를 사용합니다.

```text
GUI
  {"type":"arm_command","command":"MOVE","angles":[90,120,80,100]}\n
    ↓
Backend
  90,120,80,100\n
    ↓
ESP32
  ARM_ACK,OK\n
    ↓
Backend → 활성 Mission이면 arm_log 저장 → GUI에 arm_result
```

Arm command 종류는 `MOVE`, `HOME`, `TEACHING`, `ACTION`입니다. ESP32에는 firmware 호환을 위해 종류를 보내지 않고 기존의 네 각도 CSV만 보냅니다.

GUI의 localhost 수신은 QThread에서 수행됩니다. Teaching Action은 각 단계의 비동기 `arm_result`에서 ARM ACK를 확인한 뒤 지정된 단계 간격을 시작합니다. 따라서 PyQt main thread에서 `recv()`를 기다리지 않습니다.

## ESP32 수신 multiplexing

ESP32 socket을 읽는 코드는 `Esp32Client._receiver_loop()` 하나뿐입니다. Arm 송신 함수는 각도를 보낸 뒤 pending event를 기다릴 뿐 `recv()`를 호출하지 않습니다.

```text
ESP32 TCP
    │ newline frame
    ▼
Receiver Loop
    ▼
Parser
   / \
 ARM  AGV
  │    ├── MissionManager → agv_log
  │    └── Backend → GUI agv_event
  ▼
Pending Arm Command → arm_log + GUI arm_result
```

ESP32 → Backend protocol:

```text
ARM_ACK,OK
ARM_ACK,ERROR
AGV,TELEMETRY,54.2,0,1,0,180,180
AGV,OBSTACLE,14.1,0,1,0,0,0
AGV,STOP,14.1,0,1,0,0,0
AGV,DEST
```

모든 frame은 `\n`으로 끝납니다. 이전 firmware의 `OK\n`도 과도기 호환 ACK로 인정하지만 새 firmware는 `ARM_ACK,OK\n`을 반환합니다. `AGV,DEST`에는 존재하지 않는 sensor 값을 만들지 않고 `None`으로 routing합니다.

Wire protocol에 request ID가 없으므로 Arm 명령은 한 번에 하나만 pending 상태가 됩니다. ACK timeout이면 해당 TCP 연결을 닫습니다. 따라서 이전 연결의 늦은 ACK가 다음 명령을 완료할 수 없으며, ESP32 재연결 후 새 명령을 보내야 합니다.

Pending이 없을 때 도착한 ACK와 즉시 중복된 ACK는 `UNEXPECTED_ARM_ACK` diagnostic으로 폐기하며 저장하지 않습니다. 다만 request ID가 없는 protocol에서는 새 명령을 보낸 뒤 도착한 임의의 지연 중복 ACK를 원천적으로 구분할 수 없으므로, ESP32 firmware도 명령 한 줄당 ACK를 정확히 하나만 보내야 합니다. 향후 이 보장이 어려워지면 wire request ID를 추가해야 합니다.

잘못된 ESP32 frame은 `esp_diagnostic` event로 전달하며 receiver는 계속 실행합니다. 실제 TCP 연결이 끊긴 경우에만 ESP32 disconnected 상태로 전환합니다.

현재 GUI는 `agv_event`를 정상 event로 인식하지만 3차 dashboard 전까지 화면에는 렌더링하지 않습니다. Protocol diagnostic만 GUI log에 경고로 표시합니다.

## Mission과 DB 저장 정책

- `Mission Start`는 Backend가 `mission` row를 생성하고 `current_mission_id`를 보관합니다.
- 진행 중인 실제 Arm 전송 결과는 같은 ID의 `arm_log`에 저장됩니다.
- `ARM_ACK,OK` 또는 legacy `OK`는 `ack=1`, `ARM_ACK,ERROR`/timeout/통신 오류는 `ack=0`입니다.
- AGV frame은 실시간 `agv_event`로 GUI client에 전달되며, 활성 Mission이면 `agv_log`에 저장됩니다.
- Mission 없이 들어온 AGV frame은 실시간 전달만 하고 DB에는 저장하지 않습니다.
- Mission 없이 Arm을 움직일 수 있지만 DB에는 저장하지 않으며 GUI log에 이 정책을 표시합니다.
- ESP32가 연결되지 않아 전송 자체가 시작되지 않은 요청도 DB에 저장하지 않습니다.
- `Mission End`는 `end_time`과 선택한 `SUCCESS`, `FAILED`, `ABORTED` 결과를 갱신하고 Backend의 current ID를 해제합니다.

DB 연결마다 `PRAGMA foreign_keys = ON`을 적용합니다.

```text
mission(mission_id PK, start_time, end_time, result)
arm_log(id PK, mission_id FK, timestamp, command,
        base, shoulder, upper, forearm, ack)
agv_log(id PK, mission_id FK, timestamp, event, distance,
        left_ir, center_ir, right_ir, motor_left, motor_right)
```

`arm_log(mission_id, timestamp)`와 `agv_log(mission_id, timestamp)` index도 생성됩니다. DB schema는 2차 작업에서 변경하지 않았습니다.

## 장비 없이 실행/테스트

터미널 1에서 fake ESP32를 실행합니다.

```powershell
python tools/fake_esp32_server.py --port 5000 --mode sandwich
```

터미널 2와 3에서 Backend, GUI를 실행한 뒤 GUI의 ESP32 IP를 `127.0.0.1`로 설정합니다.

전체 자동 테스트:

```powershell
python -m unittest discover -s tests -v
```

지원하는 fake mode는 `ack`, `legacy`, `agv-before-ack`, `sandwich`, `error`, `timeout`입니다. 테스트는 parser 정상/오류, foreign key와 schema, Mission start/end, Arm/AGV log, ACK 앞·사이·뒤 AGV routing, timeout과 늦은 ACK 격리를 포함합니다.

추가 통합 테스트는 ACK 대기 중 TCP 강제 종료가 pending wait를 즉시 해제하는지, pending 없는 ACK와 중복 ACK가 폐기되는지, Arm `command_lock`이 AGV routing을 막지 않는지도 검증합니다.

## 실제 Robot Arm 확인 체크리스트

자동 테스트는 실제 Servo 구동을 검증할 수 없습니다. 3차 작업 전에 다음을 장비에서 확인해야 합니다.

1. 실제 보드 모델, 네 Servo signal pin, 별도 Servo 전원과 공통 GND 확인
2. `firmware/robot_arm_esp32/robot_arm_esp32.ino`의 네 pin 설정
3. 90도 Home 위치가 기구적으로 안전한 상태에서 ESP32 flash
4. Serial boot log에서 SoftAP IP와 TCP port 확인
5. PC를 ESP32 SoftAP에 연결
6. Backend와 GUI 실행 후 GUI에서 ESP32 연결
7. 안전한 4축 각도 한 세트 전송
8. 실제 네 Servo의 방향과 움직임 확인
9. Backend/GUI에서 `ARM_ACK,OK` 성공 확인
10. Mission Start 후 Arm 명령을 실행하고 `arm_log`에 같은 Mission ID와 `ack=1` row가 생성되는지 확인

## 향후 3차 작업

Backend의 multiplexed receiver, AGV parser, Mission DB routing은 준비되었습니다. 다음 단계에서는 실제 protocol이 확정된 뒤 아래 입력 구간만 연결합니다.

```text
Arduino Uno
    │ UART (3차에서 구현)
    ▼
ESP32
    │ 현재 multiplexed TCP
    ▼
Backend Receiver → Parser → agv_log / GUI agv_event
```

이번 단계에서는 Uno firmware, UART 수신, IR/초음파 값 생성, AGV motor 제어 및 GUI dashboard를 구현하지 않았습니다.

Uno UART protocol의 권장 기준은 Uno가 완성된 `AGV,...\n` frame을 만들고 ESP32가 parsing 없이 TCP client로 그대로 relay하는 방식입니다. 3차 구현 전에 UART baud rate, 배선, 공통 GND 및 Uno TX에서 ESP32 RX로 들어가는 신호 전압 조건을 실제 보드 구성에 맞게 확정해야 합니다.
