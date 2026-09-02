# NU54DK Arduino Core — 문서 안내

| 항목 | 내용 |
| --- | --- |
| 문서 ID | DOC-INDEX-001 |
| 문서 체계 개정 | 4.7 |
| 현재 정식 버전 | `v0.2.0` |
| 다음 목표 버전 | `v0.3.0` |
| 최종 갱신일 | 2026-09-02 |
| 작성자 | Quantum / NUCODE |

이 디렉터리는 Loader 없이 동작하는 Native Full Zephyr 기반 NU54DK Arduino Core의
**결정, 현재 설계, 제품 계획, 검증 증거와 버전별 사용자 문서**를 관리한다.

## 1. 문서 역할

| 종류 | 답하는 질문 | 갱신 방식 |
| --- | --- | --- |
| ADR | 왜 이 구조와 정책을 선택했는가? | 결정이 바뀔 때만 개정 |
| 설계 | 현재 구현 계약은 무엇인가? | 구현과 함께 갱신 |
| Master roadmap | 지금 어디까지 완료했고 다음은 무엇인가? | 단계 상태가 바뀔 때 갱신 |
| 버전 마일스톤 | 해당 버전의 범위와 종료 조건은 무엇이었는가? | 버전 완료 뒤 역사 기록으로 동결 |
| 검증 기록 | 어떤 revision과 시험이 실제로 통과했는가? | 당시 증거를 보존하고 소급 변경하지 않음 |
| 릴리스 문서 | 사용자가 특정 버전을 어떻게 설치·이전·진단하는가? | 버전별로 독립 보존 |

상세 commit, UID, COM port, CI run, HIL 수치와 checksum은 설계 문서에 반복하지 않고
[검증 기록](<./04_검증 기록/README.md>) 또는 [릴리스 문서](<./05_릴리스/README.md>)에 둔다.

## 2. 현재 기준

| 항목 | 기준 |
| --- | --- |
| nRF Connect SDK | v3.4.0 |
| Zephyr | 4.4.0 |
| 대상 | NU54DK / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Board 정의 | `board_package/NU54DK_Zephyr_DTS` 고정 Git submodule |
| 공식 사용자 OS | Windows 10/11 x64 |
| 기본 flash | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 flash | 외장 SEGGER J-Link |
| Firmware | Loader/LLEXT 없는 전체 Zephyr 정적 image |

## 3. 현재 상태

| 범위 | 상태 | 결과 |
| --- | --- | --- |
| M0~M11 | **완료** | `v0.1.0` Core, build/upload, package와 clean Windows 기준선 |
| M12~M18 | **완료** | CI/CD, profile, Core/Variant, Board/System, BLE NUS, NCS coverage와 `v0.2.0` 공개 |
| AC-01 | **자동 검증 완료** | Core·GPIO·시간 Arduino Compatibility exact-commit HIL PASS |
| AC-02 | **완료** | exact `0b7f892`의 3-wire fixture에서 Serial1, BQ25186 Wire, local SPI, ADC와 PWM handover 실기 PASS |
| AC-03 | **완료** | exact `0b7f892`의 두 보드 HIL에서 EEPROM/LittleFS 영속성·손상 거부·복구·정리 PASS |
| M19 | **자동 검증 완료** | BLE Core/GAP exact-commit 두 보드 RF HIL PASS |
| M20 | **자동 검증 완료** | 범용 GATT exact-commit 두 보드 RF HIL PASS |
| M21 | **완료** | Core `065d4f5` exact 두 보드 RF HIL + `d1902b1` Windows 11 pairing·HID 입력·bond 복원 PASS; host 39/39 |
| M22 | **RC3 memory-contract 교정·공개 검증 준비** | Loaderless 1,456 KiB application 경계와 29개 설치 예제·Upload·clean-room 재검증 |
| M23~M34 | **장기 계획** | storage/security, 고급 Memory layout·DFU, radio/OpenThread, Matter 제품선 |

AC-02A의 구현·시험 경계는
[핀과 주변장치 소유권 기준선](<./04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)에 보존한다.
AC-02B의 구현 범위와 exact 물리 증거는
[Peripheral/Analog runtime 기준선](<./04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)에 보존한다.
Storage 설계와 RC 준비 경계는 [Arduino Storage API](<./03_펌웨어 설계/10_Arduino_Storage_API.md>),
[AC-03 기록](<./04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>) 및
[M22 RC1 기록](<./04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)과
[M22 RC2 기록](<./04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)에서 역사적 공개 결과를
보존하고, RC3 memory-contract와 새 실행 결과는 RC3 릴리스·검증 문서에서 별도로 관리한다.
정확한 단계 상태의 단일 원본은
[제품 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)이다. `v0.2.0`의 공개 범위와
제약은 [v0.2.0 릴리스 문서](<./05_릴리스/v0.2.0/README.md>)를 따른다.

여기서 `완료`는 해당 버전에 선언한 제품 범위를 구현·검증했다는 뜻이다. 모든 Arduino 보드의
API와 제3자 library를 전부 제공한다는 뜻은 아니며, 전체 호환 폭은
[Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)에서 별도로 관리한다.

## 4. 목적별 바로가기

