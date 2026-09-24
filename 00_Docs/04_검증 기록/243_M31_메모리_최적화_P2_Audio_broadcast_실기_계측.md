# 243 — M31 메모리 최적화 P2: 암호화 Audio broadcast 실기 계측

## 판정과 실패 경계

두 exact NU54DK에서 고정 NCS v3.4.0의 `adaptive` 방송 source/sink를
실행했다. 공개 `BapBroadcastSource`/`BapBroadcastSink`의 동일 16-byte
Broadcast Code, 합성 16 kHz PCM→40 B LC3→BIS→decode 경로를 유지하고
thread/heap 계측만 더했다. Bluetooth 수동 `prj.conf`는 쓰지 않았다.
두 보드의 probe/COM을 확인하고 자동 unlock·mass erase 없이 sector
플래시와 halt-start로 실행했다.

Windows 경로 길이를 피하려고 단축 경로의 개발 설치본에서 빌드했다.
설치본의 Git 기저는 현재 Core commit이 아니며 수정 중인 작업본이다.
이번 역할에 직접 쓰인 BLE GAP, Audio broadcast source/sink, capability
registry, adaptive overlay와 builder 핵심 파일은 실제 저장소와 줄 끝을
제외한 내용이 일치함을 별도로 대조했다. 따라서 설치본 manifest의
`core_revision`을 현재 저장소 전체의 pristine source 증명으로 해석하지
않는다. 시험 결과는 원본 HEX hash·UART와 이 대조 범위에 한정한다.

| 실행 | 판정 | 원본 |
| --- | --- | --- |
| 첫 source/sink image | **FAIL 보존**. source는 송신을 시작했으나 sink가 `native=-31`을 보고하고 decode 0에서 멈췄다. 마지막 단계 정보가 없어 원인을 단정하지 않는다. | [최초 실패 UART·image/probe hash](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000.json) |
| sink에 실패 단계 출력 추가 후 실행 | **국소 PASS**. source 1,000 frame 송신, sink 1,000 frame decode, drop 0, PCM energy 양수, 양측 STOP. | [첫 PASS UART·image/probe hash](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-step.json) |
| 동일 최종 image 7회 추가 실행 | **7/7 국소 PASS**. 각 실행에서 source·sink 1,000 frame 이상, drop 0, 양측 STOP. 최종 image 합계 8/8. | [2회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-repeat.json) · [3회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-third.json) · [4회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-run-4.json) · [5회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-run-5.json) · [6회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-run-6.json) · [7회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-run-7.json) · [8회차](evidence/m31-p2-audio-7c918d79/broadcast-lc3-1000-run-8.json) |

첫 실패의 `-31`은 후속 8회 PASS로 소급해 삭제하지 않는다. sink
실패 단계 출력 외 firmware 의도 변경은 없었지만 재플래시·시간·무선 환경도
달라졌으므로 원인 규명이나 장기 안정성 PASS는 아니다. 최종 8회 종료
직전 집계는 source 1,086~1,134, sink 1,000~1,002 frame이고 drop은 모두 0이다.
최초 실패 원본에도 양측 STOP과 메모리 출력이 남아 있다. 재부팅 전
source UART의 오래된 `frames=2500` 줄은 새 `P2_READY` 이후 집계에서
제외해 성공 분자에 넣지 않았다.

빌드 과정에서도 P2 역할 분리의 결함을 발견했다. BAP source는 Zephyr
`CONFIG_BT_PER_ADV=y`가 필요하지만 Arduino `GapPeriodicAdvertising.cpp`는
선택되지 않는다. 공통 `BLEDevice.end()`가 Kconfig만 보고 이 구현을
강하게 참조해 최초 링크가 실패했다. 선택적으로 링크된 facade의 종료
hook만 호출하도록 약한 참조·null 검사를 적용했다. 방송 source/sink
adaptive 최종 빌드와 Host 계약 테스트로 확인했으며, 호출하지 않은
주기 광고 API의 동작을 PASS로 간주하지 않는다.

## 정적 예약과 관찰 high-water

| 역할 | FLASH 사용/분모 B | RAM 예약/분모 B | `sdc_mempool` 예약 B |
| --- | ---: | ---: | ---: |
| broadcast source | 246,660/1,490,944 | 55,747/262,144 | 3,050 |
| broadcast sink | 324,060/1,490,944 | 76,121/262,144 | 6,229 |

정적 RAM에는 stack·heap 예약과 SDC pool이 이미 포함된다. 다음 값은
최종 image의 8회 PASS 중 큰 `used/reserved` byte다.

| Thread/ISR | source | sink |
| --- | ---: | ---: |
| BT RX WQ | 384/2048 | 672/3200 |
| BT TX processor | 784/3200 | 404/904 |
| BT LW WQ | — | 936/2104 |
| sysworkq | 232/4096 | 280/4096 |
| MPSL Work | 372/1024 | 696/1024 |
| main | 3192/8192 | 2968/8192 |
| ISR0 | 560/2048 | 520/2048 |

libc malloc은 양쪽 모두 종료 시점 `free=8108`, `allocated=0`, 관찰
peak 0 B다. `sdc_mempool`은 정적 예약이지 controller 내부 high-water가
아니다. 암호화 방송 한 stream의 정상 수명 8회와 최초 실패 한 회만으로
stack·heap·SDC pool을 줄이지 않았다. sync loss·재동기화·wrong code,
다중 stream/ASE, 장기 부하와 native 동등 조건 비교는 별도다. W03의
과거 기능 검증도 이 계측 image의 메모리 최악값을 대신하지 않는다.
P2 전체와 W06은 계속 **HOLD**다.
