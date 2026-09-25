# NU54DK Arduino Core — 전 인스턴스·DMA·BLE 경쟁 기준과 마일스톤

v0.4.0 완료 상태·검증 범위는 [v0.4.0 완료 TODO](<../TODO_v0.4.0.md>)에서 관리합니다.

이 문서의 경쟁 비교와 초기 engineering 목표는 제품 방향을 설명합니다. 현재 실행 범위에서는
QDEC 추가 진단·반복 Serial handover·T13 peer 제어 System OFF 추가 2조건을 제외합니다.
S 정상·동시성·복구 결과와 U 실기를 포함한 합의 범위를 종료하고 T22 승인·T23 공개·T24 설치
검증·T25 마감까지 완료했습니다. QDEC20/21은 기본·SAMPLE/REPORT event를 제한 명시 지원합니다.
완료·제외된 시험을 다시 예약하지 않습니다.

| 항목 | 내용 |
| --- | --- |
| 문서 ID | COMPETITIVE-PARITY-001 |
| 문서 개정 | 5.1 |
| 문서 상태 | 고정 source 비교, M23~M30 완료·M31 6/8과 M32~M33 계획 |
| 현재 공개 기준 | NU54DK Arduino Core `v0.4.1` stable / release source `bbc2dc1fc5823ca465fc1d1ff2170512282b9313` |
| 비교 기준 | `lolren/nrf54-arduino-core` `v1.0.17` / commit `a6bb99879aa14cbff362a5478d5f1189848b4200` |
| SoC·SDK 기준 | nRF54L15 / NCS v3.4.0 / Zephyr 4.4.0 |
| 최종 갱신일 | 2026-09-25 |
| 작성자 | Quantum / NUCODE |

이 문서는 nRF54L15 주변장치의 **모든 실제 인스턴스**, EasyDMA 경로와 Bluetooth LE 기능군을
경쟁 기준으로 관리한다. 소스에 class나 register wrapper가 존재하는 것, Arduino 사용자에게
독립 객체로 노출되는 것, build되는 것, 실제 보드에서 동작하는 것과 여러 인스턴스가 동시에
동작하는 것을 서로 다른 상태로 취급한다.

현재 지원 범위는 [Arduino API 지원 범위](04_Arduino_API_지원_범위.md)가 소유한다. 이 문서의
`목표`와 `계획`은 공개 지원 선언이 아니다. 완료 단계와 제품 순서는
[Master roadmap](02_구현_로드맵.md)이 소유한다.

2026-09-16 개정의 실행 원본은 [전체 Bluetooth 기능·예제 계약](19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md)과
[M31](../TODO_M31.md)·[M32](../TODO_M32.md)·[M33](../TODO_M33.md) TODO다. nRF54L15에서 적용 가능한
고정 NCS 예제마다 Arduino 제공 경로를 배정한다. 보드 3개 기능시험을 기본으로 하며 정밀 RF 보정·
음질·절대 거리/각도 정확도는 사용자 결정에 따라 필수 gate 밖이다. 1~7절의 과거 목표보다 이 계약이 우선한다.
Apple/Google·외부 vendor 기능과 mic/speaker·외장 장치는 작동 가능한 구현·예제·설정/연결 안내·
자동 가능한 검사가 필수다. 실제 장치 운용·interop는 사용자 추후 검증으로 인계하며 해당 `NOT RUN`은
v0.5.0 개발·공개를 차단하지 않는다. 검증되지 않은 장치 지원·호환성은 선언하지 않는다.
2026-09-21 결정에 따라 v0.5.0은 M31 완료 후 Windows 우선으로 릴리스한다. M32·M33 추가 기능과
Ubuntu/macOS 확대는 버전 미정 후속 범위다. 해당 OS의 실제 설치·USB upload·serial·debug는
후속 지원 공개 때 사용자가 검증하며 M33의 세 Host 증거 gate를 유지한다.

M28은 **W01~W08·9개 test ID**, M29와 M30은 각각 **W01~W08·10개 test ID를 완료**했다.
M30-W08은 실제 전원 차단 4지점 × 3회(12/12)를 통과했다. M31은 **W01~W06 완료 6/8**,
W07~W08 미착수다. M32·M33은 각각 0/12·0/8로 미착수다. M28~M30의 기능 지원성·
장비·정량 합격 기준은 [M28 착수 계약](15_M28_BLE_GAP_Link_Privacy_착수_계약.md), 전체 제품선
상태는 [v0.5.0 착수 계획](../TODO_v0.5.0.md)에서 관리한다. 준비 문서를 구현·실기 PASS로 해석하지
않으며 v0.4.1의 기존 지원·시험 결과와 현재 사용 중인 보드·환경은 변경하지 않는다.

새 리팩토링 진단은 M23~M27을 재번호화하지 않는다. T11 뒤 R00~R05 정확성, R06~R13 구조·도구
리팩토링을 최종 physical gate의 선행조건으로 연결한다. R13과 전체 software gate 뒤 최종 exact
source로 current-source T11 회귀와 T12~T15를 한 번 수행하고 R14에서 RC를 고정한다. 상세 범위와 상태는
[리팩토링 문서 안내](<14_리팩토링/README.md>)와
[진행 체크리스트](<14_리팩토링/05_리팩토링_진행_체크리스트.md>)를 따른다.

---

## 1. v0.3.0 시점의 비교 결론

1~7절은 아래 고정 source의 v0.3.0 비교와 당시 목표입니다. v0.4.0에서 이룬 결과는 8절에
분리하며, 과거 격차를 현재 미구현 목록으로 해석하지 않습니다. 비교 결과는 다음과 같습니다.

1. 비교 대상은 bare-metal register wrapper와 base-address 생성자를 통해 UARTE, SPIM/SPIS,
   TWIM/TWIS, PWM, PDM, I2S, QDEC 등 **더 많은 인스턴스에 닿는 소스 경로**를 제공한다.
2. 비교 대상은 UARTE ring·double buffer, SPIM/TWIM staging buffer, PWM sequence, PDM/I2S
   double buffer 등 **직접 EasyDMA 경로가 더 넓다**.
3. 그러나 `Serial2`는 `Serial1`의 참조 별칭이고, `SPI`와 `SPI_HS`는 모두 SPIM00을 사용한다.
   저수준 wrapper나 예제의 존재도 모든 인스턴스의 동시 HIL PASS를 뜻하지 않는다.
4. NU54DK Core는 v0.3.0에서 Serial1/UART30, Wire/I2C22, SPI/SPI00, SAADC와 PWM20~22의
   제한된 제품 경로만 제공하므로 **인스턴스 노출 폭과 명시적 DMA API에서 뒤처진다**.
5. NU54DK Core의 강점은 Zephyr/NCS driver, DTS·pinctrl·runtime PM과 하나의
   `IoResourceManager`에서 UART/I2C/SPI personality 충돌까지 fail-closed로 관리하는 구조다.
   이 구조를 버리지 않고 전체 인스턴스로 확장한다.

따라서 경쟁 목표는 객체 이름이나 register wrapper 수가 아니다. **전기적으로 사용할 수 있는
각 물리 인스턴스를 독립적으로 선택하고, 동일 serial block의 personality 충돌을 막고, 서로 다른
block의 허용 조합을 동시에 실행하며, DMA 수명주기와 오류 복구까지 HIL로 증명하는 것**이다.

---

## 2. 비교 기준과 판정 축

### 2.1 고정한 소스

