# 253 — M31 P2 Audio broadcast source 재시작·sink 재가입 메모리 계측

> **증거 경계:** 아래 미계측은 해당 실행의 한계다. 지원 역할·용량에 맞춘 현재 P2
> 세 잔여 축과 제외 조건은 [현행 판정 경계](README.md#p2-기록의-현행-판정-경계)를 따른다.

## 판정

고정 NCS `v3.4.0`의 두 exact NU54DK에서 현재 저장소의 `adaptive`
암호화 LC3/BIS source·sink 시험 image를 사용했다. 시험 sketch에 메모리
출력과 sink의 공개 `end()`→`begin()` 재가입 명령만 추가했다. 역할별
probe UID·app/aux COM·HEX를 실행 전에 대조했고, 자동 unlock·mass erase
없이 기존 sector flash image를 reset-halt-drain-resume으로 시작했다.
세 번째 보드는 건드리지 않았다. 원본 JSON에는 익명 probe hash, HEX
SHA-256, UART와 양측 STOP을 보존한다.

| 실행 | 결과 | 원본 |
| --- | --- | --- |
| 첫 1회 시도 | **FAIL 보존**. 최초 sink 동기화가 `native=-31, step=10`으로 실패했다. source는 계속 송신했으나 decode 0이었다. 양측 STOP은 확인했다. | [초기 sync 실패](evidence/m31-p2-native-comparison-2cf92933/audio-broadcast-initial-sync-fail-01.json) |
| 한정 재시도 실행 1회 | **국소 PASS**. 첫 동기화는 재시도 없이 성립했고 source SWD reset 뒤 sink 공개 API 재가입 1/1, 누적 decode 207·drop 0, 양측 STOP. 작업용 원본은 `C:\r31k\p2_audio_broadcast_rejoin-retry-1.json`에 남겼다. | 시험 image와 공개 실행기 아래 참조 |
| 같은 image의 source reset·sink 재가입 20회 | **국소 PASS**. 최초 sync 재시도 0회, reset 후 명시적 재가입 20/20(각 1회), sink stream 21회·누적 decode 2,107·drop 0, 각 100-frame milestone 연속·PCM energy 양수, 양측 STOP. 매 reset에서 이전 sink session은 `native=-8, step=11` 실패를 20회 보고했고 이후 새 session으로 복구했다. | [20회 UART·메모리·image/probe hash](evidence/m31-p2-native-comparison-2cf92933/audio-broadcast-rejoin-memory-20.json) |
| 메모리 판정기를 보강한 같은 image의 독립 20회 | **국소 PASS**. 메모리 출력 완전성·stack 예약 초과·STOP 때 libc 할당 0을 실행기가 추가로 검사했다. 재가입 20/20(각 1회), sink stream 21회·누적 decode 2,106·drop 0, 양측 STOP. 기존 session의 `native=-8, step=11` 20회도 보존했다. | [독립 20회·자동 메모리 요약](evidence/m31-p2-native-comparison-2cf92933/audio-broadcast-rejoin-memory-20-telemetry.json) |

두 번의 독립 20회 PASS는 첫 실행의 `-31`을 소급 삭제하지 않는다. `-8`은 의도적인
source 단절 뒤 기존 sink session의 상태 보고이며, 새 session이 실제
stream·decode까지 회복된 경우만 성공으로 셌다. sink 실패를 자동
복구로 둔갑시키지 않는다. 현재 실행기는 실패 또는 30초 timeout마다
최대 3회만 명시적 재가입을 요청하고 초과 시 FAIL로 끝난다. 두 20회 모두
추가 요청이 필요하지 않았다. 이는 실물 전원 차단이 아닌 **SWD reset**이며,
다중 BIG/BIS·복수 sink·wrong code·장기 RF 간섭은 이번 부하에 없다.

시험 source HEX SHA-256은
`e8beaf0804f00fecdb73f93fe8300dbe0d08bd2528cc3a6e00413f45dc03817e`,
sink는
`d6a33ca6579e6536e02b976345c99dbda869f8885fe234b4b6fd50204fceb548`다.
두 역할의 정적 FLASH/RAM은 source `246,736/55,747 B`, sink
`324,360/76,121 B`다. 이 image는 계측용 sketch 변경 상태에서 빌드되어
제품 릴리스의 clean-source image 증명이 아니다. build manifest의 Core
기저는 `e70af9dabd8c397c2a77f8b314092b82dcc89da8`, board gitlink는
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain bundle은
`dcbdc366a1`이다. 원본 HEX hash와 빌드에 포함된 시험 sketch 변경을
함께 대조해야 하며 기저 commit만으로 image byte를 재현했다고 하지 않는다.

## 재가입 중 관찰한 high-water

다음 값은 독립된 두 20회 실행의 `used/reserved` 중 더 큰 byte다. source는
매번 reset하므로 **한 source 수명 중**의 최고치이고, sink는 각 실행에서
20회 재가입을 계속한 **한 수명 중**의 최고치다. 서로 다른 수명의 사용량을
누적한 값은 아니다.

| Thread/ISR | source | sink |
| --- | ---: | ---: |
| BT RX WQ | 384/2,048 | 704/3,200 |
| BT TX processor | 784/3,200 | 404/904 |
| BT LW WQ | — | 1,184/2,104 |
| sysworkq | 232/4,096 | 248/4,096 |
| MPSL Work | 372/1,024 | 760/1,024 |
| main | 3,192/8,192 | 2,968/8,192 |
| ISR0 | 560/2,048 | 512/2,048 |

양쪽 libc malloc의 관찰 peak는 0 B, STOP 때 `allocated=0`,
`free=8108`이다. 정적 `sdc_mempool` 예약은 controller 내부 실행 중
high-water가 아니다. sink MPSL Work의 관찰 여유는 264 B에 불과하므로
이 수치로 stack이나 pool을 줄이지 않는다. 이 재가입 실기는
[243번의 정상·연속 부하](243_M31_메모리_최적화_P2_Audio_broadcast_실기_계측.md)를
보완하지만 모든 Audio 방향·stream 수·오류 조건의 최악값은 아니다.
**P2 전체는 HOLD**다.
