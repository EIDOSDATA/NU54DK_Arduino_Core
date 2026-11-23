# 문서 안내

## 사용 안내

| 찾는 내용 | 문서 |
| --- | --- |
| 처음 설치하고 Blink 업로드하기 | [프로젝트 README](../README.md#빠른-시작) |
| v0.6.0 공개 설치와 버전 전환 | [설치 안내](<05_릴리스/v0.6.0/README.md>), [버전 전환](<05_릴리스/v0.6.0/MIGRATION.md>) |
| 지원 OS, IDE Upload, YAML 오류 | [검증 환경](<05_릴리스/v0.6.0/SUPPORT_MATRIX.md>), [문제 해결](<05_릴리스/v0.6.0/TROUBLESHOOTING.md>) |
| IDE의 Feature set 12개 비교 | [메뉴 이름별 용도, 준비물과 대표 예제](<05_릴리스/v0.6.0/FEATURE_SETS.md>) |
| 예제 코드 따라 하기 | [Blink, SerialEcho, 보드 두 대로 BLE 메시지 보내기](<05_릴리스/v0.6.0/EXAMPLE_WALKTHROUGH.md>) |
| 더 많은 예제와 결선 찾기 | [204개 예제 색인](../libraries/EXAMPLES.md), [API 범위](<01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>), [P2/P4 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>) |

## 개발과 검증

| 찾는 내용 | 문서 |
| --- | --- |
| 브랜치 준비와 검사 | [기여 안내](../CONTRIBUTING.md), [고정 Nordic 환경 설치](<02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>) |
| 현재 진행과 다음 작업 | [개발 인계](HANDOFF.md), [M33 TODO](TODO_M33.md), [최종 후보 체크리스트](<05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>) |
| W06 수락 범위와 원형 증거 | [M33 인계](M33_HANDOFF.md#판단-정정과-증거-경계) |
| 소스별 CI와 실기 | [검증 근거](<05_릴리스/v0.6.0/TESTING.md>), [번호별 검증 기록](<04_검증 기록/README.md>) |
| Mac 실기 자료와 writer 인계 | [Mac 인계](MAC_HANDOFF.md), [Mac 후속 작업 안내](MAC_START_PROMPT.txt) |
| 설치 및 패키징 설계 | [native Boards Manager 설계](<02_빌드 설계/14_native_Boards_Manager_package와_CI.md>), [RC1 실기 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>) |
| SDK 후속 전환 | [v0.7.0 계획](TODO_v0.7.0.md) |

## TODO 읽기·갱신 범위

[M33](TODO_M33.md)과 [v0.6.0](TODO_v0.6.0.md)은 해당 버전의 결과를, [v0.7.0](TODO_v0.7.0.md)은 예정된 SDK 전환을 다룹니다. 이전 버전과 M31, M32의 완료 TODO는 각 검증 당시의 근거를 찾을 때 사용합니다.

## 현행 안내와 기록 구분

| 문서 종류 | 읽는 기준 |
| --- | --- |
| README·현행 설계·도구 안내 | 현재 사용·개발 계약. 예전 버전 전용 설계는 제목과 적용 범위에 별도 표시 |
| TODO·인계 | M33·v0.6.0은 현행 계획, v0.7.0은 예정된 SDK 전환, HANDOFF는 재개 절차. 완료 TODO 6개는 갱신 동결한 당시 이력이며 재실행 지시가 아님 |
| 검증 기록·evidence | 당시 source·조건·실제 결과. 후속 해결은 안내 링크로 연결하고 원본 판정은 보존 |
| 버전별 공개 릴리스 문서 | 해당 package에 고정된 내용. 현재 stable은 v0.6.0 안내 사용 |

폴더는 역할에 따라 `00_사전 리서치`(배경), `01_아두이노 코어 설계`(공개 계약),
`02_빌드 설계`(설치·빌드), `03_펌웨어 설계`(runtime), `04_검증 기록`(재현 증거),
`05_릴리스`(버전별 사용자 안내)로 구분합니다. 기존 링크와 evidence 경로를 보존하기 위해
완료 기록을 다른 번호나 폴더로 옮기지 않습니다.

## 설계 문서 목차

SDK 설치와 고정 입력은 [Host별 환경 설치](<02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>), 실제 결과는 [Host 원장](../variants/nu54dk/host-readiness.json)에 있습니다.

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
- [M28 BLE GAP·Link·Privacy 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)
- [M29 ATT/GATT·L2CAP 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)
- [M30 BLE Security·Profile·DFU 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)
- [문서 전면 검토와 개선 마일스톤](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)
- [NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)
- [M31 Bluetooth 착수·판정 계약](<01_아두이노 코어 설계/20_M31_Bluetooth_착수_계약.md>)
- [M31 메모리 최적화 통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)
- [M32 BLE·Mesh·무선 착수 계약](<01_아두이노 코어 설계/22_M32_BLE_Mesh_무선_착수_계약.md>)
- [M33 전체 예제 원장과 릴리스 계약](<01_아두이노 코어 설계/23_M33_전체_예제_원장과_릴리스_계약.md>)

### 설치·빌드·업로드

- [West Native Blink PoC — M3 역사적 기준선](<02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [NU54DK Build Adapter 설계](<02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI 및 IDE 통합 설계](<02_빌드 설계/03_Arduino_CLI_통합.md>)
- [빌드 캐시와 산출물](<02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [Host 경로·권한·cache·lock](<02_빌드 설계/13_Host_경로_권한_cache_lock.md>) — HOST-W05 개발 계약
- [업로드와 디버그](<02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 패키징 (v0.5.0 기록)](<02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 프로필과 Arduino 예제 배포 — 설치본과 개발 소스](<02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [CI/CD와 재현 빌드 — 지원 기준선과 main 회귀](<02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)
- [Windows 개발환경 설정](<02_빌드 설계/09_Windows_개발환경_설정.md>)
- [후속 다중 Host 지원 계약 — 기존 파일명 유지](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)

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
- [Arduino 구성 프로필과 예제 노출 정책](<00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>): 사용자 구성과 예제 소유권 결정
- [M33 Bluetooth Qualification 적용성](<00_사전 리서치/04_M33_Bluetooth_qualification_적용성.md>): NCS 3.4.0 component 근거와 제품별 남은 절차

## 문서 관리 원칙

M32 완료 후 문서 정비·main 통합은 [295번 기록](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>),
검토 범위·방법과 hash는 [문서 감사 원장](document-review.json)에 기록합니다.
이전 공개·통합 결정은 [검증 기록 목차](<04_검증 기록/README.md>)에서 찾습니다.

- 진행 상태는 해당 현행 TODO와 인계에서 갱신합니다. 완료 TODO에는 다른 마일스톤의 진행률을 동기화하지 않고, README·설계 문서에도 시각별 실기 보고를 반복하지 않습니다.
- 전체 문서 점검은 완료 TODO의 재작성 지시가 아닙니다. 완료 문서의 링크·hash·생성 계약을 검사할 수는 있지만, 내용 변경은 명시적인 정정·재개 범위가 있을 때만 수행합니다.
- 설계 문서는 동작·소유권·오류 계약, 검증 기록은 exact source·시험 조건·실제 결과를 설명합니다.
- 과거 검증·공급 종료 버전 문서는 당시 사실을 보존합니다. 현재 지원·재실행 지시로 읽지 않습니다.
- 생성 문서는 JSON·생성기를 수정한 뒤 재생성합니다. SDK·서드파티·기존 공개 패키지는 문서 정리로 바꾸지 않습니다.
- 사용자 결정에 따른 시험 제외·알려진 제한은 성공한 시험과 구분합니다. 범위와 기록을 함께 남깁니다.
- 문서 삭제는 고유한 결정·검증 근거가 없고 들어오는 링크까지 정리할 수 있는 경우에만 판단합니다.

## 결과 표기

| 표기 | 뜻 |
| --- | --- |
| PASS | 적힌 source·조건·횟수에서 판정 기준 충족 |
| FAIL | 실제 실행에서 기준 미충족. 최초 실패 원본 보존 |
| HOLD | 미해결 원인·조건·증거 부족으로 판정 또는 완료 보류 |
| NOT RUN | 실행하지 않음. 준비·build 통과와 별개 |
| UNSUPPORTED | 해당 controller·SDK·profile의 근거로 확인된 미지원. 칩 전체 불가로 확대하지 않음 |
| 사용자 수용·범위 제외 | 작업 범위 결정. 실패 수정이나 새 실기 PASS가 아님 |

과거 기록의 당시 수치는 현재 진행률에 다시 더하지 않습니다. 명령·핀표는 해당 fixture의 계약이며
현재 결선을 바꾸라는 지시가 아닙니다. 고정 원본을 참고할 때는 문서에 적힌 source와 날짜를 함께 확인합니다.

HOST-W07의 대상 OS 다섯 행과 단계별 명령은 [RC1 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)를 따른다. C5 Windows 11 완료를 보존한다. C10 Ubuntu24.04/WSL2 실적과 이후 호환성 순서는330번 기록과 Host 계약을 따른다.
