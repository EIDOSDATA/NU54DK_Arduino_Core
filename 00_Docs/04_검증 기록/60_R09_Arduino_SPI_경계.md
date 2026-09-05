# R09 Arduino SPI facade/backend 경계

상태: 완료. 종료 commit은 R09 SPI facade/backend 구현 commit으로 식별한다. 시작 commit `8d39e578639594abc748b81a531d5409f32e83d6`.
T14 구조 회귀이며 current-source T11은 실행하지 않는다.

## 구현 전 책임 대응표

| 기존 `cores/arduino/SPI.cpp` 책임 | 분리 후 위치 | 유지할 상태·연결 |
| --- | --- | --- |
| `ZephyrSPI` Arduino virtual 구현·singleton·transaction·buffer/bit order·interrupt mask | 기존 SPI.cpp facade | 공개 SPI reference와 vtable 계약 유지; mutex, thread owner, 진단 atomic과 interrupt token 단일 소유 |
| chosen/SPI00 조건·device·binding·runtime route·started | `internal/spi/SpiZephyrBackend.cpp` | 기존 startup 초기화·route lease 유지; facade mutex 안에서만 내부 함수 호출 |
| nRF54 frequency predicate·Zephyr mode/config·driver transfer | 같은 backend 파일 | frequency policy와 두 configuration buffer 및 pointer를 backend가 소유 |
| facade/backend 연결 | `internal/spi/SpiBackendOperations.h` | 고정 내부 함수만 추가; 새 virtual HAL·동적 할당·공개 header 변경 없음 |
| Arduino 설정 검증·오류 우선순위 | facade | controller → frequency → bit order → mode 순서 유지; frequency 허용 여부만 backend에 조회 |
| CMake·package | 기존 SPI Kconfig 조건에 backend 추가 | 선택/비선택 source 각각 1/0개; cores 포함 정책 유지 |

분할 전 실제 SPI.cpp와 실제 ArduinoCore-API header를 Host에서 실행한다.
device·route·pinctrl·SPI driver는 제어 가능한 mock이며 R08의 실제 route 검증과 연결한다.
begin/end 재시도, transaction 소유 thread, mode/bit order/frequency, 수동 CS, chunk 실패,
interrupt suspend/restore 실패를 고정한 뒤 같은 harness로 분할 후 비교한다.

## 결과와 보존한 동작

| 검사 | 결과 |
| --- | --- |
| 공개/진단 header 5개 | 전체 bytes 동일 |
| 기존 helper·diagnostic·interrupt 20개 본문 | whitespace·global namespace 표기 외 동일 |
| 실제 SPI Host 12개 시나리오 | 분할 전/후 PASS |
| 전체 Host | 620개 중 618 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / C/C++/ino 293개 PASS |
| target | M7·B2·AC02B DUT/peer·M3 총 5개 build-only PASS |
| source 소속 | SPI 선택 3개 구성에 facade/backend 각각 1개, 비선택 2개 구성에는 0개 |
| current-source T11 | NOT RUN |

초기 target 실행은 SPI를 선택한 구성과 peer 4개가 빌드되고 M3가 실패했다.
원인은 R08의 단독 M3 CMake 목록에 새 table 구현을 누락한 것으로, [59번 보완](59_R08_자원과_경로_수명주기.md)에
실패와 `b3a6b90` 수정·M3 1/1 재빌드를 별도로 기록했다. 처음 실행 전체를 PASS로
다시 표시하지 않는다. 수정은 M3 자체 목록에만 적용되므로 나머지 4개를 반복 빌드하지 않았다.

같은 B2 image의 flash는 125,456 → 125,616 bytes, RAM은 68,272 bytes로 같다.
SPI singleton object 4 bytes·공개 reference 4 bytes·mutex 20 bytes·route 4,224 bytes·
configuration 두 개 56 bytes가 유지됐고 기존에 링크된 SPI 공개/진단 함수가 누락되지 않았다.
파일 경계를 만든 비용이며 성능·메모리 개선으로 주장하지 않는다.

facade는 Arduino mode/controller/bit order 검증, transaction owner, in-place 32-byte chunk,
16-bit 전송 순서 및 interrupt token을 소유한다. backend만 chosen device·SPI00 제한·
runtime route·nRF54 prescaler·Zephyr configuration·spi_transceive에 접근한다. 기존
configuration slot은 검증 시도마다 전환하고 interrupt suspend 성공 뒤에만 publish한다.
공유 mutable extern은 추가하지 않았으며 backend의 내부 함수는 facade mutex 안에서 호출한다.

Host는 4개 mode × 2개 bit order, 유효/무효 frequency와 오류 우선순위, CS 없는 configuration,
begin/end 재시도, 다른 실제 thread의 소유권 거부, 두 번째 chunk driver 실패 시 첫 chunk만
반영, interrupt suspend 실패의 역순 복구 및 restore 실패의 token 보존/재시도를 검사했다.
target compile과 mock driver는 실제 SCK·CS·DMA 종료 또는 결선 PASS의 근거가 아니다.

[gate·source](evidence/r09-8d39e57/software-and-source.json),
[보존 비교](evidence/r09-8d39e57/comparison.json),
[target 결과](evidence/r09-8d39e57/target-build.json),
[메모리·symbol·소속](evidence/r09-8d39e57/target-comparison.json),
[분할 전](evidence/r09-8d39e57/before.txt)과 [후](evidence/r09-8d39e57/after-initial.txt)를 보존한다.

다음 R10은 기존 Serial Fabric 5개 adapter를 유지하면서 registry·IRQ·lifecycle을
분리하고 STOP 대기의 전역 mutex 범위를 줄인다. 같은 handle/block의 교차 연산은
예약된 상태로 거부하고 다른 block의 진행을 실제 Host thread로 확인한다.
직접 nrfx와 Arduino backend의 Kconfig 상호 배제는 유지한다.
