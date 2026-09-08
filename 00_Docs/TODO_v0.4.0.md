# v0.4.0 개발 현황과 실행 TODO

현재 정식 배포는 **v0.3.0**입니다. v0.4.0은 T13 복구 검증 단계이며 RC·정식 공개 전입니다.
이 문서가 현재 상태와 다음 작업의 기준입니다. 세부 실행 기록을 다른 README에 복사하지 않습니다.

## 1. 현재 상태

| 마일스톤 | 상태 | 근거와 남은 일 |
| --- | --- | --- |
| T01~T09 준비, R00~R13 리팩토링 | 완료 | 준비·Host·target 근거43~66번 |
| T11 통신 단독 기능 회귀 | 완료 | source별 UART/SPI/TWI 일곱 묶음67~73번 |
| T12 GPIO·Analog·Timer·Stream 기능 | 완료 | QDEC는 알려진 문제를101번에 보고하고 검증 작업 종료 |
| T13 정상 안정성 | 완료 | 단독29/29·동시7/7, 합계36/36. 당시 source별 결과 |
| T13 고정 serial 취소/NACK | 완료 | 21/21. TWIM 네 인스턴스400/400 포함 |
| T13 PWM 복구 | 완료 | 6/6 |
| T13 serial 자원 충돌 | 사용자 수용 완료 | 예행14/14·5조건 각100회. 나머지9조건 반복 생략 |
| T13 연속 통신 종류·역할 전환 | 범위 제외 | 사용자 지시로 중단. 기존5항목을 진행률에서 제외, 재실행 없음 |
| T13 I2S/PDM 복구 | 3/4 | I2S B 공급 중단 후 정상 재시작이 남음 |
| T13 나머지 S 오류 복구·System OFF·U | 미완료 | 아래 실행 순서 참조 |
| T14~T18 결함·지원·사용자 통합 | 진행/대기 | QDEC 제한 포함, 최종 지원 승격·패키지 통합은 미완료 |
| R14·T19~T25 RC·승인·공개 | 대기 | 공개 승인과 실제 배포는 별도 |

상세 결과와 연속 전환 제외 결정은 [109번](<04_검증 기록/109_T13_S_세_복구_묶음_재검증.md>),
이번 문서 정리·S 재개는 [110번](<04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)에서 관리합니다.
기존 성공·실패 원본을 보존하며 부분 완료나 시험 제외를 새 물리 PASS로 세지 않습니다.

## 2. 현재 재개 체크포인트

**현재 작업:** 전체 문서 정리·커밋·푸시를 완료하고 현재 장치와 S 조건을 대조해 순서1~3을 재개했습니다.
I2S B는 새 계측 source182ef13의 예행 뒤5회 성공·6회차 정상 구간13word 불일치로 실패했습니다.
DMA·GPIO·IRQ·RAM과 종료 원본을 보존했으며 원인은 미확정입니다. UART20·30 A와 UART21·22·30 B
CTS100회는 완료했습니다. UART21·22 A, C01·C05 A, UART20 B는 반복 중 실패했고 원본·
양쪽 정리를 보존했습니다. C01 B도74회 뒤75회차 정상 재시작에서, C05 B도11회 뒤12회차에서 실패했습니다.
기존54조건의 확정 통과는5조건이며 실패 수정과 독립 조건 실행을 이어갑니다.
parity A 네 예행의 mask6은8N1/8E1 불일치 주입으로 생길 수 있는 parity+framing인데,
기존 판정기가 mask2만 허용해 거부했습니다. parity bit를 필수로 유지하면서 mask6도 허용하도록
고쳤습니다. 정상 구간의 오류0 기준은 유지하며 수정 source의 새 예행·100회가 필요합니다.
기존 CTS12 결과를 보존하고 parity부터 남은42조건의 실행 대열을 교체합니다.
UART20 B의 첫 수신4byte가 송신 frame2 시작과 일치했습니다. CTS 시험의 양쪽 RX 준비를
먼저 확인한 뒤 송신하는 절차를1a00a832로 커밋·푸시했습니다. exact Host108·문서·계약·정렬을
통과했고 두 역할 target·원격 Host838도 통과했습니다. UART20 B 예행 뒤61회는 성공했으나
62회차 통신·CTS 구간에서 양쪽 framing 오류가 발생했습니다. 초기 RX 준비 보완만으로
해결되지 않았으며 실패 원본과 정리를 보존하고 독립 조건을 이어갑니다.
System OFF 전용 중계는 e791a58의 RX 준비 후 응답으로 debug 유지 진단을 통과했지만
정상 mode에서는 실패했습니다.03257b6의 HFXO 보완 후에도 최초 응답 timeout이었으며 B의
RX 시작 시 LOW·이벤트 큐 초과를 기록했습니다. 양쪽 STOP·clock 참조 반환·17핀 입력을
확인했습니다.28cf880 계측에서는 A의 reset 전후 TX/RX가 모두 HIGH였지만 응답이 없었고,
B의 cleanup SWD도 No ACK였습니다. pin reset만으로 회복되지 않아 reset 유지 접속 후
실제 HALTED 상태·부팅 코드 일치를 확인하고 재개했습니다. 이후 양쪽 STOP·입력을
증명하고 UART22 B 본 검증부터 재개했습니다. B 최초 실패 시점 RAM은 보존하지 못했고,
902a1da의 fast polling 비교도 첫 중계 응답 timeout이었습니다. 이번에는 B의 부팅7ms
RX LOW와 최초 hardware framing(mask4)을 보존했고 양쪽 STOP·입력 반환도 확인했습니다.
실제 OFF 성공은0회입니다. 남은 순서1~3의 확정 완료는6/58(약10%)입니다.
S 결선을 유지합니다. U 재배치·QDEC 재진단·연속 handover·정식 공개는 이번 자동 실행에 포함하지 않습니다.

