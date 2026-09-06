# NU54DK Arduino Core — 검증 기록 안내

| 항목 | 내용 |
| --- | --- |
| 문서 성격 | 실행 당시의 revision, 환경, 명령과 결과를 보존하는 역사 증거 |
| 완료 범위 | M1~M23, M26 판정, `v0.1.0`·`v0.2.0`·`v0.3.0` 정식 공개 |
| 진행 범위 | `v0.4.0` M24~M25 physical gate와 M27 release 준비 |
| 현재 정식 버전 | `v0.3.0` |
| 최종 갱신일 | 2026-09-06 |

이 디렉터리는 **현재 사용법이나 다음 작업을 설명하는 곳이 아니다.** 각 기록의 `다음 단계`,
`HOLD`, `미실행`과 `NOT RUN`은 그 문서를 작성한 시점의 경계를 뜻한다. 현재 상태는
[Master roadmap](<../01_아두이노 코어 설계/02_구현_로드맵.md>), 현재 사용자 절차는
[v0.3.0 릴리스 문서](<../05_릴리스/v0.3.0/README.md>)를 따른다.

## v0.1.0 기반 — M1~M11

| 단계 | 결과 | 기록 |
| --- | --- | --- |
| M1 | 도구·board·CMSIS-DAP/pyOCD 기준선 | [M1 기록](01_M1_도구와_보드_기준선.md) |
| M2 | Zephyr module과 Arduino runtime 골격 | [M2 기록](02_M2_Zephyr_Module과_Runtime_기준선.md) |
| M3 | GPIO·시간·scheduler 수직 경로 | [M3 기록](03_M3_GPIO_시간과_Scheduler_기준선.md) |
| M4 | ArduinoCore-API 계약 | [M4 기록](04_M4_ArduinoCore_API_계약_기준선.md) |
| M5 | Arduino CLI Build Adapter | [M5 기록](05_M5_Arduino_CLI_Build_Adapter_기준선.md) |
| M6 | 기본 API·Serial·interrupt | [M6 기록](06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md) |
| M7 | Wire·SPI·ADC·PWM | [M7 기록](07_M7_Wire_SPI_ADC_PWM_기준선.md) |
| M8 | upload와 debug | [M8 기록](08_M8_업로드와_디버그_기준선.md) |
| M9 | 증분 build·cache·재현성 | [M9 기록](09_M9_증분_빌드_캐시와_재현성_기준선.md) |
| M10 | Boards Manager·clean Windows | [M10 기록](10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md) |
| M11 RC1 | 기술 gate 통과 뒤 GUI UTF-8 결함으로 회수 | [RC1 역사 기록](11_M11_v0.1.0_rc1_릴리스_후보_기준선.md) |
| M11 RC2 | clean Windows 설치·compile·upload·실행 | [RC2 수동 검증](12_M11_v0.1.0_rc2_공개_후_수동_검증.md) |
| Stable | `v0.1.0` 정식 공개 | [v0.1.0 공개 기록](13_v0.1.0_정식_릴리스_공개_기록.md) |

## v0.2.0 개발 — M12~M18

| 단계 | 결과 | 기록 |
| --- | --- | --- |
| M12 | CI/CD와 Linux/Windows 재현 build | [M12 기록](14_M12_CI_CD_기준선.md) |
| M13 | 구성 profile과 Arduino 예제 | [M13 기록](15_M13_구성_프로필_검증.md) |
| M14 | Core API와 DTS 기반 Variant | [M14 기록](16_M14_Core_API와_Variant_기준선.md) |
| M15 | NU54DK Board/System API와 System OFF | [M15 기록](17_M15_NU54DK_Board_System_기준선.md) |
| M16 | BLE NUS Peripheral/Central | [M16 기록](18_M16_BLE_NUS_기준선.md) |
| M17 | NCS 기능·예제 coverage와 feasibility | [M17 기록](19_M17_NCS_기능과_예제_Coverage_기준선.md) |
| M18 RC | RC1 공개 검증과 RC2 교정 | [M18 RC 기록](20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md) |
| Stable | `v0.2.0` 정식 공개와 공개 수명주기 | [v0.2.0 공개 기록](21_v0.2.0_정식_릴리스_공개_기록.md) |

