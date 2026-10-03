# BLE Core/GAP API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-BLE-GAP-001 |
| 문서 개정 | 1.9 |
| 문서 상태 | v0.5.0 stable GAP 계약과 M28 확장, v0.6.0 M32-W03~W05 완료한 개발 API |
| 적용 제품 버전 | stable `v0.5.0`의 `ble`·지정 확장 profile, 개발 중 `v0.6.0` |
| 최종 갱신일 | 2026-10-01 |
| 대상 library | `NUCODE_BLE` |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 목적과 범위

아래 본문은 stable v0.5.0 계약이다. M28 확장과 역사 RC 검증은 마지막 절에서 구분한다.

M19는 NUS에 종속되지 않는 Arduino 친화 BLE lifecycle과 GAP API를 제공합니다. 공개 헤더는
Zephyr type을 노출하지 않습니다. M19의 단일 연결·31-byte legacy advertising 계약에서
v0.5.0은 central 1 + peripheral 1의 두 link와 아래 M28 확장으로 범위를 넓혔습니다.

기본 API는 `v0.3.0`부터 정식 지원했으며 v0.4.1까지 같은 공개 범위를 유지했습니다. 도입 당시 두 보드 RF PASS는
[M19 BLE Core/GAP 검증](<../04_검증 기록/23_M19_BLE_Core_GAP_검증.md>), stable package 승격은
[v0.3.0 정식 공개 기록](<../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)이 소유합니다.

| 객체 | 책임 | 고정 경계 |
| --- | --- | --- |
| `BLEDevice` | stack 1회 초기화, 이름, main-thread event dispatch | image당 1개 |
| `BLEAdvertising` | flags, interval, UUID, manufacturer/service data | advertising·scan response 각각 31 byte |
| `BLEScan` | active/passive scan, 이름·UUID·주소 filter | bounded 결과 queue, payload 31 byte |
| `BLEConnection` | connect, disconnect, explicit reconnect, MTU/PHY/parameter 요청 | central 1 + peripheral 1; 기존 인자 없는 API는 호환 view |
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
함께 확인해야 합니다. v0.5.0은 central 1 + peripheral 1의 동시 두 link와 단일 central pending connect를 지원합니다.
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

## M28 개발 결과와 공개 경계

v0.5.0의 multi-role/link, extended·periodic advertising, PAwR와 privacy는
[M28 계약](<../01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)의 W01~W08과
9개 test ID를 완료했고 [정식 v0.5.0](../05_릴리스/v0.5.0/README.md)에 포함됐다.
v0.4.1 stable의 연결 1개·legacy 31-byte 계약은 역사 기준선으로 보존한다.

| 정식 확장 API/자원 | M28에서 확인한 상한과 동작 |
| --- | --- |
| `BLEConnectionHandle`·상세 event | central 1 + peripheral 1, 총 2-link; generation으로 stale callback 차단 |
| Extended advertising/scanning | generation set 1개, payload 최대 255 byte, SID·PHY·TX power metadata |
| Periodic advertising/sync·PAST | periodic sync 1개, report 최대 255 byte, 현재 connection handle에 결합한 transfer |
| PAwR advertiser/scanner | 4 subevent × 4 response slot, payload 최대 249 byte |
| Privacy·link control | RPA timeout 1~3600초, identity·DLE·parameter·remote-info를 link별 조회 |

인자 없는 기존 singleton API는 호환 view를 유지한다. 현재 자원과 실제 두/세 보드 결과는
[M28 readiness](../../variants/nu54dk/m28-ble-readiness.json)와
[140번 기록](<../04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)을 따른다.

## v0.6.0 M32-W03 timing·feature API

M32-W03 구현 commit `30258a57…`은 기존 generation handle과 main-thread callback 규칙을 유지하면서
다음 per-link 제어·조회 API를 추가했다. W03 exact HIL은 완료했으며 이 v0.6.0 개발 결과를
현재 v0.5.0 stable 지원 범위로 소급하지 않는다.