- 구조를 선택한 이유: [ADR-0001](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
- 일반 사용자의 구성 UX: [ADR-0002](<./00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)
- 현재와 다음 단계: [제품 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
- 현재 공개 API: [Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- 설치·package 구조: [Boards Manager 설계](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- 현재 사용자 문서: [v0.2.0 릴리스 문서](<./05_릴리스/v0.2.0/README.md>)
- RC 시험 절차: [v0.3.0-rc.3 Testing](<./05_릴리스/v0.3.0-rc.3/TESTING.md>)
- 실제 시험 증거: [검증 기록 안내](<./04_검증 기록/README.md>)
- 다음 버전 범위: [v0.3.0 구현 마일스톤](<./01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)

## 5. 문서 구성

### 00. 사전 리서치와 결정

- [ADR-0001 — 개발 방식 비교와 아키텍처 결정](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
- [ADR-0002 — Arduino 구성 profile과 예제 노출 정책](<./00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)

### 01. Arduino Core 설계

- [저장소 구조와 소유권](<./01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
- [제품 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
- [Pin과 Variant 설계](<./01_아두이노 코어 설계/03_핀과_Variant_설계.md>)
- [Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [v0.2.0 구현 마일스톤](<./01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)
- [NCS v3.4.0 기능·예제 지원 매트릭스](<./01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)
- [v0.3.0 구현 마일스톤](<./01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)

### 02. 빌드 설계

- [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [Build Adapter](<./02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI와 IDE 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>)
- [Build cache와 산출물](<./02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [Upload와 debug](<./02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 package](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 profile과 Arduino 예제](<./02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [CI/CD와 재현 build](<./02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)

### 03. Firmware 설계

- [Arduino Runtime](<./03_펌웨어 설계/01_Arduino_Runtime_설계.md>)
- [GPIO와 시간 API](<./03_펌웨어 설계/02_GPIO와_시간_API.md>)
- [주변장치 API](<./03_펌웨어 설계/03_주변장치_API.md>)
- [시험 전략](<./03_펌웨어 설계/04_테스트와_검증.md>)
- [NU54DK Board/System API](<./03_펌웨어 설계/05_NU54DK_Board_System_API.md>)
- [BLE NUS API](<./03_펌웨어 설계/06_BLE_NUS_API.md>)
- [BLE Core/GAP API](<./03_펌웨어 설계/07_BLE_Core_GAP_API.md>)
- [BLE 범용 GATT API](<./03_펌웨어 설계/08_BLE_범용_GATT_API.md>)
- [BLE 보안과 표준 Profile API](<./03_펌웨어 설계/09_BLE_보안과_표준_Profile_API.md>)
- [Arduino Storage API](<./03_펌웨어 설계/10_Arduino_Storage_API.md>)

### 04. 검증 기록

M1~M18과 정식 공개 증거, `v0.3.0` AC-01~AC-03·M19~M22의 구현·검증 증거는
[검증 기록 안내](<./04_검증 기록/README.md>)에서 찾는다. 이 디렉터리의 문서는 당시 revision과
결과를 보존하는 역사 기록이다.

### 05. 릴리스 문서

현재 stable `v0.2.0`, 새 `v0.3.0-rc.3` 후보와 보존된 `v0.1.0`/RC 문서는
[릴리스 문서 안내](<./05_릴리스/README.md>)에서 구분한다.

## 6. 단일 원본 규칙

| 정보 | 단일 원본 |
| --- | --- |
| 현재·다음 마일스톤 상태 | Master roadmap |
| 물리 pin, pinctrl, peripheral route와 runner | Board submodule |
| Arduino 논리 pin과 API 계약 | Pin/Variant·API 설계 문서와 source |
| 기능별 NCS 지원 판정 | Machine-readable coverage ledger와 지원 매트릭스 |
| 실제 PASS/FAIL, revision과 측정값 | 검증 기록 |
| 공개 archive, checksum과 version별 제약 | 해당 릴리스 문서 |
| 설치용 최신 stable URL | 저장소 최상위 `README.md`와 package index |

## 7. 제목과 버전 규칙

- 제품 version은 `v0.1.0`, `v0.2.0`, `v0.3.0`처럼 쓰며 package metadata만 `v`를 뺀다.
- 마일스톤 번호는 제품 version과 독립된 연속 번호다.
- 문서 개정은 `1.0`, `2.0`처럼 표시하고 제품 SemVer와 혼용하지 않는다.
- 활성 설계는 현재 계약을 쓰고, 과거 목표·실측값은 검증 또는 릴리스 기록으로 보낸다.
- 검증 기록의 과거 `다음 단계`, `HOLD`, `NOT RUN`은 당시 판정이며 현재 상태로 읽지 않는다.

## 8. 유지 규칙

1. 구현하지 않은 기능을 지원 완료로 표시하지 않는다.
2. 마일스톤 완료에는 build, CI 또는 HIL evidence를 연결한다.
3. Board submodule과 vendored ArduinoCore-API는 문서 정리 중 수정하지 않는다.
4. 일반 사용자 절차에서 raw `prj.conf`/overlay 편집을 요구하지 않는다.
5. 사용자 예제는 `libraries/*/examples`를 단일 원본으로 사용한다.
6. NCS/Zephyr/Toolchain 또는 board revision이 바뀌면 기존 검증의 유효성을 다시 판정한다.
7. 구조 변경 뒤 UTF-8, 상대 Markdown link와 package allowlist를 함께 검사한다.
