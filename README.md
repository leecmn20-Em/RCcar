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
    │ UART2 115200 bps (GPIO16 RX / GPIO17 TX)
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
  robot_arm_esp32/robot_arm_esp32.ino Servo + SoftAP/TCP + AGV UART relay
ino/
  ino.ino             기존 AGV 제어 + 200ms tracing/obstacle/stop protocol
  modules/DebugLog.h  Uno UART debug 출력의 compile-time switch
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
- UART2의 Uno `AGV,...\n` frame을 해석하거나 변경하지 않고 TCP로 relay

ESP32 DevKit V1(ESP-WROOM-32) 기준 핀 계획은 다음과 같습니다. GPIO 16/17은 Uno UART2 연결에 사용하므로 Servo에 사용하지 않습니다.

| 역할 | ESP32 GPIO |
| --- | ---: |
| Base Servo signal | 18 |
| Shoulder Servo signal | 19 |
| Upper Servo signal | 21 |
| Forearm Servo signal | 22 |
| Uno → ESP32 UART2 RX | 16 |
| ESP32 → Uno UART2 TX | 17 |

Servo 네 개는 ESP32 보드의 USB/5V 핀에서 직접 급전하지 않고 별도 5V 전원에 연결합니다. 권장 용량은 최소 4A, 가능하면 5A이며, 외부 전원 GND와 ESP32 GND는 반드시 공통으로 연결합니다. `softAP_tcp.cpp`는 Servo/PWM 제어가 없는 네트워크 참고 코드로 유지합니다.

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
AGV,TRACING,450,0,1,0,95.25,97.50
AGV,OBSTACLE,110,0,1,0,0.00,0.00
AGV,STOP,110,0,1,0,2.10,1.85
```

모든 frame은 `\n`으로 끝납니다. AGV 필드는 `event,distance_mm,left_ir,center_ir,right_ir,left_rpm,right_rpm` 순서이며 마지막 두 값은 실수형 measured RPM입니다. Uno는 200ms 주기(5Hz)로 AGV frame을 보냅니다. 초음파 장애물 상태가 `false → true`로 바뀐 첫 frame은 다른 상태보다 우선하여 `AGV,OBSTACLE`을 한 번 보냅니다. 이후 양쪽 measured RPM이 모두 `3.0` 이하인 상태가 400ms 연속 유지되면 장애물 여부와 관계없이 정지를 확정하고, 확정 정지 중에는 매 주기 `AGV,STOP`을 계속 보냅니다. 정지 해제도 즉시 처리하지 않고, 한쪽 RPM이라도 `5.0` 이상인 상태가 400ms 연속 유지되어야 moving 상태로 복귀합니다. 정지 중 한 frame에서만 `30 RPM`처럼 값이 튀면 해당 raw RPM은 frame과 DB에 그대로 남지만 event는 `STOP`을 유지하며, 다음 frame에서 해제 조건이 끊기면 확인 시간을 처음부터 다시 계산합니다. 두 임계값 사이에서는 직전 상태를 유지하여 측정값 경계에서 event가 반복 전환되는 것을 막으며, 위 조건에 해당하지 않는 정상 주행 frame은 `AGV,TRACING`입니다. PWM duty는 더 이상 wire protocol로 전송하거나 DB에 저장하지 않습니다.

현재 Wheel RPM 추정기는 마지막 encoder pulse를 최대 1초 동안 유지합니다. 따라서 물리적으로 멈춘 시점부터 `STOP`이 처음 전송되기까지 실제 장비에서는 약 1.4~1.6초 지연될 수 있으며, 이 값은 실장 테스트에서 encoder 특성에 맞춰 조정해야 합니다.

구형 Uno firmware도 마지막 두 숫자 필드를 전송하지만 그 값은 RPM이 아니라 duty입니다. Backend는 이를 구분할 수 없으므로 RPM protocol이 적용된 최신 Uno firmware와 함께 사용해야 합니다.

Uno의 `Serial`은 기본적으로 기계 protocol 전용입니다. `ENABLE_AGV_DEBUG`의 기본값은 `0`이며, 사람이 보는 boot/IR/motor log는 이 값이 활성화된 개발 build에서만 출력됩니다. 운영 중 debug를 켜면 ESP32가 해당 문자열도 그대로 relay하므로 Backend diagnostic이 발생할 수 있습니다.

Backend parser는 `AGV,TRACING`, `AGV,OBSTACLE`, `AGV,STOP`, `AGV,DEST`를 인식합니다. 현재 Uno firmware는 measured RPM 기반으로 `STOP`을 생성하지만, 실제 목적지 판정 조건이 아직 없으므로 `DEST`는 생성하지 않습니다. 이전 firmware의 `OK\n`도 과도기 호환 ACK로 인정하지만 새 firmware는 `ARM_ACK,OK\n`을 반환합니다.

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
        left_ir, center_ir, right_ir, left_rpm, right_rpm)
```