| 범위 | 공개 API와 경계 |
| --- | --- |
| Connection Subrating | `setDefaultSubrate()`, `requestSubrate()`, `subrate()`와 `subrate_changed`; factor·continuation·latency·timeout 조합을 호출 전에 검증 |
| Shorter Connection Interval | `setDefaultConnectionRate()`, `requestConnectionRate()`, `connectionRate()`, `minimumConnectionInterval()`과 `connection_rate_changed`; interval은 요청 125 us·결과 us 단위 |
| Frame Space Update | `requestFrameSpace()`, `frameSpace()`와 `frame_space_changed`; PHY·spacing mask와 0~10,000 us 범위를 검증하고 controller status를 보존 |
| Extended LE Feature Set | local 32-byte 지원 범위와 remote 최대 248-byte page 복사, page 0의 8-byte·후속 page의 24-byte indexing, 최대 page 10 거부 |
| Channel classification | 37-channel map, reserved bit 0과 최소 활성 channel 2개를 검사한 뒤 controller에 복사 |
| SCA 적용성 | 고정 controller의 SCA 절차와 Zephyr Host 요청·report API 부재를 `BLESleepClockAccuracySupport`의 두 필드로 분리 |

모든 비동기 결과는 link slot에 복사한 뒤 `BLEDevice.poll()` event로 전달한다. Disconnect·slot 재사용 때
Subrating, rate, Frame Space, remote feature cache를 지워 stale handle이 다음 generation의 결과를 읽지
못하게 한다. `ConnectionSubrating*`, `FrameSpaceUpdate*`, `ShorterConnectionIntervals*`,
`BleThroughput*`, `ExtendedLeFeaturePages`, `SleepClockAccuracyUpdate`, `LeChannelMapControl` 예제가 단위와
지원 경계를 출력한다.

초기 software 검사와 DP/AP 접근 중단 당시의 미완료 시도는
[279번 기록](<../04_검증 기록/279_M32_W03_W04_software와_HIL_blocker.md>)에 보존한다.
이후 exact identity·sector flash·STOP을 포함한 W03 HIL을 완료했으며 최종 판정은
[288번 기록](<../04_검증 기록/288_M32_W03_연결_timing_feature_exact_HIL_완료.md>)과
[M32 TODO](../TODO_M32.md)를 따른다. 초기 시도의 NOT RUN을 소급해 PASS로 바꾸지 않는다.

## v0.6.0 M32-W04 광고·identity·자원 API

M32-W04 구현 commit `b8d0c0c1…`은 singleton 호환 view를 유지하면서 최대 3개의 generation 기반
`BLEExtendedAdvertisingSet`, 최대 2개의 `BLEPeriodicSync`, `BLEIdentity`, `BLEAdvertisingLists`를
추가했다. 생성·시작·중지·삭제는 고정 slot을 사용하며, 삭제나 session 전환 뒤의 handle은
`stale_handle`로 거부한다.

| 범위 | 공개 API와 경계 |
| --- | --- |
| Multiple advertising | set별 legacy/extended·connectable/scannable·primary/secondary PHY·SID·coding·payload를 보존하고 활성 set 변경과 자원 초과를 fail-closed로 거부 |
| Directed advertising | peer 주소·local identity·high/low duty timeout을 명시하며 연결 완료 뒤 재광고는 sketch가 결정 |
| Identity와 list | identity 생성/reset/delete 및 accept/resolving/periodic advertiser list 추가·삭제·clear; 활성 절차 중 controller가 거부한 상태를 그대로 반환 |
| EAD | 16-byte session key·8-byte IV·5-byte randomizer를 복사해 암복호화하고 인증 실패·재사용 randomizer를 거부하며 임시 key/plaintext를 지움 |
| Coding selection | coded PHY에서 S=2/S=8 선호를 명시하며 coded controller 설정이 없는 image는 build/profile 단계에서 분리 |
| 동시 scan/initiate | `CONFIG_BT_SCAN_AND_INITIATE_IN_PARALLEL` 전용 profile에서 scan을 유지한 채 연결을 시작; 기본 profile의 기존 배타 규칙은 보존 |