## v0.3.0 — Arduino Compatibility, BLE와 정식 공개

| 작업 | 현재 결과 | 기록 |
| --- | --- | --- |
| AC-01 | connector GPIO, open-drain, level IRQ, pulse/shift와 안전한 callback mask의 exact-commit HIL PASS | [AC-01 기록](22_AC-01_GPIO_호환성_검증.md) |
| M19 | BLE Core/GAP 두 보드 RF HIL PASS; 첫 자동 PHY 요청 실패와 교정 이력 보존 | [M19 기록](23_M19_BLE_Core_GAP_검증.md) |
| M20 | 범용 GATT server/client 두 보드 RF HIL PASS | [M20 기록](24_M20_범용_GATT_검증.md) |
| M21 | Core `065d4f5` exact 두 보드 RF HIL + `d1902b1` Windows 11 pairing·HID 입력·bond 복원 PASS; host 39/39 | [M21 기록](25_M21_BLE_보안과_표준_Profile_검증.md) |
| AC-02A | 고정 슬롯 핀·주변장치 소유권 manager, 부팅 registry와 GPIO 충돌 gate; target ztest 8/8 PASS | [AC-02A 기록](26_AC-02A_핀과_주변장치_소유권_기준선.md) |
| AC-02B | exact `0b7f892`의 3-wire fixture에서 Serial1·BQ25186 Wire·local SPI·ADC→PWM handover 실기 PASS | [AC-02B 기록](27_AC-02B_Peripheral_Analog_runtime_기준선.md) |
| AC-03 | exact `0b7f892`의 두 보드에서 EEPROM/LittleFS 영속성·손상 거부·복구·정리 PASS | [AC-03 기록](28_AC-03_Storage와_Library_호환성_기준선.md) |
| M22 RC1 | fixed gate PASS 뒤 tagged clean-room 실행기 결함으로 formal 검증 중단; tag·자산 불변 보존 | [RC1 기록](29_M22_v0.3.0_rc1_통합_릴리스_기준선.md) |
| M22 RC2 | 새 plan·4 gate, 29개 설치 예제·실제 Upload·public clean-room lifecycle와 cleanup PASS | [RC2 기록](30_M22_v0.3.0_rc2_통합_릴리스_기준선.md) |
| M22 RC3 | 1,456 KiB memory contract, fixed gate·29/29 compile와 실제 Upload PASS; 사용자 reset 중단을 기록하고 stable lifecycle로 인계 | [RC3 검증·인계 기록](31_M22_v0.3.0_rc3_검증과_stable_인계.md) |
| M22 Stable | 독립 package 재현, RC3 runtime 동등성, 설치 lifecycle·29/29 compile·NU54DK Upload와 정식 공개 PASS | [v0.3.0 정식 공개 기록](32_M22_v0.3.0_정식_릴리스_공개_기록.md) |

## v0.4.0 개발 — Peripheral Parity

