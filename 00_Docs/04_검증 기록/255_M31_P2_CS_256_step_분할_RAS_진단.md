# 255 — M31 P2 CS 256-step·분할 RAS 실기 진단

## 판정

고정 NCS `v3.4.0`·Zephyr `4.4.0`, 현재 `M31-MEM-OPT`의 `adaptive`
CS initiator와 기존 reflector를 두 exact NU54DK에서 실행했다. 실행 직전
probe UID·app/aux COM과 HEX SHA-256을 대조했고, 세 번째 보드는 접근하지
않았다. 자동 unlock·mass erase 없이 지정 보드만 sector flash했다. 각 실행은
reset-halt-drain-resume으로 시작해 양측 `P2_STOP`을 확인했다.
기준 Core HEAD는 `74617414c1e2040c3c431b9e7cce6e136d653bd3`,
board submodule은 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`다.

이전 [252번 진단](252_M31_P2_CS_장절차_반복계수_경계_진단.md)은
`main_mode_repetition`과 절차 길이를 늘려도 93~98 step에 머물렀다.
이번에는 고정 Zephyr API의 `channel_map_repetition`을 진단 image에서만
1→2 또는 1→3으로 바꾸고 장절차 값(`1000`, `10000/75000` μs)을 적용했다.
제품 소스는 빌드 후 기본값(`1`, `128`, `16000/16000` μs)으로 되돌렸다.
두 진단 빌드 시점은 `source_clean=false`이며 제품 기본 설정의 변경이 아니다.

| 실행 | 실제 수신 결과 | 판정·원본 |
| --- | --- | --- |
| 채널맵 반복 2, 10 raw | local/peer 189~194 step, counter gap 0, 양측 STOP | **진단 범위 PASS**. [원본](evidence/m31-p2-native-comparison-2cf92933/cs-chmap-repeat2-10.json) |
| 채널맵 반복 3, 10 raw | local/peer 모두 256 step, peer RAS 2,367~2,382 B, ATT MTU 65 B, gap 0, 양측 STOP | **256-step·분할 재조립 국소 PASS**. [원본](evidence/m31-p2-native-comparison-2cf92933/cs-chmap-repeat3-diag-10.json) |
| 같은 반복 3, 100 raw | 100개 모두 local/peer 256 step, peer RAS 2,367~2,388 B, 45→47 counter gap 1, 양측 STOP | **연속성 HOLD**. [원본](evidence/m31-p2-native-comparison-2cf92933/cs-chmap-repeat3-diag-100.json) |
| 기본 image 복구, 100 raw | raw 100/100, gap 0, 양측 STOP | **기본 image 복구 PASS**. [원본](evidence/m31-p2-native-comparison-2cf92933/cs-default-recovery-after-chmap-100.json) |

반복 2 원본의 `P2_READY` 앞에는 이전 UART 수명의 `CS_RAW counter=11`
한 줄이 남아 있다. 실행기는 READY 이후의 새 10건만 판정했다.

반복 3의 시험용 `CS_DIAG`는 RAS parser 직전 `peer_steps.len`, 로컬 step
byte 수와 `bt_gatt_get_mtu()`를 같은 counter로 출력했다. 고정 SDK의
`ras_rrsp.c`는 한 notification의 RAS payload를 `ATT_MTU-4` 이하로
제한하고, `ras_rreq.c`는 segment header의 순서·first/last를 확인해
`peer_steps`에 재조립한다. 이번 MTU 65 B의 한 notification 한계는 61 B다.
완성된 peer RAS가 최소 2,367 B이므로 **한 notification으로는 불가능**하고,
그 counter의 다중 segment 전송·재조립 경로가 실행됐다고 판정한다.
byte 수로부터 최소 39개 segment가 필요하며, 2,379 B를 넘는 결과는
최소 40개가 필요하다. 실제 segment callback 개수는 별도로 계측하지
않았으므로 그 숫자를 실측값으로 쓰지 않는다. 반복 3 image의 `CS_RAW`에는
실제 양쪽 256 step이 있고, SDK의 256-step
예약 상한만을 사용량으로 오인한 결과가 아니다. 거리값은 비보정 RTT
추정이며 거리 정확도의 근거가 아니다.

반복 2 initiator HEX SHA-256은
`6d8fe14c041b47b273323aa03260e33634c8ef78d7a482b047429a020bb437ed`,
반복 3 진단 HEX는
`35600bd52de57428d37256cd12e1890fe0961c871b34ec62b4e86336b0691883`다.
두 image의 정적 FLASH/RAM은 각각 `243,720/80,458 B`,
`243,892/80,458 B`다. 반복 3의 `printk` 계측으로 FLASH·타이밍이
기본 image와 다르다. reflector HEX는 기존
`1efe4958284c05bc91a3695029d5f0e5d4eb1ad513eb0ac19148972f8d3a8ba5`,
복구 initiator는 기존
`989b19432357e0f678de8426827b7ddfe1d4424b90c2c557ace599a263a2e6e2`다.

## 100건 부하의 동적 메모리와 잔여

반복 3의 100건 종료 high-water는 initiator BT RX WQ
`1,520/3,200 B`, BT TX `744/3,200 B`, BT LW WQ `936/2,104 B`,
main `1,048/8,192 B`; reflector BT RX WQ `1,232/3,200 B`,
RAS RRSP WQ `428/1,024 B`, BT LW WQ `1,168/2,104 B`,
MPSL Work `760/1,024 B`였다. 양쪽 libc malloc 관찰 peak는 0 B,
initiator Zephyr `k_heap` peak는 264 B다. reflector MPSL Work의 관찰
여유 264 B와 아직 계측하지 않은 오류 경로를 고려하면 stack·heap·RAS
buffer·controller pool을 축소할 근거가 없다.

최대 256-step과 분할 RAS의 **정상 수신 경로**는 이번 진단 범위에서
처음 확인됐다. 그러나 100건의 gap 1은 [245번 장기 누락](245_M31_P2_CS_장기_연속성_진단.md)의
정상 callback 뒤 누락·RF abort·단일 버퍼/RAS 도착 순서 문제를 해결하지
않는다. 실행기의 `HOLD`는 이 한 건의 원인이 분류되지 않았다는 뜻이지
모든 RF 시험에 gap 0을 요구하는 제품 인수 기준은 아니다. 같은 보드의
[Nordic native 비교](250_M31_P2_native_CS_비교와_DF_재진단.md)에서도
1,000 유효 RAS당 gap 4·7건이 있었다. 이 image에서 segment 손실·재전송,
peer 이탈·재연결 뒤 최대 절차의 메모리/연속성, 256-step reflector 쪽의
모든 오류 경로도
미검증이다. 따라서 **CS 전체와 P2 전체는 계속 HOLD**다.

## 문서·Host 회귀와 제출 범위

제품 C/C++와 고정 SDK·board submodule은 변경하지 않았다. 진단 설정을
되돌린 제품 initiator source의 Git blob은 기준 HEAD와 동일하다.
저장소의 Markdown 411개를 strict UTF-8로 읽고 로컬 링크를 검사해
오류 0건, 공개 library 16개·예제 113개 구조 감사도 문제 0건이었다.
NCS Python 환경의 전체 Host suite는 **1,495건, skip 2, 오류 0**으로
통과했다. 먼저 시스템 Python으로 실행한 suite는 `pyserial` 부재로
HIL 모듈 네 개를 import하지 못해 1,487건 중 오류 4건이었다. 이를
제품 회귀로 분류하거나 통과로 계산하지 않았고, 동일 source를 필요한
의존성이 있는 NCS Python으로 전체 재실행한 결과만 최종 Host 판정으로
사용했다. 기존 실패 JSON과 이번 100건 HOLD 원본은 그대로 보존한다.
