# NU54DK Arduino Core — 문서 안내

| 항목 | 내용 |
| --- | --- |
| 문서 ID | DOC-INDEX-001 |
| 문서 체계 개정 | 7.0 |
| 현재 정식 버전 | `v0.3.0` |
| 다음 목표 버전 | `v0.4.0` |
| 최종 갱신일 | 2026-09-06 |
| 작성자 | Quantum / NUCODE |

이 디렉터리는 Loader 없이 동작하는 Native Full Zephyr 기반 NU54DK Arduino Core의
**결정, 현재 설계, 제품 계획, 검증 증거와 버전별 사용자 문서**를 관리한다.

`v0.4.0` 작업을 시작하거나 이어받을 때는 [실행 TODO·재개 체크포인트](./TODO_v0.4.0.md)를
먼저 읽는다. 시험 자동화 준비부터 결선·기능 검증·패키지 통합·RC·정식 공개까지 25개 작업의
선행조건·완료 기준·사용자 행동을 관리하며, 현재 다음 항목은 TODO의 체크포인트에서 확인한다.

과거 exact source의 T11은 역사적 단독 기능 체크포인트로 보존한다. R00~R13의 정확성·구조
리팩토링과 최종 전체 software gate는 [64번 기록](<./04_검증 기록/64_R13_도구_정책_build_구조.md>)으로 완료했다.
Current-source T11은 exact 154324c의 Fixture 101 기능 1,644개를 통과했다. 다음은 Fixture 102 전원 OFF 결선 변경이다.
사용자 확인과 current-source T11 회귀 뒤 Fixture 401부터 T12~T15 통합 실기를 진행한다.

T01~T09의 [기능 시험 목록](<./01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>)과
[준비·구현 대조 기록](<./04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>)에서 대상·합격 기준·남은 보완을 확인한다.

## 1. 문서 역할

| 종류 | 답하는 질문 | 갱신 방식 |
| --- | --- | --- |
| ADR | 왜 이 구조와 정책을 선택했는가? | 결정이 바뀔 때만 개정 |
| 설계 | 현재 구현 계약은 무엇인가? | 구현과 함께 갱신 |
| Master roadmap | 지금 어디까지 완료했고 다음은 무엇인가? | 단계 상태가 바뀔 때 갱신 |
| 활성 TODO | 지금 어떤 세부 작업을 어떤 조건으로 재개하는가? | 작업 전 계획·종료 시 체크포인트와 증거 링크 갱신; 완료 뒤 보관/삭제 조건 적용 |
| 리팩토링 계획 | 어떤 정확성·구조 작업을 언제 어떤 회귀와 함께 수행하는가? | R00~R14 체크리스트와 T/M 연결을 함께 갱신 |
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
| M22 | **완료** | Loaderless 1,456 KiB 경계, stable 재현 build, 29/29 설치본 compile, NU54DK Upload와 `v0.3.0` 정식 공개 |
| M23 | **완료** | 75개 peripheral identity manifest·생성 matrix·공개 조회 API와 공통 block/channel/DMA 소유권 |
| M24~M27 | **진행 중** | M24 23개 serial personality 단독 기능 HIL PASS, M25 analog/stream과 전체 동시성·soak 대기; M26 완료, M27 최종 RC·공개 gate HOLD |
| M28~M33 | **계획** | Bluetooth LE 전 기능군·Mesh·Channel Sounding과 `v0.5.0` |
| M34~M45 | **장기 계획** | security/update, radio/OpenThread와 Matter 제품선 |

AC-02A의 구현·시험 경계는
[핀과 주변장치 소유권 기준선](<./04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)에 보존한다.
AC-02B의 구현 범위와 exact 물리 증거는
[Peripheral/Analog runtime 기준선](<./04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)에 보존한다.
Storage 설계와 RC 준비 경계는 [Arduino Storage API](<./03_펌웨어 설계/10_Arduino_Storage_API.md>),
[AC-03 기록](<./04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>) 및
[M22 RC1 기록](<./04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)과
[M22 RC2 기록](<./04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)에서 역사적 공개 결과를
보존한다. RC3 memory-contract와 당시 clean-room 인계 경계는
[M22 RC3 검증·인계 기록](<./04_검증 기록/31_M22_v0.3.0_rc3_검증과_stable_인계.md>)에서 관리한다.
정식 stable의 재현 build, 설치 수명주기와 공개 identity는
[v0.3.0 정식 공개 기록](<./04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)에 고정한다.
정확한 단계 상태의 단일 원본은
[제품 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)이다. `v0.2.0`의 공개 범위와
제약은 역사 문서로 보존하며 현재 사용법은 [v0.3.0 릴리스 문서](<./05_릴리스/v0.3.0/README.md>)를 따른다.

여기서 `완료`는 해당 버전에 선언한 제품 범위를 구현·검증했다는 뜻이다. 모든 Arduino 보드의
API와 제3자 library를 전부 제공한다는 뜻은 아니며, 전체 호환 폭은
[Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)에서 별도로 관리한다.

## 4. 목적별 바로가기