| 작업 | 현재 결과 | 기록 |
| --- | --- | --- |
| M23 | 75개 identity manifest·생성 matrix·공개 조회 API, 같은 block 상호배타와 block/channel/DMA 원자적 lease PASS | [M23 기록](33_M23_Peripheral_Inventory와_공통_소유권_기준선.md) |
| M24 작업 1 | 5개 serial block·23개 personality의 route/API/DMA/errata 계약과 exact DTS·문서 drift gate PASS | [M24 작업 1 기록](34_M24_Serial_Fabric_경로와_API_계약_기준선.md) |
| M24 작업 2 | Allocation-free typed handle, 원자적 route/DMA lease, bounded handover와 target semantic build PASS | [M24 작업 2 기록](35_M24_Serial_Fabric_공통_backend_기준선.md) |
| M24 작업 3~6 | 23개 direct adapter source/build PASS, 온보드 runner 준비; SWD `No ACK`와 외부 fixture gate HOLD | [M24 adapter·HIL 기록](36_M24_Serial_Fabric_adapter와_온보드_HIL_준비.md) |
| M25 | Analog·event·stream 전 instance 후보 source/build PASS, 온보드 runner 준비; physical gate HOLD | [M25 기록](37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md) |
| M26 | System 기능 16개 전수 판정·unknown 0, TEMP·WDT30 runner 준비; physical gate HOLD | [M26 기록](38_M26_System_Peripheral_판정과_온보드_HIL_준비.md) |
| M27 | 비공개 RC 이중 package 재현·설치본 29/29 compile PASS; physical·공개 gate HOLD | [M27 자동 준비·HOLD 기록](39_M27_v0.4.0_rc1_자동_준비와_HOLD.md) |
| 온보드 재개 | 새 18/18 build·M26 flash/readback 확인; READY 누락·reset 경계 잡음·USB 이탈로 formal HIL HOLD | [온보드 재개·진단 기록](40_M24_M26_온보드_재개와_USB_UART_진단.md) |
| 온보드 교정·재검증 | `51c1986` 18/18 build, UART 4개·TWIM 3개·내부 VDD/event·TEMP/WDT30 formal PASS; 외부 fixture·최종 release HOLD | [교정·실기 재검증](41_M24_M26_온보드_protocol_교정과_실기_재검증.md) |
| 검증 범위 합의 | 두 NU54DK 기반 코어 기능 HIL 유지, 정밀 계측·외부 부품별 호환성은 범위 밖; 미실행 기능·공개 HOLD 유지 | [코어 기능 검증 범위](42_v0.4.0_코어_기능_검증_범위_합의.md) |
| Fixture 101 UART | exact `2542a01`에서 P2↔P1 UARTE 양방향 data 1,620·예상 오류 24·cleanup 2건 PASS; 다른 fixture HOLD | [M24 Fixture 101 실기 검증](44_M24_Fixture_101_UART_실기_검증.md) |
| Fixture 102 UART | exact `ff3423e`에서 P0↔P1 UARTE 양방향 data 810·예상 오류 12·cleanup 2건 PASS; Fixture 103·SPI·TWI HOLD | [M24 Fixture 102 실기 검증](45_M24_Fixture_102_UART_실기_검증.md) |
| Fixture 103 UART | exact `b3c689b`에서 P1↔P1 UARTE20/21/22 전 조합 양방향 data 2,430·예상 오류 36·cleanup 2건 PASS; SPI·TWI HOLD | [M24 Fixture 103 실기 검증](46_M24_Fixture_103_UART_실기_검증.md) |
| Fixture 201 SPI | exact `f21377e`에서 P2↔P1 SPIM/SPIS 18,169개 계획 벡터·cleanup 2건 PASS; Fixture 202~203·TWI 301 HOLD | [M24 Fixture 201 실기 검증](47_M24_Fixture_201_SPI_실기_검증.md) |
| Fixture 202 SPI | exact `1a133e6`에서 P0↔P1 SPIM/SPIS 9,084개 계획 벡터·cleanup 2건 PASS; Fixture 203·TWI 301 HOLD | [M24 Fixture 202 실기 검증](48_M24_Fixture_202_SPI_실기_검증.md) |
| Fixture 203 SPI | exact `4af93da`에서 P1↔P1 SPIM/SPIS 전 조합 27,252개 계획 벡터·cleanup 2건 PASS; TWI 301 HOLD | [M24 Fixture 203 실기 검증](49_M24_Fixture_203_SPI_실기_검증.md) |
| Fixture 301 TWI | exact `e2f045c`에서 P1↔P0 TWIM/TWIS20·21·22·30 전 조합 1,986개 기능 record·cleanup 2건 PASS; T11 완료, 동시성·soak HOLD | [M24 Fixture 301 실기 검증](50_M24_Fixture_301_TWI_실기_검증.md) |
| R00 기준선 | exact `ec3bba3`의 API·CLI·저장 계약, software gate와 대표 target 10/10 build-only·ELF/메모리·symbol 기준선; 새 physical NOT RUN | [R00 리팩토링 기준선](51_R00_리팩토링_기준선.md) |

## 기록 해석 규칙

