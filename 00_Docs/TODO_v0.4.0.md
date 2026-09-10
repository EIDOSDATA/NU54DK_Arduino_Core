# v0.4.0 개발 현황과 실행 TODO

현재 정식 배포는 **v0.3.0**입니다. v0.4.0은 T13 복구 검증 중이며 RC·정식 공개 전입니다.
현재 상태와 다음 작업은 이 문서에서 관리하고, 실행별 원본은 [검증 기록](<04_검증 기록/README.md>)에 보존합니다.

## 1. 현재 상태

| 마일스톤 | 상태 | 근거와 남은 일 |
| --- | --- | --- |
| T01~T09 준비, R00~R13 리팩토링 | 완료 | 준비·Host·target: 43~66번 |
| T11 통신 단독 기능 회귀 | 완료 | source별 UART/SPI/TWI 일곱 묶음: 67~73번 |
| T12 GPIO·Analog·Timer·Stream 기능 | 사용자 수용 완료 | QDEC 알려진 문제는 101번에 보존, 추가 진단 제외 |
| T13 정상 안정성 | 완료 | 단독 29/29 + 동시 7/7 = 36/36. 각 시험 당시 source의 결과 |
| T13 고정 serial 취소/NACK | 완료 | 21/21 |
| T13 PWM 복구 | 완료 | 6/6 |
| T13 serial 자원 충돌 | 사용자 수용 완료 | 예행 14/14, 5조건 각 100회. 나머지 9조건 반복 생략 승인 |
| T13 연속 통신 종류·역할 전환 | 범위 제외 | 시리얼 핸드오버 재실행·추가 검증 없음 |
| T13 I2S/PDM 복구 | 4/4 | I2S role2 공급 중단·재시작 정식 100/100 완료. 111번 |
| 요청한 잔여 S 1~3단계 | **38/58 (65.5%)** | 잔여 20조건. 집계와 다음 순서는 아래 2절 |
| U 준비 | 소프트웨어 준비 완료 | 전용 image·Host·CI 통과. U 재결선과 실기는 미실행 |
| T14~T18 결함·지원·사용자 통합 | 진행/대기 | 알려진 제한 정리와 최종 지원 판정·패키지 통합 |
| R14·T19~T25 RC·승인·공개 | 대기 | 공개 승인과 실제 배포는 별도 |

QDEC·시리얼 핸드오버 제외와 충돌 반복 생략은 사용자 범위 결정이며 새 물리 PASS가 아닙니다.
기존 정상 36조건과 수용된 시험을 다시 예약하지 않습니다.

## 2. 현재 재개 체크포인트

**2026-09-09 선행 문서 정리를 완료했습니다.** 저장소 Markdown 225개를 먼저 완독한 뒤 현재 지시·과거 기록·
지원 범위를 정리했습니다. 보드 접근·GPIO 구동·flash 없이 문서만 정리했으며, 실기 완료 수는 바뀌지 않았습니다.
문서 정리 완료 보고 뒤의 실기 순서는 **현재 S 전체 GPIO 연결성 확인 → 실패 원인 해결과 동일 조건 재검증 →
잔여 S 종료 → U 결선 안내·준비**입니다.

### 완료 수와 잔여 항목

분모 58은 이번 요청의 S 정리 범위이며 v0.4.0 전체 진행률이 아닙니다.
구성은 I2S 1 + S 오류 복구 54 + System OFF 2 + 기존 요구 대조 1입니다.

| 항목 | 완료 / 전체 | 상태 |
| --- | ---: | --- |
| UART break | 8 / 8 | 양 역할, 각 100회 |
| UART parity | 8 / 8 | 양 역할, 각 100회 |
| UART CTS | 12 / 12 | 단독 및 C01/C05 조건 완료 |
| UART RX 공급 지연 | 8 / 8 | 양 역할 400/400씩, 합계 800회 |
| 기존 요구·구현·증거 대조 | 1 / 1 | 대조 완료, 미실기를 PASS로 대체하지 않음 |
| I2S 원래 경로 복구 | 1 / 1 | role2 starvation/restart 정식 100/100 완료 |
| SPI 경계 복구 | 0 / 10 | short SPIM22 정상 재시작 실패 원인 수정, exact 전체 재시험 전 |
| TWI SDA stuck-low | 0 / 4 | 남은 실기 |
| TWIS 공급 지연 | 0 / 4 | 남은 실기 |
| System OFF timer/GPIO | 0 / 2 | 선행 중계 문제 포함, 새 실기 성공 0회 |
| **합계** | **38 / 58** | **65.5%, 잔여 20조건** |

### 해결한 문제와 아직 남은 문제

