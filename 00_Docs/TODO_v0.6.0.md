# v0.6.0 개발 계획 — M32·M33 Bluetooth 확장과 예제 완성

| 항목 | 현재 상태 |
| --- | --- |
| 목표 버전 | **v0.6.0 — 계획, 미공개** |
| 진행 범위 | M32 구현·검증 마감, 문서 정비와 main 통합; M33-W02 완료, W03 다음 |
| 기능 작업 | M32 **12/12 완료**, M33 **2/8** — W01 원장, W02 표준 GATT·Beacon 완료 |
| Host 트랙 | HOST-W01~W03 완료 **3/8**; M33-W06 완료 후 W04부터 순차 재개, 그 전 착수 대기 |
| 현재 지원·설치 | Windows 10/11 x64용 **v0.5.0** |
| 개발·보존 | `main`에서 분기한 `Dev-0.6.0-M33`; M32 브랜치 삭제·로컬 bundle 보관, 원격 `Release-0.5.0` 기준선 보존 |
| SDK | NCS v3.4.0 pin 유지; v3.4.1 전체 전환은 SDK 전용 제품 v0.7.0 |
| 최종 갱신일 | 2026-10-04 |

이 문서는 v0.6.0의 계획 진입점이다. 버전 배정은 기능 구현 완료, Host 보류 해제, 실물 작업,
tag·Release·index 공개 승인을 뜻하지 않는다. 소스·설치 패키지의 제품 버전은 아직 0.5.0이며,
공개 v0.5.0 자산을 바꾸거나 v0.6.0으로 재명명하지 않는다.

## 1. 후속 버전 배정

| 버전 | 마일스톤·목표 | 상태 |
| --- | --- | --- |
| v0.5.x | 공개 v0.5.0의 버그 수정·유지보수 정책 | 새 수정판을 이번에 생성하지 않음 |
| **v0.6.0** | **M32·M33 — 최신 BLE 제어·Mesh·최소 무선 공존·예제와 릴리스 완성** | M32 완료, M33-W02 완료·W03 다음·미공개 |
| **v0.7.0** | **SDK-W01~W06 — NCS 3.4.0→3.4.1 전체 전환만 수행** | [SDK 전용 계획](TODO_v0.7.0.md), 0/6 미착수 |
| v0.8.0 | M34~M37 — Security/Storage/Update | 후속 계획 |
| v0.9.0 | M38~M41 — Radio/Network | 후속 계획 |
| v0.10.0 | M42~M45 — Matter | 후속 계획 |

M 번호와 기능 소유권은 유지하고 후속 제품선의 버전만 순차 이동한다. ARF-01은 기존대로
M32-W04에 포함한다. 별도 ARF 작업은 기존 의존 순서와 독립적인 버전 결정 조건을 유지하며
v0.6.0이나 SDK 전용 v0.7.0에 일괄 포함하지 않는다. 현재 결정 원본은
[293번 기록](<04_검증 기록/293_v0.7.0_SDK_전환_전용과_후속_마일스톤_재배정.md>)이며
앞선 276번의 배정은 역사로 보존한다.

## 2. 구현 순서와 담당 문서

