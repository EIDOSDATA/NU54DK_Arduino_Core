# BLE 범용 GATT server/client API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-BLE-GATT-001 |
| 문서 개정 | 1.6 |
| 문서 상태 | v0.4.1 정식 GATT 계약과 v0.5.0 M29 개발 확장 |
| 적용 제품 버전 | `v0.3.0`·`v0.4.0`·`v0.4.1`의 `ble` profile, `v0.5.0` 개발 source |
| 최종 갱신일 | 2026-09-15 |
| 대상 library | `NUCODE_BLE` |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 목적과 범위

Server schema부터 예제·검증 절까지는 설치·지원 v0.4.1 계약이다. 하단의 M29 절은
개발 `main`의 확장을 설명하며, 두 범위의 value 크기·연결 수·지원 operation을 혼합하지 않는다.

M20은 M19 Core/GAP 위에 vendor service를 만들고 사용하는 범용 GATT API를 제공합니다. NUS처럼
고정 profile wrapper가 아니라 UUID, property, permission과 bounded value를 sketch가 선언합니다.

이 API는 `v0.3.0`부터 정식 지원하며 v0.4.1에서도 같은 공개 범위를 유지합니다. 도입 당시 두 보드 RF PASS는
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

## M28 회귀 결과와 M29 전환 경계

M28은 기존 단일-link GATT server/client를 M20 회귀에서 PASS하고 3보드 LINK 확인용 GATT
`LINK_UP`을 사용했다. Local central client와 실제 subscribe한 incoming server link를 구분하지만,
두 link의 임의 동시 GATT operation을 M28 지원으로 주장하지 않는다. Generation별 client session,
remote handle·subscription과 long/reliable·cache·CoC 확장은 M29에서 고정 자원·상호운용 시험과
함께 계약한다. 현재 설치·지원 v0.4.1의 단일 connection session은 그대로 유지한다.

## M29-W02~W06 개발 확장

아래 항목은 현재 `0.4.1-dev` source에서 구현·검증한 v0.5.0 후보이며 설치·지원 v0.4.1 API로
소급하지 않는다.

- connection generation handle을 받는 GATT client overload와 link별 고정 operation context 2개
- MTU 247에서 최대 512-byte long read와 response write, link별 prepare/execute transaction 1개
- characteristic당 descriptor 4개, read multiple handle 4개, 동기 authorization과 link 지정 전송
- bonded identity·database hash·UUID·schema·CRC를 결합한 84-byte GATT cache record 4개
- generation opaque handle의 LE CoC server 1개·channel 2개·512-byte SDU

LE CoC는 `BLEL2cap.startServer()`, `connect()`, `send()`, `disconnect()`와 `connected()`를 제공한다.
공개 handle에는 raw `bt_l2cap_chan *`를 담지 않으며 slot 재사용은 generation이 바뀌므로 이전
handle이 새 channel을 조작할 수 없다. RX payload는 channel당 4개의 512-byte record에 복사하고
전체 TX buffer는 4개로 제한한다. TX pool 또는 controller credit이 부족하면 blocking·heap 확장
대신 `false`, `BLEError::busy`와 driver 오류를 반환한다.

Connected·disconnected·received·sent·reconfigured event는 고정 queue를 거쳐
`BLEDevice.poll()` 문맥에서만 전달한다. `received`의 data pointer는 해당 callback 동안만 유효하다.
`BLEDevice.end()`는 session generation을 먼저 바꾸고 queue/RX ownership을 폐기한 뒤 active
channel을 종료한다. Late callback과 disconnect 뒤 stale handle은 새 session이나 재사용 slot을
수정하지 않는다.

`M29-COC-01`과 `M29-NEG-01`은 exact `767bb4af…`에서 두 실제 NU54DK로 2채널·512-byte SDU를
방향별 channel당 1,000회, malformed·offset·execute·PSM·credit 각 20회와 disconnect/reconnect를
검증했다. 이 결과는 NU54DK 간 LE CoC 범위이며 cross-vendor peer, Signed Write와 EATT 지원을
의미하지 않는다. 상세 근거는
[146번 기록](<../04_검증 기록/146_M29_W06_LE_CoC_credit_buffers.md>)에 있다.

## M29-W07 Signed Write·EATT와 통합 완료

두 기능은 기본 BLE profile에서 OFF이며 별도 library header를 포함할 때만 선택한다.

| 선택 library | 개발 계약 | 작성된 예제 |
| --- | --- | --- |
| `NUCODE_BLE_LegacySigning` | deprecated legacy opt-in; bonded CSRK·local/remote counter 영속성과 replay 거부 | `LegacySignedWritePeripheral`, `LegacySignedWriteCentral` |
| `NUCODE_BLE_EATT` | experimental opt-in; 암호화된 link당 최대 2 bearer, GATT의 `unenhanced`/`enhanced` 선택 | `EattPeripheral`, `EattCentral` |

Exact `c71ef4a2…`의 두 보드 HIL에서 Signed Write 20회·warm reboot counter 유지·replay 수락 0,
EATT의 암호화 전 거부·2 bearer·상한 초과 거부·production enhanced read/write와 bearer별
1,000 SDU를 검증했다. Payload 오류·deadlock·starvation은 0이다. 이 결과로 SDK의
deprecated/experimental 등급을 안정 기능으로 바꾸지 않는다.

후속 통합은 exact `16eb8fce…`에서 3보드 `M29-MULTI-01`·`M29-REG-01`을 PASS했고,
exact `a964ae20…`에서 Windows WinRT peer 교차 제조사 GATT 상호운용을 PASS했다.
이로써 M29는 작업 묶음 8/8(100%), test ID 10/10을 완료했다. 후속 M30도 8/8·10/10과
실제 전원 차단 12/12를 완료했다. M31은 W01~W03 완료 3/8이며 잔여 범위는 [M31 TODO](../TODO_M31.md)를 따른다.
세부 API·자원과 단계별·완료 exact 원본은
[M29 계약](<../01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)과
[147번 기록](<../04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>),
[149번 완료 기록](<../04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)에서 관리한다.
