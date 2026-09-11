# 문서 안내

현재 정식 배포는 **v0.4.0**입니다. 설치와 사용은 버전별 안내를, 완료된 개발·검증 과정은
TODO와 검증 기록을 확인하세요.

| 목적 | 읽을 문서 |
| --- | --- |
| 처음 설치·업로드 | [프로젝트 README](../README.md), [v0.4.0 사용자 안내](<05_릴리스/v0.4.0/README.md>) |
| v0.4.0 완료 상태 | [v0.4.0 완료 TODO](TODO_v0.4.0.md), [정식 공개 기록](<04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>) |
| 다른 PC에서 개발 재개 | [인계 문서](HANDOFF_v0.4.0_다른_PC.md), [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>) |
| API·GPIO·설계 계약 | 아래 설계 문서 목차 |
| 실제 검증 결과 | [검증 기록](<04_검증 기록/README.md>) |
| 결선·실기 실행 | [HIL 안내](../tests/hil/nu54dk/README.md), [T13 S/U 결선](../tests/hil/nu54dk/T13_PLAN.md) |
| 정식·이전 버전 문서 | [릴리스 안내](<05_릴리스/README.md>) |

## 설계 문서 목차

### 코어·핀·API·로드맵

- [저장소 구조와 소유권](<01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
- [제품 로드맵과 구현 마일스톤](<01_아두이노 코어 설계/02_구현_로드맵.md>)
- [NU54DK Arduino 핀과 Variant 설계](<01_아두이노 코어 설계/03_핀과_Variant_설계.md>)
- [NU54DK Arduino API 지원 범위](<01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [NU54DK Arduino Core v0.2.0 — 구현 마일스톤](<01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)
- [NCS v3.4.0 기능·예제 지원 매트릭스](<01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)
- [NU54DK Arduino Core v0.3.0 — 구현 마일스톤](<01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)
- [전 인스턴스·DMA·BLE 경쟁 기준과 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>)
- [M23 — nRF54L15/NU54DK Peripheral 인스턴스 매트릭스](<01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>)
- [M24 작업 1~5 — Serial Fabric 전 instance와 EasyDMA](<01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>)
- [M26 System Peripheral 지원 경계](<01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>)
- [v0.4.0 기능 시험 목록](<01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>)
- [NU54DK P2/P4 커넥터 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)

### 설치·빌드·업로드

- [West Native Blink PoC — M3 역사적 기준선](<02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [NU54DK Build Adapter 설계 — v0.4.0](<02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI 및 IDE 통합 설계 — v0.3.0](<02_빌드 설계/03_Arduino_CLI_통합.md>)
- [빌드 캐시와 산출물 — v0.3.0 계약](<02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [업로드와 디버그 — v0.3.0 지원 경계](<02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 패키징 — stable v0.4.0](<02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 프로필과 Arduino 예제 배포 — v0.4.0 정식](<02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [CI/CD와 재현 빌드 — v0.4.0 stable 현재 계약](<02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)
- [Windows 개발환경 설정](<02_빌드 설계/09_Windows_개발환경_설정.md>)

### Runtime·주변장치·BLE·Storage

- [NU54DK Arduino Runtime 설계](<03_펌웨어 설계/01_Arduino_Runtime_설계.md>)
- [NU54DK Arduino GPIO와 시간 API 설계](<03_펌웨어 설계/02_GPIO와_시간_API.md>)
- [NU54DK Arduino 주변장치 API 설계](<03_펌웨어 설계/03_주변장치_API.md>)
- [NU54DK Arduino Core 테스트와 검증](<03_펌웨어 설계/04_테스트와_검증.md>)
- [NU54DK Board/System API 설계](<03_펌웨어 설계/05_NU54DK_Board_System_API.md>)
- [NUCODE BLE NUS API 설계](<03_펌웨어 설계/06_BLE_NUS_API.md>)
- [BLE Core/GAP API 설계](<03_펌웨어 설계/07_BLE_Core_GAP_API.md>)
- [BLE 범용 GATT server/client API 설계](<03_펌웨어 설계/08_BLE_범용_GATT_API.md>)
- [BLE 보안과 표준 Profile API](<03_펌웨어 설계/09_BLE_보안과_표준_Profile_API.md>)
- [NU54DK Arduino Storage API 설계](<03_펌웨어 설계/10_Arduino_Storage_API.md>)

## 리팩토링과 배경 자료

- [R00~R14 리팩토링 안내](<01_아두이노 코어 설계/14_리팩토링/README.md>): 구현 순서·체크리스트·최종 RC 연결
- [최초 조사·아키텍처 결정](<00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>): 당시 설계 판단

## 문서 관리 원칙

- 완료 상태와 제품선 작업은 TODO 또는 후속 계획 한곳에서 갱신합니다. README·설계 문서에 시각별 실기 보고를 반복하지 않습니다.
- 설계 문서는 동작·소유권·오류 계약, 검증 기록은 exact source·시험 조건·실제 결과를 설명합니다.
- 과거 검증·공급 종료 버전 문서는 당시 사실을 보존합니다. 현재 지원·재실행 지시로 읽지 않습니다.
- 생성 문서는 JSON·생성기를 수정한 뒤 재생성합니다. SDK·서드파티·기존 공개 패키지는 문서 정리로 바꾸지 않습니다.
- 사용자 결정에 따른 시험 제외·알려진 제한은 성공한 시험과 구분합니다. 범위와 기록을 함께 남깁니다.

## 결과 표기

| 표기 | 뜻 |
| --- | --- |
| PASS | 적힌 source·조건·횟수에서 판정 기준 충족 |
| FAIL | 실제 실행에서 기준 미충족. 최초 실패 원본 보존 |
| NOT RUN | 실행하지 않음. 준비·build 통과와 별개 |
| 사용자 수용·범위 제외 | 작업 범위 결정. 실패 수정이나 새 실기 PASS가 아님 |

과거 기록의 당시 수치는 현재 진행률에 다시 더하지 않습니다. 명령·핀표는 해당 fixture의 계약이며
현재 결선을 바꾸라는 지시가 아닙니다. 고정 원본을 참고할 때는 문서에 적힌 source와 날짜를 함께 확인합니다.