| 대상 | 확인·수정·재검증 | 남은 경계 |
| --- | --- | --- |
| UART line 오류 | 오류 callback 폭주, 진행 중 RX abort 중복 STOP을 수정. 시험 시작 순서도 교정해 break/parity 16조건 완료 | 새 오류 발생 시 새 원본을 보존해 진단 |
| C01 UART + TWI | 반환 UARTE 버퍼 재공급 누락과 TWIS 승격 버퍼 prepare 누락 수정. C01 900초와 양 역할 CTS 100회 완료 | 중간 실패 기록은 유지. CTS 전체 12조건 완료 근거와 구분 |
| UART RX 지연 | 누적 완료 수가 홀수인 재시작에서도 slot 0부터 시작하던 시험 펌웨어 오류. `completed % 2`로 시작 slot 선택 | source `3f4a1890`에서 양 역할 각 400회와 cleanup 통과 |
| net5: A P1.06 ↔ B P1.07 | 과거 LOW 전달 실패 후 같은 선 재검사 20/20, 불일치 0 | 현재도 단선이라고 단정하지 않음. 전체 S 연결성은 실기 재개 때 다시 확인 |
| I2S net6 과거 진단 | 원래 경로 수신 오류와 패드 전이 부족, 반대 endpoint 진단 100회 성공을 보존 | 후속 원래 role2 정식 100/100으로 완료. 과거 실패 원인은 소급 변경하지 않음 |
| I2S role2 재검증 | 0dda7f9의 원래 starvation/restart 정식 100/100, cleanup 203·idle 400 통과 | 완료. 진단용 교환 경로와 구분 |
| SPI SPIS 연속 버퍼 | short 정식 SPIM22 재시작 frame12가 zero RX. DWT 무작위/정확 seed 각 100회 추가 오류 없음 | END 뒤 next 요청의 무버퍼 구간을 선행 semaphore 예약으로 교정. exact SPI 10조건 재시험 전 |
| System OFF | 선행 중계 무응답과 당시 B RAM 소실 기록 보존. 새 전용 image·Host 준비 완료 | 실제 OFF/wake 성공 없음. GRTC 결함으로 확정하지 않음 |

원인 분석·수정 source·캠페인과 원본 위치는
[110번](<04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)과
[111번](<04_검증 기록/111_T13_S_I2S_완료와_SPIS_연속_버퍼_교정.md>)을 따릅니다.
디버거 관측, 변경된 경로의 성공, 예행과 부분 반복은 정식 완료 수에 더하지 않습니다.

### 실행 source와 준비 상태

| 용도 | source / build | 확인된 범위 |
| --- | --- | --- |
| 마지막 실기 image | `3f4a18906f6d72df45f5a07f901b6a7aef716a2a` / `C:/t5t04` | RX 지연 완료, 양쪽 STOP·핀 반환 |
| 현재 코드 기준 | `0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d` | U 전용 경로 준비. 문서 편집이 실기 source를 바꾸지 않음 |
| S/U image | 위 `0dda7f9d` / `C:/t5u04` | target 4/4, 관련 Host 106, style 418, docs 225, contract 46 |
| System OFF image | 위 `0dda7f9d` / `C:/t5v04` | DUT/peer build 2/2, Host 16/16. flash·실기 미실행 |
| 잔여 S 실행기 | 위 `0dda7f9d` | 관련 Host 36/36, 유한 배치 준비. 실기 미실행 |
| 원격 CI | `0dda7f9d` | Software `34321129052`, Reproducible Builds `34321128937` 성공 |

U 준비 완료는 UART00 180초 full-duplex, 양 역할 RTS/CTS와 TX/RX 취소 시험을 위한 소프트웨어
준비를 뜻합니다. S 확인을 U 재결선 확인으로 재사용하지 않으며, U 실기 완료를 뜻하지 않습니다.
CMSIS-DAP 2개 열거는 USB 식별만 확인한 것으로 SWD 연결·GPIO 결선 정상의 증거가 아닙니다.

### 결선 확인과 실패 처리

- 현재 S는 17신호 + 공통 GND입니다. 정확한 A↔B 표와 전기 조건은
  [T13 계획](../tests/hil/nu54dk/T13_PLAN.md)을 따릅니다.
- 사용자는 결선을 유지하며 손대지 않는다고 확인했고, 시간 경과에 따른 유지 확인 만료를 폐기했습니다.
  **12시간·30분 같은 임의 기한만으로 중단하거나 재확인을 요구하지 않습니다.**
- 재개 때 전체 GPIO 연결성을 먼저 검사합니다. 이상이 생기면 먼저 연결성을 다시 확인하고,
  nRF54L15의 CMSIS-DAP 디버거로 GPIO·주변장치·DMA·IRQ·버퍼 상태를 보존해 원인을 진단합니다.
- 실패 원인 규명 → 원인에 근거한 수정 → 동일 조건 재검증 순서를 지킵니다. 이유 없는 동일 실행의
  무한 반복이나 독립 시험으로 진행률만 올리는 실행은 하지 않습니다.
