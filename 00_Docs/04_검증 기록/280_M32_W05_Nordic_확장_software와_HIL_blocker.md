# M32-W05 Nordic 확장 software/build와 exact HIL 완료

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W05` Nordic LLPM·QoS·time sync·event trigger·radio notification |
| 최초 구현 revision | `85da61226c770ead63ef97512b76cbb3c2bc338e` |
| exact HIL revision | `f813356c783cf1d4a5e74f48156c6b4304d4791d` |
| 고정 기준 | NCS `v3.4.0`, Zephyr `bf801e4e3d19…`, board package `fe65f2f0880b…` |
| software/build 판정 | **PASS** |
| exact 실기 HIL | **PASS — CMSIS-DAP v2, 두 역할·세 시험군** |
| Flushable ACL | **HOLD — controller experimental, 고정 Host TX 경로 없음** |
| W05 작업 판정 | **완료** |

## 1. 구현과 교정 결과

`BLENordic`은 LLPM mode와 1~7 ms interval, QoS connection-event/channel-survey, connection
anchor report, connection/advertising/scanner/initiator event-start task와 connection radio
notification을 공개한다. Vendor HCI callback은 사용자 함수를 직접 호출하지 않고 종류별 bounded
queue에 generation과 함께 복사하며, QoS·survey·anchor callback은 `BLEDevice.poll()` 문맥에서 실행된다.

두 보드 exact HIL을 만드는 과정에서 LLPM mode를 현재 link에만 적용하던 경계와 controller가
보고하는 vendor interval encoding을 그대로 마이크로초로 해석하던 결함을 확인했다. Image-wide
LLPM mode를 다음 central 연결의 초기 interval `0x0d01`에 반영하고 `0x0d01`~`0x0d07`을 실제
1,000~7,000 us로 정규화했다. Radio notification도 이 정규화된 interval로 예약한다. Host mock은
central connect parameter와 1,000 us 변환을 직접 검증한다.

LE Flushable ACL Data는 controller experimental Kconfig와 적용성 조회까지 빌드되지만 고정 Zephyr
Host에 flushable LE ACL transmit path가 없다. 실제 보드에서도 controller=true,
host-transmit=false, usable=false를 확인했다. 전송 성공 facade를 만들지 않았고 `M32-ACL-01`은
기능 PASS가 아닌 명시적 `HOLD`다.

## 2. software/build 결과

최초 구현 source에서 공개 Arduino 예제 8/8, Nordic target contract와 관련 Host 회귀가 PASS했다.
Exact source `f813356c…`에서는 중앙·주변 역할 image를 clean build했고 결과는 다음과 같다.

| 역할 | RRAM | RAM |
| --- | ---: | ---: |
| central | 208,072 B | 55,760 B |
| peripheral | 208,168 B | 55,872 B |

W05 관련 M32 Host 63개 검사, Python compile, readiness 생성 계약과
`m32_contract.py --check`를 통과했다. 최초 target contract의 53,380/184,132 B와 exact 역할
image의 크기는 설정·HIL protocol이 달라 직접 비교하지 않는다.

## 3. exact HIL 결과

Clean source `f813356c…`에서 F/G 두 보드의 CMSIS-DAP v2 interface, SHA-256 probe identity,
VCOM, DP IDCODE·TARGETID, AHB-AP·CTRL-AP IDR와 APPROTECT 상태를 실행 직전에 대조했다. 두 image는
`auto_unlock=false`, sector erase, hardware reset으로만 기록했다. Mass erase·recover·unlock과
CMSIS-DAP v1 fallback은 사용하지 않았다.

| 역할 | QoS | Survey | Anchor | Event | Radio prepare | LLPM | 최대 anchor gap | 최대 event gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| central | 200 | 20 | 1,000 | 200 | 200 | 1,000 us | 1,000 us | 1 ms |
| peripheral | 200 | 20 | 1,000 | 200 | 200 | 1,000 us | 3,999 us | 1 ms |

`M32-NORDIC-01:primary`, `M32-SYNC-01:primary`, `M32-EVENT-01:primary`은 20회 유한 실행으로
PASS했다. Queue overflow 관측, 잘못된 LLPM/survey/task 거부, 중복 event reservation 제한,
16-bit projection wrap, disable 뒤 late callback 0과 양 역할 STOP을 확인했다. Callback은 지정된
poll/work 문맥에서 실행됐고 5,000 us anchor·5 ms event 상한을 만족했다.

원본은 [`m32-nordic-exact.json`](<evidence/m32-w05-exact-f813356c/m32-nordic-exact.json>),
serial transcript와 [`w05-closure-audit.json`](<evidence/m32-w05-exact-f813356c/w05-closure-audit.json>)에
보존한다. 앞선 개발 실패·교정 시도도 `m32-w05-development-b464c1b3`에 덮어쓰지 않고 보존했다.
외부 peer 상호운용은 사용자 후속 `NOT_RUN`이며 보드 기반 W05 완료 판정을 바꾸지 않는다.
