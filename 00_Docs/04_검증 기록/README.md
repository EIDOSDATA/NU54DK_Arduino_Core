# 검증 기록

이곳은 시험 당시의 source·환경·조건·성공·실패와 원본을 보존합니다.
현재 완료 상태와 다음 실행은 [v0.4.0 TODO](../TODO_v0.4.0.md)를 확인하세요.

현재 진행·잔여·제외 범위는 TODO, S 종료와 U 준비 근거는
[113번](113_T13_S_범위_종료와_U_준비.md), 전체 문서 정비와 남은 마일스톤은
[114번](114_전체_문서_정비와_남은_마일스톤.md)에서 확인합니다.

## 최근 확인할 기록

| 기록 | 용도 |
| --- | --- |
| [114 — 전체 문서 정비와 남은 마일스톤](114_전체_문서_정비와_남은_마일스톤.md) | 전수 검토·현행/역사 분리·U 및 T14 이후 남은 작업 |
| [113 — S 범위 종료와 U 준비](113_T13_S_범위_종료와_U_준비.md) | PASS 56 + 제외 2, System OFF 중복 판정·마지막 GPIO 진단·U 준비 |
| [112 — SPI·TWI 완료와 System OFF 원인](112_T13_S_SPI_TWI_완료와_System_OFF_원인.md) | 당시 S 56/58·레지스터·공식 예제·물리 SWD 격리 원인 |
| [111 — I2S 완료와 SPIS 교정](111_T13_S_I2S_완료와_SPIS_연속_버퍼_교정.md) | I2S 완료·SPI 최초 실패와 원인 수정 |
| [110 — 문서 정리와 S 잔여 재개](110_문서_정리와_T13_S_잔여_재개.md) | 전수 문서 감사·UART 원인 수정·U 준비 증거 |
| [109 — 세 복구 묶음과 연속 전환 제외](109_T13_S_세_복구_묶음_재검증.md) | 당시 TWIM 완료·I2S 잔여와 전환 시험 제외 결정 |
| [108 — 이전 S 실행 종료](108_T13_S_자동_실행_종료와_재개_항목.md) | 이전 실패·미실행·도구 보완 |
| [107 — S와 System OFF](107_T13_S_자동_진행과_System_OFF_계획.md) | 정상 안정성·추가 오류 복구·전원 검증 |
| [106 — Git·패키지 정리](106_Git_이력_정리와_구버전_패키지_공급_종료.md) | 공급 종료와 원본 복원 |
| [101 — QDEC 알려진 문제](101_T12_QDEC_누산_누락_원인_분리.md) | 누산 누락·보완·진단 종료 |

## 기록 읽는 방법

- PASS는 기록에 명시된 exact source·역할·핀·속도·시간·조건에만 적용합니다.
- Host·target build·실제 HIL·설치·공개 결과를 구분합니다. 준비 결과를 실기 PASS로 세지 않습니다.
- 실패·부분 완료·시험 제외·사용자 수용은 각각 별도로 남깁니다. 후속 결과로 원본을 덮어쓰지 않습니다.
- `evidence/`의 manifest는 압축 파일과 원본 byte의 SHA-256을 연결합니다.
- 과거 문서의 “다음 작업”은 당시 계획입니다. 현재 지시는 TODO와 최신 사용자 요청이 우선입니다.

## 전체 기록 목차

<details>
<summary>v0.4.0 최근 실기·인계 — 94~114</summary>

