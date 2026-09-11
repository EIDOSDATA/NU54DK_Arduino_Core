# v0.4.0 개발 완료와 실행 기록

현재 정식 배포는 **v0.4.0**입니다. 합의한 T13 S/U부터 T22 승인, T23 GitHub Release와 stable
index 공개, T24 공개 URL 설치 수명주기까지 완료했습니다. T25에서는 공개 결과와 영구 증거를
문서에 반영하고 공개 후 stable 정책·회귀 검사를 갱신했습니다. v0.4.0의 T01~T25는 모두
완료됐으며 다음 제품 개발은 제품 로드맵에서 관리합니다.
최종 상태는 이 문서에서 관리하고, 실행별 원본은 [검증 기록](<04_검증 기록/README.md>)에 보존합니다.

## 1. 현재 상태

| 마일스톤 | 상태 | 근거와 남은 일 |
| --- | --- | --- |
| T01~T09 준비, R00~R13 리팩토링 | 완료 | 준비·Host·target: 43~66번 |
| T10 첫 시험 결선 확인 | 완료 | Fixture 101의 보드·DAP UART 분리·USB 재연결: 44번 |
| T11 통신 단독 기능 회귀 | 완료 | source별 UART/SPI/TWI 일곱 묶음: 67~73번 |
| T12 GPIO·Analog·Timer·Stream 기능 | 사용자 수용 완료 | 합의한 기능 범위 완료, source별 원본은 74~103번에 보존 |
| T13 정상 안정성 | 완료 | 단독 29/29 + 동시 7/7 = 36/36, 대표 C05 3600초 포함. 각 시험 당시 source의 결과 |
| T13 고정 serial 취소/NACK | 완료 | 21/21 |
| T13 PWM 복구 | 완료 | 6/6 |
| T13 serial 자원 충돌 | 사용자 수용 완료 | 예행 14/14, 5조건 각 100회. 나머지 9조건 반복 생략 승인 |
| T13 I2S/PDM 복구 | 4/4 | I2S role2 공급 중단·재시작 정식 100/100 완료. 111번 |
| 요청한 잔여 S 1~3단계 | **범위 종료: PASS 56 + 제외 2 / 58** | System OFF 2조건은 기존 M15 실기와 중복되는 T13 추가 결합 시험으로 제외. 113번 |
| T13 U 준비·실행 | **완료** | `4f380931` exact image에서 UARTE00 180초, RTS/CTS 200/200, TX/RX 취소 400/400 PASS. 115번 |
| T14 결함·충돌 판정 | **완료** | PWM 자원 식별 1건 해결, 세 미커버 요구 판정 완료. 116번 |
| T15 지원 범위 확정 | **완료** | M24/M25 fixture physical gate PASS. 당시 QDEC partial·비공개 판정은 124번에서 제한 명시 공개 지원으로 재확정 |
| T16 설치 통합 | **완료** | `fabric` profile·facade·예제·30개 설치 목록 통합. 118번 |
| T17 문서·지원 매트릭스 정리 | **재조정 완료** | public 64/75, QDEC20/21 partial 근거·지원 계약과 사용자 문서 일치. 124번 |
| T18 공개 절차 준비 | **완료** | stable 생성·검증, 승인 evidence 결합과 공개 명령 분리. 120번 |
| R14·T19 RC 고정·전체 회귀 | **재검증 완료** | exact `1e97ae49`, 35/35 target·원격 CI·RC 이중 재현 PASS. 124번 |
| T20 RC 설치 수명주기 | **재검증 완료** | 새 RC 설치·30/30 예제·Upload·전환·제거·재설치 PASS. 124번 |
| T21 stable 최종 검사 | **재검증 완료** | 새 stable 이중 재현·30/30·Upload·RC runtime 동등성 PASS. 123·124번 |
| T22~T25 승인·공개·마무리 | **완료** | 승인·11개 자산·stable index 공개, 공개 설치 30/30·Upload·전환·제거·재설치 PASS. 125번 |

T13 QDEC manual read 단독/C07·시리얼 핸드오버·peer 제어 System OFF 제외와 충돌 반복 생략은 범위 결정이며 새 물리
PASS가 아닙니다.
기존 정상 36조건과 수용된 시험을 다시 예약하지 않습니다.

