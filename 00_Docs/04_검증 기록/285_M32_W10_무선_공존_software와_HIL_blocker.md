# M32-W10 지원 무선 공존 software와 exact HIL 완료

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W10` BLE/Mesh/IEEE 802.15.4/ESB와 외부 1-wire 공존 |
| 구현 revision | `512b027a6b1b9966ef70ead8c6bc07d7a16522d5` |
| 세 보드 HIL 준비 revision | `042cfb32de7d…` |
| 고정 기준 | NCS `v3.4.0`, Zephyr `bf801e4e3d19…`, board package `fe65f2f0880b…` |
| software/build 판정 | **PASS** |
| exact 실기 HIL | **PASS — 세 내부 조합, protocol별 4,000/4,000, loss·corrupt·starvation 0** |
| W10 작업 판정 | **완료 — clean exact build 9/9·세 조합 HIL·negative·restart·STOP PASS** |

## 1. 지원 조합과 경계

고정 SDK가 제공하는 controller·MPSL 경로를 실제 target build로 대조해 다음 네 profile을 추가했다.

| profile | 판정 | controller·radio 소유권 |
| --- | --- | --- |
| `coexistence_ble_mesh` | 적용 가능 | 단일 SDC가 BLE connection과 Mesh bearer를 함께 소유 |
| `coexistence_ble_154` | 적용 가능 | SDC와 direct nRF 802.15.4 driver가 MPSL multiprotocol 경로를 공유 |
| `coexistence_ble_esb` | candidate | SDC와 ESB가 experimental MPSL timeslot 두 session을 사용 |
| `external_coexistence` | template | SDC의 MPSL CX 1-wire grant input과 local grant simulator output |

모든 protocol을 한 image에 합치지 않는다. IEEE 802.15.4와 ESB의 direct radio owner 조합은 기존
`radio-owner` conflict로 계속 거부한다. Mesh DFU 최대 profile과 direct radio profile도 단순 합산하지
않고 공존 전용 profile을 요구한다. ESB 공존은 고정 SDK에서 build되는 candidate일 뿐 W09 단독 HIL과
W10 공존 HIL 전에는 제품 지원으로 승격하지 않는다.

`NUCODE_Radio_Coexistence`는 heap 없이 protocol별 요청·전달·drop·sequence/hash 오류, timeslot 실패,
재시작 횟수, starvation과 최대 service 간격을 고정 배열에 기록한다. 세 공존 예제는 1초마다 BLE와
상대 protocol 통계를 각각 출력해 `M32-COEX-01`의 동시 관측 입력으로 사용한다. 외부 1-wire backend는
MPSL RADIO READY publish를 EGU로 계수한다.

외부 결선은 DAP UART P1.4~P1.7을 피하고 P1.10(P4-8) output과 P1.14(P4-12) grant input을 사용한다.
해당 pin의 LED load를 피하도록 `pwm20`, `led1`, `led3`를 profile에서 비활성화했다. 실제 연결·외장
arbitration 운용은 사용자 후속 `NOT_RUN`이고 내부 공존 결과로 대체하지 않는다.

## 2. exact build 결과

Implementation revision의 NU54DK native target 네 조합이 모두 PASS했다.

| 조합 | RRAM | RAM |
| --- | ---: | ---: |
| BLE + Mesh | 240,892 B | 57,024 B |
| BLE + IEEE 802.15.4 | 134,396 B | 42,612 B |
| BLE + ESB | 123,836 B | 36,148 B |
| BLE + external 1-wire | 137,268 B | 37,164 B |

네 target 모두 Core `7e756311d3ad`, board `fe65f2f0880b`, NCS `99553055607b`, Zephyr
`bf801e4e3d19`, GNU 14.3.0으로 빌드했다. BLE+IEEE 802.15.4 image에서 derived
`CONFIG_NRF_802154_MULTIPROTOCOL_SUPPORT`, BLE+ESB에서 `CONFIG_ESB_MPSL_TIMESLOT`, 외부
profile에서 실제 `mpsl_cx_1wire.c` link를 확인했다. 고정 SDK upstream의 `esb_ptx_ble`도 별도
target probe로 PASS했다. Mesh upstream probe의 trusted-storage link 오류는 upstream sample 자체의
storage 구성 문제였고, 저장소 native BLE+Mesh target과 Arduino example은 같은 controller 조합으로
별도 PASS했다.

Arduino IDE 경로는 다음 공개 예제 4/4를 exact source에서 빌드했다.

| profile | 예제 | RRAM | RAM |
| --- | --- | ---: | ---: |
| `coexistence_ble_mesh` | `BleMeshCoexistence` | 421,056 B | 162,997 B |
| `coexistence_ble_154` | `Ble154Coexistence` | 356,679 B | 137,190 B |
| `coexistence_ble_esb` | `BleEsbCoexistence` | 335,820 B | 129,441 B |
| `external_coexistence` | `RadioCoexistenceOneWire` | 326,104 B | 127,622 B |

각 build context에서 profile, 선택 feature와 핵심 Kconfig를 대조한다. 긴 진단용 smoke 경로에서는
Windows `MAX_PATH` 경계에 걸린 security archive object가 실패했지만, 제품 기본 cache 설계와 같은 짧은
local cache root에서 동일 source를 다시 실행해 통과했다. 이는 source/link 결함이나 비결정적 재시도로
판정하지 않았고 exact PASS는 짧은 cache root 실행만 기록한다.

Host 계약, readiness schema, profile/feature negative, example guidance와 `git diff --check`도 PASS했다.

### 2.1 세 보드 exact HIL 실행 경로

Revision `042cfb32de7d…`에서 BLE+IEEE 802.15.4, BLE+ESB, BLE+Mesh를 각각 DUT·radio/Mesh peer·
BLE peer의 세 image로 분리했다. 세 조합 모두 protocol별 20회 × 200 frame, 즉 4,000 frame을 보내며
중간 BLE disconnect/reconnect와 상대 radio stop/restart를 한 번 수행한다. 손실은 protocol별 80 이하,
corrupt·sequence/hash 오류와 starvation은 0, 최대 service 간격은 500 ms 이하로 판정한다. 잘못된
configuration·payload 길이와 두 번째 radio owner도 별도 negative로 거부한다.

| 조합·역할 | RRAM | RAM |
| --- | ---: | ---: |
| BLE+IEEE 802.15.4 DUT | 222,752 B | 59,692 B |
| BLE+IEEE 802.15.4 radio peer | 87,756 B | 35,520 B |
| BLE+IEEE 802.15.4 BLE peer | 192,292 B | 55,916 B |
| BLE+ESB DUT | 203,464 B | 51,932 B |
| BLE+ESB radio peer | 56,112 B | 21,396 B |
| BLE+ESB BLE peer | 192,292 B | 55,916 B |
| BLE+Mesh DUT | 324,652 B | 80,259 B |
| BLE+Mesh Mesh peer | 319,444 B | 73,199 B |
| BLE+Mesh BLE peer | 192,292 B | 55,916 B |

아홉 native image build와 M32 Host 81/81, `m32_contract.py --check`, C++ 정렬·`git diff --check`를
PASS했다. `m32_coexistence_run.py`는 clean source와 Core/board/NCS/Zephyr revision을 잠그고 세 probe의
register identity를 한 번씩 수집한 뒤 조합별 image를 순차 sector flash한다. Flash와 identity 조회는
CMSIS-DAP v2만 사용하며 `cmsis_dap_v1=False`, hardware reset, `auto_unlock=false` 경계를 유지한다.
증거 ID는 내부 조합 세 개만 각각 `M32-COEX-01:ble_154`, `:ble_esb`, `:ble_mesh`로 기록하며 외부
1-wire 실기를 대신 주장하지 않는다.

## 3. 남은 실기 판정

W09의 IEEE 802.15.4·ESB 단독 송수신은 exact `c817a27e…`에서 각 2,000/2,000으로 PASS했다.
현재 F/G probe는 CMSIS-DAP v2 DP/AP에 응답하지만 E probe의 v2 bulk endpoint는 USB 재연결 전까지
응답하지 않아 세 보드 공존 역할의 identity·image를 모두 확정할 수 없다. Mass erase·recover·unlock과
CMSIS-DAP v1 fallback은 수행하지 않았다.

따라서 다음은 아직 PASS가 아니다.

- 조합별 20회, protocol별 4,000 packet, 허용 손실 80 packet과 최대 service 간격 500 ms
- BLE connection과 Mesh/802.15.4/ESB의 protocol별 sequence/hash·drop·starvation 동시 판정
- double ownership·slot 부족·상대 protocol 종료/재시작·peer loss의 30초 bounded recovery
- STOP 뒤 RADIO·clock·timer·DPPI·buffer 반환과 주요 BLE 기능 회귀
- 외부 1-wire 실제 grant 허용/거부와 RADIO READY event 상관관계

E probe의 CMSIS-DAP v2 접근이 복구되면 clean `042cfb32…` 이후 revision에서 아홉 image를 다시
빌드하고 source/image/role hash를 대조한 뒤 준비된 runner로 세 내부 조합을 순차 실행한다. Sector
방식과 `auto_unlock=false`를 유지한다. W10을 완료 분자에 넣지 않은 채 W11의 독립적인 software
회귀·유한 soak 준비를 계속한다.

## 4. `b91e248a` 최초 exact 실행의 802.15.4 초기화 결함

세 probe의 CMSIS-DAP v2 접근이 정상화된 뒤 clean `b91e248ab7a3…`에서 아홉 image를 다시 빌드하고
최초 exact 실행을 시작했다. 세 보드의 DP/AP, TARGETID, AHB AP, CTRL AP와 APPROTECT 상태는 모두
정상이었지만 첫 `ble_154` DUT가 `READY`에 응답하기 전에 중단됐다. 이 FAIL은 삭제하거나 PASS로
덮어쓰지 않고 `evidence/m32-w10-exact-b91e248a/`에 보존한다.

디버거로 DUT의 PC, PSP exception frame과 SCB fault register를 읽은 결과 CFSR/HFSR는 0이었고,
`nrf_802154_request_swi.c`의 `req_enter()` queue-full assertion이
`nrf_802154_assert_handler()`를 거쳐 `k_panic()`에 진입한 상태였다. W09 단독 802.15.4 HIL과 대조해
W10의 direct API 역할 두 conf에만 `CONFIG_NRF_802154_TEMPERATURE_UPDATE=n`이 빠진 것을 확인했다.
이 구성에서는 application의 `Radio154::begin()`이 `nrf_802154_init()`을 호출하기 전에 POST_KERNEL
온도 work가 즉시 CCA update SWI request를 발행할 수 있다. 따라서 direct API가 초기화 순서를 직접
소유하는 DUT와 radio peer에서 자동 온도 work를 끄고, 실제 세션 시작 뒤 라이브러리가 radio를
초기화하도록 W09와 같은 경계를 적용한다.

이 변경은 NCS·nrfxlib를 수정하거나 assertion을 우회하지 않는다. 최초 FAIL revision의 image를
재사용하지 않고 수정 commit에서 두 image를 포함한 아홉 역할을 모두 다시 빌드한 뒤 exact HIL을
재실행한다. Mass erase, recover, unlock 또는 CMSIS-DAP v1 fallback은 사용하지 않는다.

## 5. `aa39b707` 재실행과 ESB 공존 전송 창 보정

초기화 수정 commit `aa39b7079369…`의 clean source에서 아홉 image를 모두 다시 빌드해 실행했다.
`ble_154`는 BLE·802.15.4 각각 4,000/4,000, 손실·corrupt·starvation 0, BLE 최대 service gap
243 ms, 802.15.4 최대 service gap 18 ms로 PASS했다. BLE reconnect, radio restart와 세 negative도
모두 한 번씩 통과했다. 이 결과와 뒤이어 발생한 FAIL은
`evidence/m32-w10-exact-aa39b707/`에 함께 보존한다.

`ble_esb` radio peer는 4,000개 제출 뒤 ACK 3,910, 최종 ACK 미수신 event 90으로 허용 경계 80을
10개 넘었다. 실패 직후 CMSIS-DAP v2 attach로 RAM을 읽은 결과 DUT는 ESB payload 4,000개를 모두
수신했고 corrupt 0, radio restart 1이었다. Peer의 재시작 뒤 driver 통계도 요청 2,000, ACK 2,000,
TX_FAILED event 51, 총 시도 3,289였다. 즉 payload 손실이나 queue drop이 아니라 BLE가 PRX radio를
점유한 구간에서 600 us 간격의 기본 3회 재전송이 ACK 반환 창을 덮지 못한 경우다. Nordic NCS
`esb_ptx_ble`도 MPSL 공존 송신을 연속 포화시키지 않고 기본 100 ms 간격으로 진행한다.

W10은 4,000개 분모와 600초 제한을 유지하면서 ESB에 최대 15회·1,000 us 재전송 창과 packet 사이
10 ms 간격을 명시한다. 이는 허용 손실을 늘리거나 판정기를 완화하는 변경이 아니다. BLE·ESB 양쪽에
유한 service 기회를 주고, 2 Mbps·hardware ACK·중간 stop/restart·기존 80개 손실 상한을 그대로
재검증한다. 변경 revision에서 아홉 image를 다시 빌드하고 세 조합 전체를 처음부터 재실행한다.

## 6. `1d15401f` 재실행과 ESB 종료 순서 교정

전송 창 보정 commit `1d15401f9c85…`의 clean source에서 아홉 image를 다시 빌드해 실행했다.
`ble_154`는 BLE·802.15.4 각각 4,000/4,000, 손실·corrupt·starvation 0, BLE 최대 gap
200 ms, radio 최대 gap 16 ms와 재연결·재시작·negative·STOP을 모두 PASS했다. `ble_esb`도
BLE·ESB 각각 4,000/4,000, 손실·corrupt·starvation 0, BLE 최대 gap 151 ms, ESB 최대 gap
24 ms로 전송 창 문제가 해소됐다. 다만 DUT의 마지막 `STOPPED cleanup=fail`로 runner가 종료했으며,
이 FAIL과 미실행 `ble_mesh`를
`evidence/m32-w10-exact-1d15401f/`에 그대로 보존한다.

실패 직후 CMSIS-DAP v2 attach로 DUT의 ESB backend 64 byte를 읽었다. PRX는 재시작 후
2,000개를 모두 수신했고 duplicate·hash 오류·drop·timeslot 실패는 0이었다. 그러나
`error=driver_error`, `driver_error=-16(-EBUSY)`, `started=true`, `stops=0`이었다. 애플리케이션이
`BLESerial.end()`로 disconnect를 먼저 시작한 뒤 `NUCODEEsb.cancel()`을 호출해 `esb_suspend()`가
`-EBUSY`를 반환했고, 논리 AND의 short-circuit로 `NUCODEEsb.stop()`은 호출되지 않았다.

직접 IEEE 802.15.4·ESB DUT는 두 번째 radio를 먼저 cancel/stop한 뒤 BLE를 종료하도록 순서를
고정한다. 정리 실패 판정은 완화하지 않았고 Host 계약에 radio stop이 BLE end보다 앞서는지
고정했다. 새 clean revision에서 아홉 image와 세 조합 전체를 처음부터 다시 실행하기 전에는
W10을 PASS로 세지 않는다.

## 7. `2dbc281d` 재실행과 restart 경계 duplicate 교정

종료 순서 수정 commit `2dbc281d0c9f…`의 clean source에서 아홉 image를 새로 빌드해
전체를 재실행했다. `ble_154`는 BLE·802.15.4 각각 4,000/4,000, 손실·corrupt·starvation 0,
최대 gap 151/21 ms, 재시작·negative·세 역할 STOP을 모두 PASS했다. `ble_esb` radio peer도
4,000/4,000 ACK·실패 0, BLE peer도 4,000·reconnect 1·write 실패 0을 달성했다. 다만 DUT가
`radio_received=4001`에서 엄격한 `result_boundary`로 FAIL했고 Mesh는 미실행이다. 원본은
`evidence/m32-w10-exact-2dbc281d/`에 보존한다.

실패 직후 CMSIS-DAP v2 attach로 DUT를 읽은 결과 애플리케이션은 BLE 4,000, ESB 4,001,
corrupt 0, radio restart 1이었다. restart 뒤 ESB backend은 2,001개를 수신했고 driver 자체의
duplicate·hash 오류·drop·timeslot 실패는 모두 0, 마지막 sequence는 3,999였다. Peer는 정확히
4,000개를 제출하고 4,000 ACK를 받았다. 이 결과는 PRX stop/restart와 PTX hardware ACK 재시도가
겹치면 restart 직전의 마지막 payload가 새 PRX session에 한 번 더 전달되지만, backend의
`last_sequence`가 `begin()`에서 초기화되어 session 간 duplicate로 표시하지 못한 경계와 일치한다.

HIL DUT는 새 전송을 분모에 더하기 전에 논리 session의 마지막 sequence를 별도로 유지하고,
driver 재시작 전·후에 연속한 동일 sequence만 duplicate로 제외한다. 서로 다른 sequence,
hash/payload 오류, 손실, service gap과 4,000 분모 판정은 완화하지 않는다. 새 clean revision의
아홉 image와 세 조합 전체를 다시 실행하기 전에는 W10을 PASS로 세지 않는다.

## 8. `6d40e926` 전체 재실행과 Mesh settings 호환 교정

restart 경계 교정 commit `6d40e9261a5b…`의 clean source에서 BLE+802.15.4와 BLE+ESB는 각각
BLE·상대 radio 4,000/4,000, 손실·corrupt·starvation 0, 재시작 1회와 세 역할 cleanup을 PASS했다.
BLE+Mesh는 이전 W08 image가 저장한 `bt/mesh/SSeq`를 읽는 중 fault가 발생했다. 디버거의 PSP
exception frame과 settings call stack을 대조한 결과, W10 profile에서
`CONFIG_BT_MESH_PROXY_SOLICITATION`이 비활성화되어 해당 key handler가 빠졌고 commit 전용
`bt/mesh` 상위 handler의 null `h_set`이 선택된 것이 원인이었다.

Mesh facade는 표준 `settings_load()`의 load·commit 원자성을 유지하면서 비활성 선택 기능의
`bt/mesh/SSeq`와 `bt/mesh/SRPL`만 소비하는 정적 호환 handler를 등록한다. BLE facade가 같은 image에
있으면 settings one-shot 결과를 공유해 두 번째 전체 load를 막는다. 직접 subtree load와 저장 key
삭제 방식은 각각 commit 순서 분리와 ZMS name/value 불일치를 만들었으므로 최종 구현에서 제거했다.
기존 실패 evidence는 `m32-w06-*6d40e926*`, `m32-w10-mesh-*6d40e926*`에 삭제하지 않고 보존한다.

진단 중 생긴 ZMS 불일치를 복구할 때는 DTS의 `storage_partition`을 다시 확인하고 DUT와 Mesh peer의
`0x174000..0x17cfff`, 정확히 36,864 byte만 `0xff`로 기록했다. CMSIS-DAP v2, 500 kHz,
`auto_unlock=false`를 사용했고 전 범위 readback을 확인했다. Application·MCUboot·slot 영역과 세 번째
BLE peer 저장소는 건드리지 않았으며 mass erase·recover·unlock은 수행하지 않았다.

## 9. local provisioner 구성과 CDB partial restore 복구

Mesh Config Client는 자기 자신의 access message를 loopback하지 않으므로 local provisioner의 AppKey
등록과 model bind를 원격 Config Client 요청으로 처리하면 timeout이 발생한다. Facade는 local address에
한해 `bt_mesh_app_key_add()`와 model의 고정 key slot을 직접 사용하고, 원격 node에는 기존 Config
Client 경로를 유지한다. CDB valid flag는 남았지만 primary subnet이 없는 partial restore도
`bt_mesh_cdb_subnet_get(BT_MESH_NET_PRIMARY)`로 확인한 뒤 CDB만 재생성한다.

HIL 구성 순서는 원격 node AppKey·bind를 먼저 완료하고 local client를 구성하도록 고정했다. PB-ADV
link close 뒤 1,500 ms settle과 configuration timeout 최대 3회도 기록한다. 이 변경으로 세 역할
READY·CLEAR·BEGIN, provisioning, remote/local bind와 실제 Mesh traffic 진입을 확인했다.

## 10. acknowledged Status 유실 복구와 개발 HIL PASS

첫 4,000-packet 개발 실행은 BLE가 완주했지만 Mesh acknowledged Status 한 건이 유실된 뒤 peer가
1,433에서 무기한 pending 상태가 되어 session timeout으로 끝났다. Generic OnOff의 같은 transaction을
중복 적용하지 않도록 facade에 명시적 transaction ID overload를 추가하고, HIL은 Status가 없을 때
같은 TID를 packet당 최대 3회만 재전송한다. 전체 acknowledgement 재전송도 허용 손실 경계 80 이하로
판정한다.

최초 1,000 ms timeout에서는 Mesh 4,000/4,000과 재전송 3회를 달성했지만, 디버거로 읽은 DUT
통계가 Mesh 최대 gap 1,061 ms·starvation 3을 보여 500 ms 공존 경계를 위반했다. timeout을 300 ms로
낮춘 최종 개발 실행 `evidence/m32-w10-mesh-gap-dev-6d40e926.*`은 다음을 기록했다.

| 역할 | 결과 |
| --- | --- |
| Mesh peer | sent/acknowledged `4,000/4,000`, restart `1`, failure `0`, config retry `0`, ack retry `1` |
| BLE peer | sent `4,000`, reconnect `1`, write failure `0` |
| DUT | BLE/Mesh `4,000/4,000`, loss·corrupt·starvation `0`, restart 각 `1`, gap `200/348 ms` |
| 종료 | 세 역할 `STOPPED cleanup=pass` |

이 결과는 dirty source의 `PASS_CANDIDATE`이므로 W10 완료 증거가 아니다. Host 21/21,
`m32_contract.py --check`, 두 Mesh target build와 `git diff --check`는 PASS했다. 수정 checkpoint를
commit·push한 뒤 clean SHA에서 아홉 image를 모두 다시 빌드하고 세 조합 전체 exact HIL을 처음부터
재실행한다.

## 11. clean `512b027a` 전체 exact PASS와 W10 완료

안정화 checkpoint `512b027a6b1b9966ef70ead8c6bc07d7a16522d5`를 push한 뒤 dirty 변경이 없는
상태에서 W10 아홉 역할을 NCS v3.4.0·Zephyr `bf801e4e3d19…`·board `fe65f2f0880b…`·toolchain
`dcbdc366a1`로 다시 빌드했다. Twister 9/9는 warning·failure·error 없이 PASS했고 각 build record의
Core revision은 `512b027a6b1b…`로 일치했다.

세 NU54DK의 probe identity hash와 COM mapping을 다시 확인한 뒤 BLE+IEEE 802.15.4, BLE+ESB,
BLE+Mesh 순서로 전체 exact HIL을 실행했다. 세 조합 모두 CMSIS-DAP v2, sector flash, hardware reset,
`auto_unlock=false`를 사용했고 mass erase·recover·unlock과 V1 fallback은 없었다.

| 조합 | DUT BLE/radio 수신 | peer 송신/ACK | gap BLE/radio | 복구·negative·종료 |
| --- | ---: | ---: | ---: | --- |
| BLE+IEEE 802.15.4 | `4,000/4,000` | `4,000/4,000` | `151/20 ms` | reconnect·restart 각 1, 세 negative·STOP PASS |
| BLE+ESB | `4,000/4,000` | `4,000/4,000` | `151/24 ms` | reconnect·restart 각 1, 세 negative·STOP PASS |
| BLE+Mesh | `4,000/4,000` | `4,000/4,000` | `151/124 ms` | config/ack retry 0, reconnect·restart 각 1, STOP PASS |

모든 조합의 loss·corrupt·starvation·peer failure·BLE write failure는 0이고, 세 조합의 아홉 역할이
모두 `STOPPED cleanup=pass`를 기록했다. Exact 원본은
`evidence/m32-w10-exact-512b027a/m32-coexistence.json`과 transcript이며, 요약 원장은 같은 폴더의
`w10-closure-audit.json`이다. `M32-COEX-01`은 내부 세 조합에 대해서만 PASS로 승격한다.
외부 1-wire arbitration 실제 결선과 외부 peer 상호운용은 사용자 후속 `NOT_RUN`이며 W10 개발
완료나 현재 v0.6.0 M32 진행을 차단하지 않는다.