`agv_log`는 센서 값과 실측 RPM만 저장하는 RPM-only 구조입니다. 기존 DB에 duty 컬럼이 있으면 Backend 시작 시 `agv_log`를 새 구조로 migration합니다. 이 과정에서 mission ID, 시각, event, 거리, IR 센서, RPM 값은 보존하고 duty 컬럼은 제거합니다. `arm_log(mission_id, timestamp)`와 `agv_log(mission_id, timestamp)` index도 생성됩니다.

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

1. ESP32 DevKit V1의 Servo signal 배선이 GPIO 25/26/27/32 순서와 일치하는지 확인
2. 별도 5V 4A 이상 Servo 전원과 ESP32의 공통 GND 확인
3. 90도 Home 위치가 기구적으로 안전한 상태에서 ESP32 flash
4. Serial boot log에서 SoftAP IP와 TCP port 확인
5. PC를 ESP32 SoftAP에 연결
6. Backend와 GUI 실행 후 GUI에서 ESP32 연결
7. Home `90,90,90,90`을 확인한 뒤 각 축을 하나씩만 `80`과 `100`으로 움직임
8. GPIO/관절 순서, 회전 방향, 기구 끝단 간섭을 확인하고 특히 Shoulder 부하를 주의
9. Backend/GUI에서 `ARM_ACK,OK` 성공 확인
10. Mission Start 후 Arm 명령을 실행하고 `arm_log`에 같은 Mission ID와 `ack=1` row가 생성되는지 확인

## 3차 AGV UART relay

기존 라인트레이싱 센서·모터 제어 주기는 변경하지 않고 Uno protocol 출력과 ESP32 relay 구간을 연결했습니다.

```text
Arduino Uno
    │ UART 115200 bps, AGV frame
    ▼
ESP32
    │ UART2 bytes를 현재 multiplexed TCP로 그대로 relay
    ▼
Backend Receiver → Parser → agv_log / GUI agv_event
```

Uno는 `DrivePolicy::range`의 mm 거리, Left/Center/Right IR, 두 Wheel의 `getEstimatedRPM()`을 사용합니다. RPM은 `Serial.print(value, 2)`로 소수점 둘째 자리까지 전송합니다. 센서 5ms, motor 10ms, 제어 20ms 주기는 유지하고 DB용 AGV frame만 200ms 주기로 추가했습니다. Event 우선순위는 장애물 `false → true` transition의 1회 `OBSTACLE`, 확정 정지 상태의 `STOP`, 그 외 정상 주행 상태의 `TRACING` 순서입니다. 양쪽 measured RPM이 모두 `3.0` 이하인 상태가 400ms 연속 유지되면 정지를 확정합니다. 정지 후에는 한쪽 RPM이라도 `5.0` 이상인 상태가 400ms 연속 유지되어야 moving으로 복귀하므로, 엔코더의 단발성 RPM spike는 `STOP`을 해제하지 않습니다. 확정 정지 중에는 장애물 여부와 관계없이 매 200ms마다 `STOP`을 전송합니다.

UART2는 ESP32 GPIO 16(RX2)과 GPIO 17(TX2), 115200 bps를 사용합니다. Uno D1 TX의 5V logic은 ESP32 GPIO 16에 직접 연결하지 않고 전압 분배기 또는 level shifter를 거쳐야 합니다. 반대 방향은 ESP32 GPIO 17 TX2에서 Uno D0 RX로 연결하며 두 보드의 GND를 공통으로 연결합니다. 현재 ESP32 → Uno 명령은 구현하지 않았습니다.

남은 3차 작업은 실제 장비에서 UART/TCP/DB 연속 경로와 RPM 기반 `STOP` 판정을 검증하고 GUI dashboard를 구현하는 것입니다. `DEST`는 실제 목적지 판정 조건을 정한 뒤 추가합니다.