## 2. 최종 완료 체크포인트

### 정식 공개 완료

- **T01~T25: 25/25 완료(100%)**, R00~R14 완료. 합의한 범위의 수정 대기 확정 코어 결함은 없습니다.
- 정식 source는 `ad829439e570c7510fce2f8cc7252e5b9ef32b04`, 공개 버전은
  [`v0.4.0`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.4.0)입니다.
- 공개 package는 library 9개·예제 30개입니다. 공개 URL 설치 후 **30/30 compile**, 대표 Blink Upload,
  `0.4.0 → 0.3.0 → 0.4.0` 전환·제거·재설치·prerequisite 보존을 확인했습니다.
- 최종 마감 commit `5a3fcbf3`의 원격 Software Gates 7/7, Reproducible Builds 8/8이 성공했습니다.
- 공개 자산 identity·승인·실행별 원본은 [125번 최종 기록](<04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)에 있습니다.
  추가 제품 개발은 [로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>)과 새 작업 지시에서 시작합니다.

### 공개 후 문서 유지보수

2026-09-12 문서 전수 정비를 완료했습니다. 기존 Markdown 257개(저장소 251 + 보드 6)를 검토하고,
README·문서 진입점·현행 안내의 가독성과 경로를 정리했습니다. T01~T25 완료 상태·공개 자산·
과거 시험 판정은 보존했고 생성 문서는 원본 계약·생성기와 함께 교정했습니다.
1차 문서 252개 링크·생성 계약·CI 계약 46개·Host 회귀 26개를 통과했습니다. 후속 점검의 추가 교정과 OS 차단 SKIP 1건은 126번에 구분했습니다.
이번 문서 정비는 새로운 물리 PASS가 아닙니다. 상세는 [126번 정비 기록](<04_검증 기록/126_정식_공개_후_문서_전수_정비.md>)을 따릅니다.

### T13 완료 수

분모 **58은 요청한 S 정리 범위**이며 v0.4.0 전체 마일스톤 수가 아닙니다.
아래 56에는 기존 요구 대조 1건이 포함되므로 56개 모두를 새 물리 시험으로 해석하지 않습니다.

| 항목 | 완료 / 전체 | 실제 확인 범위 |
| --- | ---: | --- |
| UART break·parity | 16 / 16 | 양 역할, 각 100회 |
| UART CTS | 12 / 12 | 단독 및 C01/C05 조건 |
| UART RX 공급 지연 | 8 / 8 | 양 역할 400회씩, 합계 800회 |
| 기존 요구·구현·증거 대조 | 1 / 1 | 대조 완료. 미실기 대체 아님 |
| I2S 원래 경로 복구 | 1 / 1 | role2 starvation/restart 100/100 |
| SPI 경계 복구 | 10 / 10 | short·unready, 5개 인스턴스 각 100회 |
| TWI SDA stuck-low | 4 / 4 | TWIM20/21/22/30 각 100회 |
| TWIS 공급 지연 | 4 / 4 | TWIS20/21/22/30 각 100회 |
| **S 합계** | **PASS 56 + 제외 2 / 58** | 범위 종료. 미실행을 PASS로 계산하지 않음 |
| **UARTE00 별도 시험** | **완료** | 4-net 검사·통신 180초·flow 200회·TX/RX 취소 400회 |

S 종료 근거는 [113번](<04_검증 기록/113_T13_S_범위_종료와_U_준비.md>), U 종료 근거는
[115번](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)입니다.
System OFF timer·사용자 버튼 wake는 기존 M15에서 **검증 완료(정상)**했습니다.
T13 peer 제어 추가 결합 2조건의 제외와 구분합니다.

### 해결 완료한 문제