| 순서 | 결선 | 작업 |
| --- | --- | --- |
| 1 | S | I2S B 공급 중단·정상 복구.182ef13 예행PASS·5/100 뒤6회차 정상 구간13word 오류. 원본 보존·추가 원인 조사 |
| 2 | S | UART CTS12·parity/break16·RX 공급 지연8, SPIS 짧은 DMA/미준비10, TWI stuck-low4·TWIS write 공급 지연4의 기존54조건 |
| 3 | S | System OFF bridge·timer/GPIO wake. CS 조기 종료·TWIS read 지연·GPIOTE/DPPI/domain·PWM/Arduino API 충돌의 기존 요구와 구현·증거 대조 |
| 4 | U | S 범위 정리 뒤 GPIO 배치를 안내하고 현재 재배치 확인. UART00 안정성·flow·취소·재시작 |
| 5 | 해당 범위 | T14/T15 결함·지원 범위 → T16~T18 사용자 통합 → R14/T19~T21 RC·회귀·설치 → T22 공개 승인 |

### 실행 환경과 중단 조건

- 저장소: `EIDOSDATA/NU54DK_Arduino_Core`, `main`. 매 재개 시 실제 경로·HEAD·dirty·submodule을 확인합니다.
- 현재 PC 경로는 `C:/Users/eidos/GitHub/NU54DK_Arduino_Core`입니다. 새 PC에서 같은 경로를 가정하지 않습니다.
- 보드·SDK·toolchain 원본은 submodule, CI lock과 prerequisite pins를 사용합니다. SDK/서드파티는 임의 수정하지 않습니다.
- 실기 image는 clean exact source·board gitlink·역할·HEX 해시·해당 Host/target gate를 결합합니다.
  main의 문서 커밋을 이전 image의 검증 source로 바꾸지 않습니다.
- 현재 S는17신호+GND입니다. P1.04/05·P1.06/07·P2.02/04 교차, P2.07/08 미연결입니다.
  정확한 A↔B 표는 [T13 결선](../tests/hil/nu54dk/T13_PLAN.md)을 따릅니다.
- 기존 S 유지 확인은2026-09-08 22:13:18 KST부터 다음 날10:13:18 KST까지입니다.
  사용자 변경 보고·USB 이탈·확인 만료를 확인하며, 만료를 임의 연장하거나 이전 COM을 재사용하지 않습니다.
- SWD는10MHz, exact UID, 배타 lock, sector flash, `auto_unlock=false`, controlled reset/start입니다.
  원시 UID는 공개하지 않으며 자동 mass erase/unlock/recover는 하지 않습니다.
- 매 campaign의 결선 사전검사·양쪽 STOP·clock 해제·GPIO 반환을 증거로 남깁니다.
  정지를 확인하지 못하면 다음 출력을 시작하지 않습니다. 실패 원본을 보존하고 독립 항목만 계속합니다.
- 실패 소스를 무작정 반복하지 않습니다. 판정기 오류·실제 데이터 오류·미실행을 구분하고 필요한 수정을 재검증합니다.
- 단독180초·일반 동시900초·대표C05 3600초가 합의된 시간입니다. 이미 끝난 정상36항목을 다시 예약하지 않습니다.

### 구현·문서·Git 규칙

1. 사용자 지시를 먼저 적용하고 이번 T/R 범위·산출물·검사 방법을 기록합니다.
2. 주석은 한국어 Doxygen, C/C++는 BSD/Allman·4칸이며 한 줄 제어문에도 중괄호가 필요합니다.
3. 리팩토링 변경은 [R00~R14 안내](<01_아두이노 코어 설계/14_리팩토링/README.md>)와 진행 체크리스트를 대조합니다.
4. 관련 Host·target·계약·문서·정렬 검사를 수행하고 원본·미실행·실패를 구분합니다.
5. 커밋·푸시 뒤 exact SHA의 CI를 확인합니다. 진행 중 CI를 성공으로 기록하지 않습니다.
6. 작업 종료·인계 때 이 체크포인트와 해당 검증 기록을 갱신합니다. 현재 사용자 지시·실행 상태는 과거 일지보다 우선합니다.

## 3. 작업별 원본과 범위

| 작업 | 먼저 대조할 원본 |
| --- | --- |
| 전체 범위·상태 | [로드맵 §8](<./01_아두이노 코어 설계/02_구현_로드맵.md>), [경쟁 마일스톤 M24~M27](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>), [42번 합의](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>) |
| 리팩토링 안정화·선행 구조 작업 | [리팩토링 문서 안내](<./01_아두이노 코어 설계/14_리팩토링/README.md>), [통합 실행계획](<./01_아두이노 코어 설계/14_리팩토링/02_리팩토링_통합_실행계획.md>), [진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>) |
| 인스턴스·공유 자원·DMA | [inventory JSON](../variants/nu54dk/peripheral-manifest.json), [생성 matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>), [serial 계약 JSON](../variants/nu54dk/serial-fabric-contract.json) |
| 통신·analog·stream 후보 | [SerialFabric](../cores/arduino/nucode/SerialFabric.h), [AnalogFabric](../cores/arduino/nucode/AnalogFabric.h), [StreamFabric](../cores/arduino/nucode/StreamFabric.h), [Kconfig](../zephyr/Kconfig), [M24 계약](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>) |
| HIL·결선·환경 | [HIL README](../tests/hil/nu54dk/README.md), [Windows 개발환경](<./02_빌드 설계/09_Windows_개발환경_설정.md>), [보드 회로도](<../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>)와 해당 board source |
| M25·M26 구현 이력 | [37번 M25](<./04_검증 기록/37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>), [M26 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>), 41번의 최신 기본 실기 증거 |
| RC·공개 | [M27 도구 안내](../tools/release/M27_README.md), [RC 준비 문서](<./05_릴리스/v0.4.0-rc.1/README.md>), [readiness](../variants/nu54dk/v0.4.0-release-readiness.json) |

