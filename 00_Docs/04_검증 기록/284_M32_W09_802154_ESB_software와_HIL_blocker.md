# M32-W09 IEEE 802.15.4·ESB software와 exact HIL 완료

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W09` IEEE 802.15.4 최소 TX/RX와 ESB PTX/PRX |
| 구현 revision | `82361413bc0377871fffd74f4a23eca5a98a2abb` |
| exact HIL revision | `c817a27ed765641bdf41e4e386664a8aa8c173f9` |
| 고정 기준 | NCS `v3.4.0`, Zephyr `bf801e4e3d19…`, board package `fe65f2f0880b…` |
| software/build 판정 | **PASS** |
| exact 실기 HIL | **PASS — CMSIS-DAP v2, 두 protocol 각 2,000/2,000** |
| W09 작업 판정 | **완료** |

## 1. 구현 결과

단독 radio용 `NUCODE_Radio_IEEE802154`, `NUCODE_Radio_ESB` library와 각각 전용인
`radio_ieee802154`, `radio_esb` profile을 추가했다. 두 공개 header는 Zephyr·Nordic SDK type을
노출하지 않고 고정 크기 packet, sequence, FNV-1a payload hash, ACK/실패/재전송/중복/drop 통계와
bounded `cancel()`·`stop()`을 제공한다.

IEEE 802.15.4 경로는 고정 NCS의 direct nRF 802.15.4 driver를 사용한다. short PAN/address와 ACK
요청 data frame, channel 11~26, CCA, 최대 8회 재시도와 80 byte payload를 경계로 두었다. callback에서
ACK와 RX raw buffer를 반환하고 수신 데이터는 고정 `k_msgq`로 복사한다. ESB 경로는 DPL, hardware
ACK/retry, 1/2 Mbps, channel 0~100, 최대 15회 재전송, 8개 pipe와 20 byte application payload를
경계로 두고 TX/RX FIFO를 suspend·flush·disable한다.

두 profile은 같은 image에서 서로를 선택할 수 없고 feature conflict도 `radio-owner`로 fail-closed한다.
IEEE 802.15.4 image는 nRF 802.15.4 driver가 RADIO와 MPSL clock·GRTC·DPPI 경로를 소유하며, ESB
image는 ESB가 RADIO·TIMER10·DPPI와 clock을 소유한다. ESB standalone은 MPSL timeslot을 켜지 않고
FEM-only 기반만 사용한다. 따라서 이번 단계는 protocol별 전용 image이고 BLE/Mesh와의 scheduler·
timeslot 공존 주장은 W10 판정 전에는 하지 않는다.

## 2. 예제·build 결과

Exact implementation source에서 다음 Arduino 역할 예제 **4/4 PASS**를 확인했다.

| profile | 역할 예제 | 최대 RRAM | 최대 RAM |
| --- | --- | ---: | ---: |
| `radio_ieee802154` | `Radio154Transmitter`, `Radio154Receiver` | 97,166 B | 38,748 B |
| `radio_esb` | `EsbPtx`, `EsbPrx` | 66,640 B | 27,876 B |

각 build context에서 권장 profile과 `nucode.radio.ieee802154` 또는 `nucode.radio.esb` feature,
해당 Kconfig symbol을 대조했다. 첫 fresh Arduino smoke에서 Windows filesystem의 archive 입력 object가
즉시 보이지 않는 일회성 build-tool 오류가 발생했다. 동일 exact source를 한 번 다시 실행해 통과했고,
이후 나머지 세 역할도 같은 작업자 상한 4에서 통과했다. 기능 source·link 오류는 없었다.

NU54DK native target 결과는 다음과 같다.

| target | RRAM | RAM |
| --- | ---: | ---: |
| `tests/zephyr/m32_radio154_contract` | 82,652 B | 32,240 B |
| `tests/zephyr/m32_esb_contract` | 51,024 B | 17,608 B |

두 build record의 Core revision은 `82361413bc03`, board `fe65f2f0880b`, NCS `99553055607b`,
Zephyr `bf801e4e3d19`, compiler는 GNU 14.3.0이다. Host·생성 계약의 관련 78개 검사는 77 PASS,
환경 의존 1개 skip이고 example guidance 183개가 일치한다. `git diff --check`도 PASS했다.

## 3. exact HIL 결과

Exact source가 clean인 `c817a27e…`에서 F/G 두 보드의 CMSIS-DAP v2 interface, SHA-256 probe
identity, VCOM, DP IDCODE·TARGETID, AHB-AP·CTRL-AP IDR와 APPROTECT 상태를 실행 직전에 대조했다.
네 역할 image는 `auto_unlock=false`, sector erase, hardware reset으로만 기록했다. Mass erase·recover·
unlock과 CMSIS-DAP v1 fallback은 사용하지 않았다.

| 시험 | 송신·ACK | 수신 unique | loss / corrupt / drop | 최대 지연 | negative / STOP |
| --- | ---: | ---: | ---: | ---: | --- |
| `M32-154-01:primary` | 2,000/2,000 | 2,000/2,000 | 0 / 0 / 0 | 12 ms | channel·length 거부, 2/2 |
| `M32-ESB-01:primary` | 2,000/2,000 | 2,000/2,000 | 0 / 0 / 0 | 4 ms | rate·length 거부, 2/2 |

각 protocol은 20회 × 100 packet으로 유한 실행했다. IEEE 802.15.4는 240회 재시도 뒤에도 최종 ACK
손실이 없었고, ESB는 hardware ACK 전까지 2,951회 시도와 중간 실패 76회를 관측했지만 application
분모는 2,000/2,000이었다. 초기 개발 실행에서 nRF 802.15.4 temperature update 초기화 순서와
이미 idle인 ESB의 `-EALREADY` cleanup 경계를 발견해 fail evidence를 보존했고, 각각 configuration과
idempotent cancel/STOP 처리로 교정한 뒤 exact source에서 재검증했다.

원본은 [`m32-radio-standalone.json`](<evidence/m32-w09-exact-c817a27e/m32-radio-standalone.json>),
serial transcript와 [`w09-closure-audit.json`](<evidence/m32-w09-exact-c817a27e/w09-closure-audit.json>)에
보존한다. 외부 Thread/Zigbee peer와 상용 ESB peer 상호운용은 사용자 후속 `NOT_RUN`이며 두
board-only 시험의 완료 판정을 바꾸지 않는다. BLE/Mesh와의 공존은 W10에서 별도로 판정한다.

## 4. W08 마감 후 최신 clean HEAD 재확인

W08 마감 commit `115d039fa8bf98d379f2ece8a07d1fec7192acef`에서 네 역할 image를 모두
다시 빌드하고 두 NU54DK로 단독 radio HIL을 재실행했다. 현재 build의 IEEE 802.15.4
transmitter/receiver image는 각각 90,112 byte, ESB PTX/PRX image는 각각 57,344 byte를 exact sector
flash했다. CMSIS-DAP v2 DP/AP identity와 APPROTECT 0을 다시 확인했으며 mass erase·unlock·recover는
사용하지 않았다.

IEEE 802.15.4와 ESB는 각각 20회 × 100 packet, 2,000/2,000 ACK와 2,000/2,000 unique를 PASS했다.
Loss·corrupt·drop은 모두 0이고 최대 지연은 IEEE 802.15.4 7 ms, ESB 2 ms였다. Channel/rate와
length negative, 네 역할 STOP/cleanup도 다시 PASS했다. 최신 원본은
[`m32-radio-standalone.json`](<evidence/m32-w09-reconfirm-115d039f/m32-radio-standalone.json>)과
[`m32-radio-standalone.transcript.log`](<evidence/m32-w09-reconfirm-115d039f/m32-radio-standalone.transcript.log>),
[`w09-reconfirm-audit.json`](<evidence/m32-w09-reconfirm-115d039f/w09-reconfirm-audit.json>)이다.
Transcript SHA-256은 `df7a395b8b3095927efa5f4e35dc5afcc8d110ae0811a91922de6f7a5b93805d`다.
기존 `c817a27e…` PASS도 최초 W09 완료 원본으로 보존한다.
