# NU54DK Arduino Core — 검증 기록 안내

| 항목 | 내용 |
| --- | --- |
| 문서 성격 | 실행 당시의 revision, 환경, 명령과 결과를 보존하는 역사 증거 |
| 완료 범위 | M1~M23, M26 판정, `v0.1.0`·`v0.2.0`·`v0.3.0` 정식 공개 |
| 진행 범위 | `v0.4.0` M24~M25 physical gate와 M27 release 준비 |
| 현재 정식 버전 | `v0.3.0` |
| 최종 갱신일 | 2026-09-04 |

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

## 기록 해석 규칙

1. 정확한 commit, checksum, 장치 UID, COM port와 수치는 해당 기록을 우선한다.
2. 과거 record의 완료 판정을 현재 release의 전체 재시험으로 확대하지 않는다.
3. `build-only`, `NOT RUN`, 수동 확인과 자동 HIL을 서로 같은 PASS로 합치지 않는다.
4. 설계 변경으로 경로가 이동해도 당시 결과와 artifact identity는 소급 수정하지 않는다.
5. 현재 지원 여부는 [API 지원 범위](<../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)와
   [NCS 지원 매트릭스](<../01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)를 함께 확인한다.