| 대상 | 고정 기준 | 용도 |
| --- | --- | --- |
| NU54DK Core | `bae0957d2425e4418199a2a3a018bf8e9a0dc356` | v0.3.0 당시 공개 API·driver·resource manager 비교 |
| 비교 Core | [`a6bb998`](https://github.com/lolren/nrf54-arduino-core/tree/a6bb99879aa14cbff362a5478d5f1189848b4200) | 구현·예제·README 판정 |
| nRF54L15 | [Nordic Product Specification](https://docs.nordicsemi.com/bundle/ps_nrf54l15/page/keyfeatures_html5.html) | 실제 peripheral·EasyDMA·radio 능력 |
| NCS/Zephyr | NCS v3.4.0에 고정된 DTS·Kconfig·driver source | NU54DK에서 사용할 upstream 경로 |

경쟁 저장소는 MIT license지만 이 문서는 API와 동작을 비교하는 독립 설계 자료다. 상대 source를
복사하지 않으며 도입이 필요하면 license, attribution과 clean-room 검토를 별도 기록한다.

### 2.2 지원을 구성하는 독립 판정

| 축 | PASS 조건 |
| --- | --- |
| Silicon | nRF54L15에 해당 instance와 mode가 실제 존재함 |
| Board route | NU54DK connector·온보드 회로에서 안전한 pin route가 있음 |
| Source | driver와 선택 경로가 구현돼 있고 placeholder/no-op가 아님 |
| Arduino exposure | 공개 header, 객체·factory와 예제가 있고 잘못된 alias가 아님 |
| Build | exact NCS/board/profile에서 compile·link됨 |
| Semantic | 정상·경계·충돌·timeout·취소·재시작 시험을 통과함 |
| HIL | 실제 NU54DK와 명시한 fixture에서 신호·데이터를 검증함 |
| Concurrent HIL | 허용되는 다른 instance·기능과 동시에 실행해 독립성을 증명함 |
| Interoperability | 외부 장치·OS·다른 vendor와 상호 운용됨 |
| Qualification | 해당 Bluetooth qualification·제품 인증 근거가 별도로 있음 |

`Source`나 `Build`만 PASS한 기능은 제품 지원이 아니다. 보드에서 꺼낼 수 없는 pin은 가짜
`supported` 대신 `silicon-only` 또는 `board-unroutable`로 기록한다.

---

## 3. Serial fabric 전 인스턴스 비교

nRF54L15의 serial interface는 instance 번호별 공유 block이다. 같은 행의 UARTE, SPIM/SPIS와
TWIM/TWIS는 같은 register base와 IRQ 자원을 personality별로 공유하므로 **동시에 사용할 수 없다**.
서로 다른 행은 pin·DPPI·memory·power 제약을 만족하면 동시에 사용할 수 있다.

| 물리 block | 가능한 personality | NU54DK `v0.3.0` | 비교 Core `v1.0.17` | 경쟁 완료 기준 |
| --- | --- | --- | --- | --- |
| 00 | UARTE00, SPIM00, SPIS00 | SPI00만 공개·HIL | UARTE·SPIM/SPIS base 경로. `SPI`와 `SPI_HS`는 둘 다 SPIM00 | 고속 특성, 세 personality 선택과 상호배타, 실제 route HIL |
| 20 | UARTE20, SPIM20, SPIS20, TWIM20, TWIS20 | UARTE20은 system console 전용 | generic/base 경로 | console ownership을 보존한 선택 profile과 충돌 진단 |
| 21 | UARTE21, SPIM21, SPIS21, TWIM21, TWIS21 | 공개 객체 없음 | generic/base 경로, TWIS 예제 경로 | controller/peripheral 전 mode와 독립 HIL |
| 22 | UARTE22, SPIM22, SPIS22, TWIM22, TWIS22 | Wire/TWIM22 공개·HIL | `Wire` TWIM22와 generic/base 경로 | Wire·target와 UART/SPI 전환, stale owner 없는 반복 HIL |
| 30 | UARTE30, SPIM30, SPIS30, TWIM30, TWIS30 | Serial1/UARTE30 공개·HIL | `Wire1` TWIM30, UARTE/SPIM/SPIS generic/base 경로 | DAP route와 connector route 정책, 전 personality HIL |

### 3.1 API별 차이

| 영역 | NU54DK `v0.3.0` | 비교 Core `v1.0.17` | NU54DK 목표 |
| --- | --- | --- | --- |
| UART | `Serial` UARTE20, `Serial1` UARTE30. RX IRQ queue, TX `uart_poll_out()` | base 선택 `HardwareSerial`; 00/20/21/22/30 IRQ owner; RX/TX DMA ring | 5개 UARTE 선택·독립 객체, async RX/TX, flow control, break/error, 실제 동시 HIL |
| UART 별칭 | 독립하지 않은 `Serial2`를 제공하지 않음 | `Serial2`는 `Serial1` 참조 별칭 | 이름 하나당 실제 독립 resource. alias면 문서와 capability에 alias로 명시 |
| I2C controller | `Wire` = TWIM22, 100/400 kHz | `Wire` = TWIM22, `Wire1` = TWIM30, base 선택 20/21/22/30 | TWIM20/21/22/30, 100/400/지원 고속 mode, repeated-start 전 조합 |
| I2C target | 미지원 | TWIS callback와 저수준 TWIS 경로 | TWIS20/21/22/30, clock stretching·overflow·repeated transaction HIL |
| SPI controller | `SPI` = SPIM00, 동기 `spi_transceive()` | `SPI`/`SPI_HS` = 같은 SPIM00, generic와 저수준 SPIM 경로 | SPIM00/20/21/22/30, sync/async, CS 정책, mode·frequency·bit order HIL |
| SPI peripheral | 미지원 | 저수준 SPIS와 echo 예제 | SPIS00/20/21/22/30, semaphore·overrun·buffer turnover HIL |
| Cross-personality | 공통 `IoResourceManager`가 block+instance를 정규화해 충돌 차단 | class별 owner가 있으나 모든 personality를 묶는 중앙 lease 근거는 없음 | 현 manager를 전체 block으로 확대, reserve/commit/rollback/release 원자성 유지 |

비교 Core의 generic constructor와 저수준 wrapper는 경쟁상 중요한 장점이다. 다만 base를 받을 수
있다는 사실과 모든 route·동시 조합이 검증됐다는 사실은 구분한다. NU54DK는 source parity 뒤에도
최소한 `begin → transfer → end → 다른 personality begin` 반복, 충돌 negative와 서로 다른 block의
최대 동시 조합을 HIL로 통과해야 완료한다.

---

## 4. 나머지 peripheral 전 인스턴스 비교

| 기능군 | nRF54L15 instance | NU54DK `v0.3.0` | 비교 Core `v1.0.17` | 격차와 목표 |
| --- | --- | --- | --- | --- |
| GPIO | GPIO0/1/2 | variant capability에 등록된 connector/LED/button | broad GPIO register API | 안전한 전 board route, drive/sense/retain과 ownership HIL |
| GPIOTE | GPIOTE20/30 | Zephyr GPIO callback 경유 | base wrapper, task/event·DPPI 경로 | 두 instance channel 할당, task/event/latency·overflow 검증 |
| EGU | EGU10/20 | 내부 Zephyr 경로만 | base wrapper | direct 사용 가치 결정, IRQ/channel ownership과 HIL |
| DPPI | DPPIC00/10/20/30 | driver 내부 경로, 공개 allocator 없음 | DPPIC wrapper | domain별 channel/group allocator, publish/subscribe 충돌·전력 gate |
| Timer | TIMER00/10/20/21/22/23/24 | Arduino time·tone 내부 사용, 일반 instance API 없음 | generic Timer; standalone 예제와 제한된 instance 검증 | 7개 전부, bit width·capture/compare·one-shot/periodic·DPPI HIL |
| GRTC | 1 | Board/System counter·alarm·System OFF HIL | GRTC와 GRTC PWM wrapper | 다중 alarm/channel, capture·wake·clock 보정·resource contract |
| SAADC | 1, 최대 8 channel | 단일 read, AIN metadata 8개 중 공개 AIN5~7 | single/differential·internal input·gain·oversample·calibration | 8채널 scan, differential/internal, calibration, async continuous DMA |
| PWM | PWM20/21/22, 각 4 channel | PWM20 `analogWrite`, PWM21 `tone`, PWM22 Servo | 세 base, 4채널·sequence mode·DPPI/DMA | 12 HW channel의 명시적 allocator, sequence/loop/DPPI와 동시 HIL |
| PDM | PDM20/21 | 미지원 | 두 base, capture·double buffer 경로 | 두 instance stream, clock/pin route, overrun과 동시 DMA HIL |
| I2S | I2S20 | 미지원 | TX/RX/duplex double-buffer 경로 | TX/RX/duplex, word/clock format, underrun/overrun과 codec HIL |
| QDEC | QDEC20/21 | 미지원 | 두 base 선택 경로 | v0.4.0의 기본·SAMPLE/REPORT event 지원 결과와 manual read/clear 제한은 아래 M25 참조 |
| COMP/LPCOMP | 각 1 기능군 | 미지원 | register wrapper와 예제 경로 | 입력 route·reference·hysteresis·wake/DPPI, analog conflict HIL |
| TEMP | 1 | NCS direct 가능, 공개 wrapper 없음 | wrapper | accuracy 경계와 blocking/async API, radio calibration 간섭 확인 |
| WDT | WDT30/31 | Board/System WDT 한 경로 HIL | base wrapper | 두 instance, channel·pause·reset reason·System OFF 정책 |
| NFCT | 1 | board pin conflict로 비적용 처리 | partial wrapper/예제 | 실제 NU54DK route 재감사 후 board-unroutable 또는 profile+HIL 확정 |
| RADIO | 1 | BLE controller 경유 | raw RADIO와 BLE/802.15.4/CS 실험 경로 | raw profile·MPSL 소유권·protocol coexistence를 별도 제품선에서 검증 |
| Crypto/security | CRACEN, KMU, RNG, TAMPC 등 | 일부 NCS build inventory | register wrapper가 더 넓음 | PSA 우선 public 경계, key lifetime·secure ownership·오용 방지 |
| Power/clock/cache | SoC system block | Zephyr PM/clock/cache 사용 | register wrapper가 더 넓음 | Zephyr ownership 유지, 필요한 진단만 노출하고 coherency를 자동 보장 |
| VPR | VPR/RISC-V coprocessor | 미지원 | partial 저수준 경로 | NCS 지원성·memory/mailbox·debug를 먼저 조사하고 제품 가치 gate |
| sQSPI | VPR SoftPeripheral | 미지원 | 비교 Core 자체 matrix도 미완료 | VPR firmware·memory/mailbox·board route inventory 뒤 지원·비적용 판정 |

Native USB device, DAC, Wi-Fi radio처럼 nRF54L15에 같은 hardware가 없는 기능은 경쟁 때문에
가짜 API를 만들지 않는다. 외장 chip으로 제공하는 기능은 `external-add-on` profile로 분리한다.

---

## 5. EasyDMA 비교와 필수 계약

Zephyr/nrfx driver가 내부에서 EasyDMA를 쓴다는 사실과 Arduino 사용자가 비동기·연속 전송을
제어할 수 있다는 사실은 다르다. NU54DK `v0.3.0`의 SPIM/TWIM/SAADC/PWM/UARTE driver는
내부적으로 DMA를 사용할 수 있지만, 공개 API는 대체로 동기 호출이나 단일 sample에 한정된다.

| 경로 | NU54DK `v0.3.0` | 비교 Core `v1.0.17` | 경쟁 완료 기준 |
| --- | --- | --- | --- |
| UARTE | RX IRQ queue, TX byte별 poll API; driver 내부 EasyDMA | 1024 B RX ring, 512 B RX double buffer, 512 B TX ring, 256 B TX DMA chunk | async ring/double buffer, backpressure, zero-length·abort·restart·error HIL |
| SPIM | 동기 Zephyr transceive; nrfx DMA·bounce/DMM·chunk 경로 | 512 B aligned staging chunk로 직접 DMA | sync/async, RAM 접근성, MAXCNT 분할, cache coherency, CS lifetime |
| SPIS | 없음 | direct DMA와 semaphore 경로 | double buffer, ACQUIRED/END, overrun, host timing과 cancel |
| TWIM | 동기 controller; nrfx DMA buffer 준비 | aligned staging buffer 직접 DMA | no-copy 가능 조건, repeated-start, NACK·bus recovery·timeout |
| TWIS | 없음 | target buffer와 callback 경로 | RX/TX buffer turnover, clock stretch, overflow와 stop/restart |
| SAADC | 단일 read; nrfx DMA buffer | 단일·differential read와 보정, hardware DMA | multi-channel scan, double buffer, sampling timer/DPPI, calibration gap |
| PWM | Arduino output; nrfx sequence DMA | sequence mode와 DPPI 직접 제어 | RAM sequence ownership, loop/end/refresh, concurrent 3-instance playback |
| PDM | 없음 | double-buffer stream | continuous stream, buffer release deadline, dropped-frame counter |
| I2S | 없음 | TX/RX/duplex double buffer | full-duplex ownership, underrun/overrun, clock master/slave HIL |
| RADIO DFE/IQ | 공개 경로 없음 | CS 실험과 raw radio 경로 | IQ/sample buffer DMA, antenna pattern, timestamp·calibration metadata |

모든 DMA 공개 경로는 다음 계약을 공통으로 가져야 한다.

1. 허용 memory 영역, alignment, 최대 `MAXCNT`, scatter/chunk 정책을 API에 명시한다.
2. 비동기 호출 뒤 buffer 소유권과 재사용 가능 시점을 completion event로 반환한다.
3. non-DMA-accessible buffer는 명시적으로 거부하거나 bounded bounce buffer를 사용한다.
4. data cache가 있는 경로는 clean/invalidate와 memory barrier를 driver가 책임진다.
5. `end()`, timeout, cancel, error, System OFF와 runtime PM에서 DMA가 buffer를 더 만지지 않음을
   증명한다.
6. ISR에서는 allocation과 무제한 대기를 금지하고 callback을 bounded event로 main thread에 넘긴다.
7. block personality 전환 시 task·event·IRQ·DPPI publish/subscribe와 pin을 모두 해제한다.
8. throughput, CPU 점유율, latency, overrun/drop과 전원 모드 조건을 HIL 결과에 함께 기록한다.
   `v0.4.0`에서는 소프트웨어·peer로 관측 가능한 값과 측정 방법을 남기며, 정밀 시간·전력 실측은
   [코어 기능 검증 범위 합의](<../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)에 따라 필수 gate가 아니다.

---

## 6. Bluetooth LE 전 기능군 격차

여기서 `전 기능`은 nRF54L15 hardware와 고정 NCS/Zephyr 조합이 제공할 수 있는 Bluetooth LE
기능군을 뜻한다. BR/EDR은 hardware 범위가 아니며, Bluetooth SIG의 모든 adopted service를
한 릴리스에서 전부 wrapper로 복제한다는 뜻도 아니다. Service/profile catalog는 우선순위와
상호 운용 근거를 가진 별도 ledger로 관리한다.

아래 표는 v0.3.0 시점의 비교·목표를 보존한다. 이후 확인한 SDC 방향탐지 경계, signed write의
deprecated 상태와 EATT의 experimental 상태를 포함한 현행 착수 조건은 8절 M28~M33을 따른다.

| 기능군 | NU54DK `v0.3.0` | 비교 Core `v1.0.17` | 목표 |
| --- | --- | --- | --- |
| 역할·topology | Peripheral 또는 Central, single active link | 실용 single active link 중심 | Central+Peripheral 동시, multi-link와 자원 한계 공개 |
| Controller/Host capability | 고정 profile·API 범위 | custom host/controller + CS용 SDC/MPSL | SDC/HCI feature bit·Kconfig·host API 자동 ledger와 unsupported fail-closed |
| Legacy advertising·scan | 지원·두 보드 HIL | 지원 | 회귀 유지, filter·duplicate·active/passive 전 조합 |
| Extended advertising/scanning | 미지원 | partial, local chain/reassembly 중심 | connectable/nonconnectable, multi-set, cross-vendor HIL |
| Periodic advertising/sync | 미지원 | 미지원 | advertiser, sync, transfer와 loss/recovery |
| PAwR | 미지원 | 미지원 | subevent/response, multi-peer timing·loss HIL |
| 최신 controller feature | 미지원 | 공개 완성 근거 없음 | NCS v3.4.0의 HCI feature·Kconfig inventory로 encrypted advertising data 등 적용 가능 항목을 누락 없이 판정 |
| Connection control | 기본 lifecycle | partial | parameter update, channel map/classification, event length, supervision |
| PHY·DLE·MTU | 제한된 PHY/MTU 경로 | 1M/2M/Coded S2/S8, DLE 251, MTU 247 | 양방향 요청·fallback, throughput·range·error HIL |
| Power control | 미지원 | 공개 완성 근거 없음 | LE Power Control, path-loss monitoring와 Tx power report |
| Subrating·신규 timing | 미지원 | 공개 완성 근거 없음 | connection subrating, frame-space update와 shorter interval 지원성 |
| Privacy | bond 일부 | RPA partial, controller list policy 미완 | RPA, resolving/filter accept/periodic advertiser list와 key lifecycle |
| ATT/GATT server | 기본 service/characteristic·notify/indicate | long value·descriptor·authorization·cache까지 더 넓음 | descriptor, prepare/execute, long/reliable op, DB change 전 계약 |
| GATT client | discover/read/write/CCC 기본 | 구현 폭이 더 넓음 | 모든 discovery, long/read-multiple/write-command/signed-write |
| Service Changed·cache | 미지원 | Service Changed와 robust caching | database hash, robust caching, reconnect·firmware migration HIL |
| L2CAP | ATT 사용, public CoC 없음 | LE CoC/EATT 미지원 | LE CoC credit/MTU, multiple channel, EATT와 starvation/error HIL |
| SMP/security | LE SC, passkey·bond 기본 | Just Works/passkey/Numeric Comparison/OOB, bond DB | 전 IO capability, OOB, key size·distribution·삭제·실패·rate limit |
| Signed write | 미지원 | 지원 표기 | CSRK/sign counter persistence·replay negative와 interop |
| Standard profiles | BAS/DIS/HID keyboard | NUS/HID와 다중 service | HID 전체 class, 표준 service/profile 우선순위 catalog와 OS HIL |
| ISO | 미지원 | 미지원 | CIS/CIG, BIS/BIG, sync·loss·buffer/latency와 controller/host 경계 |
| LE Audio | 미지원 | 미지원 | LC3, unicast/broadcast audio, BAP/CAP 등 채택 범위와 audio HIL |
| Direction Finding | 미지원 | 미지원 | AoA/AoD, CTE, antenna switching, IQ DMA와 calibration |
| Channel Sounding | 미지원 | experimental standalone two-board | connected ACL procedure, security, distance calibration·cross-vendor HIL |
| Mesh | 미지원 | 미지원 | provisioning, relay/friend/LPN/proxy, model·settings와 multi-board HIL |
| BLE DFU | 미지원 | secure DFU 미지원 | signed image, BLE transport, rollback·power-loss recovery |
| Multiprotocol | 미지원 | 별도 실험 경로 | BLE+802.15.4/ESB coexistence, MPSL ownership과 starvation HIL |
| Interoperability | NU54DK 두 보드와 Windows 11 일부 | 기능별 partial | Android/iOS/Windows/Linux, Nordic·타 vendor matrix와 장시간 soak |
| Qualification | 제품 qualification 선언 없음 | qualification 미완 | QDID·DN/host/controller/Mesh 적용성 검토와 제품별 증거 분리 |

Nordic [nRF54L15 qualification matrix](https://docs.nordicsemi.com/bundle/comp_matrix_nrf54l15/page/comp/nrf54l15/nrf54l15_ble_qdid_qual_matrix.html)의
항목은 component 적용성 자료다. NCS Kconfig에 기능이 있거나 Nordic component가 qualified됐다는
사실만으로 NU54DK Arduino Core 제품이 qualified됐다고 표시하지 않는다.

비교 Core의 Channel Sounding은 경쟁상 선행 구현이지만 현재 문서 기준으로 Nordic SDC/MPSL을
쓴 standalone 두 보드 실험 경로다. connected ACL, 보정된 거리, cross-vendor와 qualification이
완료된 제품 기능으로 확대 해석하지 않는다. 당시 목표에 포함한 보정·상호운용의 현행 배치는
8절을 따른다. M31은 연결·보안·CS/RAS 데이터·복구, M33은 외부 peer 적용성을 담당하며 정밀 보정은 필수 밖이다.

---

## 7. v0.3.0 기준 격차와 개발 우선순위

| 우선순위 | 격차 | 이유 |
| --- | --- | --- |
| P0 | instance/capability machine-readable ledger 부재 | 구현·보드 route·HIL 상태를 이름이나 README 문장과 분리할 기준이 먼저 필요 |
| P0 | serial block 전체의 public 선택·동시성 부족 | UART/I2C/SPI 경쟁 폭의 핵심이며 block personality 안전성과 직접 연결 |
| P0 | 공통 DMA 계약과 async API 부족 | 대용량 UART/SPI/audio/ADC/BLE radio 확장의 성능·안전 기준 |
| P1 | SAADC scan, PWM sequence, PDM/I2S/QDEC/timer 전체 instance 부족 | 센싱·모터·audio 제품 사용성을 결정 |
| P1 | BLE extended/periodic/PAwR, multi-link, privacy 부족 | 현대 BLE GAP 기반 기능의 선행조건 |
| P1 | GATT long/cache, L2CAP CoC/EATT, security 세부 부족 | 실제 library·OS 상호운용과 고성능 GATT의 기반 |
| P1 | ISO/LE Audio, AoA/AoD, connected Channel Sounding, Mesh 부재 | nRF54L15 차별 기능과 경쟁 제품선 |
| P2 | comparator/NFCT/VPR/security 등 저수준 breadth 부족 | 고급 사용자 parity에 필요하나 board route·제품성 판단이 선행 |
| P2 | 체계적인 cross-vendor·qualification 준비 부족 | source parity를 제품 신뢰도로 전환하는 마지막 gate |

---

## 8. 재편된 마일스톤

### M23 — 경쟁 inventory와 공통 계약

- 상태: **완료** — 75개 identity schema/manifest, generated runtime·문서 matrix, 공개 identity API와
  block/channel/DMA 공통 lease를 고정했다.

- SoC instance, board route, owner, public object, driver, DMA, build, semantic, HIL 상태를 담는
  machine-readable manifest를 만든다.
- 각 객체의 실제 hardware identity를 조회할 capability API와 진단 형식을 고정한다.
- 동일 block personality 상호배타, 서로 다른 block 동시성, pin/DPPI/timer/DMA memory ownership을
  하나의 계약으로 확장한다.
- `Serial2 = Serial1`과 같은 독립성을 가장하는 alias를 금지한다.
- 완료 gate: schema test, 전 instance 누락 검사, generated matrix와 source/DTS 불일치 fail-closed.
  실행 결과는 [M23 검증 기록](<../04_검증 기록/33_M23_Peripheral_Inventory와_공통_소유권_기준선.md>)과
  [generated matrix](09_M23_Peripheral_인스턴스_매트릭스.md)에 보존한다.

### M24 — Serial fabric 전 인스턴스와 DMA

- 상태: **작업 1~6·T15 지원 판정·T16 설치 통합 완료** — 5개 block·23개 personality, 핀 bank, singleton/고급 API 경계,
  DMA lifecycle과 관련 errata를 [M24 Serial Fabric 계약](10_M24_Serial_Fabric_경로와_API_계약.md)에
  고정하고 CI drift 검사를 연결했다. 회로도 재검토로 단독 HIL primary 자원 6개와 무배선 자동화
  후보 7개·외부 fixture 필요 16개도 계약에 추가했다. 실행 결과는
  [M24 작업 1 검증 기록](<../04_검증 기록/34_M24_Serial_Fabric_경로와_API_계약_기준선.md>)에 보존한다.
  작업 2에서는 allocation-free typed handle, 원자적 route/DMA lease와 bounded handover backend를
  구현하고 target semantic build를 통과했다. 결과는
  [M24 작업 2 검증 기록](<../04_검증 기록/35_M24_Serial_Fabric_공통_backend_기준선.md>)에 보존한다.
  작업 3~5에서 UARTE 5개, SPIM/SPIS 각 5개, TWIM/TWIS 각 4개의 direct nrfx adapter와
  sync/async·double-buffer API가 target build를 통과했다. 온보드 UARTE 4개와 TWIM 3개의
  기본 data-path는 `51c1986`에서 PASS했다. Exact 결과는
  [온보드 교정·재검증](<../04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)을 따른다.

#### 리팩토링 전 단독 HIL의 근거

| Fixture | exact source | 당시 PASS 범위 | 근거 |
| --- | --- | --- | --- |
| 101 UART P2↔P1 | `2542a01` | 정상 1,620·예상 오류 24·cleanup 2 | [44](<../04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>) |
| 102 UART P0↔P1 | `ff3423e` | 정상 810·예상 오류 12·cleanup 2 | [45](<../04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>) |
| 103 UART P1↔P1 | `b3c689b` | 정상 2,430·예상 오류 36·cleanup 2 | [46](<../04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>) |
| 201 SPI P2↔P1 | `f21377e` | 계획 ID 18,169 | [47](<../04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>) |
| 202 SPI P0↔P1 | `1a133e6` | 계획 ID 9,084 | [48](<../04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>) |
| 203 SPI P1↔P1 | `4af93da` | 계획 ID 27,252 | [49](<../04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>) |
| 301 TWI P1↔P0 | `e2f045c` | 기능 1,986·cleanup 2 | [50](<../04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>) |

UART 103의 접촉 교란·`FRAMING`, SPI 201의 8 MHz 수신 지연/RXDELAY 교정,
TWI 301의 내부 pull-up·clock-stretch 지연 buffer 결함은 각 실패 원본과 함께 보존한다.
SPI 201의 2/4/8 MHz·Mode 0~3·MSB/LSB·sync/async·이중 buffer·cancel/recovery 범위는 47번이 소유한다.

이후 current-source T11 완료 근거는 리팩토링 체크리스트와 67~73번 기록을 따른다.
이전 SWD `No ACK`는 보존하며 기본 PASS를 전체 복구·동시성 PASS로 확대하지 않는다.

#### API와 검증 경계

- UARTE00/20/21/22/30, SPIM/SPIS00/20/21/22/30, TWIM/TWIS20/21/22/30을 구현한다.
- Arduino 호환 singleton과 고급 instance factory/direct handle의 책임을 분리한다.
- UARTE의 고정 event ring과 두-buffer 연속 RX, SPI·I2C sync/async,
  target/peripheral double buffer와 공통 DMA 수명주기를 제공한다. 범용 N-buffer circular DMA queue로
  과장하지 않으며 더 깊은 queue와 backpressure 최적화는 별도 성능 gate에서 판단한다.
- 완료 판정 축: 각 personality 단독 HIL, 같은 block 충돌 negative, 허용 topology의 동시
  HIL, timeout/cancel/error 복구, throughput·CPU·손실·soak 기록.
  전원 모드 lease의 올바른 해제는 필수이며 외부 계측 기반 전류·파형 보증은 제외한다.
  반복 Serial handover와 T13 peer 제어 System OFF 추가 결합은 사용자 지시로 제외했다.
  구현 backend나 M15 공개 System OFF 지원을 제거한다는 뜻은 아니다.
- R00~R13과 이후 T11 회귀는 완료했다. 후속 runtime/link 변경이 있으면 실제 영향에 따라
  필요한 동일 조건을 재검증하며, 과거 source의 PASS를 새 image에 복사하지 않는다.

| 작업 | 범위 | 상태 |
| --- | --- | --- |
| 1 | Route/API/errata, 단독 HIL primary 자원 계약과 자동 drift 검사 | **완료** |
| 2 | 공통 backend, typed handle, personality handover | **완료** |
| 3 | UARTE 5개와 async RX/TX DMA | **source/build/semantic 완료 · Fixture 101~103 외부 route PASS** |
| 4 | SPIM/SPIS 각 5개와 sync/async·double buffer | **source/build/semantic 완료 · Fixture 201~203 P2/P0/P1↔P1 PASS** |
| 5 | TWIM/TWIS 각 4개와 repeated-start·target double buffer | **source/build/semantic·Fixture 301 단독 기능 HIL 완료** |
| 6 | 온보드·peer 기능, 충돌·허용 동시성·복구·성능·soak | **T15 지원·physical gate 확정 완료** |

### M25 — Analog·timing·audio·event 전 인스턴스

- 상태: 기능 검증·T14 자원 충돌 판정·T15 physical 판정과 T16 설치 노출 완료. T22 전 범위
  재확정에서 QDEC20/21을 partial 근거와 manual read/clear 제한을 명시한 공개 지원으로 전환했다.
  구현 이력은 [M25 검증 기록](<../04_검증 기록/37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>),
  source별 요구 대조는 102번, 외부 ADC 반복 수 차이는 103번, fixture 경계는 42번 기록에 보존한다.
- 주요 기능 결과: SAADC AIN0~7·내부 ADC/event, PDM 기본/연속, C17 GPIO/GPIOTE·PWM 675+288·I2S 432 PASS.
  TIMER는 95번의 실제 범위로 완료 정리했다. QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT
  event 경로를 지원하며 반복 manual read/clear 무손실은 보증하지 않는다.

- SAADC 8채널 scan/differential/internal/calibration/oversampling/continuous DMA를 제공한다.
- PWM20/21/22의 12 hardware channel과 sequence/DPPI/DMA를 명시적 Fabric 소유권으로 관리한다.
  기본 analogWrite PWM20/tone PWM21/Servo PWM22와 Fabric profile의 배타 경계를 유지한다.
  기본 API가 유휴 block을 자동 공유하는 기능은 완료 범위가 아니며 후속 ARF-02 opt-in 과제다.
- TIMER00/10/20~24, GPIOTE20/30, EGU10/20, DPPIC00/10/20/30,
  PPIB00/01/10/11/20/21/22/30과 GRTC 고급 경로를 제공한다.
- PDM20/21·I2S20은 DMA streaming/double-buffer API, QDEC20/21은 하드웨어 누산·read/clear·IRQ event API와 fixture를 사용한다. QDEC에는 DMA가 없다.
- LED·button·VBAT monitor와 내부 event 경로는 보드 자체 자동 runner에 우선 배치한다. 외부 기능
  시험은 두 NU54DK의 안전한 ADC 입력·PWM capture·PDM/I2S/QDEC 합성 신호/loopback을 사용한다.
  실제 핀을 통과하는 신호와 기대 sample/frame/count는 필수이며 handle 생성으로 대체하지 않는다.
- 완료 gate: 현행 범위에 포함된 instance의 단독·허용 동시 기능 HIL, 기본 timing·DMA overflow/underrun·복구·long-run soak.
  T13의 QDEC20/21 manual read 단독·C07은 실행 대상에서 제외했으며, 지원 근거인 기본 QDEC와
  SAMPLE/REPORT event 결과와 구분한다.
  정밀 ADC 정확도·jitter·음질·신호 품질, 실제 마이크·코덱·엔코더별 호환성은 필수 gate에서 제외한다.
  합성 peer 신호를 아직 구현하거나 검증하지 못한 경로는 `NOT RUN`/HOLD를 유지한다.
- R03에서 ISR/thread 진단 snapshot, queue overflow, stop generation과 lock 대기 계약을 먼저 고정하고
  R11 구조 분할이 이를 보존하는지 검증한다. R13과 current-source T11 회귀 뒤 고정한 exact image만
  M25 physical gate에 사용한다.

### M26 — 나머지 SoC 기능과 board 경계

- 상태: **전수 판정 완료, TEMP·WDT30 기본 physical HIL PASS** — 16개 기능에 지원 경계를 부여해
  `unknown`을 0으로 만들고 strict ledger·생성 문서·CI gate를 연결했다. TEMP·WDT30/31 후보와
  무배선 TEMP·WDT30 reset을 41번 기록에서 검증했다. 세부 판정은
  [M26 지원 경계](11_M26_System_Peripheral_지원_경계.md)와
  [M26 검증 기록](<../04_검증 기록/38_M26_System_Peripheral_판정과_온보드_HIL_준비.md>)을 따른다.

- COMP/LPCOMP, TEMP, WDT30/31, NFCT, power/clock/cache, CRACEN/KMU/RNG/TAMPC와 VPR/sQSPI를
  재고 조사하고 wrapper/direct/profile/비적용 경계를 확정한다.
- raw RADIO는 BLE controller와 동시 소유하지 못하게 하고 다음 radio 제품선의 profile 기반을 만든다.
- TEMP·내부 event·WDT semantic처럼 외부 신호가 불필요한 항목은 자동화하고, NFCT·RF·전원 특성처럼
  보드 경계 밖의 peer·안테나·계측이 필요한 항목은 별도 physical gate로 남긴다.
- 완료 gate: 모든 silicon instance가 `supported`, `partial`, `silicon-only`, `board-unroutable`,
  `not-applicable` 중 하나와 근거를 가지며 `unknown`이 남지 않음.

### M27 — `v0.4.0` Peripheral Parity 릴리스

- 상태: **완료 / v0.4.0 정식 공개** — M24/M25 physical gate와 T16 설치 통합 뒤 QDEC 지원 범위를
  재확정했고 T19~T21 RC/stable 검증을 다시 통과했다. T22 승인, T23 tag·Release·stable index 공개,
  T24 공개 설치본 예제 30/30·Upload·설치 수명주기와 T25 마감을 완료했다. 최종 결과는
  [125번 기록](<../04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)을 따른다.
  [39번 초기 HOLD 기록](<../04_검증 기록/39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)의 29개 staging
  예제 결과는 당시 준비 이력으로 보존한다.

- M23~M26 manifest, examples, HIL, package install과 clean-environment 재현 build를 통합한다.
- 비교 Core의 공개 예제와 동일 use case를 독립 시험으로 실행하고 부족한 항목은 known limitation에
  정확히 남긴다.
- 완료 gate: 전 인스턴스·DMA release matrix, Boards Manager lifecycle, stable artifact와 공개 검증.
  M24·M25의 검증 깊이는 [42번 범위 합의](<../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)를
  따른다. R00~R13, current-source T11과 T12~T15 통합 실기를 완료하고 R14에서 RC를 다시 고정한다.
  장비·외부 부품 품질 보증을 제외해도 필수 기능 HIL이나 frozen RC gate는 생략하지 않는다.

### M28 — BLE GAP·Link·Privacy 확장

- nRF54L15·고정 NCS의 controller Kconfig, host API와 board 경계를 대조한 machine-readable
  [BLE readiness 원장](../../variants/nu54dk/m28-ble-readiness.json)을 준비했다. `M28-W01`의
  capability image·`M28CAP/1` parser·target build와 actual HCI 6/6, W02~W06 production 구현,
  W07 2·3보드 HIL과 W08 인계를 완료했다. 정적 `candidate`와 runtime HCI·구현·RF PASS는 분리한다.
- 기존 `requestPhy()`·`requestMtu()`와 legacy GAP은 회귀 기준선으로 유지한다. 신규 범위는
  multi-role/multi-link, extended/periodic advertising·scanning, sync/PAST와 PAwR이다.
- 기존 `BLEConnection` 호환 view를 보존하면서 신규 generation per-link handle/event, link-control,
  연결·buffer 상한과 자원 반환을 구현했다. 다중 GATT/security 확장은 M29/M30에서 별도 계약한다.
- M28의 PHY/DLE/MTU·connection parameter·remote-info 범위는 기존 계약으로 완료했다.
  Power Control/Path Loss, channel classification·신규 timing·subrating, 다중 advertising set과
  identity/list 확장은 **M32-A의 신규 구현**이다. M28 완료 원장에 추가 PASS를 소급하지 않는다.
- RPA lifecycle과 identity 관측을 기존 bond storage 회귀와 함께 검증했다.
- 완료 gate: [M28 착수 계약](15_M28_BLE_GAP_Link_Privacy_착수_계약.md)의 9개 test ID와 고정
  topology·연결 수·OS/peer matrix에서 reconnect·loss·long-run HIL을 수행한다.

### M29 — ATT/GATT·L2CAP 완성

- 현재 상태: W01~W08과 10개 test ID를 완료했다. 두 보드 SIGN/EATT, 세 보드
  `M29-MULTI-01`·`M29-REG-01`과 Windows/Intel 기본 GATT를 별도 증거로 확인했다.
  [M29 계약](16_M29_ATT_GATT_L2CAP_착수_계약.md)과
  [149번 기록](<../04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)을 따른다.
- long/reliable read/write, descriptor·authorization과 read multiple을 확장한다.
- Service Changed, database hash와 robust caching을 firmware migration까지 검증한다.
- LE Credit Based Channel과 EATT의 MTU/credit/starvation/error 경계를 정한다. 고정 NCS의 Zephyr는
  `BT_SIGNING`을 **deprecated**, `BT_EATT`를 **experimental**로 분류한다.
- signed write와 EATT는 각각 기본 OFF인 legacy opt-in·experimental opt-in library로 구현했다.
  Deprecated/experimental 상태는 두 보드 HIL PASS 뒤에도 유지하며 기본 BLE profile의 안정 기능으로
  승격하지 않는다. 제외·SDK 교체는 별도 승인 없이 결정하지 않는다.
- 완료 gate: 승인한 정책·상한에 따른 server/client 양방향, multi-channel, cross-vendor와 malformed
  peer negative. Signed write를 포함하면 CSRK·counter 영속성과 replay 거부를 함께 검증한다.

### M30 — BLE Security·Profile·DFU

- 기존 SMP IO capability 5종, LE Secure Connections와 bond API는 회귀 기준선이다. OOB,
  key distribution/size 정책, bond migration·privacy와 추가 OS 상호운용을 신규 범위로 구분한다.
- 기존 BAS/DIS/HID keyboard와 추가 HID class·adopted services/profiles를 분리한 catalog를 승인한다.
- BLE DFU에 필요한 최소 MCUboot·고정 layout·서명/검증·BLE transport·rollback·power-loss recovery를
  먼저 구현·검증한다. Loaderless 기본값은 유지하고 update는 검증한 선택 profile 또는 application
  template로 제공한다. 별도 `secure_ble_dfu` profile을 채택했고 W08 실제 전원 복구까지 완료했다.
- 유선 OOB는 W03 실기를 완료했다. NFC NDEF adapter는 Host/build만 검증하고 RF NOT RUN·지원 제외를 유지한다.
- 당시 다중 Host 계획의 HOST-W01~HOST-W03을 완료했다. 기존 `.exe`·`%LOCALAPPDATA%`·batch
  가정 inventory와 공통 Python backend·OS별 resolver·얇은 `.cmd`/`.sh` launcher 기반을 보존한다.
  HOST-W04 이후의 확대는 후속 범위로 보류하며 M31 Windows 공개와 분리한다.
- M36에는 해당 layout·image/key 정책·업데이트 상태 전이·복구 시험 결과를 인계한다. M36은 이를
  여러 layout/transport로 확장·hardening하며, M30의 필수 서명·복구 검증을 뒤로 미루는 단계가 아니다.
- 완료 gate: M30 계약의 10개 test ID와 update recovery HIL. OS별 pairing UX·추가 peer 상호운용은
  M33 matrix에서 적용 범위를 추적하며 NU54DK scripted pairing PASS로 모든 OS UX를 대체하지 않는다.
- W08은 재개 도구·산출물·preflight 복구 → 사람 준비 확인 → 실제 차단 → 영향 회귀·마감 순서로
  완료했다. Exact 결과와 제외한 Host timeout 시도는
  [161번 기록](<../04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)을 따른다.

### M31 — ISO·LE Audio·Direction Finding·Channel Sounding

M31-W01~W08 **8개 작업**은 [M31 TODO](../TODO_M31.md)에서 관리한다. W01의 고정 NCS
parity 원장·capability, W02 설치본 ISO 11예제·11역할, W03 Audio 11/11과 W04 DF를 완료했다.
근거는 [W02 최종 기록](<../04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)과
[W03 완료 감사](<../04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)다.
HOST는 독립 3/8 완료이며 W04 이후는 사용자 지시로 보류한다. Windows v0.5.0의 package·설치·
RC·공개 gate는 M31-W08, 후속 다중 Host 확대의 최종 수락은 M33-W07~W08이 소유한다.
메모리 최적화 P0·P1·P2와 W04~W06을 완료했으며 다음 순서는 W07 → W08이다.
P2 세 축의 오류·최악 부하, 최종 크기와 Nordic native 비교는
[262번](<../04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)을 따른다.

| 하위 gate | 계획 범위 | 선행 결정·완료 증거 |
| --- | --- | --- |
| M31-A ISO·LE Audio | CIS/CIG·BIS/BIG·combined/time sync, LC3, BAP/CAP, PACS/ASCS, BASS assistant/delegator, CSIP, PBP, VCP/VOCS/AICS, MICP, MCP/MCS, CCP/TBS, TMAP/GMAP/HAP/HAS | 역할별 source/build 적용성, 고정 buffer·stream 예산, 합성 PCM·SDU 실제 전송·codec·제어·오류 복구, 역할별 Arduino 예제 |
| M31-B Direction Finding | **W04 완료** — AoA CTE TX와 별도 LL 연결 응답, 제품 IQ RX·AoD 미지원 판정 | 현재 소스 TX·연결 응답 HIL PASS. 고정 NCS v3.4.0·nRF54L15 제품 SDC IQ RX·AoD는 `UNSUPPORTED`. [263번](<../04_검증 기록/263_M31_W04_Direction_Finding_완료.md>) |
| M31-C connected Channel Sounding | DF와 별도 A1_B1의 두 역할, 보안 ACL initiator/reflector, capability·procedure·RAS, raw 결과·거리 산출 | 기본 2보드 자동 HIL의 실제 procedure·결과·peer loss/reconnect·security negative, 정밀 거리 정확도 보증 제외 |

기본 NCS SDC의 AoA CTE 광고 송신은 국소 PASS지만 연결 응답 명령은 실제 image에서
Unknown HCI Command였다. 공개 연결 응답 예제는 별도 Zephyr LL을 사용하며
[174번 기록](<../04_검증 기록/174_M31_W04_연결_CTE_응답_실기.md>)의 범위를 따른다. AoD는 미지원이다.
송신 경로를 AoA 각도 산출이나 IQ 수신 전체 지원으로 해석하지 않는다. nRF54L DTS의 DFE 존재와
controller 지원은 별개이므로, 칩에 방향탐지 hardware가 없다고 단정하지도 않는다.
제품 IQ RX의 고정 SDK 미지원 근거는 [259번](<../04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)을 따른다.
연결형 Zephyr LL 내부 IQ 20 report·1,640 sample·cleanup 국소 PASS와 connectionless IQ 0·fault는
과거 진단으로 보존하며 제품 수신 지원이나 P2 필수 재시험으로 승계하지 않는다.
안테나 배열 부재가 제품 RX 미지원의 이유는 아니다. SDK/controller 변경은 P2 완료 조건이 아니며
안테나 전환·각도 산출·정밀 교정은 기존 사용자 후속·범위 제외 정책을 유지한다.
CS의 간헐 loss/counter gap은 P2에서 비차단 관찰값이다. 유효 결과·step·양측 STOP·fault 검사와
최대 절차의 peer 이탈·복구를 구별하며 0-gap을 추가 완료 조건으로 두지 않는다.

완료 gate는 적용 가능한 보드 기반 기능의 정량 HIL과 모든 역할의 제공/미지원 판정이다. Raw IQ가
미실행이면 실제 controller/build/runtime 사유를 기록하며 배열이 없다는 이유만으로 장비 부족 처리하지 않는다.
M31-W06은 네 기능 전체 동시 실행을 요구하지 않는다. 독립 image별 자원·수명주기와 M19~M30
회귀를 검증하고, W07~W08 예제·문서 마감 뒤 Windows 릴리스 gate를 별도 판정한다.
외부 audio 입출력·안테나 전환/각도 장치·타사 peer는 구현·예제·설정/연결 안내·자동 검사까지 완료하고
실제 장치 운용/interop는 사용자 추후 검증 `NOT RUN`으로 남긴다. 이 외부 실기는 v0.5.0 비차단이다.
CTE TX image가 실행됐다는 사실은 IQ 수신 또는 각도 계산 성공이 아니다. 수신 oracle이 없는 TX는
송신 제어까지만 증명하며 적용 가능한 raw IQ 수신은 실제 별도 증거로 판정한다.

### M32 — 최신 LE Controller·Mesh 1.1·coexistence

[M32 TODO](../TODO_M32.md)의 **12개 작업**으로 확장한다. 기존 M28 2-link·1 advertising set
기준선을 유지하고 더 큰 자원/역할 구성은 별도 검증 preset으로 제공한다. M31 v0.5.0 이후의
후속 제품선이며 배포 버전은 아직 확정하지 않는다.

| 기능군·작업 | 구현해야 할 기능 |
| --- | --- |
| M32-A / W01~W05 | capability, LE Power Control·Path Loss·Tx report, Subrating·SCA Update·Frame Space·Shorter CI·LL Extended Feature Set, channel classification/event timing·PHY fallback |
| M32-A 광고·자원 | multi-set/identity, Filter Accept/Resolving/Periodic Advertiser List, directed advertising, scan while initiating, EAD·Advertising Coding Selection, 확장 budget·ARF-01 |
| M32-A Nordic | LLPM, QoS Connection Event Report·Channel Survey, connection time sync, Event Trigger·Radio Notification, experimental LE Flushable ACL |
| M32-B / W06~W08 | PB-ADV/PB-GATT·node/provisioner·relay/friend/LPN/proxy·model·settings·IV/key refresh, Remote Provisioning·SAR·Opcode Aggregator·Large Composition·Private Beacon/Proxy·Solicitation·Subnet Bridge, BLOB/DFU/Distribution |
| M32-C / W09~W10 | 최소 802.15.4/ESB 단독 TX/RX·STOP/복구 → BLE/Mesh와 지원되는 공존 조합, MPSL ownership·traffic·starvation |
| W11~W12 통합 | 2/3보드 기능·negative·유한 soak·회귀·예제·자원표·미지원 사유 마감, M33 및 M38/M39 인계 |

Mesh DFU의 최소 layout·transfer·서명·복구는 M32 범위다. 저장소 용량/배포자 역할의 제약과
확장 partition·transport는 M36으로 인계한다. 실제 전원 차단은 자동화 허가에 포함하지 않으며 별도
요청과 실행 계약이 필요하다. HOST-W07의 실행기·절차·자동 검사는 병행 준비한다. Ubuntu/macOS의
실제 설치·upload/debug/serial/lifecycle은 해당 OS 후속 릴리스의 사용자 검증으로 남긴다.

### M33 — 전체 Bluetooth 예제·상호운용·후속 릴리스

M31 Windows v0.5.0은 M31-W08이 마감한다. M33의 추가 기능·전체 catalog·Host 확대·공개는
버전 미정 후속 범위로 유지하며 현재 0/8이다.

- M28~M32의 API, profile, memory·throughput·power 한계와 interop 결과를 통합한다.
- [M33 TODO](../TODO_M33.md)의 **8개 작업**으로 전체 NCS sample/test ID를 마감한다.
- OTS/OTC·ANS·CTS·HTS·CSC/RSCS·CGMS·BMS 및 iBeacon/Eddystone/BTHome 예제를 제공한다.
  Fast Pair·ANCS/AMS는 credential·실제 ecosystem peer와 구현/build/runtime 상태를 따로 기록한다.
- HCI transport/controller·DTM은 radio 전용 validated profile/template로 제공하며 일반 BLE application과
  자원 충돌을 차단한다. BR/EDR·nRF54L15 비대상 예제는 근거 있는 비적용 행으로 보존한다.
- M31/M32의 역할별 예제와 신규 profile을 설치 목록·CI에 연결한다. Source-only, SDK native,
  NU54DK native, Arduino build, 기능 HIL, 외부 interop의 각 분모를 공개한다.
- ARF-04A 목적별 Fabric 예제는 기존 API만 사용하는 사용자 경로 보강으로 연결한다. 새 public API,
  buffered NUS·PWM pool은 [별도 후속 ARF](18_문서_전면검토와_개선_마일스톤.md)로 검증한다.
  BLE role-budget ARF-01은 M32-W04로 통합한다.
- M30에서 인계한 OS별 pairing·bond/HID UX와 security/profile 상호운용을 기능별 matrix 행으로
  추적한다. Apple/Google·외부 vendor 기능의 작동 가능한 구현·예제·설정/연결 안내·자동 검사를
  완료하고 실제 외부 peer 운용은 사용자 추후 검증 `NOT RUN`으로 인계한다. 해당 실기는 후속 제품선
  개발·공개의 차단 gate가 아니다. 기본 GATT 또는 NU54DK scripted pairing PASS로 실제 OS UX나
  vendor 호환성을 선언하지 않는다.
- Bluetooth qualification 적용성, 필요한 QDID/DN과 미완료 인증을 분리해 공개한다.
- HOST-W08에서 Windows 10/11 x64, Ubuntu 24.04부터 최신 지원 release까지 AMD64, macOS 26부터
  최신 지원 major까지 Apple Silicon의 전체 예제·대표 실제 upload/runtime·lifecycle을 마감한다.
  Ubuntu/macOS 실제 검증은 해당 OS 후속 릴리스 때 사용자가 수행하며 세 Host 증거 gate는 유지한다.
- 완료 gate: release package, 보드 기반 전체 BLE regression, 외부 장치의 구현·예제·자동 검사와
  사용자 추후 검증 상태가 명시된 mobile/desktop·cross-vendor matrix, 세 Host 지원 matrix와 공개 stable 검증.

세 Host 확대의 정확한 작업 분할·제외 범위·증거 계약은
[다중 Host 지원 착수 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 따른다.

M28은 W01~W08·9개 test ID, M29와 M30은 각각 W01~W08·10개 test ID를 완료했다.
M30-W08 실제 전원 차단은 12/12를 통과했다. M31은 6/8 완료·전체 미완료이고 M32·M33은 계획이다. M28 결과와
CMSIS-DAP 실패 진단은
[140번 기록](<../04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)에 보존한다.
[착수 계획](../TODO_v0.5.0.md)의 정책·장비·정량 기준이 미확정이면 해당 gate는 통과하지 않은
것이다. 문서 정비만으로 지원 상향·실기 PASS·일정을 확정하지 않는다.

전체 Bluetooth catalog 완료는 M33의 후속 목표이며 v0.5.0의 지원 명칭으로 사용하지 않는다.
하드웨어에 없는 BR/EDR, 모든 SIG profile의 무제한 구현 또는 인증 자동 획득을 뜻하지도 않는다.

---

## 9. 공통 HIL fixture와 증거

| 시험군 | 최소 fixture·증거 |
| --- | --- |
| Serial fabric (`v0.4.0`) | 두 NU54DK의 controller/target peer·loopback, 안전한 배선·필요 pull-up, 기대 데이터·오류·DMA·동시성·soak 증거 |
| Analog/PWM (`v0.4.0`) | 두 NU54DK의 안전한 LOW/HIGH 입력·capture, 채널·sequence·기본 주기/듀티·동시성 표본; 정밀 교정 측정 제외 |
| Audio/QDEC (`v0.4.0`) | 검증된 PDM/I2S/quadrature 합성 peer·loopback, 실제 sample/frame/count·DMA·복구·장시간 hash; 부품별 호환성 제외 |
| Event/timer (`v0.4.0`) | loopback pins, peer/internal timestamp·count, 기본 timing·latency 기록과 DPPI ownership negative; 정밀 jitter 보증 제외 |
| BLE base | 최소 3개 NU54DK와 Android·iOS·Windows·Linux peer 환경의 확보 여부, 모델·OS version 확인; 승인 topology의 packet trace·reset/reconnect soak |
| BLE advanced 기능 | 1보드 capability·CTE TX 제어, 2보드 ISO/합성 Audio/CS 및 controller 적용 시 raw IQ, 3보드 broadcast/assistant·통합; 실제 RF 데이터/절차와 복구. 외부 audio·안테나 전환/각도·타사 peer 운용은 사용자 추후 비차단 행 |
| Mesh/coexistence | 승인 2/3노드/model 구성, 최소 802.15.4/ESB 단독 TX/RX 뒤 지원 BLE/Mesh 조합의 traffic·starvation·재시작; 수동 전원 차단은 별도 실행 계약 |

위 BLE 장비 중 M28에 필요한 NU54DK·독립 DAP/UART 3경로는 W07에서 확인했다. Packet trace는
외부 sniffer 대신 세 UART와 receiver-validated GATT/periodic sequence·payload hash를 사용했다.
M29에서 Windows/Intel 기본 GATT peer를 확인했으며 다른 OS peer·고급 RF 장비 확보 여부와 수치 합격 기준은
[v0.5.0 착수 계획](../TODO_v0.5.0.md)에서 관리한다. 연결/stream/channel 수, OS·peer 조합, 시험 시간,
허용 손실·제어 timeout·복구 횟수를 시험 전에 확정한다. 미확정 값은 PASS가 아니다.
정밀 RF/audio·거리/각도 계측 제외는 2026-09-16 사용자 결정이며 v0.4.0 시험 결과의 재사용이 아니다.

각 마일스톤 기록에는 exact Core/board/NCS/toolchain revision, pin wiring, power 조건, test command,
raw log, 사용한 경우 analyzer capture hash와 PASS/FAIL 판정을 남긴다. `v0.4.0`에서 외부 분석기·
교정 전압원·오디오 장치는 필수가 아니다. 범위 밖 계측은 `범위 밖·미측정`으로 명시한다.
한 fixture에서 못 한 필수 보드 기반 기능 항목은 `NOT RUN`으로 남기며 build 결과로 대체하지 않는다.
사용자 추후 검증으로 확정한 외부 peer·mic/speaker·외장 장치 운용의 `NOT RUN`은 v0.5.0 개발·공개를
차단하지 않는다. 해당 구현·예제·설정/연결 안내와 자동 가능한 검사는 계속 필수이며, 실물 호환성은
검증 전까지 주장하지 않는다. M31 Windows 설치·실행 gate는 필수이며, 이 외부 peer 예외를
M33의 후속 세 Host 지원 증거에 적용하지 않는다.

---

## 10. 변경 관리

1. 비교 대상이 갱신돼도 이 기준선의 commit을 바꾸지 않는다. 새 version은 별도 차이 기록으로 추가한다.
2. nRF54L15 DTS 또는 Product Specification과 instance manifest가 다르면 CI를 실패시킨다.
3. board submodule route 변경은 board 저장소에서 전기 검토·HIL 후 Core gitlink로 받아온다.
4. M23 이후 구현이 끝나기 전에는 root README의 현재 지원 상태를 상향하지 않는다.
5. 완료된 M0~M22, `v0.1.0`~`v0.3.0` 검증·릴리스 문서는 소급 변경하지 않는다.
6. API·DMA·BLE 지원 상태 변경은 manifest, generated matrix, 예제, 자동 시험과 HIL 기록을 같은
   변경에서 갱신한다.

---

## 11. 참고 자료

- [비교 Core 고정 source](https://github.com/lolren/nrf54-arduino-core/tree/a6bb99879aa14cbff362a5478d5f1189848b4200)
- [비교 Core HardwareSerial](https://github.com/lolren/nrf54-arduino-core/blob/a6bb99879aa14cbff362a5478d5f1189848b4200/hardware/nrf54l15clean/nrf54l15clean/cores/nrf54l15/HardwareSerial.cpp)
- [비교 Core Wire](https://github.com/lolren/nrf54-arduino-core/blob/a6bb99879aa14cbff362a5478d5f1189848b4200/hardware/nrf54l15clean/nrf54l15clean/cores/nrf54l15/Wire.cpp)
- [비교 Core SPI](https://github.com/lolren/nrf54-arduino-core/blob/a6bb99879aa14cbff362a5478d5f1189848b4200/hardware/nrf54l15clean/nrf54l15clean/cores/nrf54l15/SPI.cpp)
- [비교 Core BLE·Channel Sounding 상태](https://github.com/lolren/nrf54-arduino-core/blob/a6bb99879aa14cbff362a5478d5f1189848b4200/README.md)
- [Nordic nRF54L15 Product Specification](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/)
- [Nordic SAADC와 EasyDMA](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/saadc.html)
- [Nordic nRF54L15 Bluetooth qualification matrix](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54l15/page/comp/nrf54l15/nrf54l15_ble_qdid_qual_matrix.html)
- [Zephyr Bluetooth feature overview](https://docs.zephyrproject.org/latest/connectivity/bluetooth/index.html)
- [고정 NCS v3.4.0 SDC 지원표와 CTE 제한](https://github.com/nrfconnect/sdk-nrfxlib/blob/v3.4.0/softdevice_controller/README.rst)
- [고정 Zephyr BT_SIGNING 정책](https://github.com/nrfconnect/sdk-zephyr/blob/bf801e4e3d19e1ffa76164346480cb7734dd2800/subsys/bluetooth/host/Kconfig#L631)
- [고정 Zephyr EATT 정책](https://github.com/nrfconnect/sdk-zephyr/blob/bf801e4e3d19e1ffa76164346480cb7734dd2800/subsys/bluetooth/host/Kconfig.gatt#L55)
- [127번 후속 계획 정비 기록](<../04_검증 기록/127_후속_마일스톤_지원_경계와_착수_계획_정비.md>)
