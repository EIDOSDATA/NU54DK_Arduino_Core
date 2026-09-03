# BLE 범용 GATT server/client API 설계

## 목적과 범위

M20은 M19 Core/GAP 위에 vendor service를 만들고 사용하는 범용 GATT API를 제공합니다. NUS처럼
고정 profile wrapper가 아니라 UUID, property, permission과 bounded value를 sketch가 선언합니다.

이 API는 `v0.3.0`에서 정식 지원합니다. Exact-commit 두 보드 RF PASS는
[M20 범용 GATT 검증](<../04_검증 기록/24_M20_범용_GATT_검증.md>), stable package 승격은
[v0.3.0 정식 공개 기록](<../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)이 소유합니다.

## Server schema

```cpp
const nucode::ble::BLEUuid serviceUuid("9f3c0001-8b7a-4d64-a1b2-001122334455");
const nucode::ble::BLEUuid valueUuid("9f3c0002-8b7a-4d64-a1b2-001122334455");
nucode::ble::BLEService service(serviceUuid);
nucode::ble::BLECharacteristic value(
    valueUuid,
    nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
        nucode::ble::BLEProperty::notify,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write,
    64U);
```

Characteristic을 service에, service를 `BLEDevice`에 추가한 뒤 `BLEDevice.begin()`을 호출합니다.
Bluetooth 시작 뒤 schema 변경은 거부합니다. 기본 Kconfig 경계는 service 4개, service당
characteristic 8개이며 characteristic value는 최대 244 byte입니다. 16/128-bit UUID를 지원하고
GATT schema의 32-bit UUID는 현재 명시적으로 거부합니다.

등록한 `BLEService`, `BLECharacteristic`과 선택적인 caller-owned value buffer는 Bluetooth image가
끝날 때까지 유효한 static/global 수명을 가져야 합니다. Setup-local 객체나 buffer는 등록 attribute와
queued event가 dangling pointer가 되므로 허용하지 않습니다. Caller-owned buffer도 공개 API를
통해서만 읽고 쓰며 sketch가 직접 수정하지 않습니다.

Database 준비는 모든 service/characteristic을 먼저 검증·구성한 뒤 등록하는 2단계입니다. 두 번째
이후 service 등록이 실패하면 앞서 등록한 service와 모든 registered flag를 rollback하므로 다음
`begin()`이 부분 database에 막히지 않습니다.

Read는 stack callback deadline 안에서 cached value를 동기 반환합니다. Write는 bounded buffer에
복사한 뒤 `BLEDevice.poll()`에서 `written` callback을 전달합니다. Prepare/execute long write는
지원하지 않고 ATT `not supported`로 거부합니다.

Peer의 BT RX callback과 Arduino thread가 공유하는 cached value/length는 spinlock으로 보호합니다.
Read, notify와 indicate는 lock 안에서 고정 buffer snapshot을 만든 뒤 stack 호출 전에 lock을
놓으므로 C++ data race와 stack-call-under-lock을 모두 피합니다.

## Notify와 indicate

`notify()`는 CCC notification 구독과 현재 ATT MTU를 확인한 뒤 전송합니다. Local TX 완료는
`notification_sent` event입니다. `indicate()`는 별도 고정 buffer가 confirmation까지 payload
수명을 보존하며, 성공은 `indication_confirmed`, peer/ATT 실패는 `indication_failed`로 구분합니다.
같은 characteristic의 indication을 동시에 두 개 시작하면 `busy`입니다.

Subscription 상태는 현재 단일 peer 연결에만 유효합니다. Disconnect 뒤 유지되거나 자동
복원된다고 가정하지 않습니다.
요청한 notify/indicate type은 `bt_gatt_subscribe()` 전에 별도 상태로 보존해 CCC write 응답보다
먼저 수신되는 packet도 정확히 분류합니다. Unsubscribe와 ATT error는 subscription 상태를
fail-closed로 지웁니다.

## Generic client

`BLEClient`는 한 번에 exact service UUID와 characteristic UUID 한 쌍을 discovery합니다. 발견한
remote service/characteristic 객체는 portable handle 복사본이며 다음 disconnect까지만
유효합니다.

지원 operation은 다음과 같습니다.

- bounded single-fragment read
- response가 있는 write
- response가 없는 write와 local TX 완료
- notification 또는 indication CCC subscribe
- unsubscribe

Operation은 한 번에 하나만 진행합니다. Disconnect 시 service/characteristic/CCC handle과 busy,
subscription 상태를 먼저 무효화하고 `handles_invalidated`를 main thread에 전달합니다. 재연결 뒤에는
반드시 discovery와 subscribe를 다시 수행해야 합니다.

각 비동기 operation, subscription과 server TX는 시작 connection과 session generation token을
보존합니다. Callback의 connection/token이 현재 link와 다르면 queue나 새 client state를 수정하지
않습니다. Public remote handle getter는 lock으로 보호한 값 복사본을 반환합니다. `end()`는 GATT
queue와 token을 명시적으로 종료하며, 늦은 이전 disconnect도 exact connection/session이 아니면
새 session을 무효화하지 않습니다.

## Callback과 오류 경계

Server write/CCC/전송 완료와 client discovery/read/write/subscription event는 모두 고정 queue로
복사되어 `BLEDevice.poll()`에서 전달됩니다. Stack callback pointer를 sketch에 보존하지 않습니다.

잘못된 schema, 중복 UUID, buffer 초과, MTU 초과, 미연결, 이미 진행 중인 operation은 boolean
실패와 `BLEDevice.lastError()/lastDriverError()`로 보고합니다. Queue overflow도 성공으로
축소하지 않습니다.
Schema mutation, notify/indicate와 모든 client operation은 main thread 전용입니다. ISR 호출은
Zephyr GATT나 mutex에 진입하기 전에 `invalid_context/-EWOULDBLOCK`으로 거부합니다.

## 예제와 검증

- `libraries/NUCODE_BLE/examples/CustomGattPeripheral/CustomGattPeripheral.ino`
- `libraries/NUCODE_BLE/examples/CustomGattCentral/CustomGattCentral.ino`
- `tests/zephyr/m20_ble_gatt_contract`
- `tests/zephyr/m20_ble_gatt_hil`
- `tests/hil/nu54dk/m20_ble_gatt.py`

두 보드 HIL은 별도 GPIO 배선 없이 exact UUID discovery, cached read, write와 write command,
notification subscribe/unsubscribe, indication confirmation, disconnect handle 무효화, reconnect 뒤
rediscovery/resubscribe를 검증합니다. Peripheral은 runner의 128-bit nonce를 cached value에 넣고
central이 첫 read에서 전체 binary challenge를 exact 비교하므로 같은 service UUID를 쓰는 주변의
stale/병렬 보드가 있어도 서로 다른 peer transcript를 하나의 PASS로 결합하지 않습니다.