- [94 — T14 PWM 지연 시작 취소와 무점퍼 검증](<94_T14_PWM_지연_시작_취소와_무점퍼_검증.md>)
- [95 — T12 내부 ADC·TIMER·이벤트 무점퍼 검증](<95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md>)
- [96 — 새 PC 인수 확인과 T12 PWM peer capture 첫 경로 준비](<96_새_PC_인수와_T12_PWM_peer_capture_준비.md>)
- [97 — T12 PWM peer capture 첫 240조건 검증](<97_T12_PWM_peer_capture_첫_240조건_검증.md>)
- [98 — T13 단독 안정성 3분 기준 조정](<98_T13_단독_안정성_3분_기준_조정.md>)
- [99 — 공통 결선 검사와 승인 전 자동 진행 계획](<99_공통_결선_검사와_승인_전_자동_진행_계획.md>)
- [100 — T12 공통 기능 묶음과 T13 시험 조합 확정](<100_T12_공통_기능_묶음과_T13_조합_확정.md>)
- [101 — T12 QDEC 누산 누락 원인 분리](<101_T12_QDEC_누산_누락_원인_분리.md>)
- [102 — 개발 문서 전수 검토와 v0.4.0 마일스톤 체크포인트](<102_개발_문서_전수_검토와_마일스톤_체크포인트.md>)
- [103 — TIMER 기능 완료 정리와 T13 자동 진행 경계](<103_TIMER_기능_완료와_T13_진행_경계.md>)
- [104 — T13 S 결선의 복구·동시·안정성 검증](<104_T13_S_복구_동시_안정성_검증.md>)
- [105 — T13 S GPIO 전수 결선 진단](<105_T13_S_GPIO_전수_결선_진단.md>)
- [106 — Git 이력 정리와 구버전 패키지 공급 종료](<106_Git_이력_정리와_구버전_패키지_공급_종료.md>)
- [107 — T13 S 자동 진행과 peer 제어 System OFF 검증 계획](<107_T13_S_자동_진행과_System_OFF_계획.md>)
- [108 — T13 S 자동 실행 종료와 재개 항목](<108_T13_S_자동_실행_종료와_재개_항목.md>)
- [109 — T13 S 자원 충돌 수용과 세 복구 묶음 재검증](<109_T13_S_세_복구_묶음_재검증.md>)
- [110 — 전체 문서 정리와 T13 S 잔여 재개](<110_문서_정리와_T13_S_잔여_재개.md>)
- [111 — T13 S I2S 완료와 SPIS 연속 버퍼 교정](<111_T13_S_I2S_완료와_SPIS_연속_버퍼_교정.md>)
- [112 — T13 S SPI·TWI 완료와 System OFF 원인](<112_T13_S_SPI_TWI_완료와_System_OFF_원인.md>)
- [113 — T13 S 범위 종료와 U 준비](<113_T13_S_범위_종료와_U_준비.md>)
- [114 — 전체 문서 정비와 남은 마일스톤](<114_전체_문서_정비와_남은_마일스톤.md>)

</details>

<details>
<summary>v0.4.0 기능 회귀 — 67~93</summary>

- [67 — T11 Fixture 101 current-source UART 회귀](<67_T11_Fixture_101_current_source_UART_회귀.md>)
- [68 — T11 Fixture 102 current-source UART 회귀](<68_T11_Fixture_102_current_source_UART_회귀.md>)
- [69 — T11 Fixture 103 current-source UART 회귀](<69_T11_Fixture_103_current_source_UART_회귀.md>)
- [70 — T11 Fixture 201 current-source SPI 회귀](<70_T11_Fixture_201_current_source_SPI_회귀.md>)
- [71 — T11 Fixture 202 current-source SPI 회귀](<71_T11_Fixture_202_current_source_SPI_회귀.md>)
- [72 — T11 Fixture 203 current-source SPI 회귀](<72_T11_Fixture_203_current_source_SPI_회귀.md>)
- [73 — T11 Fixture 301 current-source TWI 회귀와 통신 단독 검증 완료](<73_T11_Fixture_301_current_source_TWI_회귀.md>)
- [74 — T12 Fixture 401 current-source PWM→AIN0 실기 검증](<74_T12_Fixture_401_current_source_PWM_ADC_검증.md>)
- [75 — T12 Fixture 402 current-source PWM→AIN1 실기 검증](<75_T12_Fixture_402_current_source_PWM_ADC_검증.md>)
- [76 — T12 Fixture 403 current-source PWM→AIN2 실기 검증](<76_T12_Fixture_403_current_source_PWM_ADC_검증.md>)
- [77 — T12 Fixture 404 current-source PWM→AIN3 실기 검증](<77_T12_Fixture_404_current_source_PWM_ADC_검증.md>)
- [78 — T12 Fixture 405 — 공유 AIN4 오픈드레인 실기 검증](<78_T12_Fixture_405_current_source_공유_AIN4_검증.md>)
- [79 — T12 Fixture 406 — current-source 공유 AIN5 검증](<79_T12_Fixture_406_current_source_공유_AIN5_검증.md>)
- [80 — T12 Fixture 407 준비와 Host 실행 차단](<80_T12_Fixture_407_준비와_Host_실행_차단.md>)
- [81 — T12 Fixture 407 — Host 재개와 software 검증](<81_T12_Fixture_407_Host_재개와_검증.md>)
- [82 — T12 Fixture 407 — current-source 공유 AIN6 검증](<82_T12_Fixture_407_current_source_공유_AIN6_검증.md>)
- [83 — T12 Fixture 408 — current-source PWM→AIN7 검증](<83_T12_Fixture_408_current_source_PWM_ADC_검증.md>)
- [84 — T12 Fixture 420 — QDEC 기능 검증과 준비 취소 교정](<84_T12_Fixture_420_current_source_QDEC_검증.md>)
- [85 — T12 Fixture 420 — QDEC 수정본 재검증 완료](<85_T12_Fixture_420_current_source_QDEC_재검증.md>)
- [86 — T12 Fixture 430 — I2S 부분 통과와 짧은 버퍼 실패](<86_T12_Fixture_430_current_source_I2S_검증.md>)
- [87 — T12 Fixture 430 — DMA 자원 처리 지연 교정과 I2S 전체 PASS](<87_T12_Fixture_430_current_source_I2S_재검증.md>)
- [88 — T12 Fixture 440 — PDM DMA 교정과 스테레오 미해결](<88_T12_Fixture_440_current_source_PDM_검증.md>)
- [89 — T10/T12 Fixture 440 — clock·gate 네 핀의 전기적 연결 관측](<89_T12_Fixture_440_clock_gate_분리_진단.md>)
- [90 — T10/T12 Fixture 440 — 재결선과 PDM 위상 진단](<90_T12_Fixture_440_재결선과_PDM_위상_진단.md>)
- [91 — T12 Fixture 440 — PDM 밀도와 연속 DMA 검증](<91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md>)
- [92 — T12 Fixture 440 — PDM 연속 전체 검증](<92_T12_Fixture_440_PDM_연속_전체_검증.md>)
- [93 — Host 재검증과 T12 이후 남은 작업](<93_Host_재검증과_T12_이후_남은_작업.md>)

