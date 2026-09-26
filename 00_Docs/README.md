# 문서 안내

일반 사용자는 **stable v0.4.1**, 새 Bluetooth 기능의 공개 후보를 시험하려면
**v0.5.0-rc.1** 문서를 선택합니다. 두 배포 모두 Windows 10/11 x64 대상이며,
RC는 별도 설치 목록을 사용하는 opt-in 후보입니다. v0.5.0 stable은 아직 공개하지 않았습니다.

## 사용 안내

| 목적 | 읽을 문서 |
| --- | --- |
| 처음 설치·업로드 | [프로젝트 README](../README.md), [stable v0.4.1](<05_릴리스/v0.4.1/README.md>) |
| 공개 RC 설치·변경점·제한 | [v0.5.0-rc.1 안내](<05_릴리스/v0.5.0-rc.1/README.md>) |
| 구성 프로필과 예제 | [프로필·예제 안내](<02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>) — stable 30개 / RC 113개 |
| 지원 API와 핀 | [API 지원 범위](<01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>), [P2/P4 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>) |
| 설치·업로드 문제 | [stable 문제 해결](<05_릴리스/v0.4.1/TROUBLESHOOTING.md>), [RC 문제 해결](<05_릴리스/v0.5.0-rc.1/TROUBLESHOOTING.md>) |
| 버전별 지원 상태와 이전 기록 | [릴리스 안내](<05_릴리스/README.md>) |

## 개발과 검증

| 목적 | 읽을 문서 |
| --- | --- |
| 개발 시작·기여·검사 명령 | [CONTRIBUTING](../CONTRIBUTING.md), [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>) |
| 현재 상태·다음 작업·다른 PC에서 재개 | [HANDOFF](HANDOFF.md), [RC2 교정 계획](TODO_v0.5.0-RC2.md), [v0.5.0 TODO](TODO_v0.5.0.md) |
| 완료된 M31 범위와 메모리 최적화 | [M31 TODO](TODO_M31.md), [메모리 통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>) |
| 기능·역할·검증 소유권 | [Bluetooth 전체 기능·예제 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>) |
| 후속 계획 | [M32 TODO](TODO_M32.md), [M33 TODO](TODO_M33.md), [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |
| 실제 검증 조건·실패·결과 | [검증 기록과 evidence](<04_검증 기록/README.md>) |
| 실물 시험의 안전·재현 절차 | [HIL 안내](../tests/hil/nu54dk/README.md) |

M28~M31과 Windows RC 공개·smoke는 완료했습니다. 이후 stable 승격은 별도 승인 대상이며,
M32/M33과 보류한 HOST-W04~W08을 완료된 RC의 추가 조건으로 합치지 않습니다.
세부 진행 수치와 남은 조건은 위 TODO를 기준으로 봅니다.

현재 개발 branch는 `main`에서 분기한 `0.5.0-RC2`이고 `0.5.0-RC1` branch는 별도로
보존합니다. RC2 branch 생성은 새 배포가 아니며 stable v0.4.1의 catalog·공개 자산과 공개 RC1
tag의 원래 source는 유지합니다.
기존 checkout 전환은 [CONTRIBUTING](../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)을 따릅니다.

## 현행 안내와 기록 구분

| 문서 종류 | 읽는 기준 |
| --- | --- |
| README·현행 설계·도구 안내 | 현재 사용·개발 계약. 예전 버전 전용 설계는 제목과 적용 범위에 별도 표시 |
| TODO·인계 | 완료 TODO는 당시 이력, v0.5.0 TODO는 현재 남은 조건, HANDOFF는 재개 절차. 완료 시험의 재실행 지시가 아님 |
| 검증 기록·evidence | 당시 source·조건·실제 결과. 후속 해결은 안내 링크로 연결하고 원본 판정은 보존 |
| 버전별 공개 릴리스 문서 | 해당 package에 고정된 내용. stable은 v0.4.1, RC 시험은 v0.5.0-rc.1 안내 사용 |

폴더는 역할에 따라 `00_사전 리서치`(배경), `01_아두이노 코어 설계`(공개 계약),
`02_빌드 설계`(설치·빌드), `03_펌웨어 설계`(runtime), `04_검증 기록`(재현 증거),
`05_릴리스`(버전별 사용자 안내)로 구분합니다. 기존 링크와 evidence 경로를 보존하기 위해
완료 기록을 다른 번호나 폴더로 옮기지 않습니다.

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
- [M28 BLE GAP·Link·Privacy 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)
- [M29 ATT/GATT·L2CAP 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)

- [M30 BLE Security·Profile·DFU 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)
- [문서 전면 검토와 개선 마일스톤](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)
- [NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)
- [M31 Bluetooth 착수·판정 계약](<01_아두이노 코어 설계/20_M31_Bluetooth_착수_계약.md>)
- [M31 메모리 최적화 통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)

### 설치·빌드·업로드

- [West Native Blink PoC — M3 역사적 기준선](<02_빌드 설계/01_West_Native_Blink_PoC.md>)
- [NU54DK Build Adapter 설계](<02_빌드 설계/02_Build_Adapter_설계.md>)
- [Arduino CLI 및 IDE 통합 설계](<02_빌드 설계/03_Arduino_CLI_통합.md>)
- [빌드 캐시와 산출물](<02_빌드 설계/04_빌드_캐시와_산출물.md>)
- [업로드와 디버그](<02_빌드 설계/05_업로드와_디버그.md>)
- [Boards Manager 설치와 패키징 — stable v0.4.1](<02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
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

## 문서 관리 원칙

공개 RC 근거는 [268번 기록](<04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>),
첫 RC 이력·문서 정리는 [269번 기록](<04_검증 기록/269_공개_RC_이력_Squash와_문서_전수_정비.md>),
후속 main 통합·이력 정리는 [270번 기록](<04_검증 기록/270_main_RC_통합_Squash와_문서_동기화.md>),
전수 검토 범위와 hash는 [문서 감사 원장](document-review.json)에 기록합니다.

- 완료 상태와 제품선 작업은 TODO 또는 후속 계획 한곳에서 갱신합니다. README·설계 문서에 시각별 실기 보고를 반복하지 않습니다.
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
