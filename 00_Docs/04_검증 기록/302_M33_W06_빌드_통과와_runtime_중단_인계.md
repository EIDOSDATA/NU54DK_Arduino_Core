# M33-W06 빌드 통과와 runtime 중단 인계

> **후속 가용성 변경:** §1~6은 로컬 자료 삭제 전 6867 기준 기록이다. 2026-10-05 후속 확인에서
> 해당 source/result/진단 root가 없어졌고 최신 구현은 94bb로 바뀌었다. 현재 재개는 아래 §7과
> [M33 인계](../M33_HANDOFF.md)를 따른다. 옛 경로·명령을 현재 입력으로 바로 실행하지 않는다.

기록일: **2026-10-05**. M33은 **W01~W05 5/8 완료**, W06은 미완료다. 사용자가 작업을 정지한 뒤
새 채팅 인계를 위한 문서 검토·갱신·커밋·푸시를 요청했다. 이 기록 작성 중 구현·target build·보드 시험은
재개하지 않았다. 현재 작업 지시는 [M33 인계](../M33_HANDOFF.md), 완료 조건은 [M33 TODO](../TODO_M33.md)를 따른다.

## 1. 저장소와 정확한 증거 기준

| 항목 | 확인한 값 |
| --- | --- |
| 저장소 / branch | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `Dev-0.6.0-M33` |
| 인계 정비 시작 HEAD | `6867d4d86ccdedfe448ef3e454c64a77f5cab82c`, origin 추적 ref와 동일, 시작 tree clean |
| 마지막 구현 commit | `fix(m33): accept sleeping readback state` |
| Board gitlink | `board_package/NU54DK_Zephyr_DTS` = `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, clean |
| SDK / toolchain | NCS 3.4.0 / `dcbdc366a1`; lock·SDK·board 변경 없음 |
| 보존 exact source | `C:\n54w06s19\source-lf`, 위 6867 revision, clean LF 독립 clone |
| 실행 결과 root | `C:\n54w06o19` |
| Git worktree / 실행 상태 | 본 저장소의 등록 worktree 1개. 감사 시 관련 Python/pyOCD/CMake/Ninja/Arduino build 프로세스 없음 |
| 미착수 | HOST-W04~W08, M33-W07~W08. HOST 3/8이며 W06 완료 전 병행 금지 |

이 문서가 포함된 인계 commit은 위 source 다음의 **문서 전용 commit**이다. 새 HEAD의 빌드·실기
결과를 소급 주장하지 않는다. 기존 exact clone·실패 evidence·SDK·외부 출력 root는 변경하거나 삭제하지
않았다. 로컬 전용 대형 산출물은 Git에 포함되지 않으므로 다른 PC로 옮기면 별도 전달/다운로드가 필요하다.

## 2. 통과한 범위와 아직 없는 결과

| 검사 | 실제 결과 | 증거 |
| --- | --- | --- |
| GitHub Actions | plan·4 shard·aggregate SUCCESS, attempt 1 | [run 37265515608](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37265515608), head SHA 6867 exact |
| 로컬 artifact 재집계 | 150 slot 중 build 141/141, runtime 9 `NOT_PROVIDED`; HIL/physical/soak `NOT_RUN` | `gha\download\local-m33-w06-ci-build-aggregate.json` |
| Exact Host | PASS 59 suites / 487 tests / failed 0 / skipped 0, source clean | `host-regression\result.json` |
| 당시 board inventory | READY 3, hash-only identity | `gha\inputs\board-inventory.runtime.json` |
| BAP 준비 | `FLASH_PREPARED`, sector flash·software reset | `gha\inputs\bap-flash-record.combined.json` |
| Ecosystem client·peer | 두 build exit 0, source clean; runtime 미실행 | `runtime-fixtures\builds\ecosystem-{client,peer}\build-manifest.json` |
| Profile fixture | **FAIL: `client readback halt failed`** | `runtime-fixtures\profile-fresh.json` |
| Runtime 최종 결합 | producer 최종 manifest 없음, 9 slot 미결합 | `runtime-fixtures\runtime-producer-plan.json`만 존재; `runtime-fixtures\runtime-producer.json`·`runtime-generated` 없음 |
| W06 본 실행 | 33 family + 8 resource + 8 automatic peer = 49 group, 1,800초 soak, closure **미완료** | 완료 matrix/closure 없음 |

위 상대 로컬 경로는 모두 `C:\n54w06o19` 아래다. 141 build slot과 49 physical group은 서로 다른
분모이며 141/141로 W06 진행률 100%를 주장하지 않는다. Artifact 계획의 48 campaign과 dispatcher의
33+8+8 group도 서로 다른 분류다. M33 전체 완료 수는 여전히 5/8이다.

BAP flash 뒤 profile producer가 세 보드를 다시 프로그램했다. BAP record는 당시의 준비 증거이며
현재 firmware가 BAP라고 가정할 수 없다. Profile 실패 JSON의 `exact_program`, `results`, `cleanup`은
비어 있고 protocol 완료·STOP/자원 반환 증거가 없다. 다음 실기 전 live identity·firmware·debugger 상태와
안전한 종료 상태를 확인해야 한다. 문서 정비를 위해 보드를 다시 열거나 reset하지 않았다.

## 3. 실제 실패 지점과 진단 경계

실패 시각은 `2026-10-05T15:59:21.943085+09:00`이다. 상위 producer의 포괄 오류는
`producer subprocess failed: python.exe/m33_profile_run.py`였으며, 하위 JSON의 원문 원인은
`client readback halt failed`다. 세 역할의 sector flash record와 debugger identity가 있고, 이어 exact
image readback을 위한 client halt 확인 단계에서 실패했다. 이것은 C/C++ compile 실패가 아니다.

현재 [readback 검사](../../tests/hil/nu54dk/m33_sdk_risk_common.py)의
`readback_programmed_images`는 `session.target.halt()` 직후 `get_state()`를 **한 번만** 읽고
`HALTED`가 아니면 실패한다. 비동기 halt 완료를 기다리지 않은 경합은 조사 가설이나, 실패 당시 실제
non-HALTED 상태값이 원본에 없으므로 원인으로 확정할 수 없다. Probe 통신·target 상태·필요하면
DHCSR 등 debugger 근거를 확보하고 유한 대기·timeout·finally 복원 계약을 검토한다.
[diagnostics helper](../../tools/bluetooth/m33_diagnostics.py)의 `halt_and_wait`는 참고할 수 있지만
reset latch와 상태 복원 의미가 다를 수 있으므로 무조건 복사하지 않는다. 수정은 다음 개발 재개 범위다.

다음 두 문제는 구분한다.

- **수정 반영:** 기존 readback 전 `RUNNING`과 resume 뒤 정상 WFI `SLEEPING` 사이 전환을 복원 실패로
  오판한 문제는 6867에 수정됐다. active class는 이 두 상태만 허용하고 `HALTED`는 exact 보존한다.
- **미해결:** 이번 halt 확인 FAIL은 readback을 시작하기 전의 다른 검사다. 위 복원 수정의 검증이
  끝났다고 W06 실기 완료로 처리하거나, 현재 오류를 SDK·보드 고장으로 단정하지 않는다.

이전 `C:\n54w06diag-profile-portable-output-4\profile-fresh.json`의 native profile 성공은 옛
`9f961d3a…` 이미지와 dirty development 진단의 `DIAGNOSTIC_PASS`다. 3 security session·14 object·
2 glucose·cleanup을 관측했지만 current clean W06의 대체 증거가 아니다. 진단 source
`C:\n54w06diag-profile-portable`과 앞선 실패 root도 보존한다. `e4ced2f8…`의 Actions
[37264060631](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37264060631)도 최종 SUCCESS를
확인했으나 최신 source/산출물과 섞지 않는다.

## 4. artifact와 무결성 재사용

ZIP은 `C:\n54w06o19\gha\zips`, 분리 해제 root는 `C:\n54w06o19\gha\download`, ZIP 체크섬은
`C:\n54w06o19\gha\SHA256SUMS.txt`다. 6개 ZIP을 감사에서 재해시해 체크섬 일치를 확인했다.
아래 이름에는 공통 suffix `-37265515608-attempt-1`이 붙는다.

| Artifact prefix | ID | ZIP SHA-256 |
| --- | --- | --- |
| `m33-w06-plan` | 11326655922 | `a1f64a6463096e6a89fb3e52b56c355340052701b3e78499735f2eb4066e5988` |
| `m33-w06-build-shard-0` | 11326959479 | `ac3b70c42f969a5c463928d7840f6462268b25a80429ce95a8a76a10af5d5161` |
| `m33-w06-build-shard-1` | 11326689575 | `6342448a64523eb109f0b104b559a1483c1f165d290813c630f46ea4199441ac` |
| `m33-w06-build-shard-2` | 11327427479 | `cf8fb07b28ec3aecd4660943643b638293e7bf46d87f1a519f3c350c1538a846` |
| `m33-w06-build-shard-3` | 11327043694 | `b4884476bd65ba8c05b9f3c4d60c5147e9d8a20791e2ac3a165d749fafcf3a0f` |
| `m33-w06-build-aggregate` | 11328545201 | `3c9569e4feea180f01a4e08b0105745d5cd107989ab8c9cb68176296908af0d6` |

| 로컬 파일 (`C:\n54w06o19` 기준) | 파일 byte SHA-256 |
| --- | --- |
| `host-regression\result.json` | `27265b35264e182c0f9b54550b5c83de408f63d95b993073653666ae167cd643` |
| `gha\download\local-m33-w06-ci-build-aggregate.json` | `b21b8a01efb58e687bcea9d8262c05ddc8d14be9bf422b80a370a24623f23d7e` |
| `gha\download\local-m33-w06-build-index.json` | `98df94610430a2070386b29f62da960e6c5f42c7282e7f29d2018539648d91ed` |
| `gha\download\local-m33-w06-runtime-inputs.json` | `6a1b78a9961b8698b0dd547c26d6b1db4b79e754f70b841d6738ff07c605aa4c` |
| `gha\inputs\bap-flash-record.combined.json` | `eab38d5c7bcda161940215aac063aa58edf9e1068f1389fa97c1e11c4973546c` |
| `runtime-fixtures\profile-fresh.json` | `1a6a3a4d72c4779fd154ec28f5dc655be2ab55072aeae095d437f2934ad37288` |
| `runtime-fixtures\builds\ecosystem-client\build-manifest.json` | `1925759278e5298ab54aa71fc7f7f1461f4594dbff56019509966061b298ba57` |
| `runtime-fixtures\builds\ecosystem-peer\build-manifest.json` | `8fb39e6890d0e954539012916c1626c4a134a09774788e48e03b7aab717aaeae` |

Local aggregate 내부의 canonical `aggregate_sha256`는
`11223b24b06284f11c34aa5a2d5e5f943b8c15b4f44321a30215fca8b7a0d471`이며, 위 JSON 파일 byte hash와
다른 정의다. 원격 aggregate의 `D:/...` index를 로컬 실행에 그대로 사용하지 않는다.

`aggregate-shards`의 index/runtime/aggregate output 세 파일은 **모두 `--shards-root` 바로 아래의
서로 다른 새 이름**이어야 한다. 별도 `C:\n54w06o19\local-aggregate`에 output을 두었던 첫 시도는
이 계약으로 거부됐고, `gha\download\local-*` 이름으로 재실행한 것만 PASS다. 기존 output을 덮어쓰거나
flat extract하지 않는다. 기존 download root의 위 세 `local-*` 파일이 성공한 재집계 산출물이다.
동일 exact 검증을 필요 없이 반복하지 않되 source/계약 변경 시에는 새 exact plan과 증거를 생성한다.

## 5. 실행 명령과 재개 순서

다음은 **실패 당시 명령의 재현 기록**이지 이번 문서 작업에서 실행할 지시가 아니다. 기존 output은
덮어쓰지 않는다. 새 시도에서는 source·plan·build index·보드 mapping을 먼저 다시 검증하고 새 output을 쓴다.

```powershell
Set-Location C:\n54w06s19\source-lf
$M33Inventory = Get-Content C:\n54w06o19\gha\inputs\board-inventory.runtime.json -Raw | ConvertFrom-Json
py -3 tests/hil/nu54dk/m33_w06_runtime_fixture.py `
  --plan C:\n54w06o19\gha\download\m33-w06-plan-37265515608-attempt-1\m33-w06-artifact-plan.json `
  --build-index C:\n54w06o19\gha\download\local-m33-w06-build-index.json `
  --sdk-root C:\ncs\v3.4.0 `
  --toolchain-root C:\ncs\toolchains\dcbdc366a1\opt\zephyr-sdk `
  --output C:\n54w06o19\runtime-fixtures `
  --client-probe-sha256 $M33Inventory.physical_slots[0].probe_sha256 `
  --peer-probe-sha256 $M33Inventory.physical_slots[1].probe_sha256 `
  --third-probe-sha256 $M33Inventory.physical_slots[2].probe_sha256 `
  --execute --authorize-sector-program --authorize-software-reset --authorize-three-board-hil
```