- 구조를 선택한 이유: [ADR-0001](<./00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
- 일반 사용자의 구성 UX: [ADR-0002](<./00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)
- 현재와 다음 단계: [제품 로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>)
- `v0.4.0`의 25개 세부 작업과 인계: [실행 TODO](./TODO_v0.4.0.md)
- T11 뒤 R00~R13 선행 리팩토링과 통합 실기 순서: [리팩토링 문서 안내](<./01_아두이노 코어 설계/14_리팩토링/README.md>)
- 전 instance·DMA·BLE 경쟁 격차와 완료 조건: [경쟁 기준과 마일스톤](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>)
- M24 serial block·핀 bank·고급 API·공통 handover backend·온보드/fixture HIL 경계: [Serial Fabric 경로와 공통 backend](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>)
- P2/P4 물리 커넥터 번호와 net의 수기 확정 기준: [NU54DK P2/P4 커넥터 핀맵](<./01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)
- `v0.4.0` 두 보드 기능 HIL과 정밀 계측·외부 부품 호환성의 구분: [코어 기능 검증 범위](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)
- 첫 외부 UART P2↔P1 fixture의 양방향 1,620-vector 결과: [M24 Fixture 101 실기 검증](<./04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)
- UART P0↔P1 route의 양방향 810-vector 결과: [M24 Fixture 102 실기 검증](<./04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>)
- UART P1↔P1 전 instance 조합의 양방향 2,430-vector 결과: [M24 Fixture 103 실기 검증](<./04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>)
- SPI P2↔P1 route의 18,169-vector 결과와 8 MHz 수신 지연 교정: [M24 Fixture 201 실기 검증](<./04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>)
- SPI P0↔P1 route의 9,084-vector 결과: [M24 Fixture 202 실기 검증](<./04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>)
- SPI P1↔P1 전 instance 조합의 27,252-vector 결과: [M24 Fixture 203 실기 검증](<./04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>)
- TWI P1↔P0 전 instance 조합의 1,986-record 결과: [M24 Fixture 301 실기 검증](<./04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>)
- M23의 현재 instance별 상태: [Peripheral instance matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>)
- M26 system/security/저수준 기능 판정: [System Peripheral 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>)
- 현재 공개 API: [Arduino API 지원 범위](<./01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- Windows source 개발환경: [Windows 개발환경 설정](<./02_빌드 설계/09_Windows_개발환경_설정.md>)
- 설치·package 구조: [Boards Manager 설계](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- 현재 사용자 문서: [v0.3.0 릴리스 문서](<./05_릴리스/v0.3.0/README.md>)
- 설치·시험 절차: [v0.3.0 Testing](<./05_릴리스/v0.3.0/TESTING.md>)
- 실제 시험 증거: [검증 기록 안내](<./04_검증 기록/README.md>)
- 완료된 버전 범위: [v0.3.0 구현 마일스톤](<./01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)

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
- [전 인스턴스·DMA·BLE 경쟁 기준과 마일스톤](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>)
- [M23 Peripheral instance matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>)
- [M24 Serial Fabric 경로와 API 계약](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>)
- [M26 System Peripheral 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>)
- [NU54DK P2/P4 커넥터 핀맵](<./01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)
- [리팩토링 계획·운영·체크리스트](<./01_아두이노 코어 설계/14_리팩토링/README.md>)

### 02. 빌드 설계

- [west-native Blink PoC](<./02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [Build Adapter](<./02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI와 IDE 통합](<./02_빌드 설계/03_Arduino_CLI_통합.md>)
- [Build cache와 산출물](<./02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [Upload와 debug](<./02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 package](<./02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 profile과 Arduino 예제](<./02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [CI/CD와 재현 build](<./02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)
- [Windows 개발환경 설정](<./02_빌드 설계/09_Windows_개발환경_설정.md>)

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

M1~M23과 정식 공개 증거, `v0.3.0` AC-01~AC-03·M19~M22 및 `v0.4.0` M23~M27의 구현·검증 증거는
[검증 기록 안내](<./04_검증 기록/README.md>)에서 찾는다. 이 디렉터리의 문서는 당시 revision과
결과를 보존하는 역사 기록이다.

### 05. 릴리스 문서

현재 stable `v0.3.0`과 보존된 `v0.1.0`/`v0.2.0`/RC 문서는
[릴리스 문서 안내](<./05_릴리스/README.md>)에서 구분한다.
릴리스 문서는 `<version>/README.md`를 진입점으로 삼고 같은 역할은 영문 표준 파일명으로
통일한다. 공개가 끝난 이전 버전의 기능·측정값은 고치지 않고 경로와 색인만 관리한다.

## 6. 단일 원본 규칙

| 정보 | 단일 원본 |
| --- | --- |
| 현재·다음 마일스톤 상태 | Master roadmap |
| `v0.4.0` 세부 작업 상태·다음 행동·재개 조건 | 활성 `TODO_v0.4.0.md`; 완료 근거는 검증 기록에 연결 |
| 리팩토링 R00~R14 순서·완료 조건 | `01_아두이노 코어 설계/14_리팩토링/`의 통합 실행계획과 진행 체크리스트 |
| 물리 pin, pinctrl, peripheral route와 runner | Board submodule |
| HIL용 P2/P4 커넥터 물리 번호↔net 수기 확정표 | `13_NU54DK_P2_P4_커넥터_핀맵.md`와 기계 판독 JSON |
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

2026-09-06 후속: [65번 기록](<./04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>)의 904 PASS·파일 정리를 보존한다. 이후 DAP UART 연결 전환 뒤 [66번 기록](<./04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에서 UART idle bias를 교정하고 온보드 18개 결과·BLE 3개 pair gate를 통과했다. 이후 사용자 결선 완료 확인에 따라 exact 154324c의 current-source T11 Fixture 101을 SWD 10 MHz로 실행해 기능 1,644개를 통과했다. 현재 Fixture 101 결선·DAP UART 분리·SWD 연결 상태이며 다음은 전원 OFF·Fixture 102 결선 변경과 새 사용자 확인이다.

Current-source T11 첫 UART 회귀의 exact 증거와 다음 결선은 [67번 기록](<./04_검증 기록/67_T11_Fixture_101_current_source_UART_회귀.md>)에 연결한다. 전체 T11·T12~T15와 RC/공개는 미완료다.
