# NUCODE BLE NUS API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-M16-BLE-NUS-001 |
| 문서 개정 | 1.2 |
| 문서 상태 | `v0.2.0` 정식 NUS 계약 / `v0.3.0` 회귀 경계 |
| 적용 제품 버전 | `v0.2.0` 정식 / `v0.3.0` 개발 |
| 최종 갱신일 | 2026-08-31 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 지원 범위

`v0.2.0`은 NCS의 Nordic UART Service(NUS)를 Arduino `Stream` 형태로 제공한다. 일반 사용자는
`prj.conf`나 overlay를 직접 편집하지 않고 Arduino IDE에서 `BLE NUS` feature set을 선택한 뒤
`<NUCODE_BLE.h>`와 전역 객체 `BLESerial`을 사용한다.

지원 범위는 다음 수직 경로로 고정한다.

- NUS Peripheral: local name 설정, connectable advertising, RX characteristic write 수신,
  TX characteristic notification 송신
- NUS Central: exact local name active scan, 연결, NUS service discovery, notification 구독,
  RX characteristic write 송신
- Arduino `Stream`: `available()`, `read()`, `peek()`, `write()`, `flush()`와
  `availableForWrite()`
- 연결 상태, payload MTU, 오류와 RX overflow 조회
- 연결 해제 뒤 Peripheral 재광고와 Central 재검색
- `poll()`에서만 전달되는 사용자 event callback

정식 `v0.2.0` 구현은 임의 GATT service/characteristic 생성, GATT read, indication, bonding,
SMP와 HID를 Arduino wrapper로 제공하지 않는다. 고급 사용자는 같은 Full Zephyr image에서
Zephyr/NCS 공개 `bt_*` API를 직접 사용할 수 있으며, 이를 M16 wrapper가 가로막지 않는다.
`v0.3.0` 개발 트리의 후속 BLE API는 아래 10절에서 별도로 구분한다.

## 2. 구성과 소유권

```text
Arduino Sketch
  ↓ <NUCODE_BLE.h>, BLESerial
NUCODE_BLE::NusSerial
  ├─ Peripheral: NCS bt_nus service
  ├─ Central: NCS bt_nus_client + GATT Discovery Manager
  ├─ 고정 RX/event queue
  └─ poll() 기반 Arduino callback 전달
       ↓
Zephyr Bluetooth host/controller + nRF54L15 radio
```

관련 파일의 책임은 다음과 같다.

| 경로 | 책임 |
| --- | --- |
| `libraries/NUCODE_BLE/src/` | 공개 `NusSerial` API와 NCS NUS adapter |
| `libraries/NUCODE_BLE/zephyr/feature.yml` | `nucode.ble.nus` feature와 `ble` profile 호환 계약 |
| `libraries/NUCODE_BLE/zephyr/ble-nus.conf` | Bluetooth, NUS service/client와 GATT DM 구성 |
| `libraries/NUCODE_BLE/examples/` | Peripheral/Central Arduino 예제의 단일 원본 |
| `variants/nu54dk/profiles/ble/` | Arduino IDE의 검증된 `BLE NUS` 구성 profile |
| `tests/zephyr/m16_ble_contract` | production API의 compile/link 계약 |
| `tests/zephyr/m16_ble_hil` | Peripheral/Central role별 HIL image |
| `tests/hil/nu54dk/m16_ble_pair.py` | 두 보드 flash, UART protocol과 증거 생성 |

보드 DTS와 radio 물리 정의는 계속 `board_package/NU54DK_Zephyr_DTS`가 소유한다. M16은 보드
서브모듈을 수정하지 않았다.

## 3. 사용자 구성

Arduino IDE에서 다음 순서로 사용한다.

1. `Tools → Feature set → BLE NUS`를 선택한다.
2. `File → Examples → NUCODE BLE`에서 `NUSPeripheral` 또는 `NUSCentral`을 연다.
3. 두 예제에서 사용하는 exact local name이 같은지 확인한다. 기본값은 `NU54-NUS`다.
4. Peripheral과 Central을 서로 다른 NU54DK에 업로드한다.

Build Adapter는 Arduino source discovery에서 `<NUCODE_BLE.h>`를 찾고 feature manifest를
검증한 뒤 `ble-nus.conf`를 병합한다. `ble` profile은 기존 GPIO, Serial, Wire, SPI, ADC와 PWM
기능을 유지하면서 BLE NUS를 추가한다. 사용자가 별도의 `prj.conf`나 `app.overlay`를 만들 필요가
없다.