HIL driver는 의존성이 설치된 현재 Python(`py -3`)을 사용한다. NCS bundled Python을 직접 driver로
실행했을 때 `ctypes` import `_type_` 예외가 있었으며, 내부 west는 계속 고정 NCS/toolchain 환경을 쓴다.
이 구분은 SDK pin 변경이 아니다. Exact Host 명령은 MSYS2 UCRT64 도구가 PATH에 있는 상태에서
`py -3 tools/bluetooth/m33_regression.py host --output C:\n54w06o19\host-regression`이었다.

새 채팅 재개 순서:

1. 문서·실제 branch/HEAD/dirty/submodule을 확인하고 보존 source와 최신 문서 HEAD를 구분한다.
   `client readback halt failed`를 먼저 진단한다. 새 프로세스·probe lock·현재 board 상태를 확인하고,
   이전 cleanup 성공을 추정하지 않는다. debugger 관측과 관련 공식 근거로 원인→수정→유한 재시험한다.
2. Windows symlink preflight를 초기에 확인한다. 당시 `AllowDevelopmentWithoutDevLicense` 값이 없고
   비관리자였으며 생성 시 권한 오류가 났다. probe symlink 파일도 남지 않았다. 여전히 불가하면 사용자가
   Developer Mode 또는 동등한 승인된 실행 권한을 마련해야 한다. 임의 승격·설정 변경·copy 우회는 금지한다.
