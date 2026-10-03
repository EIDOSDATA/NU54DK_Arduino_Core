# v0.7.0 개발 계획 — NCS 3.4.1 전체 SDK 전환

**v0.7.0은 NCS 3.4.0에서 3.4.1로 개발·빌드·설치·배포 기준선을 전환하는 릴리스다.**
2026-10-01 사용자 결정에 따라 SDK 호환 수정과 기존 기능의 회귀 검증만 수행하며 신기능을
추가하지 않는다. 별도 작업 ID `SDK-W01~SDK-W06`을 사용하고 기존 M 번호는 유지한다.

| 항목 | 현재 상태 |
| --- | --- |
| 계획 | SDK-W01~SDK-W06 **0/6, 모두 미착수** |
| 실제 개발 환경 | NCS **3.4.0 유지**. 설치·checkout·lock·toolchain·board·firmware 미전환 |
| 목표 환경 | NCS **3.4.1 전체 manifest**와 검증된 대응 toolchain·board 조합 |
| 현재 설치·지원 배포 | **v0.5.0 stable**. 이 계획은 공개·지원 버전 변경이 아님 |
| 현재 v0.6.0 작업 | M32 **12/12 완료**, M33 **0/8** |
| Host | HOST-W01~W03 완료, **HOST-W04~W08 보류 유지** |

계획 작성은 SDK 전환·실기 재개·새 Host 지원이나 공개 실행 승인이 아니다. M32 BLOB은 고정
NCS 3.4.0에서 후속 exact 시험을 통과했고 과거 FAIL은 보존한다. 다음 작업은 [HANDOFF](HANDOFF.md),
v0.6.0 잔여 작업은 [v0.6.0 TODO](TODO_v0.6.0.md)에서 관리한다.

## 1. 제품선과 범위

| 제품선 | 배정 작업 | 경계 |
| --- | --- | --- |
| v0.6.0 | M32·M33 | NCS 3.4.0에서 기존 계획을 마감 |
| v0.7.0 | SDK-W01~SDK-W06 | NCS 3.4.1 전체 SDK 전환·기존 기능 유지·전환 검증만 |
| v0.8.0 | M34~M37 | Security·Storage·Update 확장 |
| v0.9.0 | M38~M41 | Radio·Network 확장 |
| v0.10.0 | M42~M45 | Matter |

포함하는 변경은 NCS·Zephyr·nrfxlib/SDC/MPSL·암호화·MCUboot 등 공식 manifest의 전체 의존성,
대응 toolchain, 필요한 Core/Kconfig/DTS 호환 수정과 설치기·Build Adapter·CI·package 계약이다.
SDK 일부 module만 임의 교체하거나 버전 문자열만 바꾸는 작업으로 완료하지 않는다.

새 공개 API, TF-M 적용 범위 확대, 새 storage API, 복수 layout·update transport, 새 radio/network,
Matter, 새 보드·Host 지원은 **v0.7.0 범위 밖**이다. SDK가 새로 제공하는 기능도 자동 노출하지
않는다. 기존 지원 API·profile·저장 형식·layout·기능 의미를 유지하고, 보안·호환성상 변경이
불가피하면 영향과 migration 방안을 별도 결정한 뒤 반영한다. 조용한 기능 삭제·fallback은 금지한다.

기존 `UNSUPPORTED`·`NOT RUN`·사용자 제외 경계는 그대로 출발점으로 삼는다. 새 SDK에 포함됐다는
이유만으로 DF IQ RX, 외부 peer 호환성 또는 미검증 조합을 지원으로 승격하지 않는다.

## 2. 작업 묶음 — 6개

| ID | 작업 | 상태 | 완료 산출물 |
| --- | --- | --- | --- |
| SDK-W01 | 환경·manifest·toolchain·board 기준선 | 미착수 | 이전/새 exact 구성과 영향·회귀 목록 |
| SDK-W02 | 기존 코드·Kconfig 호환 수정 | 미착수 | 기존 API/profile 계약을 유지하는 호환 변경·자동 검사 |
| SDK-W03 | 기존 전체 예제·역할 build와 자원 | 미착수 | clean build matrix·자원 비교·실패 판정 |
| SDK-W04 | 기존 기능 영향 HIL 회귀 | 미착수 | 적용 기능별 새 image의 runtime·복구·STOP 증거 |
| SDK-W05 | 설치기·빌더·CI·package 전환 | 미착수 | exact pin·cache 분리·격리 설치·재현성 검증 |
| SDK-W06 | 문서·기계 원장·마감과 공개 승인 | 미착수 | 정합한 지원/증거·완료 판정·별도 exact 공개 승인 |