`NUCODE_BLE` feature는 `radio`와 충돌한다. 임의의 다른 radio feature를 같은 image에 병합해
동시 동작을 추정하지 않는다. 검증된 multiprotocol profile은 후속 버전의 별도 범위다.

## 4. 공개 API

### 4.1 역할 시작과 종료

| API | 의미 |
| --- | --- |
| `beginPeripheral(local_name)` | Bluetooth/NUS를 준비하고 Peripheral 역할과 local name을 고정 |
| `startAdvertising()` | NUS UUID와 local name을 포함한 connectable advertising 시작 |
| `beginCentral()` | Bluetooth/NUS client를 준비하고 Central 역할 선택 |
| `scanForNus(exact_name)` | exact local name을 active scan하고 NUS peer에 자동 연결 |
| `disconnect()` | 현재 연결을 비동기로 종료; 자동 재광고/재검색은 유지 |
| `end()` | 광고·검색·자동 재시작을 중단하고 active connection의 종료를 요청 |

한 image의 전역 `BLESerial`은 한 시점에 Peripheral 또는 Central 역할 하나만 가진다. 역할을
중복 시작하거나 잘못된 역할의 API를 호출하면 명시적 오류로 실패한다. Bluetooth stack과 NUS
module은 image 수명 동안 한 번만 초기화하며 `end()`는 radio 동작과 role lifecycle을 끝내지만
Zephyr Bluetooth stack 자체를 unload하지 않는다. Scan callback에서 만든 `pending_connection`은
현재 `end()`가 취소하지 않으므로 연결 시도 중 호출하면 종료 뒤 연결이 성립할 수 있다. 완전한
비동기 연결 취소까지 보장하는 API로 해석하지 않는다.

### 4.2 상태와 event

| API | 의미 |
| --- | --- |
| `poll()` | 연결 후보 처리, 재광고·재검색과 queued event callback 전달 |
| `connected()` | BLE link 연결 상태 |
| `ready()` | NUS write/notification 경로가 실제 전송 가능한 상태 |
| `onEvent(callback, context)` | `poll()`을 호출한 non-ISR thread 문맥에서 전달할 event callback 등록 |
| `mtu()` | 현재 연결의 최대 NUS payload; 미연결 시 0 |
| `droppedRxBytes()` | 고정 RX queue overflow로 버린 누적 byte 수 |
| `lastError()` | 안정적인 공개 오류 분류 |
| `lastDriverError()` | 마지막 Zephyr/NCS 오류 번호 |

제공 event는 `advertising_started`, `scan_started`, `connected`, `ready`, `disconnected`,
`received`, `error`다. Bluetooth callback에서는 Sketch callback을 직접 호출하지 않는다.
수신 byte와 event를 고정 queue에 넣고 Sketch가 `BLESerial.poll()`을 호출할 때만 사용자 callback을
실행한다. 따라서 `loop()`는 매 반복에서 `poll()`을 호출해야 연결 후보 처리, 자동 재시작과
callback 전달이 계속 진행된다.

### 4.3 Stream 동작

`BLESerial`은 NUS payload를 byte stream으로 노출한다. 수신 byte는 512-byte 고정 queue에
저장되며 event queue는 16개 항목이다. Queue가 가득 차면 성공을 가장하지 않고
`rx_overflow`/`event_overflow` 오류와 drop count를 보존한다.

`write(buffer, size)`는 현재 NUS payload MTU와 내부 상한 244 byte 중 작은 크기로 자동 분할한다.
각 chunk는 NCS의 비동기 완료 callback을 기다리며 최대 5초 동안 blocking할 수 있다. 연결 또는
CCC/notification 준비가 끝나지 않았으면 0을 반환하고 `not_connected` 또는 `not_ready`를
기록한다. ISR에서 lifecycle, callback 등록 또는 write API를 호출하면 `invalid_context`로
거부한다.

## 5. Peripheral 경로

Peripheral advertising에는 일반 discoverable/non-BR/EDR flag와 NUS 128-bit UUID를 넣고,
scan response에는 complete local name을 넣는다. Peer가 NUS RX characteristic에 write한 데이터는
`BLESerial` RX queue로 들어온다. Peer가 TX notification CCC를 활성화한 뒤에만 `ready()`가
참이 되며 `write()`는 NUS TX notification을 사용한다.

연결이 끊기면 connection object가 회수된 뒤 `poll()`이 advertising을 다시 시작한다. 따라서
Sketch가 `end()`를 호출하지 않는 한 Peripheral은 다음 연결을 받을 수 있다.

## 6. Central 경로