| 문제 | 현재 상태 | 교정·검증 근거 |
| --- | --- | --- |
| 초기 UART deferred RX·SPI RXDELAY·TWIS 지연 버퍼 재개 | **해결 완료** | 수정 후 전체 재시험. 44·47·50번 |
| UART 오류 callback 폭주·RX abort 중복 STOP | **해결 완료** | core·시험 시작 순서 교정, break/parity 16조건 각 100회. 110번 |
| C01 UART/TWI 버퍼 재공급 누락 | **해결 완료** | 반환/승격 버퍼 교정, C01 900초·양 역할 CTS 100회. 110번 |
| UART RX 지연 시험 재시작 slot 오류 | **해결 완료** | `completed % 2` slot 선택, 양 역할 각 400회·cleanup. 110번 |
| I2S 짧은 버퍼 DMA 자원 처리 지연 | **해결 완료** | `36ba819` 수정 후 Fixture 430의 192조건 PASS. 87번 |
| SPIS 연속 버퍼 공백·재시작 zero RX | **해결 완료** | 버퍼 예약·시작 장벽·CS inactive·지연 교정, 10조건 각 100회. 111~112번 |
| TWI terminal 버퍼 재공급 | **해결 완료** | stuck-low 4조건 각 100회·정상 통신 복구. 112번 |
| TWIS 공급 지연 측정 기준 | **해결 완료** | 2 ms 지연 4조건 각 100회·복구 확인, 사용자 수용. 112번 |
| PDM 위상·mono gate 준비 순서 | **해결 완료** | 합성 신호·준비 순서 교정, 기본 192·밀도 32·연속 96/96. 91~92번 |
| 미시작 PWM의 STOP timeout | **해결 완료** | `080d771` 수정·두 보드 회귀, 후속 S 복구 6/6. 94·109번 |
| Fabric/public PWM block 식별 불일치 | **해결 완료** | 공통 자원 키 교정, Host·target 4/4·두 보드 520 cycle. 116번 |

번호별 원본은 [검증 기록 목차](<04_검증 기록/README.md>)에서 찾습니다.
사용자가 제외한 진단·추가 판정 요구는 현재 문제 표에 넣지 않습니다.

### T14 검증·판정 결과

| 항목 | 상태 | 판정 근거 |
| --- | --- | --- |
| GPIO alias·DMA overlap 충돌 | **검증·판정 완료** | 중복 거부·기존 소유자 보존, 31 pad mapping 전수 계약 |
| GPIOTE·DPPI active 충돌 | **검증·판정 완료** | 중복 lease·publisher 거부, 실제 DPPI10/20 두 보드 반복·반환 |
| Fabric PWM과 analogWrite/tone/Servo 충돌 | **결함 해결·판정 완료** | PWM 공통 키 교정. 두 API군은 Kconfig에서 상호 배타적 |

상세 source·명령·결과는 [116번](<04_검증 기록/116_T14_자원_충돌_판정과_PWM_식별_교정.md>)을 따릅니다.

### 후속 작업 원칙

완료된 실기·제외 항목은 자동 재예약하지 않습니다. 현재 물리 결선이나 마지막 image도 과거 문서로 추정하지 않습니다.
새 보드 작업의 연결성 검사·오류 진단·STOP/lease 규칙은 [AGENTS.md](../AGENTS.md),
새 PC 준비는 [인계 문서](HANDOFF_v0.4.0_다른_PC.md)를 따릅니다.
구현·Host·build·실기 결과를 구분하고, 매 보고에 해당 작업의 완료 범위와 진행률을 함께 적습니다.

## 3. 작업별 원본과 범위

| 작업 | 먼저 대조할 원본 |
| --- | --- |
| 전체 범위·상태 | [로드맵 §8](<./01_아두이노 코어 설계/02_구현_로드맵.md>), [경쟁 마일스톤 M24~M27](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>), [42번 합의](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>) |
| 리팩토링 안정화·선행 구조 작업 | [리팩토링 문서 안내](<./01_아두이노 코어 설계/14_리팩토링/README.md>), [통합 실행계획](<./01_아두이노 코어 설계/14_리팩토링/02_리팩토링_통합_실행계획.md>), [진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>) |
| 인스턴스·공유 자원·DMA | [inventory JSON](../variants/nu54dk/peripheral-manifest.json), [생성 matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>), [serial 계약 JSON](../variants/nu54dk/serial-fabric-contract.json) |
| 통신·analog·stream API | [SerialFabric](../cores/arduino/nucode/SerialFabric.h), [AnalogFabric](../cores/arduino/nucode/AnalogFabric.h), [StreamFabric](../cores/arduino/nucode/StreamFabric.h), [Kconfig](../zephyr/Kconfig), [M24 계약](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>) |
| HIL·결선·환경 | [HIL README](../tests/hil/nu54dk/README.md), [Windows 개발환경](<./02_빌드 설계/09_Windows_개발환경_설정.md>), [보드 회로도](<../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>)와 해당 board source |
| M25·M26 구현 이력 | [37번 M25](<./04_검증 기록/37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>), [M26 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>), 41번의 최신 기본 실기 증거 |
| RC·공개 | [M27 도구 안내](../tools/release/M27_README.md), [RC 준비 문서](<./05_릴리스/v0.4.0-rc.1/README.md>), [readiness](../variants/nu54dk/v0.4.0-release-readiness.json) |

