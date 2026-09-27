# M29-W06 LE CoC·credit·고정 buffer 완료

> 이 기록의 진행률·미실행·다음 작업은 해당 W 단계 완료 당시의 상태입니다. 후속 W07-C의
> Signed Write·EATT 2보드 결과는 [147번 기록](147_M29_W07_Signed_Write_EATT_HIL_준비.md)에,
> 현재 작업과 남은 범위는 [v0.5.0 TODO](../TODO_v0.5.0.md)에 있습니다.

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| production 구현 Core | `8125b10b90869b9cb328f28382319c827d514af2` |
| 최종 실기 Core | `767bb4af6f93cd390b139a2e5699830dcdd03262` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| production LE CoC Host | **7개 시나리오 PASS** |
| W06 parser / source 계약 | **12/12 / 7/7 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| 공개 예제 | **M29 Arduino 그룹 10/10 target build PASS** |
| 실제 2보드 | **`M29-COC-01`·`M29-NEG-01` PASS** |
| M29 진행률 | **W06 완료, 6/8** |

## 1. 구현 범위

`L2capCoc`는 기존 `BLEDevice`·GAP·GATT API와 함께 사용할 수 있는 LE Credit Based Channel
facade다. Public channel은 raw Zephyr 객체가 아닌 64-bit generation token이며, server 1개,
전체 channel 2개, 최대 SDU 512 byte, channel당 RX record 4개와 전체 TX buffer 4개만 사용한다.
Heap fallback은 없고 잘못된 PSM·빈 payload·MTU 초과·stale handle을 공개 오류로 거부한다.

Stack `connected/disconnected/recv/sent/reconfigured` callback은 고정 event record와 RX 복사본만
생성한다. Sketch callback은 `BLEDevice.poll()`에서 실행되고 수신 data pointer는 그 callback 동안만
유효하다. TX pool 또는 controller credit 고갈은 `busy`로 분류하며 blocking이나 무한 재시도를 하지
않는다. Disconnect와 `BLEDevice.end()`는 pending ownership·RX record·queue를 회수하고 session
generation을 바꿔 늦은 callback이 재사용 slot에 들어가지 못하게 한다.

공개 예제 `L2capCocServer`는 PSM `0x0080` echo server이며 모든 시작·echo 오류를 확인한다.
`L2capCocClient`는 service scan 뒤 channel 2개를 열고 각 channel에서 고유 payload의 echo를
검증한다. 단순 local send 완료를 peer 수신 성공으로 표시하지 않는다.

## 2. Host·target 결과

Production Host 실행은 generation handle, 두 slot, RX/TX 고정 ownership, credit backpressure,
disconnect 회수, stale callback과 `BLEDevice.end()`를 포함한 7개 시나리오를 통과했다. Source 계약
7개는 public API·고정 자원·main-thread callback·profile·예제·target/runner 결합을 검사한다. Parser
12개는 exact 두 role transcript 외의 ASCII/non-ASCII noise, 누락·중복·재배치, stale nonce,
wrong role/revision/수치, target FAIL과 잘못된 revision 인자를 fail-closed로 거부한다.

Exact `767bb4af…`의 `nucode.m29.ble_coc_peripheral`과
`nucode.m29.ble_coc_central`은 고정 NCS v3.4.0에서 2/2 build-only PASS, warning 0이었다.
Arduino CLI의 `v0.5.0` M29 그룹은 long/reliable write, descriptor/authorization,
LE CoC, bonded cache 공개 예제 10개를 각각 독립 build directory에서 10/10 PASS했다.

| 역할 | Flash | RAM |
| --- | ---: | ---: |
| central | 251,184 byte | 137,136 byte |
| peripheral | 250,432 byte | 136,688 byte |

## 3. 실제 두 보드 결과

Runner는 두 board UID·MSD·UART, clean exact Core·board·W06 application·공통 runner와 각 HEX 옆
build record를 확인한 뒤 UID 지정 sector flash를 수행했다. Peripheral의 PSM 128 광고를 exact
protocol로 확인한 뒤 central scan을 시작했다. 외부 GPIO·전원 결선, mass erase/recover와 PMIC
write는 사용하지 않았고 세 번째 NU54DK는 이 2보드 test ID에 필요하지 않아 flash하지 않았다.

| 판정 | 관측값 |
| --- | ---: |
| 동시 channel | 2 |
| local / remote MTU | 512 / 512 byte |
| 정상 SDU | channel당·방향당 1,000 |
| payload / cross-channel 오류 | 0 / 0 |
| malformed / PSM / credit 거부 | 20 / 20 / 20 |
| prepare offset / execute-without-prepare 거부 | 20 / 20 |
| 예상 밖 수락 | 0 |
| disconnect 후 이전 handle 거부 | 2 / 2 |
| 새 generation channel / recovery echo | 2 / 2 |
| resource recovery / stale accept | 0 / 0 |
| callback context | PASS |

최종 원시 transcript와 구조화 증거는 다음 파일에 보존한다.

- [`m29-w06-coc-evidence.json`](evidence/m29-w06-767bb4af-coc/m29-w06-coc-evidence.json)
- [`peripheral transcript`](evidence/m29-w06-767bb4af-coc/m29-w06-coc-evidence.peripheral.transcript.log)
- [`central transcript`](evidence/m29-w06-767bb4af-coc/m29-w06-coc-evidence.central.transcript.log)

## 4. 첫 protocol 실패와 동일 조건 재검증

첫 exact `8125b10b…` 실행은 두 보드 identity·flash·READY와 peripheral 시작까지 성공했지만 RF
연결 전에 Host가 `ADVERTISE|role=peripheral|status=pass`를 기대하고 target이 계약대로 출력한
`ADVERTISE|role=peripheral|psm=128|status=pass`를 거부했다. 이는 GPIO·RF·target register 실패가
아닌 공통 runner의 W06 전용 필드 누락이었다.

W02~W04의 기본 광고 record를 바꾸지 않고 공통 runner에 역할별 광고 field 인자를 추가했으며,
W06만 `psm=128|status=pass`를 전달한다. 관련 parser와 이전 long/descriptor runner 회귀를 통과한
뒤 새 exact `767bb4af…`를 같은 NCS·두 role·두 보드·수치 조건에서 한 번 재실행해 PASS했다.
첫 실패 transcript는 성공 로그로 덮어쓰지 않았다.

- [`첫 peripheral transcript`](evidence/m29-w06-8125b10b-coc/m29-w06-coc-evidence.peripheral.transcript.log)
- [`첫 central transcript`](evidence/m29-w06-8125b10b-coc/m29-w06-coc-evidence.central.transcript.log)

## 5. 지원 판정 경계와 다음 작업

이 결과로 `l2cap_credit_based_channel` implementation, `M29-COC-01`과 `M29-NEG-01`을 PASS로
닫는다. 고정 SDK source의 Kconfig/API 존재는 계속 `candidate`이며 이번 구현·target·두 NU54DK
HIL과 같은 증거가 아니다. Cross-vendor peer, external packet sniffer, Signed Write와 EATT는 이번
PASS에 포함하지 않는다.

다음 W07은 기본 OFF인 Signed Write deprecated legacy opt-in과 EATT experimental opt-in을 각각
독립 profile로 구현한다. CSRK·sign counter persistence·replay 거부와 encrypted peer·bearer별
오류·starvation을 먼저 Host/target에서 고정하고, 두 보드 `M29-SIGN-01`·`M29-EATT-01` 뒤 세 보드
`M29-MULTI-01`을 실행한다.
