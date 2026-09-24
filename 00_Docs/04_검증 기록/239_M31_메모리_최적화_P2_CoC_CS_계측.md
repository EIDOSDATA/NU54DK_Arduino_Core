# 239 — M31 메모리 최적화 P2: CoC PASS, CS 계측·연속성 HOLD

## 판정 경계

두 exact NU54DK에서 계측용 `adaptive` image를 실행했다. 공개 예제의 역할과
전송 경로를 보존하되 thread analyzer·heap runtime stats를 추가한 image다.
플래시는 probe UID/COM을 확인한 뒤 `auto_unlock=false`, sector erase만 사용했고
자동 unlock·mass erase·recover는 사용하지 않았다. image·익명 probe hash와
원본 UART는 아래 JSON에 있다. 정적 `.data + .bss`와 실행 중 high-water를
합산하거나 계측 image를 비계측 제품 image와 동일하게 취급하지 않는다.

| 역할·부하 | 결과 | 원본 |
| --- | --- | --- |
| LE CoC client/server, 두 채널 × 512 B, echo 100건, 양측 STOP | **PASS**. 두 채널 연결, remote MTU 512, echo count 1~100·내용 일치, client/server STOP. | [CoC 실기](evidence/m31-p2-coc-8f5f7cf8/coc-two-channel-512.json) |
| CS RAS initiator/reflector, 보안 연결·raw 100건·양측 STOP | **재실행 국소 PASS / 간헐 누락 원인 HOLD**. 최신 실행에서 completed/raw 100, counter gap 0, 양측 STOP. 앞선 counter 누락을 없었던 일로 취급하지 않음. | [CS 재실행](evidence/m31-p2-cs-8f5f7cf8/cs-100-raw-followup.json) · [앞선 누락](evidence/m31-p2-cs-8f5f7cf8/cs-100-raw-measured.json) |

CS 첫 계측은 flash 이전 UART에 남은 raw를 새 부팅 결과로 집계한 러너 오류로
[FAIL](evidence/m31-p2-cs-8f5f7cf8/cs-100-raw.json)이었다. 부팅 기준을
고친 뒤에도 [실제 counter 80→83 누락](evidence/m31-p2-cs-8f5f7cf8/cs-100-raw-retry.json)이
확인됐다. 주기적 메모리 출력이 시점에 영향을 줄 가능성을 제거하려고 CS의
긴 telemetry는 절차 정지 후 한 번만 출력했으나, 마지막 실행에서도 6→8
누락이 있었다. 원인을 계측 출력 하나로 단정하지 않는다. `RasInitiator.completed()`
100과 UART raw 100은 일치했으므로, 최종 누락은 UART 수신 줄 자체의 손실로
설명되지 않는다. controller/Host의 procedure abort, RAS 재조립 또는 별도
링크 조건 중 어디서 빠졌는지는 추가 분류가 필요하다.

동일 계측 HEX를 두 exact 보드에 다시 기록한 [후속 원본](evidence/m31-p2-cs-8f5f7cf8/cs-100-raw-followup.json)은
completed 100, raw 100, counter gap 0, initiator/reflector STOP으로 **이번 실행 PASS**다.
반복 가능한 정상 경로는 확인했으나 과거 누락의 발생 조건·복구 안전성은 아직
미확인이다. 따라서 간헐 누락 원인을 해결했다고 선언하지 않는다.

## 관찰 high-water

같은 계측 설정으로 생성한 역할별 `nu54-build.json`의 정적 예약량은 다음과 같다.
FLASH 분모는 loaderless code partition 1,490,944 B, RAM 분모는 262,144 B다.
RAM 사용량은 `.data + .bss`이며 아래 stack/heap 예약과 `sdc_mempool`을
이미 포함한다. 서로 다른 기능·설정의 이미지이므로 행 간 차이를 곧바로
라이브러리 하나의 절감량으로 해석하지 않는다.

