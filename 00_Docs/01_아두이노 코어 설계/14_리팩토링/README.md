# NU54DK Arduino Core — 리팩토링 문서 묶음

작성·갱신일: 2026-09-07
문서 묶음 개정: 0.4
현재 진행: R00~R13·current-source T11 완료 / T12 401~408·420 개별 시험 PASS / 430 I2S 192개 PASS / 440 clock/gate 분리 96 PASS·PDM 위상 보완 후 재시험 대기 / T14 공용 PWM 미시작 STOP 이슈 추적

## 먼저 읽을 문서

**[03_리팩토링_착수_시점_및_운영계획.md](./03_리팩토링_착수_시점_및_운영계획.md)**가 현재 상황에 맞춘 진입점이다.

핵심 결정은 **T11의 exact 실기 증거를 역사적 체크포인트로 보존한 뒤 R00~R13을 작은 검증 단위로 모두 완료하고, 최종 구조의 current-source T11 회귀와 T12~T15 통합 실기를 한 번 수행하는 것**이다. T16~T18 사용자용 통합 뒤 R14가 RC를 다시 고정하고 T19~T25의 검증·공개 gate로 연결한다. 따라서 R06~R13을 `v0.4.0` 공개 뒤로 미루지 않는다.

## 문서별 역할

| 문서 | 역할 | 이번 처리 |
| --- | --- | --- |
| [03_리팩토링_착수_시점_및_운영계획.md](./03_리팩토링_착수_시점_및_운영계획.md) | T11 완료 뒤 R00~R13·통합 실기·R14/RC까지의 시점·전환 gate | 현 상태에 맞춰 개정 |
| [04_리팩토링_작업지시서_및_검증기록.md](./04_리팩토링_작업지시서_및_검증기록.md) | R00 기준선, 한 변경 기록, 증거·인계 양식과 첫 작업 지시문 | 현 상태에 맞춰 개정 |
| [05_리팩토링_진행_체크리스트.md](./05_리팩토링_진행_체크리스트.md) | 컨텍스트와 작업자 변경에도 유지할 현재 상태·다음 행동 | 신규 활성 체크리스트 |
| [02_리팩토링_통합_실행계획.md](./02_리팩토링_통합_실행계획.md) | R00~R14의 현재 실행 순서와 상세 검증·보존 계약 | 현 상태에 맞춰 개정 |
| [01_진단_비교와_최종_판단.md](./01_진단_비교와_최종_판단.md) | F01~F08, 이전 진단·격리 실험의 근거 수준 | 기준 commit에 고정한 진단 기록 |
| [99_최초_리팩토링_설계안_참고.md](./99_최초_리팩토링_설계안_참고.md) | 최초 설계안의 파일별 분할·도구 구조 참고 | 원본 byte를 보존한 참고 자료 |

## 기준점과 상태 해석

01번과 99번의 분석 기준은 `4af93daa542b4b84e39381317d4747b3df3ff5c8` 부근의 정적 진단이다. 현재 실행 순서는 exact `e2f045c1b4272d986d17456c5af051fe8af74f19`의 Fixture 301 PASS와 T11 완료를 반영한 02·03·05번 문서 및 활성 TODO를 따른다. 과거 상태와 예시 경로는 최신 구현 사실로 확대하지 않는다.

문서 우선관계는 다음과 같다. 실제 사용자 지시·현장 안전·현재 저장소 계약을 먼저 확인한다. 03번은 시점과 진행 방식을 보완하고, 02번은 기술 작업의 기준으로 유지한다. 서로 충돌하는 항목은 차이를 기록해 범위를 결정하며 어느 문서도 source/HIL의 사실을 덮어쓰지 않는다.

R00의 실제 source·도구·계약·target/메모리 기준선은 [51번 기록](<../../04_검증 기록/51_R00_리팩토링_기준선.md>)에 보존했다. Fixture 301의 HIL 사실은 별도 검증 기록이 소유하며, R01 이후 source 구현은 번호 순서로 진행한다. 계획 문서의 체크만으로 source/HIL 또는 공개 지원 승인을 확대하지 않는다.

