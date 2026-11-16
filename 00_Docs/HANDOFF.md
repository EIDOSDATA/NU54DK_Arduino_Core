# 개발 인계

현행 위치는 **M33-W07 / HOST-W08 문서 준비 완료·최종 gate 미완료**다. Host6/8·지원 목표 검증3/5를 유지한다. Windows11 기준선과 Ubuntu24.04·26.04/WSL2 완료, C11 macOS26·27 software PASS를 보존하며 Mac 실기는 `NOT_RUN`이다. 문서 선행 정리와 릴리스 잔여 순서는 [332번](<04_검증 기록/332_HOST_W08_문서_지원표_선행_정리.md>)을 따른다. 전체204를 반복하지 않는다.

W06은 실제 PASS 46개와 사용자 승인 3개(#29·40·44)를 구분하여 수락 마감했다.
원형 strict 기술 완료는 미충족이며 #29 원인 분석은 유예했다.
[310번 수락 마감](<04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>), [311번 명시 수락 정정](<04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>)과
[공개 hash 참조](<04_검증 기록/evidence/m33-w06-b46ce570/closure-reference.json>)가 최종 결과다. 현행 범위는
[M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용)이 소유한다.
실제 작업본·source·진행 항목·종료 증거와 과거 자료의 위치는 [M33 인계](M33_HANDOFF.md)에서 찾는다.

## 현재 상태

| 범위 | 상태·정본 |
| --- | --- |
| 현재 제품 | Windows 10/11 x64용 [stable v0.5.0](<05_릴리스/v0.5.0/README.md>) |
| v0.6.0 개발 | M32 12/12, M33 **수락 6/8·기술 5/8**, W06 strict 예외 보존 — [계획](TODO_v0.6.0.md) |
| Host | **6/8**, 현재 **M33-W07의 HOST-W08 문서 선행 정리 완료**. Windows11·Ubuntu24/26 WSL2 검증3/5. Mac26/27 실기 NOT_RUN, W07·W08 최종 gate 미완료 |
| HOST-W06 마감 검증 | H12 `6364a1d9955f79fef0ac1f3219883a9d77e24f32`: 세 OS 각204예제·거부9개, 204개 실제 image 비교 PASS. native30/30·software9/9·prerequisite3/3·build-only6/6 — [322번](<04_검증 기록/322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md>). 실제 OS USB gate는 NOT_RUN |
| HOST-W07 현재 | C5 Windows 기준선과 C10 Ubuntu24.04·26.04/WSL2 완료를 보존한다. C11 교정·macOS26/27 CI 결과는 [331번](<04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>), C6~C10 원형 PASS·FAIL은 [330번](<04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>), 검증 배정은 [Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>). 공개 URL 검증은 별도 공개 승인 뒤 수행한다. |
| 기준 저장소·브랜치 | `D:/w06/a/user/hardware/nucode/zephyr` · `Dev-0.6.0-M33` |
| 실제 작업본·source | `D:/w06/control/continuation.json`의 `active_workflow` |
| 현재 이력 | 사용자 요청으로 M33의 main 이후 87 commit을 하나로 정리; [원본 bundle·복구](M33_HANDOFF.md#m33-원본-이력-보관--2026-10-07-squash) |
| 개발 검증 방식 | [W06 재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>) — 실패별 수정과 최종 동일 source gate를 분리 |
| 현행 실행 순서 | [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) · [RC1 실기 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>) · [M33 TODO](TODO_M33.md) |
| 검증 결과·종료 증거 | `continuation.json.active_workflow`에서 해당 source·attempt의 원본을 확인. 과거 PASS를 현재 source 실적으로 합성하지 않음 |
| 실제 재개 절차·보존 자료 | [M33 인계](M33_HANDOFF.md) |

## 먼저 읽기

1. [AGENTS](../AGENTS.md)와 [M33 인계](M33_HANDOFF.md).
2. [M33 TODO](TODO_M33.md)의 W07·W08, [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>), [RC1 실기 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>).
3. 현행 [331번 C11 macOS 교정·호환성](<04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>)과 [Host 원장](../variants/nu54dk/host-readiness.json). C6~C10은330번, C5 Windows 완료는 [329번](<04_검증 기록/329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md>)에 보존한다.
4. 과거 실패 원인이 필요할 때 [302번](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md>)·
   [303번](<04_검증 기록/303_M33_W06_재실행_최소화와_checkpoint_개선_계획.md>)의 해당 절만 참조.
5. 과거 개발49 완료와 판단 정정은 [306번](<04_검증 기록/306_M33_W06_개발_49개_완료와_최종_빌드_중단_인계.md>)·[307번](<04_검증 기록/307_M33_W06_연속검증_판단_정정과_마감_계획.md>)의 역사 기록이다. W06 증거 해석이 필요할 때만 [W06 절](TODO_M33.md#m33-w06--자원회귀상호운용)과 [재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>)를 참조하며 #29 분석은 유예한다.

완료 TODO 6개와 과거 실기·릴리스 기록은 현행 지시가 아니다. [읽기·보존 범위](README.md#todo-읽기갱신-범위)를 따른다.
이전 인계의 긴 source별 일지는 Git 이력과 번호별 검증 기록에 보존하며 이 진입점에 반복하지 않는다.

## 실행 경계

- 실기 writer와 로컬 무거운 build/HIL은 하나. 이번에 허용된 병렬 문서/파일 검토는 같은 범위만 다룬다.
- 2026-10-11 문서 push는 개발 문서 동기화이며 W06 완료가 아니다. 현재 실패별 로컬 수정·검증에서도
  개별 항목마다 대규모 공식 CI를 재시작하지 않는다.
- 모든 새 작업·cache·임시는 D 아래. C의 NCS/toolchain 설치본은 입력으로만 사용한다.
- NCS 3.4.0과 board/toolchain pin 유지. 3.4.1 전체 전환은 [v0.7.0](TODO_v0.7.0.md)이다.
- 현재 장치·symlink·firmware·STOP은 재개 시 실제 확인한다. 삭제된 파일이나 옛 hash로 PASS를 합성하지 않는다.
- 개발 smoke·Host·build와 최종 실제 보드 PASS를 분리한다. 문서 정비는 W06 완료가 아니다.
- W06 수락 마감 후 사용자 지시로 HOST-W04를 시작했다. HOST-W04~W06 → W07 도구 → M33-W07 RC1 → HOST-W08 문서 선행 정리 → 남은 Mac 실기·최종 후보 정합화 → HOST-W07/W08·M33-W07 마감 → M33-W08 별도 공개 승인 순서다.
- Apple/Google·외장 장치는 사용자 후속 NOT_RUN, Ubuntu/macOS 실제 지원 검증은 RC 단계다.

## 과거 결과 찾기

| 필요한 근거 | 문서 |
| --- | --- |
| v0.5.0 공개·지원 경계 | [274번](<04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>) · [v0.5.0 Testing](<05_릴리스/v0.5.0/TESTING.md>) |
| M29-W01~W08 8/8 완료와 M30 인계 | [ATT/GATT·L2CAP 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) · [고정 readiness 원장](../variants/nu54dk/m29-ble-readiness.json) |
| M30-W01~W08 완료와 M30-POWER-01 원본 근거 | [Security·Profile·DFU 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) · [고정 readiness 원장](../variants/nu54dk/m30-ble-readiness.json) |
| M32 완료 | [M32 완료 TODO](TODO_M32.md) · [287번](<04_검증 기록/287_M32_W12_정합성_감사와_후속_인계.md>) |
| M33 W01~W05 완료 | [M33 TODO](TODO_M33.md)와 연결된 296·298~301번 기록 |
| M32 통합·이력 보관 | [295번](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>) · [이력 보관](M33_HANDOFF.md#m32-원본-이력-보관) |
| 전체 문서 감사 | [문서 안내](README.md) · [감사 원장](document-review.json) |

공개 tag·Release·asset, 최초 FAIL/HOLD/NOT_RUN 원본은 보존한다. 2026-10-11 문서 정리·push와
이후 사용자가 승인한 실패별 수정·로컬 실기는 구분한다. main 통합·추가 squash·공개 게시 권한은
추정하지 않으며 현행 실행 순서는 [RC1 실기 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)와 [M33 TODO](TODO_M33.md)를 따른다.

HOST-W04 완료 source·설치3OS 원문과 HOST-W05 착수 범위는 [313번](<04_검증 기록/313_HOST_W04_설치_마감과_HOST_W05_경로_cache_lock_착수.md>)을 따른다.
