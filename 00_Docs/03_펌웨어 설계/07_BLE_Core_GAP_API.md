# BLE Core/GAP API 설계

## 목적과 범위

M19는 NUS에 종속되지 않는 Arduino 친화 BLE lifecycle과 GAP API를 제공합니다. 공개 헤더는
Zephyr type을 노출하지 않으며, 동적 할당 없이 단일 연결과 31-byte legacy advertising을
명시적으로 지원합니다.

| 객체 | 책임 | 고정 경계 |
| --- | --- | --- |
| `BLEDevice` | stack 1회 초기화, 이름, main-thread event dispatch | image당 1개 |
| `BLEAdvertising` | flags, interval, UUID, manufacturer/service data | advertising·scan response 각각 31 byte |
| `BLEScan` | active/passive scan, 이름·UUID·주소 filter | bounded 결과 queue, payload 31 byte |
| `BLEConnection` | connect, disconnect, explicit reconnect, MTU/PHY/parameter 요청 | 동시 peer 1개 |
| `BLEUuid` | 16/32/128-bit UUID 저장·형식화 | heap 없음 |
| `BLEAddress` | public/random LE 주소 복사본 | heap 없음 |

## Lifecycle

GATT service schema가 있다면 `BLEDevice.begin()` 전에 모두 등록합니다. `begin()`은 공용 stack
owner를 통해 `bt_enable()`을 image 전체에서 정확히 한 번만 호출합니다. `CONFIG_BT_SETTINGS`가
켜진 image는 enable 직후 `settings_load()`도 정확히 한 번 수행하며, M21 보안 모듈은 같은
결과를 `settingsReady()`와 `settingsResult()`로 조회합니다.

`BLEDevice.end()`는 library가 시작한 광고·scan·연결만 끝냅니다. Controller stack 자체는
disable하지 않습니다. 다시 사용하려면 같은 image에서 `begin()`을 호출할 수 있지만, 등록한
GATT schema와 controller의 one-time lifecycle은 유지됩니다.

NUS facade(`BLESerial`)와 범용 facade(`BLEDevice`)는 한 image에서 lifecycle owner를 공유합니다.
둘 중 하나가 시작된 동안 다른 facade의 `begin()`은 상태 오류로 거부합니다. `end()` 중인 pending
connect와 active link는 취소한 뒤 connection object가 recycle될 때까지 owner를 유지하므로, 이전
NUS 연결이 새 범용 session에 들어오는 전환 race도 fail-closed입니다. 범용 `end()`는 session
generation을 먼저 바꾸고 pending/active link와 GAP·scan·GATT queue를 비워 이전 callback을 다음
`begin()`에 전달하지 않습니다.

## Callback 문맥

Zephyr Bluetooth callback은 사용자 callback을 직접 호출하지 않습니다. GAP event와 scan 결과는
고정 message queue로 복사되고 `BLEDevice.poll()`에서만 사용자 callback을 호출합니다. 따라서
Arduino sketch는 `setup()/loop()`와 같은 main thread에서 callback을 처리합니다.

광고·scan·연결·schema 변경과 GATT operation을 포함한 공개 제어 API도 Arduino main thread에서만
호출합니다. ISR에서 호출하면 controller API나 mutex로 들어가지 않고 `invalid_context`로
거부합니다.

Queue가 가득 차면 오래된 결과를 암묵적으로 성공 처리하지 않습니다. `lastError()`,
`droppedEvents()`와 `droppedResults()`로 overflow를 확인할 수 있습니다.

## Advertising과 scan 경계

- Legacy advertising payload는 31 byte를 넘으면 `payload_overflow`로 거부합니다.
- 128-bit UUID, manufacturer data와 이름을 함께 쓰려면 이름을 scan response에 두는 구성이
  일반적입니다.
- 이름 filter 결과는 scan response에서 올 수 있습니다. 이 결과의 `connectable` 값만으로
  원본 advertising type을 추정하지 말고 filter가 보존한 peer 주소를 사용합니다.
- UUID filter는 UUID가 실린 원본 advertising payload를 대상으로 하므로 연결 가능 여부와
  manufacturer data를 같은 결과에서 함께 확인할 수 있습니다.
- 여러 service UUID는 16/32/128-bit 폭마다 하나의 complete-list AD field로 결합합니다. 같은
  complete-list type을 여러 field로 반복하지 않으며, 결합 뒤 31 byte를 넘으면 시작을 거부합니다.
- scan과 advertising을 한 controller에서 동시에 시작하는 요청은 상태 오류로 거부합니다.

## 연결 경계

`connect()`는 scan 결과의 주소 복사본으로 비동기 연결을 시작합니다. `reconnect()`는 마지막
peer 주소에 새 연결을 시작하는 명시적 요청이며 자동 재연결 정책은 제공하지 않습니다.
Disconnect 이후 advertising 재시작과 client 재연결 시점은 sketch가 결정합니다.

MTU, PHY와 connection parameter 요청은 controller/peer의 비동기 협상입니다. 요청 성공은 최종
협상값 보장이 아니며 `mtu_changed`, `phy_changed`, `parameters_changed` event와 현재 getter를
함께 확인해야 합니다. 이 버전은 동시 연결 1개와 단일 pending connect만 지원합니다.
`txPower()`는 PHY별 transmit-power-control 설정을 요구하지 않는 legacy current/max 조회 경로를
사용하며, 실제 연결 HIL에서 성공과 반환 범위를 확인합니다.

## Profile resolver

공개 예제는 sidecar `prj.conf` 없이 `feature_set=ble` profile을 사용합니다. Header include로
기존 `nucode.ble.nus` feature가 선택되고 같은 feature conf가 Core/GAP와 범용 GATT source에 필요한
Kconfig를 제공합니다. M16 NUS example과 feature ID를 유지해 기존 sketch 선택 계약을 깨지 않습니다.

## 예제와 검증

- `libraries/NUCODE_BLE/examples/GAPPeripheral/GAPPeripheral.ino`
- `libraries/NUCODE_BLE/examples/GAPCentral/GAPCentral.ino`
- `tests/zephyr/m19_ble_gap_contract`
- `tests/zephyr/m19_ble_gap_hil`
- `tests/hil/nu54dk/m19_ble_gap.py`

두 보드 HIL은 별도 GPIO 배선 없이 BLE RF로 advertise, UUID/manufacturer filter, connect,
disconnect, readvertise와 explicit reconnect를 검증합니다. USB 두 개는 각 보드의 전원·DAPLink
flash·UART evidence 수집에 사용합니다. Runner의 128-bit nonce 전체에서 service UUID를 만들고
central이 이를 exact filter하므로 두 transcript가 같은 실제 RF fixture를 만났음을 결합합니다.