R01의 source target 교정과 실제 9개 target build-only 결과는
[52번 기록](52_R01_CMake_source_소속_교정.md)에 연결한다. 새 physical 결과는 없다.
R02의 완료·DMA 수명주기 수정은 [53번 기록](53_R02_Serial_완료와_DMA_수명주기.md)의
production Host 회귀 24개와 target 12/12 build-only에 연결한다.

완료된 T01~T09 준비·무배선 검증과 T10 이후 외부 결선 경계는 [43번 준비 기록](43_v0.4.0_시험_준비와_구현_대조.md)을 따른다.
준비 목록과 Host 검사 성공은 새 physical PASS가 아니다.

1. 정확한 commit, checksum, 장치 UID, COM port와 수치는 해당 기록을 우선한다.
2. 과거 record의 완료 판정을 현재 release의 전체 재시험으로 확대하지 않는다.
3. `build-only`, `NOT RUN`, 수동 확인과 자동 HIL을 서로 같은 PASS로 합치지 않는다.
4. 설계 변경으로 경로가 이동해도 당시 결과와 artifact identity는 소급 수정하지 않는다.
5. 현재 지원 여부는 [API 지원 범위](<../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)와
   [NCS 지원 매트릭스](<../01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)를 함께 확인한다.

R03 Analog/Stream ISR·stop 및 DMA 실패 수명주기는 [54번 기록](54_R03_Analog_Stream_ISR_정지_동기화.md)의
production 회귀 26개와 target 5/5 build-only에 연결한다. 새 physical 결과는 없다.

R04 File 공유 slot 참조·마지막 close·thread 교차는 [55번 기록](55_R04_File_공유_slot_수명주기.md)의
production 회귀 8개와 AC-03 target 2/2 build-only에 연결한다.

R05 Core 소스·설치 package identity는 [56번 기록](56_R05_Core_소스와_패키지_identity.md)의
6개 Host 회귀, target 2/2 및 ELF 문자열 확인에 연결한다.

R06 builder 모듈 추출·설치 compile 및 공백 recipe 교정은 [57번 기록](57_R06_builder_모듈과_설치_경로.md)에 연결한다.

R07 EventFabric registry/peripheral 분할은 [58번 기록](58_R07_EventFabric_책임_분할.md)의
전후 Host·target·symbol·메모리 비교에 연결한다.

R08 자원 정책·transaction·동기화 및 runtime route phase/획득 기록 분리는
[59번 기록](59_R08_자원과_경로_수명주기.md)에 연결한다.

R09 Arduino SPI facade/backend 분리는 [60번 기록](60_R09_Arduino_SPI_경계.md)에 연결한다.

R10-A Serial Fabric STOP 예약과 동시 호출 수정은 [61번 기록](61_R10_Serial_Fabric_동시_호출.md)에
연결한다. R10-A/B/C software 완료 당시 current-source T11은 미실행이었다.

R11 Analog/Stream peripheral 분리는 [62번 기록](62_R11_Analog_Stream_peripheral_분리.md)에 연결한다.

R12 BLE·Storage 분리는 [63번 기록](63_R12_BLE_Storage_수명주기.md)에 연결한다. GAP/GATT/Security·Storage와 전체 R12 software 회귀를 완료했다.

R13 도구·정책·build 구조와 최종 software 입력은 [64번 기록](64_R13_도구_정책_build_구조.md)에 연결한다.

R13 뒤 USB 무배선 온보드 904 PASS와 중간 파일 정리는 [65번 기록](65_R13_후속_USB_무배선_실기와_정리.md)에 연결한다. 해당 65번 실행 당시 두 보드는 USB만 연결되어 있었고 외부 current-source T11은 미실행이었다.

DAP UART 연결 전환 뒤 BLE 회귀와 온보드 유휴 bias 교정은 [66번 기록](66_T09_UART_유휴_bias와_BLE_회귀.md)에 연결한다. 해당 66번 실행 당시 외부 current-source T11은 미실행이었다.

사용자 Fixture 101 결선 완료 뒤 exact 154324c·SWD 10 MHz의 기능 1,644 PASS는 [67번 기록](67_T11_Fixture_101_current_source_UART_회귀.md)에 연결한다. 해당 실행 뒤 Fixture 102로 이어졌다.

