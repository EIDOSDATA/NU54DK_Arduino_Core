# R11 Analog/Stream peripheral 분리

상태: software 완료. 시작 commit `f1501ed`; T12/T14 software 회귀. current-source T11 및 T12 실기는 미실행이다.

| 기존 책임 | 분리할 위치 | 보존할 경계 |
| --- | --- | --- |
| AnalogFabric.cpp factory·family mutex·초기 IRQ 연결 | 기존 파일 | mutex 1개, singleton과 초기화 우선순위 |
| SAADC context·DMA·nrfx·IRQ·lifecycle | internal/analog/SaadcFabric.cpp | sample 단위, 3개 DMA lease, STOP·진단 |
| PWM sequence context·nrfx·IRQ·lifecycle | internal/analog/PwmSequenceFabric.cpp | 3개 instance, sequence 길이·step·STOP |
| Analog 공통 queue·결과 변환 | internal/analog/AnalogFabricInternal.h | 기존 8개 event queue와 spinlock |
| StreamFabric.cpp factory·family mutex·초기 IRQ 연결 | 기존 파일 | mutex 1개와 metadata spinlock 1개 |
| PDM/I2S/QDEC context·nrfx·IRQ·lifecycle | internal/stream의 각 peripheral cpp | sample/word/report 의미, 고정 queue와 DMA token |
| Stream 공통 queue·DMA·pin helper | internal/stream/StreamFabricInternal.h | 기존 12개 queue, DMA metadata 접근의 짧은 spinlock |

각 peripheral의 context와 driver는 해당 cpp 내부에서 소유한다. mutable extern 또는 새 public
API를 만들지 않는다. 공통 mutex/metadata lock은 내부 accessor로만 접근한다. IRQ trampoline을
각 cpp로 옮기되 기존 factory의 SYS_INIT에서 동일 순서로 연결한다. 기존 R03 white-box Host는
동일 구현을 포함하여 진단 pair/lease 내부 불변조건을 유지하고, 새 data-path Host는 실제 cpp를
별도 translation unit으로 링크하여 public API와 fake nrfx callback 사이를 검증한다.

분할 전후 연속 payload·double buffer 반환 순서, underrun/overflow, STOP/재시작 및 복합 부하를
비교한다. 고정 RAM 주소의 Host process 전용 메모리에 알려진 패턴을 채우고 callback의 주소·길이와
내용 보존을 확인한다. 이것은 EasyDMA/ADC/오디오/PWM 파형의 물리 시험이 아니다. 공개 header와
기존 R03 STOP generation·실패 시 lease 유지·queue 외 STOP 신호를 보존한다.

## 결과와 제한

| 검사 | 결과 |
| --- | --- |
| 본문 / 공개·동기화 header | 124개 본문 보존 / 3개 byte 동일 |
| 독립 링크 data-path Host | 분할 전후 모두 PASS; 5개 peripheral 동시 활성, 1,000 frame/event 교환, 10회 STOP·재시작 |
| R03 production Host | 기존 26개 STOP·overflow·timeout·동시 호출·release/commit 실패 시나리오 PASS |
| 전체 Host | 623개 중 621 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / 305개 PASS |
| target | Analog·Stream·onboard HIL·DUT/peer·미선택 구성 6/6 build-only PASS, 223.42초 |

기존 family mutex 2개와 IRQ 연결 순서·우선순위를 보존했다. Stream metadata spinlock은
factory가 단일 소유하고 accessor로 접근한다. context·driver는 각 peripheral cpp에서
소유하며 mutable extern을 추가하지 않았다. 의미가 같은 queue/결과 helper만 header에
공유하고 SAADC sample lease와 Stream token은 기존 차이를 유지했다.

새 Host는 실제 cpp를 따로 링크하고 nrfx fake에 전달된 첫/다음 buffer·길이·PWM repeat를
확인한다. callback에 교대로 반환한 두 buffer의 주소·sample/word 수·data 패턴, I2S 첫 요청과
underrun 구분, PDM/QDEC overflow, 음수 QDEC 누산 값, RAM 범위 거부와 STOP 뒤 lease 0을
검증한다. 이 복합 부하는 Host API/event interleave이며 실제 동시 EasyDMA·파형 시험은 아니다.
R03의 제어된 실제 Host thread 정지/다른 block 진행도 그대로 통과했다.

초기 새 harness는 SYS_INIT을 버리던 mock 때문에 unused-function, inline GPIO 정의의
별도 TU 링크에서 실패했다. mock은 초기화 함수 참조만 보존하고 GPIO 외부 정의를 제공하도록
수정했다. 분리 직후 shared header의 상대 include가 Host의 serial 전용 pin stub를 선택한
실패는 production 내부 header의 명시적 상대 경로로 수정했다. 이후 Host·target 전체가 통과했다.
실제 library 동작 수정으로 이 실패들을 우회하지 않았다.

| 동일 구성의 flash / RAM | 이전 | 이후 |
| --- | --- | --- |
| M25 Analog | 73,348 / 31,128 B | 73,316 / 31,128 B |
| M25 Stream | 76,972 / 32,040 B | 77,200 / 32,040 B |
| pair DUT | 183,824 / 161,496 B | 184,000 / 161,496 B |

context·driver·family mutex 객체 크기와 공개 method symbol은 보존됐다. pair의 metadata
spinlock은 이 설정에서 빈 C++ 객체 1바이트이며 이전에는 최적화로 제거됐다. accessor 뒤
실체가 생겼지만 총 RAM은 padding 내에서 동일하다. M25 Stream의 진단 설정에서는 기존과
동일한 4바이트 lock이다. flash 증감을 측정값 그대로 기록하며 성능 향상을 주장하지 않는다.
명시적 CMake 목록의 Analog 3개·Stream 4개 source는 선택 시 각 1회, 미선택 시 0회다.

[gate](evidence/r11-f1501ed/software-and-source.json),
[본문·header·source](evidence/r11-f1501ed/comparison.json),
[target](evidence/r11-f1501ed/target-build.json),
[target 기준선](evidence/r11-f1501ed/target-before.json),
[메모리·symbol·소속](evidence/r11-f1501ed/target-comparison.json),
[data 전](evidence/r11-f1501ed/data-before3.txt)·[후](evidence/r11-f1501ed/data-after2.txt),
[R03 회귀](evidence/r11-f1501ed/r03-after.txt)를 보존한다.
current-source T11 및 T12 physical은 NOT RUN이며 다음 작업은 R12 BLE/Storage다.
