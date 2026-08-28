# NU54DK Arduino Core 문서 안내

이 디렉터리는 Loader 없이 동작하는 Native Full Zephyr 기반 NU54DK Arduino Core의 결정, 설계, 구현 순서 및 검증 기준을 관리한다.

## 기준 환경

| 항목 | 기준 |
| --- | --- |
| 작성자 | Quantum / NUCODE |
| nRF Connect SDK | v3.4.0 |
| Zephyr | 4.4.0 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 정의 | `board_package/NU54DK_Zephyr_DTS` Git 서브모듈, `fe65f2f0880b` 고정·읽기 전용 |
| 초기 지원 운영체제 | Windows |
| 기본 플래시 경로 | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 플래시 경로 | 외부 J-Link |
| 펌웨어 구조 | Loader/LLEXT 없는 전체 Zephyr 정적 이미지 |

## 권장 열람 순서

1. [개발 방식 비교 및 아키텍처 결정](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
2. [저장소 폴더 구조](<./01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
3. [구현 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
4. [M1 도구 환경과 보드 실기 기준선](<./04_검증 기록/01_M1_도구와_보드_기준선.md>)
5. [M2 Zephyr module과 runtime 기준선](<./04_검증 기록/02_M2_Zephyr_Module과_Runtime_기준선.md>)
6. [M3 GPIO·시간·Scheduler 기준선](<./04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
7. [M4 ArduinoCore-API 계약 기준선](<./04_검증 기록/04_M4_ArduinoCore_API_계약_기준선.md>)
8. [M5 Arduino CLI Build Adapter 기준선](<./04_검증 기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
9. [M6 기본 Arduino API, Serial과 인터럽트 기준선](<./04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
10. [M7 Wire·SPI·ADC·PWM 기준선](<./04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
11. [M8 업로드와 디버그 기준선](<./04_검증 기록/08_M8_업로드와_디버그_기준선.md>)
12. [M9 증분 빌드·캐시와 재현성 기준선](<./04_검증 기록/09_M9_증분_빌드_캐시와_재현성_기준선.md>)
13. [M10 Boards Manager와 clean Windows 기준선](<./04_검증 기록/10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>)
14. [M11 v0.1.0-rc.1 릴리스 후보 기준선(역사적 검증 기록)](<./04_검증 기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)
15. [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>)
16. [Build Adapter 설계](<./02_빌드 설계/02_Build_Adapter_설계.md>)
17. [Arduino CLI 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>)
18. [Boards Manager 설치와 패키징](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
19. [v0.1.0-rc.1 배포 중단 기록](<./05_릴리스/00_v0.1.0_rc1_배포_중단_기록.md>)
20. [v0.1.0-rc.2 릴리스 노트](<./05_릴리스/07_v0.1.0_rc2_릴리스_노트.md>)

## 문서 구성

### 00. 사전 리서치

- [개발 방식 비교 및 아키텍처 결정](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>): 후보 구조, 비용, 가중치 및 최종 아키텍처 결정

### 01. Arduino Core 설계

- [저장소 폴더 구조](<./01_아두이노 코어 설계/01_저장소_폴더_구조.md>): 저장소 경계와 디렉터리 책임
- [구현 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>): M0~M11 작업 순서와 단계별 완료 기준
- [핀과 Variant 설계](<./01_아두이노 코어 설계/03_핀과_Variant_설계.md>): DTS 단일 원본과 Arduino 논리 핀 매핑
- [Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>): API 우선순위와 호환성 상태 관리

### 02. 빌드 설계

- [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>): 첫 수직 PoC의 생성 파일, 명령 및 통과 기준
- [Build Adapter 설계](<./02_빌드 설계/02_Build_Adapter_설계.md>): Arduino 빌드 입력을 Zephyr build graph로 변환하는 계약
- [Arduino CLI 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>): `.ino` 전처리, library discovery 및 platform recipe 연결
- [빌드 캐시와 산출물](<./02_빌드 설계/04_빌드_캐시와_산출물.md>): 증분 빌드, cache key 및 ELF/HEX 관리
- [업로드와 디버그](<./02_빌드 설계/05_업로드와_디버그.md>): pyOCD/J-Link runner, probe 선택 및 복구 정책
- [Boards Manager 설치와 패키징](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>): 공개 preview index, 사용자 영역 Nordic prerequisite, 재현 가능한 package와 clean Windows 수명주기 계약

### 03. 펌웨어 설계

- [Arduino Runtime 설계](<./03_펌웨어 설계/01_Arduino_Runtime_설계.md>): `setup()`/`loop()`, 스레드, C++ runtime 및 idle 정책
- [GPIO와 시간 API](<./03_펌웨어 설계/02_GPIO와_시간_API.md>): 디지털 GPIO, `millis()`, `delay()` 및 ISR 경계
- [주변장치 API](<./03_펌웨어 설계/03_주변장치_API.md>): Serial, interrupt, I2C, SPI, ADC 및 PWM 확장 순서
- [테스트와 검증](<./03_펌웨어 설계/04_테스트와_검증.md>): host, Zephyr, Arduino CLI 및 NU54DK HIL 시험

### 04. 검증 기록

- [M1 도구 환경과 보드 실기 기준선](<./04_검증 기록/01_M1_도구와_보드_기준선.md>): 고정 도구 버전, C++ pristine build, CMSIS-DAP V2/pyOCD 기본 경로와 실제 LED 실행 증거
- [M2 Zephyr module과 runtime 기준선](<./04_검증 기록/02_M2_Zephyr_Module과_Runtime_기준선.md>): Core module, C++ runtime 정책, negative build와 `setup()`/`loop()` 실기 증거
- [M3 GPIO·시간·Scheduler 기준선](<./04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>): GPIO·시간 API, loop 정책, sample/negative build와 Twister HIL 완료 증거
- [M4 ArduinoCore-API 계약 기준선](<./04_검증 기록/04_M4_ArduinoCore_API_계약_기준선.md>): 고정 upstream snapshot, 라이선스 경계와 NU54DK target compile 증거
- [M5 Arduino CLI Build Adapter 기준선](<./04_검증 기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md>): `.ino`·library discovery에서 Full Zephyr 산출물까지의 Arduino CLI 수직 경로와 자동 회귀 증거
- [M6 기본 Arduino API, Serial과 인터럽트 기준선](<./04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>): ArduinoCore-API 공통 구현, 실제 UART Serial HIL, target ztest와 P1.13 물리 edge 완료 증거
- [M7 Wire·SPI·ADC·PWM 기준선](<./04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>): M7 공개 API·DTS/Kconfig 계약, 0x6A HIL 안전 경계와 실제·미검증 결과 행렬
- [M8 업로드와 디버그 기준선](<./04_검증 기록/08_M8_업로드와_디버그_기준선.md>): manifest 검증, Arduino Upload recipe, pyOCD 10회 HIL과 source breakpoint 증거
- [M9 증분 빌드·캐시와 재현성 기준선](<./04_검증 기록/09_M9_증분_빌드_캐시와_재현성_기준선.md>): persistent cache key, ccache, lock/LRU와 cold/warm/손상 복구 실측 증거
- [M10 Boards Manager와 clean Windows 기준선](<./04_검증 기록/10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>): 공개 preview의 clean Windows 최초 설치, build/upload와 전체 수명주기 완료 증거
- [M11 v0.1.0-rc.1 릴리스 후보 기준선](<./04_검증 기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>): 회수 전 exact RC 필수 gate 8/8, M10 retained-prerequisite 원격 회귀와 pyOCD+UART HIL을 보존한 역사적 증거

### 05. 릴리스

- [v0.1.0-rc.1 배포 중단 기록](<./05_릴리스/00_v0.1.0_rc1_배포_중단_기록.md>)
- [v0.1.0-rc.1 마이그레이션 안내](<./05_릴리스/01_v0.1.0_rc1_마이그레이션.md>)
- [v0.1.0-rc.1 문제 해결](<./05_릴리스/02_v0.1.0_rc1_문제해결.md>)
- [v0.1.0-rc.1 릴리스 노트](<./05_릴리스/03_v0.1.0_rc1_릴리스_노트.md>)
- [v0.1.0-rc.1 알려진 제약](<./05_릴리스/04_v0.1.0_rc1_알려진_제약.md>)
- [v0.1.0-rc.2 마이그레이션 안내](<./05_릴리스/05_v0.1.0_rc2_마이그레이션.md>)
- [v0.1.0-rc.2 문제 해결](<./05_릴리스/06_v0.1.0_rc2_문제해결.md>)
- [v0.1.0-rc.2 릴리스 노트](<./05_릴리스/07_v0.1.0_rc2_릴리스_노트.md>)
- [v0.1.0-rc.2 알려진 제약](<./05_릴리스/08_v0.1.0_rc2_알려진_제약.md>)

## 현재 진행 상태

| 단계 | 상태 | 설명 |
| --- | --- | --- |
| M0 기반 고정 | 완료 | 저장소 구조와 NU54DK 보드 서브모듈 연결 완료 |
| M1 도구·보드 실기 기준선 | **완료** | read-only 보드 package로 C++·Blinky pristine build 통과, 기존 CMSIS-DAP V2/pyOCD 실기 검증 유지 |
| M2 Zephyr module·Core 골격 | **완료** | clean module·runtime·Core 비활성·C++ 정책 build 통과, 기존 runtime HIL 유지 |
| M3 west-native GPIO·시간 | **완료** | sample 3종 pristine build, negative와 NU54DK ztest/Twister HIL 9/9 통과 |
| M4 ArduinoCore-API 계약 | **완료** | 1.5.2 고정 snapshot·라이선스 고지·NU54DK API 계약 pristine build 통과 |
| M5 Arduino CLI Build Adapter | **완료** | Full Zephyr 산출물 5종 생성과 staged-copy 자동 회귀 6/6 통과 |
| M6 기본 Arduino API | **완료** | 공통 API·Serial·interrupt 구현, target ztest 10/10·COM10 Serial HIL·실제 P1.13 `FALLING`/`RISING`/`CHANGE` HIL 통과 |
| M7 버스·아날로그·PWM API | **완료** | NU54DK Twister target 11/11·전체 Builder 8/8(M7 예제 4/4)·I2C/ADC/PWM HIL·SPI00 4 MHz 40-byte 물리 loopback 통과 |
| M8 업로드와 디버그 | **완료** | manifest·artifact·probe 안전검사, Arduino CLI pyOCD upload 10/10, 최종 UART reset과 `setup()` source breakpoint 통과 |
| M9 증분 빌드·캐시·재현성 | **완료** | persistent tree와 canonical key, host 43/43, library·parallel·M9 Arduino CLI 회귀 및 실측 기준선 통과 |
| M10 Boards Manager 패키징 | **완료** | 공개 preview `0.0.96`→`0.0.97`, clean Windows 11/11 단계와 pyOCD upload 10/10 통과 |
| M11 v0.1 릴리스 후보 | **RC 교정 중** | `v0.1.0-rc.1`의 exact gate 8/8 기록은 보존하되 Arduino IDE post-install gRPC UTF-8 결함으로 배포를 중단하고 `v0.1.0-rc.2` 재검증·공개 준비 중 |

상세 상태는 [구현 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)을 단일 기준으로 관리한다.

## 문서 유지 규칙

1. 구현되지 않은 기능을 지원 완료로 표시하지 않는다.
2. 로드맵 상태를 완료로 변경할 때 빌드 로그, 시험 결과 또는 CI 실행 기록을 함께 남긴다.
3. 물리 핀과 주변장치 정보는 보드 패키지를 단일 원본으로 유지하며, Core 작업에서는 서브모듈을 읽기 전용 입력으로 취급한다.
4. Core 문서에는 Arduino 논리 번호, 변환 규칙 및 API 의미만 기록한다.
5. NCS, Zephyr, Toolchain 또는 보드 package 기준 commit이 바뀌면 모든 검증 결과의 유효성을 다시 판단한다.
6. 설계 변경이 아키텍처 결정에 영향을 주면 결정서의 결정 이력과 로드맵을 함께 갱신한다.
