# 개발 인계

W06은 실제 PASS 46개와 사용자 승인 3개(#29·40·44)를 구분하여 수락 마감했다.
원형 strict 기술 완료는 미충족이며 #29 원인 분석은 유예했다.
[310번 수락 마감](<04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>)과
[공개 hash 참조](<04_검증 기록/evidence/m33-w06-b46ce570/closure-reference.json>)가 최종 결과다. 현행 범위는
[M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용)이 소유한다.
실제 작업본·source·진행 항목·종료 증거와 과거 자료의 위치는 [M33 인계](M33_HANDOFF.md)에서 찾는다.

## 현재 상태

| 범위 | 상태·정본 |
| --- | --- |
| 현재 제품 | Windows 10/11 x64용 [stable v0.5.0](<05_릴리스/v0.5.0/README.md>) |
| v0.6.0 개발 | M32 12/12, M33 **수락 6/8·기술 5/8**, W06 strict 예외 보존 — [계획](TODO_v0.6.0.md) |
| Host | **5/8**, **HOST-W05 완료·HOST-W06 진행 중**. 이후 W06→W07 준비→RC1→실제 OS→W08 마감 순서 |
| Host 현재 검증 | [315번](<04_검증 기록/315_HOST_W05_native_마감과_HOST_W06_package_착수.md>) — H5 native SDK3/3·OS별 unit·software9/9·build-only6/6 성공. H8 실제3OS 설치·955파일 대조·204예제 발견 PASS, Blink의 SDK Git 전달 FAIL 교정 중 — [318번](<04_검증 기록/318_HOST_W06_H8_설치_통과와_SDK_Git_전달_교정.md>) |
| 기준 저장소·브랜치 | `D:/w06/a/user/hardware/nucode/zephyr` · `Dev-0.6.0-M33` |
| 실제 작업본·source | `D:/w06/control/continuation.json`의 `active_workflow` |
| 현재 이력 | 사용자 요청으로 M33의 main 이후 87 commit을 하나로 정리; [원본 bundle·복구](M33_HANDOFF.md#m33-원본-이력-보관--2026-10-07-squash) |
| 개발 검증 방식 | [W06 재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>) — 실패별 수정과 최종 동일 source gate를 분리 |
| 현행 실행 순서 | [M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용) |
| 검증 결과·종료 증거 | `continuation.json.active_workflow`에서 해당 source·attempt의 원본을 확인. 과거 PASS를 현재 source 실적으로 합성하지 않음 |
| 실제 재개 절차·보존 자료 | [M33 인계](M33_HANDOFF.md) |

## 먼저 읽기

1. [AGENTS](../AGENTS.md)와 [M33 인계](M33_HANDOFF.md).
2. [M33 TODO](TODO_M33.md)의 W06 완료 조건과 [재설계 문서](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>).
3. 필요한 범위의 [전체 기능 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)과
   [도구 안내](../tools/ci/m33_w06_artifacts.md).
4. 과거 실패 원인이 필요할 때 [302번](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md>)·
   [303번](<04_검증 기록/303_M33_W06_재실행_최소화와_checkpoint_개선_계획.md>)의 해당 절만 참조.
5. 과거 개발49 완료와 판단 정정은 [306번](<04_검증 기록/306_M33_W06_개발_49개_완료와_최종_빌드_중단_인계.md>)·[307번](<04_검증 기록/307_M33_W06_연속검증_판단_정정과_마감_계획.md>)의 역사 기록이다. 현행 범위는 M33 TODO의 W06 절을 따른다.

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
- W06 수락 마감 후 사용자 지시로 HOST-W04를 시작했다. HOST-W04~W06 → W07 도구 → M33-W07 RC1 → 실제 OS 검증·HOST-W08 → M33-W07 마감 → M33-W08 별도 공개 승인 순서다.
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
추정하지 않으며 현행 실행 순서는 [M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용)을 따른다.

HOST-W04 완료 source·설치3OS 원문과 HOST-W05 착수 범위는 [313번](<04_검증 기록/313_HOST_W04_설치_마감과_HOST_W05_경로_cache_lock_착수.md>)을 따른다.