범위는 Windows용 `v0.4.0` 코어 기능이다. Linux/macOS 지원과 새 BLE 확장을 추가하지 않는다.
당시 온보드 자원·두 NU54DK의 peer/loopback·합성 신호·capture를 사용했다.
새 실기는 별도 요청과 시험별 결선 계약을 따른다. 외부 마이크/코덱/엔코더별 호환성, 정밀 ADC·jitter·전력·음질·신호 품질은
필수 gate 밖이다. **코어의 실제 데이터 경로·DMA·오류 복구·동시성·soak는 면제하지 않는다.**
합성 peer로도 신호를 생성·검증할 수 없는 필수 경로는 HOLD이며, 추가 범위 변경은 사용자에게 확인한다.

생성 문서는 JSON·생성기를 고친 뒤 재생성한다. Board submodule, SDK와 기존 공개 자산은 임의로
수정하지 않는다. `v0.3.0` 미만 공개 공급은 종료했다. 이전 tag·asset 원본은106번의 archive에 보존하며 현재 공개 자산은 변경하지 않는다.

## 4. A단계 — 결선 없이 준비 (T01~T09, 완료)

T01~T08의 상세 초기 계획·구현 대조·실패/수정 이력은
[43번 준비 기록](<04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>)에 보존합니다.
완료한 준비 작업을 현재 대기 목록으로 다시 등록하지 않습니다.

- [x] **T01 — 최종 시험 목록 확정:** 75개 identity·19개 family, test ID·route·속도·buffer·반복·판정 기준 고정.
- [x] **T02 — 코드와 검증 상태 대조:** source·build·실기·공개 API·profile을 분리하고 보완 항목 연결.
- [x] **T03 — 두 보드 공통 실행기:** exact UID·role·image·nonce·배타 lock·실패 journal·STOP 계약 준비.
- [x] **T04 — UART·SPI·I2C 시험 프로그램:** 각 인스턴스의 송수신·mode·DMA·flow/error·취소·재시작 판정 준비.
- [x] **T05 — ADC·PWM·타이머·이벤트 시험:** 안전한 입력·capture·sample/count·소유권 판정 준비.
- [x] **T06 — PDM·I2S·QDEC 합성 신호:** 신호원과 수신 oracle 준비. 당시 준비 완료와 후속 실기 결과는 별개.
- [x] **T07 — DMA·복구·동시성·안정성 실행기:** 오류 주입·buffer 반환·누수·유한 반복·soak 기준 준비.
- [x] **T08 — 결선표와 스위치 안내:** fixture별 GPIO·GND·전압·pull-up·DAP UART 분리·금지 net 계약 확정.
- [x] **T09 — Host·target·무배선 회귀:** 준비 source와 실제 image를 대조하고 온보드 시험 완료.

T09 주요 근거:

| 실행 시점 | 검증 범위 | 기록 |
| --- | --- | --- |
| 준비 종료 `696defb` | 두 역할 target 2/2, 무배선 primitives 904 PASS | [43번](<04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>), [원본](<04_검증 기록/evidence/696defb/pair-primitives-696defb.json>) |
| DAP UART 회귀 `373d98d`·BLE `18a7cbe` | 온보드 18 PASS, M19/M20/M21 pair PASS | [66번](<04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>) |
| R13 이후 `c94298f` | 두 보드 온보드 904 PASS | [65번](<04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>) |

당시 외부 fixture가 NOT RUN이었다는 사실은 유지합니다. 후속 T11/T12 완료를 취소하거나
T09 온보드 PASS로 외부 실기를 대신하지 않습니다.

## 5. B단계 — 결선·기능·복구 검증 (T10~T15)