Exact a49cc0d·SWD 10 MHz의 Fixture 102 기능 822 PASS는 [68번 기록](68_T11_Fixture_102_current_source_UART_회귀.md)에 연결한다. 해당 실행 뒤 Fixture 103으로 이어졌다.

Fixture 103 exact 7aece93·SWD 10 MHz 기능 2,466 PASS와 최초 peer flash 실패·한정 재개는 [69번 기록](69_T11_Fixture_103_current_source_UART_회귀.md)에 보존했다. Current-source UART 세 묶음을 완료했다.

Fixture 201 exact 0f429e7·SWD 10 MHz 기능 18,169 PASS와 새 결선은 [70번 기록](70_T11_Fixture_201_current_source_SPI_회귀.md)에 보존했다. 해당 실행 뒤 Fixture 202로 이어졌다.

Fixture 202 exact 1349e20·SWD 10 MHz 기능 9,084 PASS, 최초 peer flash 실패·한정 재개는 [71번 기록](71_T11_Fixture_202_current_source_SPI_회귀.md)에 보존했다.

Fixture 203 exact be49207·SWD 10 MHz 기능 27,252 PASS, 최초 DUT flash 실패·한정 재개는 [72번 기록](72_T11_Fixture_203_current_source_SPI_회귀.md)에 보존했다. Current-source SPI 세 route를 완료했다.

Fixture 301 exact 9a63251·SWD 10 MHz 첫 실행 1,986 PASS와 current-source T11 단독 통신 회귀 완료는 [73번 기록](73_T11_Fixture_301_current_source_TWI_회귀.md)에 보존했다. UART·SPI·TWI 일곱 묶음 61,423개 기능 결과를 대조했다. 이후 T12 Fixture 401~404도 각각 48개를 통과했으며 405도 오픈드레인 시험을 완료했으며 다음은 필수 후속 406→407→408이다.

T12 Fixture 401 exact a12e444·SWD 10 MHz 첫 실행 48개 기능 PASS와 10,368 samples·cleanup 48개는 [74번 기록](<74_T12_Fixture_401_current_source_PWM_ADC_검증.md>)에 보존했다. T12는 부분 완료이며 405도 오픈드레인 시험을 완료했으며 다음은 필수 후속 406→407→408이다. PWM 주기·듀티 capture와 T12 나머지 요구·후속 gate는 이 결과로 완료 처리하지 않는다.

T12 Fixture 402 exact ff483a1·SWD 10 MHz 첫 실행 48개 PASS는 [75번 기록](<75_T12_Fixture_402_current_source_PWM_ADC_검증.md>)에 보존했다. 401·402 합계 기능 96개·samples 20,736개이며 각 exact identity는 구분한다. 405도 오픈드레인 시험을 완료했으며 다음은 필수 후속 406→407→408이다.

T12 Fixture 403 exact c95b904·SWD 10 MHz 첫 실행 48개 PASS는 [76번 기록](<76_T12_Fixture_403_current_source_PWM_ADC_검증.md>)에 보존했다. 401~403 합계 기능 144개·samples 31,104개이며 각 exact identity는 구분한다. 405도 오픈드레인 시험을 완료했으며 다음은 필수 후속 406→407→408이다.

T12 Fixture 404 exact e080bbc·SWD 10 MHz 첫 실행 48개 PASS는 [77번 기록](<77_T12_Fixture_404_current_source_PWM_ADC_검증.md>)에 보존했다. 401~404 합계 기능 192개·samples 41,472개이며 각 exact identity는 구분한다. 405도 오픈드레인 시험을 완료했으며 다음은 필수 후속 406→407→408이다.

T12 Fixture 405 exact 9fc12bf·SWD 10 MHz **첫 실행 12개 PASS**, LOW/해제/LOW·2,592 samples·cleanup 12개와 GPIO readback은 [78번 기록](<78_T12_Fixture_405_current_source_공유_AIN4_검증.md>)에 보존했다. 공유 AIN4/P1.11의 기능을 확인했으며 후속 **406→407→408을 모두 수행**한다. 제품 core 변경 없이 Host 648개·pair target 2/2를 통과했고 T12 전체·후속 gate는 미완료다.