### SDK-W01 — 비교 가능한 전환 기준선

- [ ] v0.6.0에서 수용·마감한 exact source와 기능/예제/role/profile 목록을 전환 기준선으로 고정한다.
  M32의 완료 근거를 보존하며, 미완료 M33을 SDK 전환으로 대체하거나 완료 처리하지 않는다.
- [ ] 3.4.0의 manifest·module SHA·toolchain·board gitlink·지원 계약과 공개 자산을 보존한다.
  3.4.1은 별도 환경에서 전체 manifest와 대응 toolchain을 확인하고 새 exact lock을 만든다.
- [ ] 공식 release note·보안 권고·module 이력을 다시 확인하고 Kconfig/API/binding·board 호환성을
  대조한다. 기존 board 변경이 필요하면 전환에 필요한 최소 범위와 변경 사유를 기록한다.
- [ ] 현재 사용 조건과 공식 결함 조건을 대조해 적용/비적용/미확정 및 회귀 test ID를 연결한다.
  [SDK 변경·개발 영향](<00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)은 조사 출발점이며
  모든 module diff나 새 SDK 동작 검증을 대신하지 않는다.

### SDK-W02 — 기존 코드·구성 호환

- [ ] 변경·삭제된 SDK API, Kconfig symbol/default, Devicetree binding과 link 구성을 확인하고
  기존 Core/library/Sketch 동작을 유지하는 호환 수정만 적용한다.
- [ ] profile·library feature·전문가 override의 병합·금지 조합·진단을 검사한다. 존재하지 않는
  symbol이나 기능을 조용히 무시하지 않으며 최종 `.config`·DTS·link 결과를 확인한다.
- [ ] 기존 loaderless 및 승인된 MCUboot profile의 partition·storage 주소·서명·rollback 계약을
  보존한다. build 성공을 위해 새 layout이나 신뢰키 정책을 임의 도입하지 않는다.
- [ ] 영향받는 Host unit/contract/negative 검사와 생성 계약 검사를 통과한다. 구현 검사와
  target build·실기 결과는 분리한다.

### SDK-W03 — 기존 전체 build·자원 회귀

- [ ] 착수 기준선의 모든 공개 예제, 지원 role/profile 및 기존 필수 native/HIL target을 새 SDK로
  clean build한다. 목록·분모·source·SDK/toolchain·설정·image hash를 남긴다.
- [ ] 기존 조건과 같은 입력으로 FLASH/RRAM·RAM·stack/heap·SDC pool 요구량과 정렬을 비교한다.
  크기 증가·warning·잔여 여유를 기록하고 합격 기준을 실행 전에 확정한다.
- [ ] 최소/기능 선택/profile/전문가 override와 서명 image 생성·layout 검사를 적용 범위대로
  확인한다. 이전 SDK cache나 생성 산출물이 새 성공에 섞이지 않게 한다.
- [ ] 실패는 원인·수정·같은 조건 재검증으로 닫는다. compile PASS를 runtime PASS로 확대하지 않는다.

### SDK-W04 — 기존 기능 영향 HIL 회귀

- [ ] W01에서 확정한 영향 matrix에 따라 기존 GPIO/Serial/Analog/Storage·BLE·ISO/Audio·CS·Mesh·
  DFU·공존의 적용 경로를 검증한다. 기존 기능의 정상·오류·취소·복구·유한 soak 기준을 유지한다.
- [ ] 관련 SDK 패치 조건을 포함한다: latency/Subrating 전환, CIS 종료 부하, BIS 재가입/손실,
  CS 종료/peer loss, Mesh LPN 해제, BLOB·signed MDFU 및 사용 중 watchdog의 boot/update 경로.
  비대상 칩·미사용 기능은 근거와 함께 비적용으로 분리한다.