- [x] **T10 — 첫 시험 묶음의 결선 확인:** Fixture 101의 보드·DAP UART 분리·USB 재연결을 확인했습니다.
  근거는 [44번](<04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)입니다.
  실제 결선을 바꾸면 새 표를 확인하지만 유지 중인 S에 임의 만료 시간을 적용하지 않습니다.

- [x] **T11 — M24 통신 인스턴스 기능 검증:** UART 101~103, SPI 201~203, TWI 301을 완료했습니다.
  초기 결과는 44~50번, R00~R13 후 current-source 회귀 7묶음·61,423개 기능은
  [67~73번 기록](<04_검증 기록/README.md>)에 있습니다. 각 source의 단독 PASS를 후속 source·동시성 PASS로 복사하지 않습니다.

### 리팩토링과 최종 회귀의 연결

- [x] **R00~R13:** 정확성 안정화·구조 리팩토링과 software gate 완료.
  단계별 기준·완료 근거는 [리팩토링 체크리스트](<01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)에서 관리합니다.
- [x] **current-source T11:** R13 이후 영향 통신의 단독 회귀 완료. 후속 runtime 변경은 영향받는 동일 조건을 재검증합니다.
- [x] **R14:** T16~T18 사용자 통합 뒤 T11~T15 결과를 포함해 RC를 다시 고정하고 T19로 전환했습니다. [121번 기록](<./04_검증 기록/121_T19_RC_소스_고정과_전체_회귀.md>)을 따릅니다.

- [x] **T12 — M25 입력·출력·스트림 기능 검증:** 합의한 범위를 사용자가 완료로 수용했습니다.
  미실행 반복과 실패 원본을 유지하며, 제외된 조건을 PASS나 결함 해결로 바꾸지 않습니다.

| T12 범위 | 완료·제한 근거 |
| --- | --- |
| ADC/PWM fixture 401~408 | 74~79·82~83번. 401~404/408 각 48조건, 공유 AIN4/5/6 각 12조건 |
| I2S fixture 430 | 87번 192조건 PASS |
| PDM fixture 440 | 91~92번 기본·밀도·연속 96/96, 초기 실패와 후속 수정 구분 |
| 내부 ADC·TIMER·이벤트 | 95번. TIMER 7,040회 범위와 완료 결정은 103번 |
| C 공통 GPIO/PWM/I2S | 100번. GPIO/GPIOTE 2,502, PWM 675+288, I2S 432 PASS |
| 반복 수·실행 범위 차이 | 103번. 계획 수치를 실제 실행 수로 대체하지 않음 |

각 기록은 [검증 목차](<04_검증 기록/README.md>)에서 찾습니다. 제외된 항목의 원본과 제한은
기존 이력에 보존하며 현재 수정·재시험 목록에는 넣지 않습니다.

- [x] **T13 — 복구·동시 실행·장시간 안정성 검증**
  - 당시 합의한 시간 기준: 사용자 지시로 단독 각 인스턴스 180초. 동시 각 확정 조합 900초, 전체 대표 고부하 한 조합 3600초로 대체. 결과에는 요청/실제 연속 시간을 모두 기록하고 3분을 10분·2시간 통과로 확대하지 않는다.
  - 상태·선행: **합의 범위 완료**. S는 PASS 56 + System OFF 추가 결합 2건 제외, U는 115번의 UART00 물리시험 PASS다. QDEC20/21 manual read 단독·C07 및 연속 handover는 제외하며 T12 완료를 다시 보류하지 않는다.
  - 완료 실행: UARTE00 1 Mbit/s 8N1 full-duplex 180초, 양 역할 RTS/CTS 각 100회, TX/RX DMA 취소·fresh restart 각 역할 100회. 완료한 S 정상 36조건(C05 3600초 포함)과 수용된 충돌·복구를 중복 예약하지 않는다.
  - 완료 기준: source·topology·rate·시간·buffer·loss·latency/CPU 관측 방법과 누수/복구 판정이 기록된다. 장시간 시험을 코드 구현만으로 완료 처리하지 않는다.
  - 결선·증거: [T13 계획](../tests/hil/nu54dk/T13_PLAN.md), 생성 topology JSON과 [115번 완료 기록](<./04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)에 원래 계획·적용 범위·원본 hash를 구분한다.

