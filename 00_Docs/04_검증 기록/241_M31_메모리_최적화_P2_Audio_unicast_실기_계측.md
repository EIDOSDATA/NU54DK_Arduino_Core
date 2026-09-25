# 241 — M31 메모리 최적화 P2: LE Audio unicast LC3 실기 계측

> **역사 기록:** 아래 미계측 범위는 이 image의 증거 한계다. 후속 양방향·복구 결과와
> 현재 P2 세 잔여 축은 [M31 TODO](../TODO_M31.md), 제외 조건은 [현행 판정 경계](README.md#p2-기록의-현행-판정-경계)를 따른다.

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
| 동일 image의 연속 10,000 frame | **국소 PASS**. 100-frame 간격의 송신·복호화가 각각 10,000까지 연속 증가하고 drop 0·energy 양수. STOP 시 총 10,003/10,003, 양측 종료 확인 | [장기 실기 UART·image/probe hash](evidence/m31-p2-audio-bdd0be53/unicast-lc3-10000.json) |

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

아래 사용 최고치는 동일 HEX의 1,000/10,000 frame 두 실행에서 각 항목의
더 큰 값을 취했다. 하나의 동시 peak 합계가 아니다.

| Thread/ISR | source 최대 used/reserved B | sink 최대 used/reserved B |
| --- | ---: | ---: |
| BT RX WQ | 1520/3200 | 1248/3200 |
| BT TX processor | 704/3200 | 404/3200 |
| BT LW WQ | 936/2104 | 1168/2104 |
| sysworkq | 288/4096 | 400/4096 |
| MPSL Work | 356/1024 | 712/1024 |
| main | 3192/8192 | 2976/8192 |
| ISR0 | 544/2048 | 572/2048 |

양쪽 libc malloc 정지 시점은 `free=8108`, `allocated=0`, 관찰 peak
0 B였다. `sdc_mempool` 값은 정적 예약이지 controller 내부 high-water가
아니다. 계측 image·한 stream·정상 종료의 관찰만으로 stack, malloc
arena, Zephyr heap, controller pool을 줄이지 않는다. 암호화/peer loss,
다중 ASE·codec 방향·broadcast Audio, 장기 부하와 native 동등 조건
비교는 별도다. 이 결과는 **unicast Audio 국소 PASS**이며 P2 전체,
W04/W05/W06 또는 v0.5.0 공개 PASS가 아니다.

후속 [254번 source 재시작·sink 재연결 계측](254_M31_P2_Audio_unicast_재연결_메모리_계측.md)은
adaptive source의 재연결에서 확장 scan을 호출하는 결함을 발견·수정했다.
수정 image의 source SWD reset 20/20, sink 누적 decode 2,933·drop 0,
양측 STOP을 확인했다. 최초 및 guard-only 실패 원본도 보존했다.