범위는 Windows용 `v0.4.0` 코어 기능이다. Linux/macOS 지원과 새 BLE 확장을 추가하지 않는다.
온보드 자원·두 NU54DK의 안전한 peer/loopback·합성 신호·capture를 사용하며, 필요한 점퍼·풀업은
시험별로 안내한다. 외부 마이크/코덱/엔코더별 호환성, 정밀 ADC·jitter·전력·음질·신호 품질은
필수 gate 밖이다. **코어의 실제 데이터 경로·DMA·오류 복구·동시성·soak는 면제하지 않는다.**
합성 peer로도 신호를 생성·검증할 수 없는 필수 경로는 HOLD이며, 추가 범위 변경은 사용자에게 확인한다.

생성 문서는 JSON·생성기를 고친 뒤 재생성한다. Board submodule, SDK와 기존 공개 자산은 임의로
수정하지 않는다. `v0.3.0` 미만 공개 공급은 종료했다. 이전 tag·asset 원본은106번의 archive에 보존하며 현재 공개 자산은 변경하지 않는다.

## 4. A단계 — 결선 없이 준비 (T01~T09)

- [x] **T01 — 최종 시험 목록 확정**
  - 상태·선행: 완료 / TODO·42번 합의·41번 실기 기록과 exact board gitlink 대조. 결선 불필요.
  - 할 일: 인스턴스·모드·route별 test ID, 속도, buffer 크기, 반복/soak 시간, 예상 결과·오차·오류 조건을 정의한다.
  - 완료 기준: 재사용/신규 시험, 온보드/결선/범위 밖, 적용 가능한 DMA·flow control·errata가 구분된 시험표와 누락 검사가 있다.
  - 증거: [시험 목록](<./01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>)과 [43번 준비 기록](<./04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>). 75 identity·19 family와 executable vector/fixture 고정, 누락 검사 PASS.

- [x] **T02 — 현재 코드와 검증 상태 대조**
  - 상태·선행: 완료 / T01과 43번의 기능군별 source·공개 경계·남은 보완 및 75개 생성 matrix 대조. 결선 불필요.
  - 할 일: source·build·실기·공개 API·설치 profile을 별도 축으로 대조하고 누락 구현을 식별한다.
  - 완료 기준: 모든 대상에 근거 파일/시험/commit 또는 구체적 미완료 사유가 연결되고 T04~T07·T16의 보완 목록이 있다.
  - 증거: 43번 §기능별 대조·PREP-01~08·T04~T08 구현 기록. 실제 HIL 미실행과 T16 공개 통합은 별도 유지.

- [x] **T03 — 두 보드 공통 실행기 준비**
  - 상태·선행: 완료 / SWD protocol·exact image/UID·role/nonce·배타 lock·실패 journal/STOP·dual-boot helper와 외부 명시적 CLI 준비.
  - 할 일: DUT/peer UID·COM·role·exact source/HEX hash를 결합하고 명령 순서·nonce·timeout·실패 log·재개 경계를 구현한다.
  - 완료 기준: 동일 보드 중복 선택, role 반전, stale packet, 다른 commit, noisy/truncated frame, 중단 후 잘못된 PASS 재사용을 Host 시험에서 거부한다. 실행 중 보드 점유는 배타적이다.
  - 증거: `v04_pair.py`, `v04_campaign.py`, 두 fixture runner와 Host 전체 gate PASS. stale·중복·중단·poison 조건을 거부.

- [x] **T04 — UART·SPI·I2C 시험 프로그램 준비**
  - 상태·선행: 완료 / 온보드 UART·cancel/handover, 외부 UART 135·SPI 1,513·TWI 328개 sync/async·single/double-buffer·flow/error/cancel/NACK/stuck-low/clock-stretch·정상 재시작 image/oracle·gate·CLI 준비. 외부 실행은 T10 이후.
  - 할 일: UARTE 5개, SPIM/SPIS 각 5개, TWIM/TWIS 각 4개의 승인 경로와 역할에 송수신·flow control·DMA·buffer 전환 시험을 연결한다.
  - 완료 기준: 각 대상의 DUT/peer image와 host 판정이 build/unit을 통과하고 시험표와 연결된다. PMIC는 승인된 읽기 전용 경계를 유지한다.
  - 증거: Host 전체 PASS, `C:/r45` pair image 포함 full20 build-only PASS. 온보드 기존 PASS는 41번, 외부는 NOT RUN.

- [x] **T05 — ADC·PWM·타이머·이벤트 시험 프로그램 준비**
  - 상태·선행: 완료 / 내부 VDD·AVDD와 timer/event, 외부 AIN0~3/AIN7·PWM20/21/22 channel slot 0~3·단일/이중 DMA 판정 준비. AIN4는 405 오픈드레인, AIN5는 406 입력 바이어스로 추가 기능 시험하며 AIN6/407은 버튼 공유 입력 바이어스 시험으로 준비하고 실기는 별도 판정한다.
  - 할 일: 안전한 ADC 입력·scan/sample 순서·DMA, PWM 채널/sequence의 peer capture, timer/event/DPPI 소유권을 시험한다.
  - 완료 기준: 예상 값·count·기본 timing 허용 범위를 검사하는 image/runner와 Host 시험이 준비된다. 교정 전압·정밀 jitter 보증과 구분한다.
  - 증거: signal fixture 401~404/408, fixture별 48 vector, Host PASS와 M25 Analog/pair target build PASS. 이 준비 시점에는 외부 신호 NOT RUN이었다. 현재 401~408 실기는 T12와 74~79·82~83번에 구분 등록했다.