- [x] **T14 — 발견된 결함 수정과 재시험**
  - 완료 결과: GPIO alias·DMA overlap, 활성 GPIOTE·DPPI, Fabric/public PWM 자원 충돌 요구를 모두 판정했습니다.
  - 결함 상태: PWM block 식별 불일치 1건을 발견해 `24582dcc`에서 해결했고 미해결 확정 코어 결함은 0건입니다.
  - 회귀: 계약 46개, 전체 Host, inventory·생성 계약, target 4/4 build, 두 보드 28 command·520 cycle HIL을 통과했습니다.
  - 결선·증거: [116번 기록](<./04_검증 기록/116_T14_자원_충돌_판정과_PWM_식별_교정.md>)과 익명화한 `hardware.json`을 따릅니다.

- [x] **T15 — 실기 결과와 지원 범위 확정**
  - 완료 결과: M24 23 identity HIL pass, M25 34 pass·QDEC20/21 partial을 manifest에 반영했습니다.
  - 지원 경계: T15 당시 public 14개와 설치 통합 전 internal candidate를 분리했습니다. T16~T17에서 지원 판정이 끝난 identity를 `fabric` profile public으로 승격했고 QDEC 제한은 유지합니다.
  - 당시 readiness: `m24_fixture_hil`·`m25_fixture_hil` PASS, release blocker 6개 잔여. 이들은 후속 T19~T22에서 완료됐습니다.
  - 결선·증거: 추가 실기 없음. [117번 기록](<./04_검증 기록/117_T15_지원_범위와_Physical_Gate_확정.md>)을 따릅니다.

## 6. C단계 — 사용자용 패키지와 최종 RC (T16~T21)

- [x] **T16 — 검증된 후보 API를 사용자용 설치 경로에 통합**
  - 완료 결과: `fabric` profile·`NUCODE_Peripheral_Fabric.h`·capability·설치 예제와 M27 30개 lock을 연결했습니다.
  - 지원 경계: 기존 singleton과 직접 Fabric은 profile로 분리합니다. QDEC20/21은 124번에서
    SAMPLE/REPORT event 경로 지원과 반복 manual read/clear 무손실 제외 계약으로 재확정합니다.
  - 검증: 실제 격리 설치본과 T16 target build, Host·CI·inventory·style gate를 통과했습니다.
  - 결선·증거: 새 flash·결선 없음. [118번 기록](<./04_검증 기록/118_T16_Peripheral_Fabric_설치_통합.md>)을 따릅니다.

- [x] **T17 — 문서·지원 매트릭스 정리**
  - 완료 결과: README·API·예제·pin/ownership·제한·환경·마일스톤과 release notes·migration·known issues·testing·troubleshooting을 실제 `fabric` 지원 범위에 맞췄습니다.
  - 지원 원장: 75개 identity 중 public 64개·HIL pass 62개입니다. QDEC20/21은 public/partial이며,
    나머지 system identity 11개는 근거에 따라 internal 또는 none입니다.
  - 검증: 생성 원본/문서, Host·CI·inventory·문서·style gate를 통과했고 과거 검증·공개 자산은 소급 변경하지 않았습니다.
  - 결선·증거: 새 flash·결선·물리 PASS 없음. [119번 기록](<./04_검증 기록/119_T17_문서와_지원_매트릭스_정리.md>)을 따릅니다.

- [x] **T18 — M27 정식 공개 절차 준비**
  - 완료 결과: `m27_stable_release.py`로 stable prepare·plan 검증·읽기 전용 사전점검·Release 게시·index 게시를 분리했습니다.
  - 차단 계약: 잘못된 version/commit, 미완료 technical gate, exact plan에 결합되지 않은 T22 승인, 기존 tag/Release/version과 asset byte 불일치를 거부합니다.
  - 검증: 과거 stable allowlist를 영구 변경하지 않는 실행 중 후보 구성과 승인 전 외부 명령 미호출을 unit/contract로 확인했습니다.
  - 결선·증거: 새 flash·결선·공개 작업 없음. T18 완료가 공개 실행 허가는 아닙니다. [120번 기록](<./04_검증 기록/120_T18_stable_공개_절차와_승인_차단.md>)을 따릅니다.

