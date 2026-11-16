# v0.6.0 Release notes 초안 — 미공개

M32·M33의 개발 결과를 후속 릴리스에 연결하는 초안이다. 정식 version·source·배포 hash는
[릴리스 체크리스트](RELEASE_CHECKLIST.md)의 최종 후보 단계에서 고정한다.

## 개발 범위

- M32의 전력·Path Loss·연결 timing·광고/identity·Nordic 확장, Mesh/BLOB/DFU,
  802.15.4·ESB 단독 및 허용 공존 작업은12/12 완료했다. 적용 기능과 제외 조합은 [M32 TODO](../../TODO_M32.md)를 따른다.
- M33의 전체 sample inventory, GATT/profile·beacon, 외부 ecosystem companion,
  DTM/HCI template, 역할별 설치 예제 작업은 W01~W05를 완료했다.
  24개 library·204개 예제의 설치/compile 근거와 실제 runtime 범위는 [M33 TODO](../../TODO_M33.md)를 따른다.
- Host 공통 prerequisite·launcher·경로/cache/lock·package CI와 WSL2 경로를 준비했다.
  실제 지원 확정 범위는 [지원표](SUPPORT_MATRIX.md)와 분리해 읽는다.
- C11은 Darwin 소유 process group 정리에서 마지막 SIGKILL의 EPERM 뒤 실제 그룹 소멸을 확인한다.
  macOS26·27 fresh software 검증을 통과했고 이전 C10 FAIL은 보존했다.

## 사용자에게 알려야 할 경계

M33-W06은 **실제 PASS46 + 명시 수락3(#29·40·44)**으로 마감했다. 49개 기술 PASS가 아니며
해당 FAIL·집계 원형은 [310번](<../../04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>),
#40·44의 별도 명시 수락과 판단 정정은 [311번](<../../04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>)에 보존한다.
#29 원인 분석은 유예한다. 이 예외를 새로운 source의 PASS로 옮기지 않는다.

Apple/Google·외부 제품·외장 장치의 실제 interop는 사용자 후속 `NOT_RUN`이다.
자동 scripted peer 결과는 제품 인증이나 실제 외부 제품 상호운용 보증이 아니다.
실험 profile·template는 해당 예제의 설정·credential·peer·결선 요구사항을 따른다.
NCS3.4.0과 고정 toolchain을 유지하며 이번 릴리스 준비에서 SDK를 교체하지 않는다.

API/profile 이동과 opt-in은 [Migration](MIGRATION.md), 제한은 [Known issues](KNOWN_ISSUES.md)를 따른다.