- [ ] 기존 3.4.0 기반 image에서 새 image로의 승인된 업데이트 경로, invalid image/key 거부,
  counter/rollback·설정 보존을 검증한다. 새 power-cut·layout/transport 확장은 M36의 별도 범위다.
- [ ] 실행 시 현재 CMSIS-DAP **V2**·USB/COM 역할을 다시 확인하고 exact source/image·nonce·
  모든 필수 UART 결과·STOP·cleanup을 결합한다. debugger 완료 관측은 누락된 최종 UART/STOP의
  대체 증거가 아니다. 실패·NOT RUN 원본을 보존하며 임의 mass erase/recover/unlock을 하지 않는다.
- [ ] 정밀 RF/audio/거리 보정·사용자 후속 외부 peer 등 기존 제외를 새 필수 기능으로 늘리지 않는다.
  CS loss/counter gap의 기존 비차단 정책과 새로운 assert·fault·데이터 손상은 구분한다.

### SDK-W05 — 설치·빌드·배포 도구 전환

- [ ] prerequisite URL/hash·NCS/module/toolchain pin, 완료 marker와 Build Adapter의 exact 검사를
  새 기준선에 맞춘다. marker/pin 불일치는 실패하며 다른 SDK의 수동 설치를 자동 승인하지 않는다.
- [ ] SDK/toolchain/profile/source identity가 cache·resolved manifest에 반영되는지 확인하고,
  이전/새 SDK 전환·격리 설치·재설치·제거·오류 복구에서 잘못된 cache 재사용을 차단한다.
- [ ] 현재 승인된 Host 범위에서 CI·재현 build·package allowlist·manifest/hash·license를 검증한다.
  설치본에서 기존 전체 예제를 발견·compile하고 대표 upload/runtime·serial/debug를 확인한다.
- [ ] 이전 공개 tag/Release/asset·역사 lock/evidence는 덮어쓰지 않는다. 새 패키지의 SDK 요구사항과
  migration 안내를 분리한다. HOST-W04~W08 보류를 해제하거나 새 OS 지원을 합치지 않는다.

### SDK-W06 — 문서·원장·마감과 별도 공개 승인

- [ ] README·환경/설치·API/지원 경계·release/migration/known issues와 기계 원장을 같은 exact
  SDK·source·예제·시험 근거로 맞추고 문서 링크·생성 정합 검사를 통과한다.
- [ ] W01~W05의 변경·실제 PASS·FAIL·NOT RUN·비적용, 기존 제한과 잔여 위험을 검토한다.
  필요한 검증이 남으면 6/6이나 SDK 전환 완료로 표시하지 않는다.
- [ ] 완료 항목별 변경·검증·인계를 남기고 커밋·푸시 및 해당 source의 CI를 확인한다. 현재 문서
  계획 작성만으로 SDK 전환 작업의 완료 수를 올리지 않는다.
- [ ] 비공개 package/RC 준비와 공개 tag·Release·catalog 게시를 분리한다. 공개는 새 exact
  source·plan·자산에 대한 **별도 사용자 승인** 뒤 수행하고 공개 URL 설치 smoke를 기록한다.
  과거 v0.5.0/v0.6.0 승인을 v0.7.0 공개 승인으로 재사용하지 않는다.

## 3. 착수·인계 규칙

현재는 계획 정정만 완료하며 SDK 설치·checkout·firmware·실기 상태를 바꾸지 않는다.
실제 전환 착수 시 v0.6.0 완료 기준선과 사용자 지시를 확인하고 SDK-W01부터 진행한다.
중대한 보안 노출·assert·데이터 손상이 발견되면 범위/버전 계획과 별도로 보고하고 대응을 결정한다.
SDK pin 변경이나 backport를 문서 계획만 근거로 자동 수행하지 않는다.

각 작업의 기록에는 변경 source, SDK/board/toolchain, 실행 명령·분모·조건, 결과·실패 원본,
남은 문제와 다음 한 행동을 남긴다. 완료된 기능의 회귀와 새 기능 구현을 섞지 않는다.
상세 기능 배정은 [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 설치 pin 계약은
[prerequisite 안내](../tools/nu54-prerequisites/README.md), 실기 증거 규칙은
[HIL 안내](../tests/hil/nu54dk/README.md)를 따른다.