- [x] **T06 — PDM·I2S·QDEC 합성 신호 프로그램 준비**
  - 상태·선행: 완료 / QDEC sampling/oracle·Stream DAP 격리와 PDM SPIS clock 동기 source·I2S 양방향 pattern·QDEC PWM quadrature generator/receiver 준비. 물리 신호 성립은 T12에서 검증.
  - 할 일: PDM20/21, I2S20, QDEC20/21의 시험 신호 생성·수신, clock 역할, frame/sample 순서, quadrature 방향/count를 구현한다.
  - 완료 기준: 기대 패턴을 독립적으로 판정하고 peer 신호 능력·속도 한계를 명시한 image/runner가 build/unit을 통과한다. 미구현 신호 발생은 HOLD다.
  - 증거: fixture 420/430/440, PDM96·I2S96 vector와 Host 판정 PASS, M25 Stream/pair target build PASS. 준비 시점에는 실기 NOT RUN이었으며 현재 420 기능 48·준비 취소 6 PASS는 [85번](<04_검증 기록/85_T12_Fixture_420_current_source_QDEC_재검증.md>)에 구분한다. 430 실기는 전체 192개 PASS이며 440의 후속 실행은 88번의 부분 DMA 통과·stereo 실패로 구분한다.

- [x] **T07 — DMA 오류·복구·동시성·장시간 시험 준비**
  - 상태·선행: 완료 / DMA RAM 끝·overflow·정렬 사전 거부, 오류/cancel 뒤 복구, SPIM00+TWIM22와 PWM20+PWM21+SAADC 최소 동시성, bounded 연속 campaign 준비. 실제 soak는 T13.
  - 할 일: cancel/stop/restart, 적용 가능한 overflow/underrun·bus error·System OFF 복구, buffer 반환, 충돌 거부·허용 최대 동시 조합·soak를 구현한다.
  - 완료 기준: 오류 유도 방법·정상 복구 상태·손실 카운터·자원 누수 판정·지속시간이 정의된다. Host negative와 실물 오류 주입을 구분하고 불가능한 조건은 남긴다.
  - 증거: DMA/수명주기/fixture/campaign Host PASS와 full20 target build PASS. 더 넓은 허용 topology와 현행 180/900/3600초 결과는 T13이며 미실행.

- [x] **T08 — 시험별 안전한 결선표와 스위치 안내 작성**
  - 상태·선행: 완료 / 회로도 connector mapping, fixture 18개(405·406·407 추가), TWI pull-up과 analog/stream 역할·금지 net·스위치 조건 작성. 아직 T10 결선 요청 아님.
  - 할 일: 회로도·pinctrl과 대조해 묶음별 DUT↔peer 핀, GND·전압·pull-up·출력 방향·DAP UART switch·제어 채널을 명시한다.
  - 완료 기준: 전원 차단 후 연결/변경 순서, 출력 충돌 방지, 필요한 부품과 사용자 확인 절차가 있다. 금지된 P2 bank와 PMIC/LED 공유 신호를 무단 사용하지 않는다.
  - 증거: `v04_fixtures.json`, HIL README, fail-closed confirmation template와 Host catalog/조건 검사 PASS. 묶음마다 T10 확인 반복.