</details>

<details>
<summary>v0.4.0 구현·리팩토링 — 33~66</summary>

- [33 — M23 Peripheral inventory와 공통 소유권 기준선](<33_M23_Peripheral_Inventory와_공통_소유권_기준선.md>)
- [34 — M24 Serial Fabric 경로와 API 계약 기준선](<34_M24_Serial_Fabric_경로와_API_계약_기준선.md>)
- [35 — M24 Serial Fabric 공통 backend 기준선](<35_M24_Serial_Fabric_공통_backend_기준선.md>)
- [36 — M24 Serial Fabric adapter와 온보드 HIL 준비 기록](<36_M24_Serial_Fabric_adapter와_온보드_HIL_준비.md>)
- [37 — M25 Analog·Event·Stream Fabric과 온보드 HIL 준비 기록](<37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>)
- [38 — M26 System Peripheral 판정과 온보드 HIL 준비 기록](<38_M26_System_Peripheral_판정과_온보드_HIL_준비.md>)
- [39 — M27 v0.4.0-rc.1 자동 준비와 HOLD 기록](<39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)
- [40 — M24~M26 온보드 재개와 USB·UART 진단](<40_M24_M26_온보드_재개와_USB_UART_진단.md>)
- [41 — M24~M26 온보드 protocol 교정과 실기 재검증](<41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)
- [42 — v0.4.0 코어 기능 검증 범위 합의](<42_v0.4.0_코어_기능_검증_범위_합의.md>)
- [43 — v0.4.0 T01~T09 시험 준비와 구현 대조](<43_v0.4.0_시험_준비와_구현_대조.md>)
- [44 — M24 Fixture 101 UART 실기 검증](<44_M24_Fixture_101_UART_실기_검증.md>)
- [45 — M24 Fixture 102 UART 실기 검증](<45_M24_Fixture_102_UART_실기_검증.md>)
- [46 — M24 Fixture 103 UART 실기 검증](<46_M24_Fixture_103_UART_실기_검증.md>)
- [47 — M24 Fixture 201 SPI 실기 검증](<47_M24_Fixture_201_SPI_실기_검증.md>)
- [48 — M24 Fixture 202 SPI 실기 검증](<48_M24_Fixture_202_SPI_실기_검증.md>)
- [49 — M24 Fixture 203 SPI 실기 검증](<49_M24_Fixture_203_SPI_실기_검증.md>)
- [50 — M24 Fixture 301 TWI 실기 검증](<50_M24_Fixture_301_TWI_실기_검증.md>)
- [51 — R00 — 리팩토링 기준선과 characterization 계약](<51_R00_리팩토링_기준선.md>)
- [52 — R01 — Serial adapter의 Core target 소속 교정](<52_R01_CMake_source_소속_교정.md>)
- [53 — R02 — Serial 완료·timeout·DMA 수명주기](<53_R02_Serial_완료와_DMA_수명주기.md>)
- [54 — R03 — Analog/Stream ISR·정지 동기화](<54_R03_Analog_Stream_ISR_정지_동기화.md>)
- [55 — R04 — LittleFS File 공유 slot 수명주기](<55_R04_File_공유_slot_수명주기.md>)
- [56 — R05 — Core 소스와 패키지 identity](<56_R05_Core_소스와_패키지_identity.md>)
- [57 — R06 — builder 모듈과 설치 경로](<57_R06_builder_모듈과_설치_경로.md>)
- [58 — R07 — EventFabric 책임 분할](<58_R07_EventFabric_책임_분할.md>)
- [59 — R08 자원 관리자와 runtime route 책임 분리](<59_R08_자원과_경로_수명주기.md>)
- [60 — R09 Arduino SPI facade/backend 경계](<60_R09_Arduino_SPI_경계.md>)
- [61 — R10 Serial Fabric 동시 호출과 orchestration 분리](<61_R10_Serial_Fabric_동시_호출.md>)
- [62 — R11 Analog/Stream peripheral 분리](<62_R11_Analog_Stream_peripheral_분리.md>)
- [63 — R12 BLE·Storage 수명주기 구조 확대](<63_R12_BLE_Storage_수명주기.md>)
- [64 — R13 도구·정책·build 구조와 최종 software 입력](<64_R13_도구_정책_build_구조.md>)
- [65 — R13 후속 USB 무배선 실기와 작업 파일 정리](<65_R13_후속_USB_무배선_실기와_정리.md>)
- [66 — T09 UART 유휴 bias 교정과 BLE 무배선 회귀](<66_T09_UART_유휴_bias와_BLE_회귀.md>)