Central은 active scan에서 complete/shortened local name을 exact match한다. 주소 후보만 scan
callback에서 복사하고 실제 연결 시작은 `poll()` 문맥으로 넘긴다. 연결 뒤 GATT Discovery
Manager로 NUS service를 찾고 NUS handle을 할당한 다음 TX notification을 구독한다.

NUS service가 없거나 discovery가 실패하면 오류를 기록하고 연결을 종료한다. 연결이 끊기면
connection object 회수 뒤 같은 exact name으로 다시 scan한다. `write()`는 NUS client RX
characteristic write를 사용하고, notification은 RX queue로 전달한다.

## 7. 오류와 동시성 경계

공개 오류는 `none`, `invalid_argument`, `invalid_context`, `already_started`, `not_started`,
`wrong_role`, `not_connected`, `not_ready`, `busy`, `rx_overflow`, `event_overflow`, `timeout`,
`driver_error`로 구분한다. 일반 driver 실패는 가능한 범위에서 원래 정수 오류를
`lastDriverError()`에 보존한다. 다만 `end()`는 advertising/scan 중단과 disconnect의 개별 반환값을
공개 오류로 모두 전달하지 않으므로, 모든 NCS 오류가 보존된다고 보장하지 않는다.

대부분의 lifecycle 변경과 TX는 각각 Zephyr mutex로 직렬화한다. 현재 `end()`는 lifecycle mutex를
잡지 않는다. Connection reference와 scan 후보는 spinlock, 상태는 atomic으로 보호한다. 다만
사용자 event callback과 callback context의 수명은 Sketch가
소유하며, callback 안에서 긴 blocking 동작을 실행하면 `poll()`과 Arduino `loop()` 진행도 함께
지연된다.

## 8. 검증된 동작

공개 API/profile/feature 계약, 두 Arduino 예제, production target build와 서로 다른 두 NU54DK의
Peripheral/Central 연결·양방향 data·명시적 disconnect 뒤 재연결을 검증했다. 사용자 event
callback도 `poll()`을 호출한 Arduino 문맥에서 실행되는 것을 확인했다.

Exact payload, 반복 횟수, image, build record, UART transcript와 evidence digest는
[M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)에 기록한다.

## 9. 명시적 비지원 범위

다음 항목은 M16 완료 증거로 주장하지 않는다.

- 동적/custom GATT service 또는 characteristic builder
- GATT read와 indication
- pairing, bonding, SMP, passkey와 보안 저장소
- HID, Mesh, Channel Sounding, ISO와 DFU/OTA
- BLE와 802.15.4/Thread/ESB의 multiprotocol 동시 운용
- 장기 RF 성능, 최대 동시 연결 수, throughput 또는 저전력 전류 수치

필요한 고급 기능은 Zephyr/NCS `bt_*` API를 직접 사용하거나 후속 검증된 profile/library를
선택한다. M16 NUS HIL 한 건을 위 기능 전체의 지원 증거로 확대하지 않는다.

## 10. 현재 완료 경계와 v0.3.0 회귀

`v0.2.0`은 NUS Peripheral/Central Stream, 두 Arduino 예제, `ble` profile, strict feature
resolver, host/target 계약과 두 보드 HIL을 완료했다. 동적 GATT, read, indication, bonding과
SMP는 이 완료 범위에 포함되지 않는다.

`v0.3.0` 개발 트리에서는 M19 BLE Core/GAP과 M20 범용 GATT가 exact commit
`0103a8434ac205a953c981385ae26a2a64aeeccc`의 두 보드 HIL을 통과했다. 두 단계의 host/target 계약은
기존 NUS API, feature ID와 build bundle parity를 유지한다. M19/M20 exact HIL은 GAP/GATT 검증이며
M16 NUS 두 보드 RF HIL을 재실행한 증거로 확대하지 않는다. Pairing·bonding·BAS/DIS·HID는 공통 lifecycle을
재사용하는 별도 `NUCODE_BLE_Security` library의 M21 범위다. Core `065d4f5` exact 두 보드 HIL과
M21 host 38/38은 PASS했다. M21 진행 중 — 자동 검증 완료, Windows/스마트폰 OS HID pairing·실제 키 입력 수동 확인 대기 상태다.

- [M19 BLE Core/GAP 검증](<../04_검증 기록/23_M19_BLE_Core_GAP_검증.md>)
- [M20 범용 GATT 검증](<../04_검증 기록/24_M20_범용_GATT_검증.md>)
- [M21 BLE 보안과 표준 Profile 검증](<../04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)

후속 구현 결과를 정식 `v0.2.0` NUS 지원 범위에 소급 적용하지 않으며, M22 이전에는 전체
`v0.3.0` 정식 지원으로 표시하지 않는다.