- [x] **T09 — Host 검사·시험 펌웨어 빌드·무배선 추가 시험**
  - DAP UART 연결 후 추가 회귀: 373d98d 온보드 18 PASS와 18a7cbe BLE M19/M20/M21 pair PASS. idle bias 교정·처음 실패·새 exact 결과는 [66번 기록](<./04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에 분리 보존. 외부 current-source T11 NOT RUN.
  - R13 이후 회귀: exact c94298f의 두 보드에서 온보드 904 PASS. [65번 기록](<./04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>)에 기존 T09와 구분해 등록. 외부 current-source T11 NOT RUN.
  - 상태·선행: 완료 / clean `696defb`와 exact board gitlink에서 두 보드 역할 image와 primitives를 재검증. 외부 실행은 T10 전 금지.
  - 할 일: Host/계약/문서 검사와 필요한 target build·CI를 실행하고 온보드 UART·I2C·복구 등 가능한 추가 기능을 시험한다.
  - 완료 기준: 새 source의 image·runner·증거가 결합되고 무배선 가능 항목의 기대 결과가 통과한다. 외부 경로는 build-only로 명확히 남긴다.
  - 결선·증거: 외부 점퍼 없이 USB·지정 UID만 사용. M12 Host 전체와 `C:/r48` pair 2/2 build PASS. 두 역할에서 ping, TWIM20/21/22 PMIC, TIMER 7개 44 capture, 내부 VDD/AVDD SAADC 400회, PWM20+PWM21+SAADC 동시성까지 합계 904건 PASS. [결과](<./04_검증 기록/evidence/696defb/pair-primitives-696defb.json>)와 동일 경로 `.json.jsonl` journal에 exact image·UID hash·commit을 보존했다. 외부 경로는 `NOT RUN`.

## 5. B단계 — 사용자 결선 뒤 기능 검증 (T10~T15)

- [x] **T10 — 첫 시험 묶음의 결선 확인**
  - 상태·선행: 완료 / 사용자가 Fixture 101 배선·DUT D/peer E·양쪽 `DISABLE_UART` 분리·USB 재연결을 확인.
  - 할 일: 정확한 두 보드 role과 승인 연결표를 안내하고 사용자의 완료 확인 뒤 preflight한다.
  - 완료 기준: 현재 session의 배선표 개정·두 UID·스위치·전압/pull-up 조건이 기록된다. 사진/장치 열거만으로 전기적 연결 전체를 검증했다고 하지 않는다.
  - 증거: [44번 Fixture 101 기록](<./04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>). 이후 묶음의 결선 변경 때마다 confirmation을 반복한다.

- [x] **T11 — M24 통신 인스턴스 기능 검증**
  - 상태·선행: 완료 / Fixture 101~103 UART 정상 4,860·예상 오류 72·cleanup 6건 PASS. Fixture 201~203 SPI 계획 record 54,505개·cleanup 6건 PASS. Fixture 301 TWI 기능 record 1,986개·cleanup 2건 PASS. 23개 serial personality의 승인된 단독 경로를 실제 두 보드에서 검증했다.
  - 할 일: UART·SPI·I2C 승인 경로를 역할별로 실행하고 실제 데이터·mode·DMA 결과를 비교한다.
  - 완료 기준: T01 표의 각 단독 기능 결과가 exact evidence에 연결되고 나머지 16개 외부 경로를 build로 대체하지 않는다. 실패는 T14로 넘긴다.
  - 결선·증거: [44번 Fixture 101](<./04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>), [45번 Fixture 102](<./04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>), [46번 Fixture 103](<./04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>), [47번 Fixture 201](<./04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>), [48번 Fixture 202](<./04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>), [49번 Fixture 203](<./04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>), [50번 Fixture 301](<./04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>) exact evidence 등록. TWI는 외부 저항 없이 target TWIS 내부 pull-up을 사용했다.

### T11→최종 physical campaign 리팩토링 gate

이 gate는 새 제품 마일스톤이나 T 번호가 아니다. T14의 결함 수정·재시험을 리팩토링 문서의
R00~R14와 연결하고, 구조 변경 뒤 같은 결선을 다시 반복하지 않도록 R00~R13을 최종 외부 HIL보다
먼저 완료하는 실행 순서다.

- [x] **R00:** 현재 commit, board/NCS/toolchain, 공개 API·CLI·artifact·저장 형식, 대표 ELF와
  기존 Host/target/HIL을 [51번 characterization 기준선](<./04_검증 기록/51_R00_리팩토링_기준선.md>)으로 고정했다.
- [x] **R01:** SPIM/SPIS/TWIM/TWIS source를 명시적인 Core CMake target에 등록하고 선택/비선택·
  단독·허용 조합의 resolved config, target membership와 link를 검증한다.
- [x] **R02:** Serial stale completion·timeout·DMA buffer 반환·같은 handle의 교차 호출을 수정하고
  최종 Fixture 101~301 회귀 범위를 기록한다. 중간 PASS 캠페인은 만들지 않는다.
- [x] **R03:** Analog/Stream의 ISR 진단 snapshot·overflow·stop generation과 lock 대기를 파일 이동
  없이 수정하고 R11 및 최종 T12가 지킬 동작 계약을 고정한다.
- [x] **R04/R05:** LittleFS File retain/release와 제품 identity 원본을 구조 분할 전에 정리한다.
- [x] **R06~R07:** `nu54-builder` 순수 모듈과 `EventFabric` 기계적 분할 파일럿을 외부 계약·target
  결과가 유지되는 작은 변경으로 완료한다.
- [x] **R08~R10:** 자원/route 책임, Arduino SPI facade/backend, Serial orchestration·동시 호출 정책을
  분리하고 최종 M24·동시성 회귀 범위를 누적한다.
- [x] **R11~R12:** Analog/Stream peripheral별 분할과 BLE/Storage 수명주기 구조화를 완료하고 최종
  M25·BLE·Storage 회귀 범위를 누적한다.
- [x] **R13:** package tool·정책 생성·Kconfig/CMake·문서/증거 구조화를 완료하고 전체 Host·target·예제·
  package gate로 최종 실기 source를 고정한다.
- [x] **current-source T11 회귀:** R00~R13 최종 exact source로 영향받는 UART·SPI·TWI 단독 기능을
  재검증하고 나서 T12로 전환한다.
  - 진행: exact 154324c Fixture 101 기능 1,644 PASS. [67번 기록](<./04_검증 기록/67_T11_Fixture_101_current_source_UART_회귀.md>) 참조. Fixture 102는 exact a49cc0d 기능 822 PASS로 [68번 기록](<./04_검증 기록/68_T11_Fixture_102_current_source_UART_회귀.md>)에 등록했다. Fixture 103은 exact 7aece93 기능 2,466 PASS로 [69번 기록](<./04_검증 기록/69_T11_Fixture_103_current_source_UART_회귀.md>)에 등록해 승인 UART route 세 묶음을 완료했다. Fixture 201도 exact 0f429e7 기능 18,169 PASS로 [70번 기록](<./04_검증 기록/70_T11_Fixture_201_current_source_SPI_회귀.md>)에 등록했다. Fixture 202도 exact 1349e20 기능 9,084 PASS로 [71번 기록](<./04_검증 기록/71_T11_Fixture_202_current_source_SPI_회귀.md>)에 등록했다. Fixture 203도 exact be49207 기능 27,252 PASS로 [72번 기록](<./04_검증 기록/72_T11_Fixture_203_current_source_SPI_회귀.md>)에 등록해 승인 SPI 세 route를 완료했다. Fixture 301도 exact 9a63251 기능 1,986 PASS로 [73번 기록](<./04_검증 기록/73_T11_Fixture_301_current_source_TWI_회귀.md>)에 등록했다. 일곱 묶음의 61,423개 기능과 동일 컴파일 입력을 대조해 current-source T11 단독 회귀를 완료했다. T12 Fixture 401~404도 각각 48개를 통과했으며 405·406·407 각각 12개와 408 PWM 48개를 통과했으며 420 QDEC도 완료했으며 430 I2S는 exact 36ba819에서 192개 PASS다. 현재 440 기본 기능·밀도와 연속 96개 전체를 통과했다.
- [ ] **R14:** T16~T18의 사용자용 통합까지 끝난 뒤 current-source T11과 T12~T15 결과를 포함한
  `v0.4.0` RC를 다시 고정하고 T19로 전환한다.

세부 상태와 완료 조건은 [리팩토링 진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)가
소유한다. R01~R13 뒤 runtime byte가 바뀌면 과거 T11 PASS를 새 source 결과로 복사하지 않는다.
외부 결선 PASS 캠페인은 R13 뒤 최종 source에 한 번 수행한다.

- [x] **T12 — M25 입력·출력·스트림 기능 검증**
  - 완료 결정: 2026-09-08 사용자가 T12 기능검증과 QDEC 문제 보고 후 검증 작업 완료를 명시했다. 실제 미수행 반복과 실패 원본은 유지하며 새 PASS를 만들지 않는다.
  - 최신 진행: 100번의 GPIO/GPIOTE 2,502·PWM 675+288·I2S 432 PASS. TIMER 기능은 95번의 7,040회 PASS 범위로 완료 정리했다. QDEC는 문제·보완 기록 후 진단 종료이며 기능 240조건의 전체 PASS는 아니다. 외부 ADC 초기 반복 수와 실행 차이는 103번에 보존한다. 다음 마일스톤은 T13 준비·실기다.
  - 상태·선행: 완료(사용자 확인, QDEC 알려진 문제 보고 포함) — Fixture 401~404·408 각각 PWM 48 PASS·405 AIN4 오픈드레인·406 AIN5/407 AIN6 입력 바이어스 각각 12 PASS, 420 QDEC 기능 48·준비 취소 6 PASS, 430 I2S 192개 PASS; 440 기본 PDM·밀도 PASS·연속 96/96 PASS / T05·T06·T09, R00~R13과 current-source T11 회귀 완료, 해당 T10 확인.
  - 할 일: ADC·PWM·timer/event·PDM·I2S·QDEC의 물리 신호와 예상 sample/frame/count를 비교한다.
  - 완료 기준: 합성 peer 자체의 동작과 코어 기능을 구분해 검증하고 각 instance/mode의 증거가 있다. 신호 생성 실패는 미완료이지 계측 면제가 아니다.
  - 결선·증거: ADC401~408은74~79·82~83번, QDEC 초기420은85번, I2S430은87번, PDM440은91~92번, TIMER는95번, 공통 기능은100번에 보존한다. QDEC 제한은101번, 반복 수 대조와 TIMER 완료 결정은103번을 따른다. [검증 기록 목차](<04_검증 기록/README.md>)에서 해당 원본을 확인한다.

- [ ] **T13 — 복구·동시 실행·장시간 안정성 검증**
  - 현행 시간 기준: 사용자 지시로 단독 각 인스턴스 180초. 동시 각 확정 조합 900초, 전체 대표 고부하 한 조합 3600초로 대체. 결과에는 요청/실제 연속 시간을 모두 기록하고 3분을 10분·2시간 통과로 확대하지 않는다.
  - 상태·선행: **S 재개 준비: 정상 안정성36/36·고정 serial21/21·PWM6/6 완료, 자원 충돌 사용자 수용 완료, stream3/4·다른 오류 복구 잔여. 연속 전환은 범위 제외** / T07·해당 T11/T12 단독 PASS·해당 T10 확인. QDEC20/21 단독과 C07은 알려진 문제 보고 후 현재 실행 목록에서 제외하며, T12 완료를 다시 보류하지 않는다.
  - 할 일: 허용 topology의 동시 부하, 충돌 negative, 오류 주입·복구와 약속한 soak를 검증한다. 연속 handover 묶음은 사용자 결정으로 제외하며 재실행하지 않는다.
  - 완료 기준: source·topology·rate·시간·buffer·loss·latency/CPU 관측 방법과 누수/복구 판정이 기록된다. 장시간 시험을 코드 구현만으로 완료 처리하지 않는다.
  - 결선·증거: [T13 계획](../tests/hil/nu54dk/T13_PLAN.md)과 생성 topology JSON에 원래 계획과 현재 제외 범위를 구분한다. QDEC와 연속 전환 제외 및 최신 실행 상태는 이 문서 상단을 따른다. 기본 System OFF wake 근거와 T13의 새 요구를 먼저 대조하며 격리·재연결을 미확정 필수 단계로 안내하지 않는다.

- [ ] **T14 — 발견된 결함 수정과 재시험**
  - 현재 미해결: 101번 QDEC 동작 중 수동 read/clear 누산 누락. 마지막 일반 9/30·IRQ 보호 7/30이 399/400으로 실패했다. 사용자 지시로 진단 반복을 종료했으며 제품 core는 수정하지 않았다. 짧은 SAMPLE/REPORT IRQ 40회 일치는 대체 API의 기능/안정성 자격이 아니다.
  - 상태·선행: 진행 중 / Fixture 101 deferred RX 분기, Fixture 201 RXDELAY, Fixture 301 TWIS 지연 buffer 재개는 각각 exact 수정 뒤 전체 재시험 PASS. R01~R13은 완료했다. 420 HIL의 파형·준비 취소 교정은 exact 6bd8d3f에서 재시험 PASS. 430 짧은 buffer 오류는 exact 36ba819에서 교정·전체 재검증 PASS이며 공용 PWM 미시작 start_via_task STOP timeout은 94번의 080d771 수정·두 보드 회귀로 해결했으며, 440 stereo 위상과 모노 gate 준비 순서는 기본 전체 재시험에서 교정됐으며 연속 96개 전체 재시험도 통과했다.
  - 할 일: 실패 재현·수정·regression test를 연결하고 관련 온보드/기존 기능을 재검증한다. M26 TEMP/WDT 등 영향받는 근거도 재판정한다.
  - 완료 기준: release를 막는 미해결 코어 결함이 없고 변경된 image의 필요한 기능 시험이 통과한다. 실패 기록은 보존한다.
  - 결선·증거: 재시험 대상에 따라 필요. Fixture 201 실패·교정·전체 PASS는 [47번 기록](<./04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>), Fixture 301의 무효 결선·실패·교정·전체 PASS는 [50번 기록](<./04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>)에 등록했다. R00~R14의 진행은 [리팩토링 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)에 기록한다.

- [ ] **T15 — 실기 결과와 지원 범위 확정**
  - 상태·선행: 대기 / R00~R13 최종 source의 current-source T11과 T12~T14.
  - 할 일: instance·mode·route·rate·동시 조합별 결과를 matrix/manifest/검증 기록에 반영한다.
  - 완료 기준: 요구된 기능 HIL을 증거로 판정하고 미측정 품질은 범위 밖으로 표시한다. M24/M25 physical gate가 적법하게 갱신되며 unsupported 경로를 숨기지 않는다.
  - 결선·증거: 정리 자체는 불필요. 아직 전체 지원 승격 없음.

## 6. C단계 — 사용자용 패키지와 최종 RC (T16~T21)

- [ ] **T16 — 검증된 후보 API를 사용자용 설치 경로에 통합**
  - 상태·선행: 대기 / T15; 사전 설계·예제 초안은 준비 가능하나 지원 승격은 HIL 이후.
  - 할 일: Kconfig 후보와 설치 profile·공개 header·사용 예제·capability를 통합한다. 일반 사용자가 임의 raw 설정 편집을 하지 않도록 사용 경로를 정리한다.
  - 완료 기준: 실제 설치본에서 기능을 선택·사용하고 기존 singleton identity와 충돌 계약이 유지된다. 변경된 실행 코드/profile은 영향받는 HIL을 다시 통과한다.
  - 결선·증거: 코드·패키지 준비에는 결선 불필요, 영향받는 실기는 해당 결선 필요. 증거 미등록.

- [ ] **T17 — 문서·지원 매트릭스 정리**
  - 상태·선행: 기존 문서 유지 중, 최종 정리는 대기 / T15·T16.
  - 할 일: README·API·예제·pin/ownership·제한·환경·마일스톤·migration/release notes를 실제 범위와 맞춘다.
  - 완료 기준: 상태 칸은 일관된 상태값만 쓰고 제한은 설명으로 분리한다. 생성 원본/문서가 일치하며 과거 검증·공개 자산을 소급 변경하지 않는다.
  - 결선·증거: 불필요. 102번에 이번 개발 문서 유지 검사를 등록한다. T15/T16 이후 최종 지원·설치 경로·migration 문서 검사는 별도로 필요하다.

- [ ] **T18 — M27 정식 공개 절차 준비**
  - 상태·선행: 비공개 prepare 도구만 있음, stable 절차 미완료 / T15~T17.
  - 할 일: RC→stable package·검증·공개 경로를 별도 변경으로 준비하고 잘못된 version/commit·누락 evidence·기존 asset 덮어쓰기를 거부하도록 검사한다.
  - 완료 기준: prepare/dry-run과 실제 publication이 구분되고 모든 technical gate·최종 승인 전에는 tag/Release/index 쓰기가 불가능하다. 계약/unit 검사를 통과한다.
  - 결선·증거: 준비에 불필요. T18 완료가 공개 실행 허가는 아니며 증거 미등록.

- [ ] **T19 — RC 소스 고정과 전체 회귀 검사**
  - 상태·선행: frozen RC 없음 / R14와 T14~T18.
  - 할 일: exact clean Core/board/SDK/toolchain과 예제 집합을 고정하고 Host·문서·inventory·필요한 기존 회귀·전체 target build·CI를 실행한다.
  - 완료 기준: 고정 RC의 모든 해당 gate와 artifact provenance가 통과한다. 소스가 바뀌면 영향 분석 후 필요한 gate를 다시 실행한다.
  - 결선·증거: software gate에는 불필요, 관련 실기 회귀는 별도. 증거 미등록.

- [ ] **T20 — RC 패키지 재현성·설치 수명주기 검증**
  - 상태·선행: 과거 비공개 29/29 기록만 있음, 최종 검증 대기 / T19.
  - 할 일: ZIP·SBOM·checksum·license·manifest를 독립 생성 두 번으로 비교하고 격리 설치·전체 예제 build·실제 upload·제거·재설치·버전 전환을 검사한다.
  - 완료 기준: 현재 예제 전체(기존 29개 + 새로 추가한 예제)를 lock/발견 목록과 대조한다. 직접 staging compile을 Boards Manager 전체 lifecycle로 대체하지 않는다.
  - 결선·증거: 설치/compile에는 불필요, upload에는 지정 USB 보드 필요; 기능별 실행은 해당 결선 필요. 최종 증거 미등록.

- [ ] **T21 — 정식 0.4.0 패키지 생성·최종 검사**
  - 상태·선행: 대기 / T19·T20.
  - 할 일: stable metadata와 exact commit으로 비공개 산출물을 만들고 이중 재현, 설치본 예제·실제 upload, RC 대비 runtime payload를 검사한다.
  - 완료 기준: metadata-only 전환의 실행 코드 동등성이 입증되거나, 실행 코드가 다르면 영향받는 build/실기/설치 검증을 재수행한다. 기술 gate 결과와 후보 최종 문서가 일치한다.
  - 결선·증거: package 검사는 불필요, 업로드는 USB, 변경 기능은 해당 결선 필요. 아직 tag·Release·공개 index를 만들지 않음.

## 7. D단계 — 공개와 마무리 (T22~T25)

- [ ] **T22 — 최종 결과 확인과 공개 승인**
  - 상태·선행: 사용자 승인 대기 / T21까지 기술 gate 충족.
  - 할 일: 대상 commit/version·필수 검증·제외한 품질 측정·known limitations·공개할 자산을 사용자에게 제시한다.
  - 완료 기준: 해당 결과에 대한 프로젝트 소유자의 명시적 승인 근거가 기록된다. 42번 범위 조정이나 TODO 작성 요청을 최종 승인으로 취급하지 않는다.
  - 결선·증거: 불필요, 사람의 승인 필요. 승인 근거 미등록.

- [ ] **T23 — v0.4.0 태그·GitHub Release·자산 공개**
  - 상태·선행: 대기 / T21·T22, remote exact commit·기존 tag/asset 상태 확인.
  - 할 일: 승인한 commit에 tag를 만들고 검증된 asset·release notes를 공개한 뒤 stable index에 등록한다.
  - 완료 기준: 공개 commit·URL·크기·hash가 승인한 산출물과 일치하고 기존 공개 자산이 보존된다. 중간 실패는 상태 확인 후 안전하게 재개하며 같은 버전의 다른 bytes로 덮어쓰지 않는다.
  - 결선·증거: 불필요, 외부 공개 작업. 현재 공개 안 됨.

- [ ] **T24 — 공개 URL에서 최종 설치 검증**
  - 상태·선행: 대기 / T23.
  - 할 일: 새 격리 환경에서 실제 공개 index/archive를 받아 설치·build·upload·제거·재설치·전환을 확인한다.
  - 완료 기준: 로컬 staging/cache만으로 성공했다고 하지 않고 공개 다운로드의 version·hash·설치/실행 근거를 남긴다. 실패하면 최종 완료를 보류하고 공개 자산 불변 정책에 맞게 처리한다.
  - 결선·증거: 대표 upload는 USB 필요; 지정 기능 실행은 해당 결선. 공개 URL 검증 증거 미등록.

- [ ] **T25 — 최종 문서·커밋·푸시·CI·작업 폴더 정리**
  - 상태·선행: 최종 정리 대기 / T23·T24 및 미해결 항목 없음.
  - 할 일: 공개 결과·release identity·검증 기록·README·로드맵을 마무리하고 commit/push·최신 CI를 확인한다. 보존할 증거와 재생성 가능한 임시 출력물을 분리한다.
  - 완료 기준: 근거가 영구 보존되고 남은 이슈/프로세스/미추적 변경이 설명되며 재개할 누락 작업이 없다. 정리는 정확히 확인한 작업 경로만 대상으로 한다.
  - 결선·증거: 문서·정리에는 불필요. TODO 보관/삭제는 10절을 따르며 자동으로 함께 삭제하지 않는다.

## 8. 남은 release gate와 TODO 연결

| Readiness gate | 연결 작업 | 현재 판정 |
| --- | --- | --- |
| `m24_fixture_hil` | T04·T07~T11·T13~T15 | 필수 physical HOLD |
| `m25_fixture_hil` | T05~T10·T12~T15 | 필수 physical HOLD |
| `host_regression`, `documentation`, `zephyr_repro_build` | T16~T19, T21의 변경 영향 재검증 | frozen RC pending |
| `package_reproducibility` | T20·T21 | frozen RC pending |
| `boards_manager_lifecycle` | T20·T21; 공개 후 검증은 추가로 T24 | 필수 physical HOLD |
| `project_owner_approval` | T22 | human HOLD |

M23·후보 source/build·기본 onboard·M26 판정·기존 자산 불변 gate의 근거는 기존 ledger에 있다.
이 목록을 만들었다고 gate state를 바꾸지 않는다. 준비 완료와 실기 PASS, RC 통과와 정식 공개,
정식 공개와 공개 URL 검증 완료를 각각 구분한다.

## 9. 매 작업 종료 시 남길 인계 내용

2절 체크포인트를 갱신하고, 실제 결과는 검증 기록에 추가한 뒤 관련 T 항목의 `증거`에 링크한다.
새 컨텍스트에서 직전 명령을 무작정 다시 실행하지 않도록 다음 정보를 남긴다.

- 수행한 T 번호와 완료/부분/실패, 변경 파일과 commit·push 상태.
- 실행 명령, exact source/board/image hash, 결과·log/evidence 경로, 실제 시험과 mock의 구분.
- 중단 사유, 살아 있는 프로세스/세션, 보드 role·마지막 image·COM·스위치·결선 상태.
- 다음에 할 **구체적 한 행동**, 선행조건, 사용자가 해야 할 결선·재연결·승인.
- 재사용 가능한 build/cache의 identity와 재검증 범위. Commit/hash가 다르면 이전 성공을 이어 붙이지 않는다.
- CI run URL·대상 commit·확인 시각·상태. 미완료 run을 완료로 적거나 확인 없이 background 작업을 약속하지 않는다.

## 10. TODO 보관·삭제 조건

현재는 활성 문서이므로 삭제하지 않는다. 기본은 완료 후 보관이며, 사용자가 허용한 정리 범위에서
다음 조건을 모두 충족하면 archive 또는 삭제할 수 있다.

1. T01~T25 전체 완료와 정식 공개 URL 검증이 끝났고, 재개할 작업·미해결 문제·사용자 요청이 없다.
2. 결정·제한·최종 지원 matrix·명령·실제 증거·공개 identity가 영구 문서에 옮겨져 TODO가 유일한 근거가 아니다.
3. 삭제/이동 대상은 **이 TODO 파일**로 특정한다. 검증 기록·readiness 참조·공개 asset·SDK·사용자 파일은 포함하지 않는다.
4. [루트 작업 지침](../AGENTS.md), README, 문서 안내, 로드맵, RC·도구 안내 등 들어오는 링크를
   같은 변경에서 최종 기록 또는 보관 위치로 바꾸고 문서 검사를 통과한다.
5. 정리 결과와 Git 복구 가능 여부를 남기고 commit/push한다. 미완료 체크를 지워 완료처럼 보이게 하지 않는다.