3. Runner 수정이 필요하면 독립 진단·회귀를 먼저 충분히 검증한 뒤 새 exact source를 고정한다.
   Actions build와 독립 Host 검사를 병렬화하되 동일 보드를 여러 runner가 동시에 소유하지 않게 한다.
   기존 clean source의 증거를 새 source로 재명명하거나 provenance를 합성하지 않는다.
4. 필요한 exact runtime producer를 성공시키고 9 runtime slot 결합 → symlink stage → validate를 완료한다.
   각 campaign 직전 group 20 BAP·31 ecosystem·33 third-idle의 deterministic restore 계약을 유지한다.
5. [실행 절차](../../tools/ci/m33_w06_artifacts.md) §8에 따라 49 group → 별도 3보드 1,800초 soak →
   exact Host/SDK risk/qualification → assemble/validate를 수행하고 지원표·TODO·인계를 마감한다.
   실제 조건 미충족 SDK 위험을 PASS로 합성하지 않고 외부 Apple/Google·외장 장치는 `NOT_RUN`으로 남긴다.
6. W06 완료 조건을 충족하면 문서 갱신·커밋·푸시하고 결과를 보고한다. 자동 진행 목표는 W06까지다.
   HOST/RC/공개 순서는 유지하지만 후속 범위와 공개 권한을 이번 인계만으로 확대하지 않는다.