## 정식 위치

R01은 [52번 기록](<../../04_검증 기록/52_R01_CMake_source_소속_교정.md>)의 software/target 검증을
통과했다. R02 완료·timeout·동시 호출 수정은 [53번 기록](<../../04_검증 기록/53_R02_Serial_완료와_DMA_수명주기.md>)에
보존했다. R03 ISR·stop 동기화는 [54번 기록](<../../04_검증 기록/54_R03_Analog_Stream_ISR_정지_동기화.md>)의
26개 회귀와 target 5/5를 통과했다. R04 File 참조 관리는 [55번 기록](<../../04_검증 기록/55_R04_File_공유_slot_수명주기.md>)의
8개 회귀와 AC-03 target 2/2를 통과했다. R05 identity는 [56번 기록](<../../04_검증 기록/56_R05_Core_소스와_패키지_identity.md>)의
6개 회귀와 target 2/2를 통과했고 R06은 [57번 기록](<../../04_검증 기록/57_R06_builder_모듈과_설치_경로.md>)의
모듈/CLI 계약과 설치 compile을 통과했다. R07은 [58번 기록](<../../04_검증 기록/58_R07_EventFabric_책임_분할.md>)의
Host/target 4개 구성과 public 계약을 통과했다. R08은 [59번 기록](<../../04_검증 기록/59_R08_자원과_경로_수명주기.md>)의
Host/target 5개 구성을 통과했다. R09는 [60번 기록](<../../04_검증 기록/60_R09_Arduino_SPI_경계.md>)의
Host와 target 총 5개 구성을 통과했다. R10은 [61번 기록](<../../04_검증 기록/61_R10_Serial_Fabric_동시_호출.md>)의
동시성·구조·scope 검증을 완료했다. R11은 [62번 기록](<../../04_검증 기록/62_R11_Analog_Stream_peripheral_분리.md>)의
Host·target 6개 회귀를 완료했다. R12는 [63번 기록](<../../04_검증 기록/63_R12_BLE_Storage_수명주기.md>)의
BLE/Storage 실제 Host와 target 회귀를 완료했다. R13도 [64번 기록](<../../04_검증 기록/64_R13_도구_정책_build_구조.md>)의 전체 software gate를 완료했다. Current-source T11은 exact 154324c의 Fixture 101 기능 1,644개를 통과했다. Fixture 102도 exact a49cc0d에서 822개를 통과했으며 Fixture 103도 exact 7aece93에서 2,466개를 통과했다. 승인 UART route 세 묶음을 완료했고 Fixture 201 SPI도 exact 0f429e7에서 18,169개를 통과했다. Fixture 202도 exact 1349e20에서 9,084개를 통과했다. Fixture 203도 exact be49207에서 27,252개를 통과해 SPI 세 묶음을 완료했다. Fixture 301도 exact 9a63251에서 1,986개를 통과해 current-source T11 단독 회귀를 완료했다. T12 Fixture 401 exact a12e444·402 exact ff483a1·403 exact c95b904·404 exact e080bbc에서 각각 48개를 통과했다. 405 오픈드레인·406/407 입력 바이어스 시험과 408 PWM도 완료했으며 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다.

정식 경로는 `00_Docs/01_아두이노 코어 설계/14_리팩토링/`이다. 임시 최상위 묶음명과 문서 묶음 SemVer는 제거하고, 활성 `00_Docs/TODO_v0.4.0.md`는 기존 위치와 T01~T25 번호를 유지한다.

단일 문서만 읽어도 03번에서 착수 시점을 판단할 수 있다. 상세 기술 정의와 작업 양식을 함께 사용하려면 묶음 전체를 유지한다.

## 사용자 제공 원본 보존 확인

