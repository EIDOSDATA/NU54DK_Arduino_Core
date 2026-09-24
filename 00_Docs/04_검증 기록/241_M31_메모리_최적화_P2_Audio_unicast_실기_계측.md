# 241 — M31 메모리 최적화 P2: LE Audio unicast LC3 실기 계측

## 판정

두 exact NU54DK에 고정 NCS v3.4.0 `adaptive` Audio unicast source/sink
계측 image를 실행했다. 공개 `BapUnicastSource`의 합성 16 kHz PCM→LC3
40 B frame→CIS와 `BapUnicastSink`의 CIS→LC3 decode 경로를 유지했다.
`prj.conf`에는 thread/heap 계측 설정만 더했고 Bluetooth 수동 설정은
쓰지 않았다. 자동 unlock·mass erase 없이 sector 플래시 후 halt-start로
실행했다.

| 시험 | 결과 | 원본 |
| --- | --- | --- |
| source→sink LC3 unicast | **PASS**. source 1,000 frame 송신, sink 1,000 frame decode, drop 0, 확인한 PCM energy 모두 양수, 종료 직전 총 1,002/1,002, 양측 STOP | [최종 실기 UART·image/probe hash](evidence/m31-p2-audio-bdd0be53/unicast-lc3-1000-filtered.json) |

첫 [FAIL 원본](evidence/m31-p2-audio-bdd0be53/unicast-lc3-1000.json)은
새 부팅 전에 남은 source `frames=800` UART 줄을 같은 실행으로 집계한
러너 오류다. 새 `P2_READY` 이후 줄만 사용하도록 수정하고, 이전 실패를
덮어쓰지 않고 별도 파일로 재실행했다. 이 오류를 Audio firmware 실패나
실기 PASS로 세지 않는다.

central-only source image에서 `BLEDevice.end()`가 광고 미선택인데도
`bt_le_adv_stop()`을 링크하여 최초 빌드가 실패했다. `CONFIG_BT_BROADCASTER`
guard로 종료 시 광고 상태·호출을 역할에 맞춰 분리했다. 이후 source/sink
모두 adaptive 최종 빌드와 정상 STOP까지 통과했다. CoC-only PAwR/periodic
guard와 함께 Host 정적 계약을 추가했지만 다른 GAP 조합의 종료 실기를
자동으로 완료한 것은 아니다.

## 정적 예약과 실행 중 high-water

| 역할 | FLASH 사용 B | RAM 예약 B | `sdc_mempool` 예약 B |
| --- | ---: | ---: | ---: |
| unicast source | 334,004 | 71,403 | 5,616 |
| unicast sink | 288,628 | 67,338 | 5,586 |

FLASH 분모는 loaderless 1,490,944 B, RAM 분모는 262,144 B다. 정적
RAM에는 아래 stack·heap 예약이 포함된다. 독립 CIS/BIS image 또는
native image와 설정·payload가 달라 단순 차감으로 절감률을 만들지 않는다.

| Thread/ISR | source used/reserved B | sink used/reserved B |
| --- | ---: | ---: |
| BT RX WQ | 1520/3200 | 1232/3200 |
| BT TX processor | 704/3200 | 404/3200 |
| BT LW WQ | 936/2104 | 1168/2104 |
| sysworkq | 280/4096 | 400/4096 |
| MPSL Work | 356/1024 | 712/1024 |
| main | 3192/8192 | 2976/8192 |
| ISR0 | 544/2048 | 504/2048 |

양쪽 libc malloc 정지 시점은 `free=8108`, `allocated=0`, 관찰 peak
0 B였다. `sdc_mempool` 값은 정적 예약이지 controller 내부 high-water가
아니다. 계측 image·한 stream·정상 종료의 관찰만으로 stack, malloc
arena, Zephyr heap, controller pool을 줄이지 않는다. 암호화/peer loss,
다중 ASE·codec 방향·broadcast Audio, 장기 부하와 native 동등 조건
비교는 별도다. 이 결과는 **unicast Audio 국소 PASS**이며 P2 전체,
W04/W05/W06 또는 v0.5.0 공개 PASS가 아니다.