</details>

<details>
<summary>v0.1.0~v0.3.0 역사 기록 — 1~32</summary>

- [01 — M1 도구 환경과 NU54DK 보드 실기 기준선](<01_M1_도구와_보드_기준선.md>)
- [02 — M2 Zephyr module과 Arduino runtime 기준선](<02_M2_Zephyr_Module과_Runtime_기준선.md>)
- [03 — M3 GPIO, 시간과 Scheduler 기준선](<03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [04 — M4 ArduinoCore-API 계약 기준선](<04_M4_ArduinoCore_API_계약_기준선.md>)
- [05 — M5 Arduino CLI Build Adapter 기준선](<05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [06 — M6 기본 Arduino API, Serial과 인터럽트 기준선](<06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [07 — M7 Wire·SPI·ADC·PWM 기준선](<07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [08 — M8 업로드와 디버그 기준선](<08_M8_업로드와_디버그_기준선.md>)
- [09 — M9 증분 빌드, 캐시와 재현성 기준선](<09_M9_증분_빌드_캐시와_재현성_기준선.md>)
- [10 — M10 Boards Manager 패키징과 Clean Windows 기준선](<10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>)
- [11 — M11 v0.1.0-rc.1 릴리스 후보 기준선](<11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)
- [12 — M11 v0.1.0-rc.2 공개 후 수동 검증 기록](<12_M11_v0.1.0_rc2_공개_후_수동_검증.md>)
- [13 — v0.1.0 정식 릴리스 공개 기록](<13_v0.1.0_정식_릴리스_공개_기록.md>)
- [14 — M12 CI/CD와 재현 빌드 기준선](<14_M12_CI_CD_기준선.md>)
- [15 — M13 구성 프로필 및 예제 배포 검증](<15_M13_구성_프로필_검증.md>)
- [16 — M14 Core API와 Variant 기준선](<16_M14_Core_API와_Variant_기준선.md>)
- [17 — M15 NU54DK Board/System 기준선](<17_M15_NU54DK_Board_System_기준선.md>)
- [18 — M16 BLE NUS 기준선](<18_M16_BLE_NUS_기준선.md>)
- [19 — M17 NCS 기능과 예제 Coverage 기준선](<19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [20 — M18 v0.2.0 RC1·RC2 공개 검증 기록](<20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- [21 — v0.2.0 정식 릴리스 공개 기록](<21_v0.2.0_정식_릴리스_공개_기록.md>)
- [22 — AC-01 connector GPIO와 Arduino 호환 API 검증](<22_AC-01_GPIO_호환성_검증.md>)
- [23 — M19 BLE Core/GAP 검증](<23_M19_BLE_Core_GAP_검증.md>)
- [24 — M20 범용 GATT server/client 검증](<24_M20_범용_GATT_검증.md>)
- [25 — M21 BLE 보안과 표준 Profile 검증](<25_M21_BLE_보안과_표준_Profile_검증.md>)
- [26 — AC-02A 핀과 주변장치 소유권 기준선](<26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [27 — AC-02B Peripheral/Analog runtime 기준선](<27_AC-02B_Peripheral_Analog_runtime_기준선.md>)
- [28 — AC-03 Storage와 Library 호환성 기준선](<28_AC-03_Storage와_Library_호환성_기준선.md>)
- [29 — M22 v0.3.0-rc.1 통합 릴리스 기준선](<29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)
- [30 — M22 v0.3.0-rc.2 통합 릴리스 기준선](<30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)
- [31 — M22 v0.3.0-rc.3 검증과 v0.3.0 stable 인계 기록](<31_M22_v0.3.0_rc3_검증과_stable_인계.md>)
- [32 — M22 v0.3.0 정식 릴리스 공개 기록](<32_M22_v0.3.0_정식_릴리스_공개_기록.md>)

</details>