정상 sector program·software reset·halt/resume·read-only audit·안전 runner는 재개 후 기존 승인 범위다.
매 실행의 `--authorize-*`를 새 승인 요청으로 오해하지 않는다. 실제 사람 조작·새 권한이 반드시 필요한
경우에만 이유와 행동을 명시해 중단한다. 자동 mass erase·unlock·recover·SDK 변경은 계속 금지한다.

## 6. 문서 감사 범위와 보존

정비 시작 기준 main tracked Markdown **503개**, board submodule Markdown **6개**를 끝까지
strict UTF-8로 읽고 전체 텍스트 상태/정책 키워드를 점검했다. Main 문서의 LF 정규화 합계는
4,543,090 byte다. 이는 자동 전수 텍스트 점검이며 509개 모든 역사 문단의 기술 결과를 새로 검증했다는
뜻이 아니다. AGENTS·현행 TODO·인계·계약·SDK 기록·296~301 결과와 변경 문맥을 본문/증거로 대조했다.
과거 PASS/FAIL/HOLD/NOT_RUN·공개 자산·295번 감사 snapshot은 보존하고 현재 안내의 낡은 M33 0/8·1/8,
CI 금지, W05 69/69 표현만 교정했다. 변경 문서 hash와 실제 gate 결과는
[감사 원장](../document-review.json)의 2026-10-05 후속 항목에 남긴다.