- T13 S/U runner는 유지 결선 확인의 임의 시한을 제거했습니다. firmware 명령 lease·watchdog,
  exact UID/image·단절 fault latch는 유지하며 새 사용자 확인을 임의로 만들어 우회하지 않습니다.
- firmware watchdog·명령 lease·STOP·출력 충돌 방지·배타 probe lock은 계속 유지합니다.
  이는 사용자의 결선 유지 확인에 임의 만료 시간을 붙이는 정책과 다릅니다.
- 실제 결선 변경, USB/전원 변화, STOP 실패 등 새 이상은 확인·진단 대상으로 기록합니다.
  물리 재결선이 꼭 필요하면 정확한 선과 필요한 조치를 안내합니다.
- 양쪽 STOP·clock 해제·GPIO 반환을 확인한 뒤 다음 시험을 시작합니다.
  기본 S는 SWD 10 MHz를 유지하고 System OFF 전용 경로는 debug power 해제 후 재접속
  안정성을 위해 1 MHz `under-reset`을 사용합니다. exact UID·sector flash·`auto_unlock=false`를
  유지하며 mass erase/unlock/recover는 금지합니다.
- S 정리 뒤 U 배치를 안내합니다. 이번 자동 범위는 U 준비까지이며, QDEC 재진단·시리얼 핸드오버·정식 공개는 제외합니다.

### 구현·문서·Git 규칙

1. 실제 저장소·branch·HEAD·dirty·board gitlink를 확인하고 기존 변경을 보존합니다.
2. source·image·역할·HEX hash·실행기·Host/target 결과를 결합합니다. 문서 커밋을 이전 image의 source로 바꾸지 않습니다.
3. 한국어 Doxygen, BSD/Allman·4칸, 제어문 중괄호를 지킵니다. SDK·third-party·board 원본은 임의 수정하지 않습니다.
4. 필요한 Host·target·계약·문서·정렬 검사를 수행합니다. 구현·build·진단·실기 결과는 구분합니다.
5. 커밋·푸시를 수행한 경우 해당 exact SHA의 CI를 확인합니다. 진행 중 CI를 성공으로 기록하지 않습니다.
6. 매 보고에 완료 범위와 진행률을 함께 적습니다. 문서 정리 진도와 S 실기 58조건의 진행률은 구분합니다.
7. 종료·인계 시 현재 체크포인트와 해당 검증 기록을 갱신합니다. 최신 사용자 지시는 과거 일지보다 우선합니다.

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
- [ ] **R14:** T16~T18 사용자 통합 뒤 T11~T15 결과를 포함해 RC를 다시 고정하고 T19로 전환합니다.

- [x] **T12 — M25 입력·출력·스트림 기능 검증:** 2026-09-08 사용자가 QDEC 문제 보고를 포함해 완료로 수용했습니다.
  미실행 반복과 실패 원본을 유지하며, QDEC 전체 조건 PASS나 결함 해결을 뜻하지 않습니다.

| T12 범위 | 완료·제한 근거 |
| --- | --- |
| ADC/PWM fixture 401~408 | 74~79·82~83번. 401~404/408 각 48조건, 공유 AIN4/5/6 각 12조건 |
| QDEC fixture 420 | 85번 초기 기능 48·준비 취소 6 PASS. 101번 누산 누락 제한, 추가 진단 제외 |
| I2S fixture 430 | 87번 192조건 PASS |
| PDM fixture 440 | 91~92번 기본·밀도·연속 96/96, 초기 실패와 후속 수정 구분 |
| 내부 ADC·TIMER·이벤트 | 95번. TIMER 7,040회 범위와 완료 결정은 103번 |
| C 공통 GPIO/PWM/I2S | 100번. GPIO/GPIOTE 2,502, PWM 675+288, I2S 432 PASS |
| 반복 수·실행 범위 차이 | 103번. 계획 수치를 실제 실행 수로 대체하지 않음 |

각 기록은 [검증 목차](<04_검증 기록/README.md>)에서 찾습니다. QDEC의 수동 read/clear 누락은
T14/T15에서 알려진 제한으로 정리하며 T12를 다시 보류하거나 진단을 재개하지 않습니다.

- [ ] **T13 — 복구·동시 실행·장시간 안정성 검증**
  - 현행 시간 기준: 사용자 지시로 단독 각 인스턴스 180초. 동시 각 확정 조합 900초, 전체 대표 고부하 한 조합 3600초로 대체. 결과에는 요청/실제 연속 시간을 모두 기록하고 3분을 10분·2시간 통과로 확대하지 않는다.
  - 상태·선행: 2절의 현재 S 집계와 U 준비 상태를 따른다. QDEC20/21·C07 및 연속 handover는 제외하며 T12 완료를 다시 보류하지 않는다.
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