| 역할 | FLASH 사용 B | RAM 예약 B | `sdc_mempool` B |
| --- | ---: | ---: | ---: |
| GATT peripheral | 141,092 | 65,395 | 2,828 |
| GATT central | 155,676 | 69,807 | 2,858 |
| CoC client | 216,552 | 82,625 | 5,618 |
| CoC server | 215,888 | 82,181 | 5,618 |
| CS initiator | 243,708 | 80,458 | 7,672 |
| CS reflector | 225,148 | 63,380 | 6,732 |

이 값은 P2 계측 image의 linker 사용량이며 비계측 제품 image나 동등 기능
native 대비 절감률은 아니다. 특히 SDC pool의 예약 크기와 내부 실제
high-water는 별개다.

아래는 각 raw JSON의 `P2_STACK`에서 관찰한 최고 `used/reserved` byte다.
CS는 100개 결과 뒤 정지 시점에 읽은 값이며, CoC는 전송 중·정지 시점을
포함한다. 관찰되지 않은 error path·장기 fragmentation에 대한 보증은 아니다.

| Thread/ISR | CoC client | CoC server | CS initiator | CS reflector |
| --- | ---: | ---: | ---: | ---: |
| BT RX WQ | 960/3200 | 400/3200 | 1464/3200 | 1248/3200 |
| BT TX processor | 548/904 | 404/904 | 744/3200 | 404/904 |
| BT LW WQ | 936/2104 | 936/2104 | 936/2104 | 1168/2104 |
| BT RAS RRSP WQ | — | — | — | 428/1024 |
| BT GATT DM WQ | — | — | 352/1304 | — |
| sysworkq | 320/4096 | 288/4096 | 288/4096 | 448/4096 |
| MPSL Work | 332/1024 | 296/1024 | 504/1024 | 760/1024 |
| main | 800/8192 | 964/8192 | 1048/8192 | 1032/8192 |
| ISR0 | 432/2048 | 500/2048 | 448/2048 | 444/2048 |

CoC의 libc malloc과 관찰된 Zephyr `k_heap` peak는 두 역할 모두 0 B였다.
CS initiator의 관찰 `k_heap` peak는 264 B(정지 후 free 516 B), malloc
peak는 0 B였다. CS reflector에서는 계측된 별도 `k_heap` 항목이 없고
malloc peak 0 B였다. 이 통계에 SDC controller 내부 pool은 포함되지
않는다. 결과가 0이어도 pool 삭제·축소 근거가 아니다.

## 실행 중 수정·남은 작업

CoC-only adaptive image에서 `BLEDevice.end()`를 실제로 호출하자
미선택 PAwR/periodic 구현의 `endPawr()`·`endPeriodicAdvertising()`를
무조건 참조해 링크가 실패했다. `CONFIG_BT_PER_ADV_RSP`와
`CONFIG_BT_PER_ADV`/`CONFIG_BT_PER_ADV_SYNC`에 맞춰 호출을 제한한 뒤
client/server가 빌드되고 양측 STOP까지 실기 PASS했다. 이 수정은
CoC-only lifecycle의 결함을 닫지만 모든 periodic/PAwR 역할의 종료
실기를 대체하지 않는다.

CoC·CS의 stack, malloc arena, Zephyr heap, controller pool은 이번 측정만으로
줄이지 않았다. CS 연속 100개는 후속 1회 PASS했지만 간헐 누락 원인·오류
경로 재검증이 필요하다. 이 기록 시점에는 ISO/Audio, DF, 보안·negative·장기 부하와 native 동등 조건
비교도 **HOLD**였다. 이후 [CIS·BIS 기본 payload](240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md),
[unicast Audio](241_M31_메모리_최적화_P2_Audio_unicast_실기_계측.md),
[DF beacon TX](242_M31_메모리_최적화_P2_DF_beacon_TX_계측.md)의 국소 계측은 추가됐지만
CS 간헐 누락 원인·다른 Audio/DF RX·controller pool·동등 조건 비교는 여전히 열려 있다.
이 기록은 P2 전체 완료나 W04/W05/W06 완료가 아니다.