| 순서 | 범위 | 상세 계획 |
| --- | --- | --- |
| 1 | M32-W01: 적용 capability·예제 inventory·자원 상한·유한 시험 계약 | [M32 TODO](TODO_M32.md) |
| 2 | M32-W02~W05: 전력/Path Loss·연결 timing·광고/identity·Nordic 확장 | [M32 TODO](TODO_M32.md) |
| 3 | M32-W06~W08: Mesh 기반·Mesh 1.1·BLOB/DFU/Distribution | [M32 TODO](TODO_M32.md) |
| 4 | M32-W09~W12: 802.15.4/ESB 단독 TX/RX → 허용 공존 → 회귀·인계 | [M32 TODO](TODO_M32.md) |
| 5 | M33-W01~W06: 전체 catalog·GATT/beacon·외부 ecosystem·DTM/HCI·설치 예제·통합 검증 | [M33 TODO](TODO_M33.md) |
| 6 | M33-W06 완료 후 HOST-W04~W06 및 W07 도구 준비 — M33 기능 개발과 병렬 진행하지 않음 | [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |
| 7 | M33-W07 RC1 준비 → HOST-W07 실제 검증·W08 마감 → M33-W07 완료 | [M33 TODO](TODO_M33.md) |
| 8 | M33-W08: 별도 공개 승인·게시·공개 설치와 인계 | [M33 TODO](TODO_M33.md) |

W01 계약 이후 독립적인 BLE/Mesh 작업은 병행할 수 있다. 공존은 해당 protocol의 단독 TX/RX
증거를 선행조건으로 사용하며, M33 예제는 필요한 API가 준비되는 순서에 맞춘다. 상세 기능·검증
조건은 각 TODO와 [Bluetooth 전체 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이 소유한다.
버전 계획과 구현·build·실기·배포 완료 수는 따로 집계한다.

## 3. Host와 검증 경계

- 2026-10-03 사용자 결정에 따라 HOST-W04~W08은 M33 기능 개발과 병렬 진행하지 않는다.
  M33-W06 완료 후 HOST-W04부터 순차 재개하며, 그 전에는 착수 대기다. 일정 확정으로
  Ubuntu/macOS 정식 지원이나 실제 검증 완료를 선언하지 않는다. OS별 최종 gate는
  [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)에 유지한다.
- 해당 OS를 지원하는 릴리스에는 그 OS의 실제 설치·USB upload·serial·debug·수명주기 증거가
  필요하다. 문서 개정만으로 이 gate를 면제하거나 후속 릴리스를 Windows-only로 재정의하지 않는다.
- 외부 Apple/Google peer·마이크·스피커 등은 실사용 구현·예제·설정/연결 안내·가능한 자동 검사가
  필수다. 실제 외부 제품 운용은 기존대로 사용자 후속 NOT RUN이며 개발·릴리스 비차단이다.
- 보드 기반 기능 HIL과 Host/mock/build 결과는 구분한다. 새 물리 시험 전에 보드 mapping·결선·
  역할·유한 반복/timeout·안전 조건을 확인한다. 자동 mass erase·unlock·recover는 하지 않는다.
- v0.5.0의 완료 결과와 미지원·제외 범위는 재개하지 않는다. 새 지원 주장은 v0.6.0의 실제
  구현과 exact 증거로 판정하며, 아직 없는 기능을 현재 stable 지원으로 안내하지 않는다.

## 4. 다음 착수와 공개 조건

현재 **M32 W01~W12 12/12 완료, M33 W01~W02 2/8 완료**다. 사용자 지시로 W08~W12 개발을 재개해 마감했으며,
완료별 수치와 exact source는
[M32 TODO](TODO_M32.md), 다음 실행 절차는 [HANDOFF](HANDOFF.md)를 단일 원본으로 사용한다.
새 채팅의 작업 위치·전체 실행 순서·복사용 지시는 [M33 인계](M33_HANDOFF.md)에 있다.

| 완료 항목 | 최종 근거 |
| --- | --- |
| W08 BLOB | `40e4c46b…` clean exact 10/10회·negative·세 역할 STOP/cleanup PASS. `8dcb033e…` FAIL은 역사로 보존 |
| W08 signed MDFU | `e0a1b7fd…` clean exact 5회·두 target 10/10, negative·confirm/rollback·세 역할 STOP/cleanup PASS. 앞선 timeout·Apply·rollback state FAIL은 역사로 보존 |
| W10 공존 | clean `512b027a…`, 세 내부 조합 protocol별 4,000/4,000·negative·restart·STOP exact PASS |
| W11 회귀·soak | clean `94f02544…` native 62/62·exact family 12/12·signed MDFU 10/10·1,800초 soak PASS |
| W12 마감 | 원장·문서·예제·지원 승격 gate·M33/M36/M38/M39/M40/M42 인계 정합성 PASS, M32 12/12 완료 |

W09 단독 radio 회귀도 완료했다. M33-W01 전체 sample·예제 catalog를 마감했고 W02는 exact
`4ebd4952…`에서 표준 GATT·Beacon 구현, 공개 예제 9/9 build와 profile 3보드·native fresh→restored·
Beacon 600광고 HIL을 완료했다. 시험 소유 bond만 제한 정리했으며 외부 peer 실기는 `NOT_RUN`이다.
M33-W03~W06 기능·예제·통합 검증과 W07~W08 Host·package·공개 gate가 남아 있다.
HOST-W04는 M33-W06 완료 직후 시작하며, RC1 준비와 OS별 실기 마감을 거쳐 M33-W08로 진행한다.
현재 M33-W03이 다음이고 잔여 Host 구현은 착수 대기이며, 정식 공개 승인은 별도로 확보한다.

NCS v3.4.1의 공식 변경점·조건부 위험은
[SDK 영향 검토](<00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)에서 관리한다.
**v0.6.0은 NCS v3.4.0을 유지하고, v0.7.0에서는 NCS v3.4.1 전체 전환만 수행**한다.
v0.7.0 범위 확정은 이번 문서 작업 중 SDK 교체나 보안 문제 면제 결정이 아니다. 현재 경로에서 재현되는
중대 오류·취약성이 확인되면 변경 근거와 대응 선택지를 별도로 보고한다.

v0.6.0의 package·제품 식별자·RC 전환은 실제 개발 및 배포 준비 단계에서 정합화한다. 정식
공개는 M33의 기능·예제·Host·package gate와 exact source/plan에 대한 별도 소유자 승인 후에만
진행한다. 과거 v0.5.0 공개 승인은 v0.6.0 게시 허가가 아니다.

완료 기준선은 [v0.5.0 TODO](TODO_v0.5.0.md), 전체 제품 순서는
[로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 재개 절차는 [HANDOFF](HANDOFF.md)를 따른다.