자원 preset은 C1P1=2 link/1 peripheral/3 set/3 identity/2 sync, C2P0=2/0/1/2/2,
C0P2=2/2/2/2/1이다. target build의 RAM/RRAM은 각각 65,280/226,048 B,
60,344/218,716 B, 61,248/207,276 B로 230 KiB/640 KiB 상한을 만족했다.
공개 예제 12/12, Host 회귀 21 test와 target 5/5 build는 PASS했고 이후
`M32-ADV-01`, `M32-PRIV-01`, `M32-EAD-01` exact HIL도 완료했다.
초기 DP/AP 중단 시도는 [279번 기록](<../04_검증 기록/279_M32_W03_W04_software와_HIL_blocker.md>),
최종 완료는 [290번 기록](<../04_검증 기록/290_M32_W04_광고_identity_privacy_exact_HIL_완료.md>)에서
구분한다. 이 개발 결과를 v0.5.0 stable 지원 범위로 소급하지 않는다.

## v0.6.0 M32-W05 Nordic 확장 API

M32-W05 구현 commit `85da6122…`은 고정 NCS `v3.4.0`의 Nordic vendor HCI 기능을
`BLENordic` 객체로 제공한다. 공개 헤더에는 Zephyr·SDC type을 노출하지 않으며, 기능을 켠 image만
`CONFIG_NUCODE_BLE_NORDIC_EXTENSIONS`와 종류별 4~64개 bounded report queue를 포함한다.

| 범위 | 공개 API와 경계 |
| --- | --- |
| LLPM | `setLlpmMode()`는 active link가 없을 때 image-wide mode를 설정한다. `requestLlpmInterval()`은 2M PHY link와 1~7 ms 정수 interval만 허용하며 표준 Shorter Connection Interval API와 분리한다. |
| QoS report | `setConnectionEventReports()`와 `setChannelSurvey()`가 vendor report를 켜고, read/callback API가 controller callback 밖 수명 복사본을 main thread에 전달한다. |
| Connection time | `setAnchorPointReports()`가 event counter와 controller clock us를 전달한다. `projectAnchorPoint()`는 16-bit event counter wrap을 signed 차이로 계산하며 서로 다른 controller clock domain의 직접 비교를 보증하지 않는다. |
| Event trigger | Connection·advertising set·scanner·initiator 시작 task를 caller 소유 32-bit 주소에 연결한다. 0은 cancel이며 EGU/DPPI/peripheral 수명과 충돌 방지는 caller 책임이다. |
| Radio notification | `setRadioNotification()`은 anchor와 connection interval로 periodic absolute timer를 갱신하고 system workqueue에서 prepare callback을 호출한다. Callback은 Serial·heap·blocking/BLE 제어를 수행하지 않는다. |
| Flushable ACL | `flushableAclSupport()`가 controller experimental, Host transmit path, usable을 따로 반환한다. 고정 Host에는 flushable LE ACL TX API가 없어 usable=false이며 전송 facade를 제공하지 않는다. |

Vendor HCI callback은 connection generation을 조회한 뒤 QoS·survey·anchor 종류별 queue에 복사한다.
Queue overflow는 `event_overflow`와 누적 drop counter로 보이며, disable·`BLEDevice.end()`는 report queue와
radio timer/work를 제거한다. 설정·trigger API는 Arduino main thread 전용이고 stale connection/set,
초기화 전 호출, 정렬되지 않은 task 주소를 거부한다.

공개 예제 8/8, Nordic target contract와 관련 Host 회귀가 PASS했다. Exact revision `f813356c…`의
CMSIS-DAP v2 두 보드 HIL에서 역할별 QoS 200·survey 20·anchor 1,000·event 200·radio prepare 200,
LLPM 1,000 us를 확인했다. 최대 anchor gap 3,999 us·event gap 1 ms, overflow와 negative,
disable 뒤 callback 0·STOP을 PASS해 W05를 완료했다. Flushable ACL만 고정 Host TX 경로 부재로
unsupported/HOLD이며 지원 기능 수에 넣지 않는다. [280번 기록](<../04_검증 기록/280_M32_W05_Nordic_확장_software와_HIL_blocker.md>)과
exact JSON이 판정을 소유한다. 이 v0.6.0 개발 결과를 현재 v0.5.0 stable 지원으로 소급하지 않는다.
