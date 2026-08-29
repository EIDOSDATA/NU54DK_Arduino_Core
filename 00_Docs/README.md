# NU54DK Arduino Core — 문서 안내

| 항목 | 내용 |
| --- | --- |
| 문서 ID | DOC-INDEX-001 |
| 문서 체계 개정 | 2.2 |
| 현재 정식 버전 | `v0.1.0` |
| 다음 목표 버전 | `v0.2.0` |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |

이 디렉터리는 Loader 없이 동작하는 Native Full Zephyr 기반 NU54DK Arduino Core의 결정,
설계, 구현 순서, 검증 증거와 릴리스 기록을 관리한다.

## 기준 환경

| 항목 | 기준 |
| --- | --- |
| nRF Connect SDK | v3.4.0 |
| Zephyr | 4.4.0 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 정의 | `board_package/NU54DK_Zephyr_DTS` 고정 Git submodule |
| 공식 사용자 OS | Windows 10/11 x64 |
| 기본 플래시 | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 플래시 | 외장 SEGGER J-Link |
| Firmware | Loader/LLEXT 없는 전체 Zephyr 정적 image |

## 먼저 읽을 문서

1. [ADR-0001 — 개발 방식과 아키텍처 결정](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
2. [ADR-0002 — Arduino 구성 프로필과 예제 노출 정책](<./00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)
3. [저장소 구조와 소유권](<./01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
4. [제품 로드맵과 구현 마일스톤](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
5. [v0.2.0 구현 마일스톤](<./01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)
6. [NCS v3.4.0 기능과 예제 지원 매트릭스](<./01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)
7. [NU54DK Board/System API 설계](<./03_펌웨어 설계/05_NU54DK_Board_System_API.md>)
8. [Boards Manager 설치와 패키징](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
9. [v0.1.0 릴리스 노트](<./05_릴리스/11_v0.1.0_릴리스_노트.md>)

## 현재 진행 상태

| 범위 | 상태 | 설명 |
| --- | --- | --- |
| M0~M11 | **완료** | `v0.1.0` build, API, HIL, package와 clean Windows 공개 완료 |
| M12 | **완료** | 고정 NCS CI/CD와 Linux/Windows 재현 build |
| M13 | **완료** | `standard` profile, strict feature resolver와 Arduino 예제 7개 |
| M14 | **완료** | Core API·DTS Variant, 로컬·원격 software/runtime와 신규 pin 물리 HIL 통과 |
| M15 | **진행 중** | board/system API·예제·시험 구현 중; 자동 결과 반영과 SW0 System OFF wake 물리 HIL 대기 |
| M16 | 대기 | basic BLE Arduino library |
| M17 | 대기 | NCS 기능·예제 coverage 첫 묶음 |
| M18 | 대기 | `v0.2.0` RC와 stable 공개 |

상세 상태의 단일 원본은
[제품 로드맵과 구현 마일스톤](<./01_아두이노 코어 설계/02_구현_로드맵.md>)이다.

## 문서 구성

### 00. 사전 리서치와 결정

- [ADR-0001 — 개발 방식 비교 및 아키텍처 결정](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
- [ADR-0002 — Arduino 구성 프로필과 예제 노출 정책](<./00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)

### 01. Arduino Core 설계

- [저장소 구조와 소유권](<./01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
- [제품 로드맵과 구현 마일스톤](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
- [핀과 Variant 설계](<./01_아두이노 코어 설계/03_핀과_Variant_설계.md>)
- [Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [v0.2.0 구현 마일스톤](<./01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)
- [NCS v3.4.0 기능과 예제 지원 매트릭스](<./01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)

### 02. 빌드 설계

- [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [Build Adapter 설계](<./02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI 및 IDE 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>)
- [빌드 캐시와 산출물](<./02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [업로드와 디버그](<./02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 패키징](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 프로필과 Arduino 예제 배포](<./02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [M12 CI/CD와 재현 빌드](<./02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)

### 03. Firmware 설계

- [Arduino Runtime 설계](<./03_펌웨어 설계/01_Arduino_Runtime_설계.md>)
- [GPIO와 시간 API](<./03_펌웨어 설계/02_GPIO와_시간_API.md>)
- [주변장치 API](<./03_펌웨어 설계/03_주변장치_API.md>)
- [테스트와 검증](<./03_펌웨어 설계/04_테스트와_검증.md>)
- [NU54DK Board/System API](<./03_펌웨어 설계/05_NU54DK_Board_System_API.md>)

### 04. 검증 기록

- [M1 도구 환경과 보드 기준선](<./04_검증 기록/01_M1_도구와_보드_기준선.md>)
- [M2 Zephyr module과 runtime 기준선](<./04_검증 기록/02_M2_Zephyr_Module과_Runtime_기준선.md>)
- [M3 GPIO·시간·Scheduler 기준선](<./04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [M4 ArduinoCore-API 계약 기준선](<./04_검증 기록/04_M4_ArduinoCore_API_계약_기준선.md>)
- [M5 Arduino CLI Build Adapter 기준선](<./04_검증 기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [M6 기본 API·Serial·interrupt 기준선](<./04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<./04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M8 업로드와 디버그 기준선](<./04_검증 기록/08_M8_업로드와_디버그_기준선.md>)
- [M9 증분 빌드·캐시·재현성 기준선](<./04_검증 기록/09_M9_증분_빌드_캐시와_재현성_기준선.md>)
- [M10 Boards Manager·clean Windows 기준선](<./04_검증 기록/10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>)
- [M11 v0.1.0-rc.1 역사 기록](<./04_검증 기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)
- [M11 v0.1.0-rc.2 공개 후 검증](<./04_검증 기록/12_M11_v0.1.0_rc2_공개_후_수동_검증.md>)
- [v0.1.0 정식 릴리스 공개 기록](<./04_검증 기록/13_v0.1.0_정식_릴리스_공개_기록.md>)
- [M12 CI/CD와 재현 build 기준선](<./04_검증 기록/14_M12_CI_CD_기준선.md>)
- [M13 구성 profile 및 예제 배포 검증](<./04_검증 기록/15_M13_구성_프로필_검증.md>)
- [M14 Core API와 Variant 기준선](<./04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [M15 NU54DK Board/System 기준선](<./04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)

### 05. 릴리스 문서

`v0.1.0-rc.1`, `v0.1.0-rc.2`와 `v0.1.0`의 migration, troubleshooting, release notes와
known issues를 보존한다.

- [v0.1.0-rc.1 배포 중단 기록](<./05_릴리스/00_v0.1.0_rc1_배포_중단_기록.md>)
- [v0.1.0-rc.2 릴리스 노트](<./05_릴리스/07_v0.1.0_rc2_릴리스_노트.md>)
- [v0.1.0 migration](<./05_릴리스/09_v0.1.0_마이그레이션.md>)
- [v0.1.0 문제 해결](<./05_릴리스/10_v0.1.0_문제해결.md>)
- [v0.1.0 릴리스 노트](<./05_릴리스/11_v0.1.0_릴리스_노트.md>)
- [v0.1.0 알려진 제약](<./05_릴리스/12_v0.1.0_알려진_제약.md>)

기존 v0.1 파일명은 역사 링크 때문에 유지한다. v0.2부터는 다음처럼 버전별 디렉터리를
사용한다.

```text
05_릴리스/v0.2.0/
├─ README.md
├─ RELEASE_NOTES.md
├─ KNOWN_ISSUES.md
├─ MIGRATION.md
└─ TROUBLESHOOTING.md
```

## 문서 제목과 버전 규칙

- 제품 버전: `v0.1.0`, `v0.2.0`; package metadata만 앞의 `v`를 생략한다.
- 마일스톤: `M0`~`M18`; 제품 버전과 독립된 연속 번호다.
- 문서 개정: `1.0`, `2.0`; 제품 SemVer와 혼용하지 않는다.
- 활성 설계 문서는 가능하면 `문서 ID`, `문서 개정`, `적용 제품 버전`, `최종 갱신일`을 둔다.
- 검증·릴리스 기록은 실행 commit, 날짜와 exact 제품 version을 유지한다.
- bare `v1`을 제품 version 의미로 쓰지 않는다. 내부 항목은 `cache schema v1`처럼 대상을
  함께 적는다.

## 문서 유지 규칙

1. 구현하지 않은 기능을 지원 완료로 표시하지 않는다.
2. 마일스톤 완료에는 build log, 시험 결과 또는 CI/HIL evidence를 연결한다.
3. 보드 package와 ArduinoCore-API vendored snapshot은 Core 문서 정리 중 수정하지 않는다.
4. 물리 pin·runner·회로 문서는 보드 package를 단일 원본으로 사용한다.
5. 일반 사용자 절차에서 raw `prj.conf`/overlay 편집을 요구하지 않는다.
6. 예제는 `libraries/*/examples`를 단일 원본으로 사용한다.
7. NCS/Zephyr/Toolchain 또는 board commit이 바뀌면 기존 검증의 유효성을 다시 판정한다.
8. 구조 변경 뒤 상대 Markdown link와 package allowlist를 함께 검증한다.