아래 최초 설계안은 입력 원본 byte를 보존한다. 내용·경로 예시·과거 검증 주장을 최신 사실처럼 사용하지 않는다.

| 파일 | SHA-256 |
| --- | --- |
| `99_최초_리팩토링_설계안_참고.md` | `7a70186703016eb803ed4c4910370ba2b4094a6dc11ec9c6f15389a28fb85691` |

신규 문서의 기술 출처는 각 문서 말미에 있다. 원격 링크는 확인한 commit에 고정했고, 사용자의 실제 실행 HEAD·장치·로그는 별도 기준선에 기록하도록 했다.

2026-09-06 후속: [65번 기록](<../../04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>)의 904 PASS·파일 정리를 보존한다. 이후 DAP UART 연결 전환 뒤 [66번 기록](<../../04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에서 UART idle bias를 교정하고 온보드 18개 결과·BLE 3개 pair gate를 통과했다. 이후 사용자 결선 완료 확인에 따라 exact 154324c의 current-source T11 Fixture 101을 SWD 10 MHz로 실행해 기능 1,644개를 통과했다. 이후 exact a49cc0d의 Fixture 102 기능 822개를 SWD 10 MHz로 통과했다. 이후 exact 7aece93의 Fixture 103 기능 2,466개를 SWD 10 MHz로 통과했다. 최초 peer flash 실패와 진단은 별도 보존했다. 이후 exact 0f429e7의 Fixture 201 SPI 기능 18,169개를 SWD 10 MHz로 통과했다. 이후 exact 1349e20의 Fixture 202 SPI 기능 9,084개를 SWD 10 MHz로 통과했다. 최초 peer flash 실패와 읽기 전용 진단은 별도 보존했다. 이후 exact be49207의 Fixture 203 SPI 기능 27,252개를 SWD 10 MHz로 통과했다. 최초 DUT flash 실패와 읽기 전용 진단은 별도 보존했다. 이후 exact 9a63251의 Fixture 301 TWI 기능 1,986개를 첫 실행·SWD 10 MHz로 통과해 current-source T11 단독 통신 회귀를 완료했다. 이후 T12 Fixture 401 exact a12e444에서 PWM→AIN0 48개 기능을 첫 실행·10 MHz로 통과했다. 이후 Fixture 402 exact ff483a1에서 PWM→AIN1 48개도 첫 실행·10 MHz로 통과했다. 이후 403 exact c95b904에서 PWM→AIN2 48개도 첫 실행·10 MHz로 통과했다. 이후 404 exact e080bbc에서 PWM→AIN3 48개도 첫 실행·10 MHz로 통과했다. 당시 사용자 확인된 407 결선은 A P1.13↔B P1.14였으며 LLVM Host 회귀 뒤 결선 유지를 재확인해 407 첫 실행 12개를 통과했다. 408도 완료했으며 이후 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다.

Current-source T11 첫 UART 회귀의 exact 증거는 [67번 기록](<../../04_검증 기록/67_T11_Fixture_101_current_source_UART_회귀.md>)에 연결한다. Current-source T11 단독 회귀는 완료했으며 T12~T15와 RC/공개는 미완료다.

Current-source Fixture 102의 exact a49cc0d·822 PASS는 [68번 기록](<../../04_검증 기록/68_T11_Fixture_102_current_source_UART_회귀.md>)에 연결한다.

Current-source Fixture 103의 exact 7aece93·2,466 PASS, 최초 flash 실패·진단은 [69번 기록](<../../04_검증 기록/69_T11_Fixture_103_current_source_UART_회귀.md>)에 연결한다. Current-source UART 세 묶음을 완료했으며 각 exact 증거를 보존한다.

Current-source Fixture 201의 exact 0f429e7·18,169개 기능 PASS는 [70번 기록](<../../04_검증 기록/70_T11_Fixture_201_current_source_SPI_회귀.md>)에 연결한다. 해당 exact 원본은 별도로 보존한다.

Current-source Fixture 202의 exact 1349e20·9,084개 기능 PASS, 최초 peer flash 실패·진단은 [71번 기록](<../../04_검증 기록/71_T11_Fixture_202_current_source_SPI_회귀.md>)에 연결한다. 해당 exact 원본은 별도로 보존한다.

Current-source Fixture 203의 exact be49207·27,252개 기능 PASS, 최초 DUT flash 실패·진단은 [72번 기록](<../../04_검증 기록/72_T11_Fixture_203_current_source_SPI_회귀.md>)에 연결한다. 해당 exact 원본은 별도로 보존한다.

Current-source Fixture 301 exact 9a63251·1,986개 기능 PASS와 T11 단독 회귀 완료 근거는 [73번 기록](<../../04_검증 기록/73_T11_Fixture_301_current_source_TWI_회귀.md>)에 연결한다. 일곱 fixture의 원본 61,423개와 동일 컴파일 입력을 대조했으며 exact identity는 구분 보존한다. T12 Fixture 401~404 각 48개 PASS 뒤 405·406·407도 각각 12개를 완료했고 408도 완료했으며 420 QDEC도 완료했으며 430 I2S도 전체 192개를 통과했고 440 PDM은 위상 보완 후 재시험 대기이며 M24/M25 전체·T13~T15·RC/공개 gate는 미완료다.

T12 Fixture 401 exact a12e444·SWD 10 MHz 첫 실행 48개 기능 PASS와 10,368 samples·cleanup 48개는 [74번 기록](<../../04_검증 기록/74_T12_Fixture_401_current_source_PWM_ADC_검증.md>)에 보존했다. T12는 부분 완료이며 405 오픈드레인·406/407 입력 바이어스 시험과 408 PWM도 완료했으며 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다. PWM 주기·듀티 capture와 T12 나머지 요구·후속 gate는 이 결과로 완료 처리하지 않는다.

T12 Fixture 402 exact ff483a1·SWD 10 MHz 첫 실행 48개 PASS는 [75번 기록](<../../04_검증 기록/75_T12_Fixture_402_current_source_PWM_ADC_검증.md>)에 보존했다. 401·402 합계 기능 96개·samples 20,736개이며 각 exact identity는 구분한다. 405 오픈드레인·406/407 입력 바이어스 시험과 408 PWM도 완료했으며 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다.

T12 Fixture 403 exact c95b904·SWD 10 MHz 첫 실행 48개 PASS는 [76번 기록](<../../04_검증 기록/76_T12_Fixture_403_current_source_PWM_ADC_검증.md>)에 보존했다. 401~403 합계 기능 144개·samples 31,104개이며 각 exact identity는 구분한다. 405 오픈드레인·406/407 입력 바이어스 시험과 408 PWM도 완료했으며 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다.

T12 Fixture 404 exact e080bbc·SWD 10 MHz 첫 실행 48개 PASS는 [77번 기록](<../../04_검증 기록/77_T12_Fixture_404_current_source_PWM_ADC_검증.md>)에 보존했다. 401~404 합계 기능 192개·samples 41,472개이며 각 exact identity는 구분한다. 405 오픈드레인·406/407 입력 바이어스 시험과 408 PWM도 완료했으며 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다.

T12 Fixture 405 exact 9fc12bf·SWD 10 MHz **첫 실행 12개 PASS**, LOW/해제/LOW·2,592 samples·cleanup 12개와 GPIO readback은 [78번 기록](<../../04_검증 기록/78_T12_Fixture_405_current_source_공유_AIN4_검증.md>)에 보존했다. 공유 AIN4/P1.11의 기능을 확인했으며 이후 406·407도 완료했으며 후속 **408도 완료**했다. 제품 core 변경 없이 Host 648개·pair target 2/2를 통과했고 T12 전체·후속 gate는 미완료다.

T12 Fixture 406 exact 96f38e9·SWD 10 MHz **첫 실행 12개 PASS**, 입력 pull-down/up/down·2,592 samples·cleanup 12개와 GPIO readback은 [79번 기록](<../../04_검증 기록/79_T12_Fixture_406_current_source_공유_AIN5_검증.md>)에 보존했다. Host 649개·pair target 2/2 PASS. 당시 401~406 합계 기능 216개·samples 46,656개였으며 407의 새 결과는 아래 82번에 구분한다. 이후 사용자가 407 결선 A P1.13↔B P1.14·공통 GND와 USB 분리/재연결을 확인했다. 버튼 미누름·DAP UART 분리/SWD 연결 조건이며 LLVM Host 회귀 뒤 결선 유지를 재확인해 407 첫 실행 12개를 통과했다. 408도 완료했으며 이후 420 QDEC도 완료했으며 430 I2S도 exact 36ba819의 전체 192개를 통과했으며 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다. T12 전체·후속 gate는 미완료다.

407 재개 exact 393e419는 설치된 LLVM 22.1.8로 Host **655 PASS·1 조건부 SKIP(총 656)**, 계약 45·package 20·정렬 358·Inventory·예제 발견과 pair/BLE **target 8/8**을 통과했다. BLE 형 변환의 기계어·재배치도 6/6 동일하다. [81번 재개 기록](<../../04_검증 기록/81_T12_Fixture_407_Host_재개와_검증.md>)에 새 근거를 보존했다. 이전 Windows 차단 원본은 80번에 유지하며 보안 정책을 변경하지 않았다. 이 준비 단계에서는 결선 확인 만료로 실기를 보류했다. 이후 사용자 유지 확인을 받아 actual source 4a64c25의 407 첫 실행을 완료했으며 아래 82번에 구분한다.

T12 Fixture 407 exact 4a64c25·SWD 10 MHz **첫 실행 12개 PASS**는 [82번 기록](<../../04_검증 기록/82_T12_Fixture_407_current_source_공유_AIN6_검증.md>)에 보존했다. 버튼 미누름 AIN6/P1.13에서 입력 pull-down/up/down·2,592 samples·cleanup 12개와 입력 GPIO 24회·해제 12회를 확인했다. LOW median 0·HIGH median 3752, postflight 양쪽 source/role 확인 PASS. 당시 401~407 누계는 **228개 기능·49,248 samples·228개 cleanup**이었다. 이후 408 결과는 아래 83번에 구분한다. T12 전체·T13 이후와 readiness 미해결 8개는 유지한다.

T12 Fixture 408 exact 87b987d·SWD 10 MHz **48개 기능 PASS**는 [83번 기록](<../../04_검증 기록/83_T12_Fixture_408_current_source_PWM_ADC_검증.md>)에 보존했다. 최초 DUT flash timeout은 외부 시험 시작 전 실패였으며, 읽기 응답 회복 확인 뒤 한 번의 새 실행으로 10,368 samples·cleanup 48회를 통과했다. 두 runtime identity도 재확인했다. 401~408 누계 **276개 기능·59,616 samples·276개 cleanup**으로 AIN0~7의 개별 기능 근거를 확보했다. 420 QDEC도 완료했다. 현재 **430 I2S는 전체 192개 PASS**이며 440 PDM과 남은 T12 요구·T13 이후·readiness 미해결 8개는 유지한다.

420 QDEC 최신 결과는 [85번 기록](<../../04_검증 기록/85_T12_Fixture_420_current_source_QDEC_재검증.md>)의 **exact 6bd8d3f 기능 48·cleanup 48·시작 전 취소 6개 PASS**다. SWD 10 MHz, 22.063초 기능 실행과 두 보드 identity·핀 복원·PWM/QDEC 해제를 확인했다. [84번](<../../04_검증 기록/84_T12_Fixture_420_current_source_QDEC_검증.md>)의 이전 실패·교정 기록은 유지한다. a3d0ab5와 코드·설정이 같음을 대조했으며 이전 전체 Host 656 PASS·1 조건부 SKIP와 정렬 359 PASS는 해당 source 결과로 구분한다. 430 I2S는 아래 87번에서 오류 교정 후 전체 192개 PASS를 기록했다. 440 PDM의 최신 상태는 아래 90번 재결선·위상 진단 기록을 따른다. 공용 PWM 지연 시작 취소 이슈는 T14, 440 PDM·남은 T12 요구·T13 이후와 readiness 미해결 8개도 유지한다.

430의 이전 세 source 실패·교정·72개 부분 통과 이력은 [86번 기록](<../../04_검증 기록/86_T12_Fixture_430_current_source_I2S_검증.md>)에 보존한다.

430 I2S 최신 결과는 [87번 기록](<../../04_검증 기록/87_T12_Fixture_430_current_source_I2S_재검증.md>)의 **exact 36ba819 기능 192·cleanup 192개 PASS**다. 공용 compact DMA token 처리 지연을 교정해 queue 시간이 278~309 us에서 104~112 us로 줄었고, 수신 원본 384개·전체 payload 82,944 word를 독립 대조했다. SWD 10 MHz, 양쪽 identity·I2S off·핀 복원 확인. 전체 Host 659 PASS·1 조건부 SKIP, 계약 45·package 20·Inventory·정렬 361·관련 target 10개 PASS다. 440의 후속 실기는 88~90번에 실패·부분 결과와 재시험 준비로 구분하며, 남은 T12·T13 이후·T14 공용 PWM 이슈·readiness 미해결 8개를 유지한다. 공용 자원 변경 이후의 T11 외부 실기는 이번에 재실행하지 않았다.

440 PDM의 이전 실행은 [88번 기록](<../../04_검증 기록/88_T12_Fixture_440_current_source_PDM_검증.md>)의 **exact ea4e25a 모노 DMA 4 PASS·첫 stereo FAIL·187 미실행**이다. 밀도 비교는 미도달이며 전체 PDM PASS가 아니다. HIL buffer 공급·신호원·격리된 DAP 핀 metadata를 교정했지만 동일 stereo 채널의 원인은 미해결이다. SWD 10 MHz, cleanup 5회·양쪽 identity/peripheral off·입력 복귀 확인. 전체 Host 660 PASS·1 조건부 SKIP, 정렬 361·pair 2/2 build PASS. 확인 유효시간 20:15:39Z가 지나 440 결선·DAP UART 분리 유지 재확인 후 설정/신호 전달 진단과 전체 재검증을 진행한다. 연속 PDM 4+100 buffer·나머지 T12·T13 이후·T14 공용 PWM·readiness 8개는 유지한다.

440 최신 상태는 [90번 기록](<../../04_검증 기록/90_T12_Fixture_440_재결선과_PDM_위상_진단.md>)의 **재결선 후 clock/gate 분리 96개 PASS·PDM 위상 보완 후 재시험 대기**다. 79e4bdd는 모노 DMA 4개 뒤 stereo 부호 실패, 초기 안정화 수정 7641229는 기능 76개·61,440 samples 뒤 stereo 부호 실패(115개 미실행)를 기록했다. CONSTLAT 요청/해제와 SDK C linkage를 보완한 e9d264c는 pair 2/2·관련 Host 17·정렬 361 PASS이며 실기는 NOT RUN이다. 직전 5273b30의 전체 Host 660 PASS·1 조건부 SKIP는 해당 source 결과로 구분한다. 확인 유효시간 21:32:10Z 만료로 440 결선·DAP UART 분리 유지 답변이 필요하다. 현재 양쪽은 7641229·PDM/SPIS/GPIOTE/DPPI off·신호 입력이다. 연속 4+100 buffer·PDM/T12 전체·후속 gate·readiness 8개는 미완료다.