문서 전용 push 뒤 자동 CI가 시작되더라도 그것을 보드 시험 재개나 W06 완료로 해석하지 않는다.
인계 commit·원격 일치·clean 확인과 해당 SHA CI의 조회 시점 상태는 최종 인계 응답에 별도로 남긴다.

## 7. 로컬 자료 삭제 후 후속 인계 — 2026-10-05

사용자가 C 드라이브 작업 자료 삭제와 단일 처리 우선을 알렸다. 이번 후속 정비는 문서만 수정하고
기능 개발·target build·HIL은 재개하지 않았다. §1~6의 당시 판정·hash는 바꾸지 않고 가용성만 구분한다.

- 실제 저장소와 원격 branch는 남아 있으며 이번 시작 HEAD는 `94bb730c783f90cd7aeeb3e68b13da458c2b9459`다.
  이 commit에는 debugger halt 유한 대기·상태 복원 수정이 있으므로 §3의 옛 단일 상태 검사 설명은
  최신 코드 설명이 아니다. 변경이 실물 문제를 최종 해결했는지는 새 exact 결과로 검증해야 한다.
- `C:\n54w06s19\source-lf`·`C:\n54w06o19`와 §3의 두 진단 root,
  `C:\n54w06s4`·`C:\n54w06s5`는 `Test-Path`로 없음이 확인됐다. 이 목록 밖의 모든 C 드라이브 자료가
  삭제됐다고 확대하지 않는다. Git 저장소·두 이력 bundle·SDK/toolchain 디렉터리는 존재했다.
- 94bb의 [Actions 37287774267 attempt 1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37287774267)는
  SUCCESS이고 API의 plan·4 shard·aggregate 총 6개는 `expired=false`였다. 옛 6867 run의 6개도
  조회 시점에는 만료되지 않았다. 둘을 섞지 않으며 현재 다운로드 가능·hash 일치는 실제 복구 때 검증한다.
  94bb artifact ID는 plan `11335725081`, shard 0 `11337242599`, 1 `11337282119`,
  2 `11336383817`, 3 `11337490265`, aggregate `11338295662`다. 이번에 다운로드하지 않았다.
- 기존 미커밋 idle-fixture 경로 처리·runtime fixture 회귀·count/hash·안내 변경 4개는 보존했다.
  목록과 첫 검토 순서는 M33 인계가 소유한다. 이 문서 commit이 해당 기능 수정의 검증·채택은 아니다.
- 주 에이전트 1개가 순차 처리하며 하위 에이전트를 만들지 않는다. 기존 Actions shard는 허용하고
  로컬 무거운 build/HIL은 한 번에 하나만 실행한다. 과거 병렬 위임 지침은 이 결정으로 대체한다.
- 새 작업 root는 아직 정하지 않았다. 재개 시 짧은 새 root를 하나 정하고 source/output을 구분하며,
  필요한 동일 exact artifact만 복구한다. Source가 바뀌면 새 근거를 생성한다. 원격에 없는 local
  Host·inventory·runtime·cleanup 결과는 복구된다고 가정하지 않고 필요한 실제 검사를 다시 수행한다.
  문서의 옛 hash로 파일이나 PASS를 합성하지 않는다.

필요한 소스·도구·symlink 권한과 현재 보드 안전 상태를 확인한 다음 반영된 halt 수정 및 미커밋
idle-fixture 변경을 검토한다. 9 runtime slot·49 physical group·1,800초 soak·최종 closure는 여전히
미완료다. Ubuntu/macOS 최종 지원·외부 peer·공개 승인 경계와 NCS 3.4.0 pin은 그대로 유지한다.