- [x] **T19 — RC 소스 고정과 전체 회귀 검사**
  - 완료 결과: exact Core/board/SDK/toolchain을 고정하고 Host·문서·inventory·35개 target build와 RC package 이중 재현성을 통과했습니다.
  - 해결 결과: T16 crypto object의 Windows 절대 경로가 261자가 되어 archive가 실패한 원인을 특정하고 출력 경로를 `C:\t`로 제한해 35/35를 재검증했습니다.
  - 변경 영향: 이후 문서·readiness 변경은 runtime package 입력에서 제외합니다. runtime source가 바뀌면 전체 target gate를 다시 실행합니다.
  - 결선·증거: 새 flash·결선 없음. [121번 기록](<./04_검증 기록/121_T19_RC_소스_고정과_전체_회귀.md>)을 따릅니다.

- [x] **T20 — RC 패키지 재현성·설치 수명주기 검증**
  - 완료 결과: 격리 Boards Manager 설치, lock/발견 목록 30/30 clean compile, 실제 pyOCD Upload, `0.3.0` 전환, 제거·재설치와 prerequisite 보존을 통과했습니다.
  - 해결 결과: Nordic 공식 URL의 같은 nRF Util version byte 변경은 서명·version을 확인해 새 exact hash로 고정했습니다. 저전력 firmware의 SWD `No ACK`는 under-reset/halt로 원인을 분리하고 정상 Upload했습니다.
  - 경계: 과거 `0.3.0` byte는 변경하지 않았고 과거 post-install을 현행 URL로 소급 검증하지 않았습니다. tag·Release·stable index도 쓰지 않았습니다.
  - 결선·증거: 새 GPIO 기능 시험 없음. 지정 CMSIS-DAP 1회 Upload. [122번 기록](<./04_검증 기록/122_T20_RC_설치_수명주기와_실제_Upload.md>)을 따릅니다.

- [x] **T21 — 정식 0.4.0 패키지 생성·최종 검사**
  - 완료 결과: 비공개 RC/stable package를 각각 두 번 생성해 byte 재현성을 확인했고 정규화 runtime payload가 같았습니다.
  - 설치 검증: 격리 Boards Manager stable 설치, 발견·clean compile 30/30, 대표 Blink 실제 pyOCD Upload를 통과했습니다.
  - 변경 영향: T19 이후 host hook 호환성을 보완하고 Host·계약·문서·inventory를 재검증했습니다. 이후 설치 예제 실행기와 문서 변경은 runtime 입력에서 제외됩니다.
  - 결선·증거: 기존 S/U 기능 시험은 반복하지 않았고 USB Upload 1회만 수행했습니다. tag·Release·공개 index는 만들지 않았습니다. [123번 기록](<./04_검증 기록/123_T21_stable_패키지와_최종_검사.md>)을 따릅니다.

## 7. D단계 — 공개와 마무리 (T22~T25)

- [x] **T22 — 최종 결과 확인과 공개 승인**
  - 완료 결과: 프로젝트 소유자의 명시적 조건부 승인을 exact stable plan SHA-256 `802c15538c26aad4c51a9b8f476fdb0da6ca9b5fd44633fa072cd61429a1026c`과 source `ad829439`에 결합했습니다.
  - 승인 범위: QDEC20/21 기본 정·역회전과 SAMPLE/REPORT event 지원, 반복 Serial personality handover·모든 주변장치 동시 조합·정밀 ADC/jitter/음질/신호 무결성은 보증 밖입니다.
  - 결선·증거: 불필요. 124·125번.

- [x] **T23 — v0.4.0 태그·GitHub Release·자산 공개**
  - 완료 결과: exact `ad829439`에 `v0.4.0` tag·GitHub Release와 승인한 11개 자산을 공개했습니다.
  - stable index: `e53affd4`, 1,879 byte, SHA-256 `522f6715389d34887f4087b4e37dd2d0659d680fa119a9558200d7040514de25`; 0.4.0과 0.3.0을 제공합니다.
  - package: 2,630,374 byte, SHA-256 `6629963fc618419135b4fc0c1240fa84fa1db95fad03b92add798bbacf0c9189`. 기존 공개 자산은 변경하지 않았습니다. 125번.

