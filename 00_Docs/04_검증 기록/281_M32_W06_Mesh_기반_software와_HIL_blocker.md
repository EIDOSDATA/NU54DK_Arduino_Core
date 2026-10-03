# M32-W06 Mesh 기반 software와 exact HIL 완료

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W06` Mesh provisioning·역할·model·settings·security 기반 |
| 구현 기준 revision | `ab3f682547836afd33d6c09612f027266b144f90` |
| 마지막 실기 image revision | `45715e42e0d95e6a2e5dcf08d3067c8ca42d4241` |
| CDB 교정·짧은 확인 revision | `70a687698bdd293ae53a8cec52ca114f918a6bb4` |
| 확장 용량 profile revision | `2b9dfce2d06d62f5db76886d8359e6f148d0c8e4` |
| 고정 기준 | NCS `v3.4.0`, Zephyr `bf801e4e3d19…`, board package `fe65f2f0880b…` |
| software/build 판정 | **PASS — M32 Host 102/102, capability 포함 52/52, 세 역할 image 3/3** |
| exact 실기 HIL | **PASS — CMSIS-DAP v2 세 보드, 두 node 구성, 500/500 acknowledged message, negative·STOP** |
| W06 작업 판정 | **완료 — `M32-MESH-01`·`M32-MESHSEC-01` PASS** |

## 1. 구현 결과

`NUCODE_BLE_Mesh` library와 `nucode.ble.mesh` profile을 추가했다. 공개 header는
Zephyr type을 노출하지 않고 다음 경계를 제공한다.

- PB-ADV/PB-GATT 선택, provisioner/node 초기화, discovery·provision·cancel·reset
- Relay, Friend, LPN, GATT Proxy runtime 설정과 LPN Friend Poll
- AppKey 추가, model bind, subscription, publication, Health fault 조회
- NetKey/AppKey update와 Key Refresh phase 전환
- Generic OnOff client/server 상태·acknowledged/unacknowledged·publication
- Generic Level, Light Lightness, Sensor, Time, Scene, Scheduler client message
- 고정 `k_msgq` event queue, overflow counter, Sketch main 문맥 `poll()` callback

replay protection, sequence, IV Update와 settings 복원은 고정 Zephyr Mesh stack이 소유하며
application은 `CONFIG_SETTINGS`·`CONFIG_BT_SETTINGS`·`CONFIG_BT_MESH_RPL_STORE_TIMEOUT`을
명시한다. segmented transport는 16 segment와 고정 TX/RX context를 사용한다.

## 2. 예제·software·build 결과

Arduino 예제는 동일 source snapshot에서 **12/12 PASS**했다.

| 범주 | 예제 |
| --- | --- |
| Provisioning·foundation | `MeshProvisioner`, `MeshNode`, `MeshHealth` |
| 역할 | `MeshRelay`, `MeshFriend`, `MeshLowPowerNode`, `MeshProxy` |
| model | `MeshOnOff`, `MeshLevel`, `MeshLight`, `MeshSensor`, `MeshTimeSceneScheduler` |

`MeshOnOff`는 local Generic OnOff Server와 client 전송을 모두 포함한다. 나머지 SIG
model 예제는 고정 composition의 client와 peer server 역할 경계를 명시하며, 구현하지
않은 server 동작을 PASS로 계산하지 않는다.

`45715e42e0d…`에서 provisioner·node A·node B native image는 **3/3 PASS**했다.
확장 용량 profile을 포함한 M32 Host는 **102/102**, capability 포함 선택 검사는 **52/52**를
PASS했다.

| 역할 | FLASH | RAM |
| --- | ---: | ---: |
| provisioner | 323,584 B | 86,863 B |
| node A | 319,488 B | 86,735 B |
| node B | 319,488 B | 86,735 B |

세 image와 runner는 raw probe UID를 저장하지 않는다. SHA-256 mapping, CMSIS-DAP v2
under-reset DP/AP identity, sector flash, hardware reset, source revision·nonce를 한
attempt로 묶는다. V1 fallback은 사용하지 않았다.

## 3. exact HIL 실행 이력

2026-09-30에는 세 probe 모두 CMSIS-DAP v2 DP/AP identity와 sector flash가 정상이다.
E 장치도 V2로 정상 접근되므로 현재 blocker는 E drive나 특정 보드의 장애가 아니다.

| exact revision | 관측 결과 | 판정 |
| --- | --- | --- |
| `9d56f117…` | 초기 세 역할 실행에서 stack overflow를 확인 | FAIL |
| `97557bf5…` | 1차 stack 증설 뒤 crypto 작업 stack overflow를 확인 | FAIL |
| `cd82ca9c…` | Mesh 전용 stack 증설 뒤 fault는 사라졌지만 첫 node만 provisioning | FAIL |
| `181f0514…` | 역할 교환 실행에서도 물리 보드와 무관하게 첫 역할만 provisioning | FAIL |
| `8a68d1f3…` | 두 beacon 수집 뒤 첫 link를 열도록 바꿔도 두 번째 node provisioning 실패 | FAIL |
| `6af305d3…` | 비동기 재시도 계측에서 두 번째 link가 반복 개폐된 뒤 timeout | FAIL |
| `70a68769…` | CDB node count 2→3 교정 뒤 provisioner와 두 remote node 모두 `provisioned=1` | provisioning-only PASS |
| `7da71ab4…` | 두 provisioning 완료 직후 Config Client 요청이 PB-ADV 종료 전 시작되어 timeout | FAIL |
| `24ea967b…` | 두 node 구성 PASS 뒤 첫 RF ACK 손실에서 31/30으로 정체 | FAIL |
| `7ef6abca…` | ACK 유한 재전송 적용 뒤 간헐 Config AppKey 응답 timeout | FAIL |
| `45715e42…` | PB-ADV 종료 대기·ACK 및 Configuration 유한 재시도로 전체 분모 완료 | **PASS** |

역할 교환 전에는 G가 첫 node로 성공하고 E가 두 번째 node로 실패했다. 역할 교환 뒤에는
E가 첫 node로 성공하고 G가 두 번째 node로 실패했다. 따라서 실패는 보드별 문제가 아니라
두 번째 provisioning 순서에 결부됐다. 원인은 `CONFIG_BT_MESH_CDB_NODE_COUNT=2`가 local
provisioner 한 칸과 첫 remote node 한 칸으로 소진되어 두 번째 remote node의 CDB allocation이
실패한 것이다. `70a68769…`에서 library·contract·HIL·capability registry를 3으로 교정했다.

최종 PASS 실행의 종료 계수는 다음과 같다.

- `provisioned_nodes=2`, `configured_nodes=2`
- 기본 message 300, secured message 200, `acknowledged=500/500`
- node A/B 수신 `250/250`, payload integrity PASS
- 최대 응답 지연 121 ms, 계약 상한 2,000 ms
- unprovisioned access 2건, invalid destination 1건, wrong key 1건 거부
- 세 역할 STOP·cleanup PASS

실행 원본은 [`m32-mesh-11.json`](<evidence/m32-w06-exact-45715e42/m32-mesh-11.json>)과
[`m32-mesh-11.transcript.log`](<evidence/m32-w06-exact-45715e42/m32-mesh-11.transcript.log>)에
보존한다. 앞선 exact/diagnostic 실패도 원인과 함께 `evidence/m32-w06-*` 디렉터리에 보존한다.

## 4. CDB 교정 짧은 확인

사용자가 장시간 실행을 금지했으므로 `70a68769…` image 3/3을 CMSIS-DAP v2 sector flash한 뒤
전체 500-message 완료를 기다리지 않고 약 240초에 runner를 중단했다. 이후 각 UART에
`PROBE`를 보내 provisioner·node A·node B가 모두 같은 revision에서 `provisioned=1`임을
확인했다. 기존 실행에서 두 번째 node가 끝까지 `provisioned=0`이었던 blocker는 해소됐다.

짧은 결과는
[`cdb-capacity-check.json`](<evidence/m32-w06-quick-70a68769/cdb-capacity-check.json>)과
[`cdb-capacity-check.transcript.log`](<evidence/m32-w06-quick-70a68769/cdb-capacity-check.transcript.log>)에
보존한다. 이 결과는 provisioning만 판정하며 configuration·500-message·negative·STOP을
PASS로 승격하지 않는다.

## 5. Arduino CDB 용량 정책

W06 exact HIL은 local provisioner 한 칸과 remote node 두 칸만 필요하므로
`CDB_NODE_COUNT=3`, CDB subnet 1, CDB AppKey 2의 최소 시험 profile을 유지한다. 이 수치를
제품 전체 상한으로 사용하지 않는다.

공개 `MeshProvisioner` 예제는 `prj.conf`에서 CDB node slot 33개, subnet 4개, AppKey 8개를
선언한다. remote node 용량은 local provisioner 한 칸을 제외한 32개다. CDB 용량과 실제 local
Mesh 참여 용량이 어긋나지 않도록 `BT_MESH_SUBNET_COUNT`, `BT_MESH_APP_KEY_COUNT`,
`BT_MESH_MODEL_KEY_COUNT`도 함께 설정한다. Adaptive profile에서는 같은 여섯 값을
`nucode-build.json` capacity 계약으로 검증한다. 고급 사용자는 sketch별 `prj.conf`를 실제
설정 원본으로 사용하고 Adaptive profile에서는 같은 값을 capacity 계약에도 선언한다.

다중 subnet 생성·삭제 공개 API와 Subnet Bridge 실기는 W07 소유이며 W06 PASS 조건에 섞지 않는다.

## 6. 완료 판정

`45715e42…` exact image를 세 CMSIS-DAP v2 probe에 sector flash하고 두 PB-ADV link가 모두
닫힌 뒤 Configuration Client를 시작했다. AppKey 추가·model bind는 timeout에만 한정한 유한
재시도를 사용하며, acknowledged traffic도 최대 3회 유한 재전송한다. 이로써 일시 RF 응답 손실을
무한 대기나 false PASS로 바꾸지 않고 전체 300+200 message 분모를 완료했다.

Zephyr Mesh stack 소유인 sequence·IV Update·RPL/replay와 settings 저장 경계는 고정 Kconfig와
Host/API negative 검사를 유지한다. exact RF 실행은 공개 API로 주입 가능한 unprovisioned access,
invalid destination, wrong AppKey와 payload 무결성을 관측했다. 관측하지 않은 내부 replay packet이나
settings 손상을 RF 실측으로 표기하지 않는다.

최종 closure는
[`w06-closure-audit.json`](<evidence/m32-w06-exact-45715e42/w06-closure-audit.json>)에 고정한다.
W06은 완료 분자에 포함하며 다음 순서는 W07 Mesh 1.1 관리 exact HIL이다.
