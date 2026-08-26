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
7. [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>)
8. [Build Adapter 설계](<./02_빌드 설계/02_Build_Adapter_설계.md>)
9. [Arduino CLI 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>)

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

### 03. 펌웨어 설계

- [Arduino Runtime 설계](<./03_펌웨어 설계/01_Arduino_Runtime_설계.md>): `setup()`/`loop()`, 스레드, C++ runtime 및 idle 정책
- [GPIO와 시간 API](<./03_펌웨어 설계/02_GPIO와_시간_API.md>): 디지털 GPIO, `millis()`, `delay()` 및 ISR 경계
- [주변장치 API](<./03_펌웨어 설계/03_주변장치_API.md>): Serial, interrupt, I2C, SPI, ADC 및 PWM 확장 순서
- [테스트와 검증](<./03_펌웨어 설계/04_테스트와_검증.md>): host, Zephyr, Arduino CLI 및 NU54DK HIL 시험

### 04. 검증 기록

- [M1 도구 환경과 보드 실기 기준선](<./04_검증 기록/01_M1_도구와_보드_기준선.md>): 고정 도구 버전, C++ pristine build, CMSIS-DAP V2/pyOCD 기본 경로와 실제 LED 실행 증거
- [M2 Zephyr module과 runtime 기준선](<./04_검증 기록/02_M2_Zephyr_Module과_Runtime_기준선.md>): Core module, C++ runtime 정책, negative build와 `setup()`/`loop()` 실기 증거
- [M3 GPIO·시간·Scheduler 기준선](<./04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>): GPIO·시간 API, loop 정책, sample/negative build와 현재 실기 증거 및 미완료 항목

## 현재 진행 상태

| 단계 | 상태 | 설명 |
| --- | --- | --- |
| M0 기반 고정 | 완료 | 저장소 구조와 NU54DK 보드 서브모듈 연결 완료 |
| M1 도구·보드 실기 기준선 | **완료** | read-only 보드 package로 C++·Blinky pristine build 통과, 기존 CMSIS-DAP V2/pyOCD 실기 검증 유지 |
| M2 Zephyr module·Core 골격 | **완료** | clean module·runtime·Core 비활성·C++ 정책 build 통과, 기존 runtime HIL 유지 |
| M3 west-native Blink | 진행 중 | 결정 게이트 **CONDITIONAL GO**; clean sample 3종·negative 2종 통과, 기존 HIL과 timing trace 유지; 추가 계측과 자동 시험 대기 |
| M4~M11 | 대기 | M3 조건부 게이트에 따라 M4 착수 가능, 이후 단계는 각 선행 게이트 뒤 진행 |

상세 상태는 [구현 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)을 단일 기준으로 관리한다.

## 문서 유지 규칙

1. 구현되지 않은 기능을 지원 완료로 표시하지 않는다.
2. 로드맵 상태를 완료로 변경할 때 빌드 로그, 시험 결과 또는 CI 실행 기록을 함께 남긴다.
3. 물리 핀과 주변장치 정보는 보드 패키지를 단일 원본으로 유지하며, Core 작업에서는 서브모듈을 읽기 전용 입력으로 취급한다.
4. Core 문서에는 Arduino 논리 번호, 변환 규칙 및 API 의미만 기록한다.
5. NCS, Zephyr, Toolchain 또는 보드 package 기준 commit이 바뀌면 모든 검증 결과의 유효성을 다시 판단한다.
6. 설계 변경이 아키텍처 결정에 영향을 주면 결정서의 결정 이력과 로드맵을 함께 갱신한다.