- [x] **T24 — 공개 URL에서 최종 설치 검증**
  - 완료 결과: 새 격리 환경에서 실제 공개 index/archive를 받아 exact hash를 확인하고 설치 예제 30/30 compile을 완료했습니다. 병렬 실행 중 진단 없는 일회성 종료 1건은 같은 설치본·설정의 단독 재시도에서 compile/link/artifact 확인까지 PASS했습니다.
  - 실제 Upload: 대표 Blink를 sector-only로 지정 CMSIS-DAP에 Upload했습니다. mass erase/recover는 사용하지 않았습니다.
  - 수명주기: 0.4.0→0.3.0→0.4.0, 제거·재설치와 NCS/Toolchain prerequisite 보존을 확인했습니다. 125번.

- [x] **T25 — 최종 문서·커밋·푸시·CI·작업 폴더 정리**
  - 완료 결과: 공개 identity·검증 기록·README·로드맵·릴리스 문서를 갱신하고, 공개 후 0.4.0/0.3.0 stable 정책에 맞게 package/release 계약 검사를 고정했습니다.
  - 정리 결과: 실행 중인 build/upload 프로세스는 없고, 저장소 밖 T24 격리 설치·로그는 최종 증거로 보존했습니다. 재생성 가능한 작업 보조 파일만 제거했습니다.
  - 검증: 로컬 전체 gate와 최종 push의 GitHub software/reproducible workflow 결과를 125번에 연결합니다.

## 8. 완료된 release gate

### 완료 순서

| 순서 | 단계 | 완료 결과 |
| --- | --- | --- |
| 1 | T22 | exact 결과·공개 자산에 대한 프로젝트 소유자 승인 완료 |
| 2 | T23 | 승인한 tag·Release asset·stable index 공개 완료 |
| 3 | T24 | 공개 URL 설치·build·Upload·제거·재설치·전환 검증 PASS |
| 4 | T25 | 최종 기록·커밋·푸시·CI 확인과 작업 보조 파일 정리 완료 |

T13의 합의한 S/U 범위와 v0.4.0 T01~T25는 100% 완료됐습니다.

### 기계 판정 gate

| Readiness gate | 연결 작업 | 현재 판정 |
| --- | --- | --- |
| `m24_fixture_hil` | T04·T07~T11·T13~T15 | **PASS** |
| `m25_fixture_hil` | T05~T10·T12~T15 | **PASS**; QDEC20/21은 partial 근거를 명시한 공개 지원 |
| `host_regression`, `documentation`, `zephyr_repro_build` | T16~T19, T21의 변경 영향 재검증 | **PASS**; runtime 변경 시 재실행 |
| `package_reproducibility` | T20·T21 | **PASS**; RC/stable 이중 재현과 runtime 동등성 확인 |
| `boards_manager_lifecycle` | T20·T21·T24 | **PASS**; RC/stable 로컬 설치와 공개 URL 설치 수명주기 완료 |
| `project_owner_approval` | T22 | **PASS**; exact stable plan·source에 승인 결합 완료 |

M23·후보 source/build·기본 onboard·M26 판정·기존 자산 불변 gate의 근거는 기존 ledger에 있다.
M24/M25 physical gate는 T15 증거 대조로 PASS가 됐고 후속 공개 gate도 완료했다. 실기 PASS와 RC 통과·정식 공개,
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

T01~T25의 결정·완료 순서와 원본 증거를 연결하는 역사 문서로 보관한다. 향후 사용자가 명시적으로
이 파일의 archive 또는 삭제를 요청할 때만 다음 조건을 모두 확인한다.

1. T01~T25 전체 완료와 정식 공개 URL 검증이 끝났고, 재개할 작업·미해결 문제·사용자 요청이 없다.
2. 결정·제한·최종 지원 matrix·명령·실제 증거·공개 identity가 영구 문서에 옮겨져 TODO가 유일한 근거가 아니다.
3. 삭제/이동 대상은 **이 TODO 파일**로 특정한다. 검증 기록·readiness 참조·공개 asset·SDK·사용자 파일은 포함하지 않는다.
4. [루트 작업 지침](../AGENTS.md), README, 문서 안내, 로드맵, RC·도구 안내 등 들어오는 링크를
   같은 변경에서 최종 기록 또는 보관 위치로 바꾸고 문서 검사를 통과한다.
5. 정리 결과와 Git 복구 가능 여부를 남기고 commit/push한다. 미완료 체크를 지워 완료처럼 보이게 하지 않는다.
