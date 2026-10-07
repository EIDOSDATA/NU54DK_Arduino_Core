# M33-W06 재실행 최소화와 checkpoint 개선 계획

> **2026-10-07 후속 결정:** 이 문서의 기존 실행은 사용자 요청으로 중단했다.
> 다음 구현 기준은 [검증 파이프라인 재설계](<../02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>),
> 중단·문서 정비 결과는 [304번](304_M33_W06_실행_정리와_문서_전수_검토.md)이다.
> 아래 본문은 당시 계획·관측·수정 이력으로 보존하며 새 자동 실행 지시가 아니다.

기록 시작일: **2026-10-07**. 이 문서는 M33-W06을 완료하기 전에 반복 실행 비용을 줄이고,
관측된 전송 계층 오류와 실행기 구조 결함을 먼저 제거하기 위한 현행 작업 기준이다. 완료 결과는
별도 source의 증거를 이 문서에 소급하지 않고, 최종 exact source·run·attempt·로컬 evidence root를
확정한 뒤 후속 절에 추가한다.

## 1. 현재 판정과 문제 정의

감사 시작 기준 Core는 `a9c306be2d6d3db96e447cb0f4fb17ad8ebafcbc`, board gitlink는
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, SDK는 NCS `3.4.0`, toolchain은
`dcbdc366a1`이다. 이 source의 exact Host는 60 suite·492 test·skip 0으로 PASS했으나, 아래 개선으로
source가 바뀌면 최종 W06 증거로 재사용하지 않는다. 실행 중인 Actions build도 source가 바뀌면
중단하고 새 exact run을 만든다.

이전 matrix에서 `m28_link`와 `m29_cache`처럼 서로 다른 campaign·role의 sector program이 간헐적으로
`FlashFailure: flash init timed out`에 먼저 걸렸고, 같은 image·probe의 새 session 직접 재시험은
통과했다. 따라서 M28 또는 M29 기능 자체의 순서 오류로 단정하지 않는다. 유한 30초 init timeout은
무한 정지를 막지만, 한 session이 나빠진 뒤 같은 session을 오래 기다리는 것만으로는 복구되지 않았다.

또한 기존 matrix는 완료된 spec/result 쌍은 재검증해 재사용하지만, 실패 group의 spec 또는 부분
sidecar만 남으면 output root 전체를 거부했다. 그 결과 source가 같아도 새 root에서 앞선 PASS group을
다시 실행해야 했다. 실패 원본 보존과 실패 지점 재개를 동시에 만족하지 못한 실행기 결함이다.

과거 BAP 기록의 핵심도 유지한다. BAP는 ASCS 응답과 실제 상태 callback을 구분했고, flash 기록과
측정 reset을 분리했으며, reset 전후 UART 잔류 로그를 버린 뒤에만 측정했다. W06의 BAP pre-run
restore와 cycle runner도 program·reset·readback·UART drain 순서를 독립 검증한다. 과거 BAP PASS를
현재 source의 PASS로 복사하지 않는다.

## 2. 확정한 개선 원칙

1. **전송 계층과 기능 판정을 분리한다.** flash/erase/reset/readback 오류는 RF·GATT·PAwR·BAP
   기능 실패와 다른 reason code로 보존한다.
2. **정확한 init timeout만 공통 flash helper에서 한 번 재시도한다.** 첫 `flash init timed out`에서
   기존 session을 닫고 live probe를 다시 찾은 새 pyOCD session으로 한 번만 재시도한다. 여러 보드
   session과 third guard를 동시에 소유하는 DTM 준비 경로는 session 일부만 바꾸지 않고 fail-stop한 뒤
   안전 cleanup을 남기며, 같은 matrix session의 다음 group attempt가 전체 준비를 새 session으로
   다시 시작한다. 다른 오류, readback 불일치, timeout 소진, 부분 기능 실패는 자동 재시도하지 않는다.
3. **모든 flash algorithm 소비 경로를 감사한다.** Intel HEX, binary, sector erase, DTM 준비의 직접
   `FileProgrammer` 경로를 포함한다. 단순 memory write clear·read-only debugger audit은 flash init
   재시도 대상으로 잘못 분류하지 않는다.
4. **부분 실행은 append-only attempt로 보존한다.** group별 attempt directory에 spec, log, receipt,
   child/native evidence를 격리한다. 실패 attempt는 수정·삭제하지 않고 다음 번호에서 재개한다.
5. **재개는 동일 session 계약에서만 허용한다.** immutable matrix session은 Core source, board
   inventory byte hash, artifact root, SDK/toolchain 경로, 49 group 순서를 고정한다. 하나라도 바뀌면
   기존 완료 group을 재사용하지 않는다.
6. **source가 바뀌면 exact 증거를 다시 만든다.** Actions plan·4 shard·aggregate, local aggregate,
   Host, runtime 9 slot, stage/validate, board inventory, HIL, soak를 새 source에 결합한다. 빌드 cache는
   계산 가속에 사용할 수 있지만 옛 artifact나 PASS를 새 source로 재명명하지 않는다.
7. **복구 명령은 진단 근거 뒤에만 사용한다.** 사용자가 pyOCD mass erase·unlock·recover를 허용했어도
   일반 retry로 자동 실행하지 않는다. DP/AP·APPROTECT·readback 근거상 필요한 정확한 보드와 작업만
   명시적으로 수행하고 원본 evidence를 남긴다.

## 3. 구현·감사 gate

새 보드 matrix를 시작하기 전에 다음을 모두 닫는다.

- 공통 HEX·binary program과 sector erase가 동일한 새-session 1회 retry 계약을 사용하는지 검사한다.
- M30 DFU와 M32 Mesh DFU의 erase/binary/settings clear/reset에 120초 flash budget이 전달되는지
  검사한다.
- DTM dual-transport 준비처럼 공통 helper를 우회하는 직접 `FileProgrammer` 경로를 별도 감사하고,
  동일 안전성 또는 명시적 fail-stop 근거를 확정한다.
- 48 campaign runner의 실제 argparse interface와 dispatcher 인자를 대조해 지원하는 모든 runner에
  `--flash-timeout 120`이 전달되는지 검사한다. 자체 고정 120초 runner는 별도로 기록한다.
- BAP·ecosystem·third-idle pre-run restore의 program-all → reset-all → live readback → UART STOP/audit
  순서, 연속 probe lock, session close, 실패 시 상태 보존을 검사한다.
- bond/settings/secondary slot처럼 다음 campaign에 영향을 주는 상태와 cleanup 경로를 검사한다.
- append-only matrix attempt와 immutable session을 Host fixture로 검증한다. 부분 attempt 뒤에는
  같은 source에서 다음 attempt로 진행하고, 완료 attempt 뒤 추가 attempt·입력 drift·hash drift는
  fail-closed로 거부한다.
- 관련 집중 Host 검사와 전체 exact Host를 통과한 뒤에만 commit·push한다.

### 3.1 2026-10-07 정적 감사와 구현 결과

- W06 registry의 48 campaign·45 unique runner(그중 physical HIL 46)를 실제 argparse source로 다시
  열었다. 17개 runner가 `--flash-timeout`을 노출해 dispatcher가 120초를 전달한다. 나머지는 build-only,
  flash가 없는 측정 runner, 실행 직전 120초 state restore, 또는 공통 helper에 120초를 고정한 runner다.
- 공통 Intel HEX, binary, RRAM sector erase 세 경로는 모두 exact `FlashFailure("flash init timed out")`만
  새 probe 발견·새 session으로 한 번 재시도한다. RRAM settings clear는 flash algorithm이 아닌 memory
  write/readback이므로 이 retry에 넣지 않았다. M30 DFU와 M32 Mesh DFU의 secondary erase·binary program도
  같은 helper와 각 runner의 120초 이상 budget을 사용한다.
- 전체 source의 직접 flash algorithm 소비자는 공통 helper 외에 DTM preparation adapter,
  `m30_power_loss.py`, `m31_audio_hap_run.py`였다. 뒤의 두 runner는 W06 registry에 없다. DTM은 TX/RX/third
  세 session과 read-only third guard를 한 생명주기로 묶으므로 부분 session 자동 교체를 금지한다.
  실패 preflight·세 보드 cleanup audit를 보존하고 matrix 다음 attempt에서 group 전체를 재개한다.
- BAP의 183·190번 원인을 다시 대조했다. 현재 pre-run restore는 두 역할을 먼저 no-reset sector program하고,
  전 역할 software reset 뒤 live all-range readback을 수행한다. cycle runner는 별도 reset 전후 UART buffer를
  비운 뒤 ASCS 실제 callback 기반 상태와 stop/release 순서를 측정한다. 과거의 명령 응답 조기 판정과
  reset 잔류 로그 재사용 경로는 현재 실행 순서에 없다.
- matrix는 `m33-campaign-matrix.session.json`에 source·inventory hash·artifact/SDK/toolchain·49개 순서를
  고정한다. spec-only, invalid result를 포함한 실패 attempt를 새 디렉터리로 보존하고 다음 번호에서만
  재개한다. 최종 manifest는 각 group의 `INCOMPLETE`/`FAIL`/`PASS` attempt 이력과 byte hash를 함께 묶는다.
  완료 attempt 뒤 추가 attempt, 번호 공백, result-only, session drift는 fail-closed다.
- 관련 Host 156개와 matrix 실제 schema v2 재검증 fixture는 PASS했다. 이는 dirty 개발 source의 집중
  검사이며, 최종 commit의 clean 60-suite Host 증거를 대신하지 않는다.

## 4. 최종 exact 실행 순서

1. 감사 수정 commit을 push하고 그 SHA의 Actions plan·4 shard·aggregate를 기다린다.
2. 새 짧은 LF exact checkout과 새 evidence root를 만든다. 이전 실패·진단 root는 보존한다.
3. plan과 네 byte-bearing shard를 분리 다운로드하고 run/attempt/source/hash를 확인한다. aggregate를
   별도로 받아 local `aggregate-shards`로 141 build와 runtime 9 `NOT_PROVIDED`를 재검증한다.
4. exact Host, 보드 3대 inventory, BAP 역할별 flash record, runtime producer, runtime 9 slot bind,
   symlink stage와 150 slot validate를 완료한다.
5. 짧은 flash/erase/DTM 준비 preflight를 통과한 뒤 33 family + 8 resource + 8 automatic peer group을
   append-only matrix로 실행한다. 동일 source의 transient 실패는 실패 group의 다음 attempt부터 재개한다.
6. matrix 49/49 뒤 별도 세 보드 1,800초 soak, 최종 board inventory, 최종 Host, SDK risk,
   qualification, closure assemble/validate를 수행한다.
7. Apple/Google peer·외장 장치와 Ubuntu/macOS 실제 지원은 `NOT_RUN` 경계를 유지한다. 미실행을 PASS로
   바꾸지 않는다.
8. 현행 M33 TODO·v0.6.0 TODO·HANDOFF·지원표·검증 색인을 갱신하고 commit·push한다. M33은 W06
   완료 시 6/8이며 HOST는 3/8을 유지한다. HOST-W04 이후는 별도 사용자 확인 전 착수하지 않는다.

## 5. 완료 조건

W06 완료는 build 141/141만으로 선언하지 않는다. 같은 최종 source에 대해 runtime 9/9,
stage/validate 150/150, physical group 49/49, 세 보드 1,800초 soak, Host skip 0, SDK risk와
qualification 경계, closure 재검증이 모두 있어야 한다. 각 실패 attempt와 사용한 복구 작업은 최종
기록에서 제외하지 않으며, 최종 PASS의 source·artifact·보드 mapping과 섞지 않는다.

## 6. D 드라이브 전용 구조 개선과 재개

2026-10-07 사용자 승인으로 구조 개선 뒤 commit·push하고 W06 전체 검증까지 순차 진행한다.
착수 source는 `d79705d6b906b3128198e463dfb866e923165f76`이며 새 작업 저장소는
`D:\w06\src`, 실행·증거는 `D:\w06\runs`, 원격 artifact는 `D:\w06\artifacts`,
cache·임시 파일은 `D:\w06\cache`·`D:\w06\tmp`로 고정한다. C의 기존 SDK/toolchain은
설치 입력으로만 사용하고 새 checkout·build·실행 로그를 C에 만들지 않는다.
사용자가 이전 C 작업 자료와 D 백업을 삭제했으므로 옛 local PASS 파일의 존재를 가정하지 않는다.

기존 group checkpoint만으로 전체 실행의 중단 안전성이 충족되지는 않는다. 다음 구조를 먼저 검증한다.

1. 공통 실행 계층에서 immutable 입력 identity, 위치 매핑, 단계별 append-only attempt와
   결과 파일의 원자적 확정을 관리한다. 부분 write를 완료 결과로 읽지 않고 기존 파일을 덮어쓰지 않는다.
2. 환경·전송·기능·무결성·안전 상태·중단을 구분한다. 이미 생성된 PASS/result의 검증 오류는
   재시도 가능한 FAIL로 바꾸지 않는다. 실패 원인과 stdout/stderr를 raw UID 없이 보존한다.
3. runtime의 재사용 가능한 build와 보드 상태에 의존하는 fixture cycle을 분리한다. 실패 뒤 build를
   재검증해 재사용하되, cleanup→fresh→idle export→ecosystem 준비의 물리 의존 chain은 새 attempt에서
   다시 준비한다. 과거 checkpoint만으로 현재 firmware/STOP 상태를 추정하지 않는다.
4. 기존 probe lock·watchdog·restore·readback·STOP 검증을 유지하며, 개별 runner의 무선 의미 판정은
   바꾸지 않는다. 상태가 불명확하면 다음 보드 동작 전에 진단하며 무제한 retry하지 않는다.
5. 경로는 identity가 아닌 위치 정보로 다룬다. 이동 입력은 실제 내용과 source를 재검증하고,
   기존 절대경로가 포함된 실행 증거를 수정하거나 다른 root의 증거로 합성하지 않는다.
6. 중단/부분 기록/손상/입력 drift/재개/이동·dispatcher 계약을 Host에서 주입 검증하고 짧은 실제
   준비 chain을 통과한 뒤 최종 exact source를 고정한다. 진단 결과와 qualification 결과를 분리한다.

최종 분모 141 build, runtime 9, stage 150, physical 49, 세 보드 1,800초 및 closure 조건은
변경하지 않는다. 구조 개선 구현·회귀 통과 자체는 W06 완료가 아니며 완료 TODO와 과거 원본을 고치지 않는다.

### 6.1 구조 구현과 개발 검사

- `m33_execution.py`에 duplicate-key/부분 JSON 거부, fsync 뒤 no-clobber 원자 확정,
  상대 output 경로·hash, OS writer lock, immutable session과 append-only 단계 attempt를 추가했다.
  lock은 프로세스 종료 시 OS가 반환하고 완료 receipt는 byte/hash와 원래 의미 validator를 다시 통과해야 한다.
- runtime producer의 client/peer build를 독립 checkpoint로 나누고, 물리 준비는
  cleanup→fresh→idle export→ecosystem 한 cycle로 묶었다. 완료 build 재사용과 물리 cycle 재실행을
  Host에서 주입 검증했다. 현재 firmware/STOP는 완료 checkpoint만으로 추정하지 않는다.
- 기존 §3.1의 invalid result 재시도는 폐기했다. 이미 생성된 result의 손상은 무결성 중단이며,
  result가 없는 실패 attempt만 원본 log·spec·failure category를 보존한 뒤 다음 번호로 재개한다.
  SAFETY/INTEGRITY는 자동 재개하지 않는다. runner 비정상 종료를 기능 실패로 단정하지 않는다.
- 공통 receipt의 상대 경로는 이동을 지원하지만 기존 절대경로 기반 runtime/semantic evidence를
  편집해 이전하는 기능은 추가하지 않았다. 해당 계약이 불일치하면 새 원본 실행이 필요하다.
- 집중 검사: 공통 실행 21, matrix/회귀 66, runtime 14 모두 PASS. 실제 parser가 산출한
  test ID count/hash를 Host 계약에 반영했다. dispatcher 48/48 READY를 다시 확인했다.
- 전체 개발 Host: `D:\w06\runs\dev-host-structure`에서 61-suite / 521-test, 실패 0·skip 0.
  source가 dirty라 `result.json.status=FAIL`이며 최종 clean exact Host로 승격하지 않는다.
  구조 commit 뒤 clean Host를 다시 실행한다. BAP 183·190번 원인과 상태 callback·reset/UART drain
  분리 계약도 다시 읽었다. 새 BAP 물리 PASS를 주장하는 기록은 아니다.
- D checkout LF 준비 중 역사 log의 EOL 변경을 탐지해 원본 Git byte로 복원했다. 제품·과거 증거
  diff는 남기지 않았다. CRLF 원본 한 transcript는 local Git attribute에서 `-text`로 보존했으며
  object hash `06d670b88e063935c87702fff62ccf8824260365`와 실제 file byte를 대조했다.
  source/증거 내용을 바꾸거나 검증기를 우회한 기록은 없다.

다음은 구조 commit·push, 새 exact plan·Host·Actions, 4 shard 다운로드/재결합과 실제 fixture 준비다.

### 6.2 D/C 분리 환경의 실제 preflight 수정

구조 구현 `1413d3e882ea87be6ead33af39a913dc8cb7e3f1`을 commit·push했다. `D:\w06\e1`의
clean exact plan, Host 61-suite / 521-test / skip 0 PASS와 세 probe inventory·halt/복원 PASS를
확인했다. 이어 ecosystem client build는 target 접근 전에 고정 SDK west의
`zephyr/scripts/west_commands/build.py:534`에서 `os.path.relpath(source_dir)`가 D source와
C SDK cwd를 처리하지 못해 실패했다. 원본은 `.build-stages/build-client/attempt-0001`의
build.log·command log·failure.json에 봉인했다. firmware 기능 실패로 해석하지 않는다.

고정 west 1.5.0의 `west.util.west_topdir()`와
[Zephyr workspace 탐색 문서](https://docs.zephyrproject.org/latest/develop/west/basics.html)를
대조했다. ecosystem와 repository-owned direct-west action은 source checkout을 cwd로 사용하고
`ZEPHYR_BASE`로 고정 SDK workspace를 찾도록 수정했다. SDK sample을 source로 쓰는 diagnostics는
SDK cwd가 맞으며, Arduino builder는 이미 materialized app cwd를 사용했다. SDK source는 수정하지 않았다.

Zephyr cache의 존재하지 않는 LOCALAPPDATA 하위 경로는 SDK `.cache`로 fallback한다는 점도 확인했다.
첫 configure 진단은 이를 발견한 뒤 해당 진단 프로세스 트리를 종료했다. 이후 ecosystem 명령에
`USER_CACHE_DIR`를 output 하위로 명시하고 D local cache 경로를 준비했다. `D:\w06\diag2`의 실제
configure는 C SDK/D source 조합에서 완료됐고 cache 출력도 D로 확인했다. 이는 dirty 진단이며
qualification build나 물리 PASS가 아니다. 관련 runtime 15개·artifact 42개 Host는 PASS했다.

Actions 37516735316 attempt 1의 plan ZIP을 권한·서버 SHA-256
`7de01431dc119c54badafe92a959bd5be3b99246670c9b906700ca23c986ef12`와 대조해 D에 내려받았다.
local/CI source 비교에서 lock JSON byte hash가 autocrlf에 따라 다른 것도 실제 확인했다.
`.gitattributes`로 first-party tools/tests/core/library/variant/build source를 LF로 고정한다.
과거 문서 evidence는 범위에서 제외하고 Windows cmd/bat의 CRLF 예외는 유지한다.
source가 다시 바뀌므로 1413의 Host/build/runtime 상태는 새 source의 결과로 승계하지 않는다.

원격 구 source 실행의 cancel API는 두 차례 5xx여서 중단을 확인하지 못했다. 새 실행과 구 실행을
run/source별로 분리하며 구 실행이 끝나더라도 새 qualification으로 사용하지 않는다.
로컬 SSH directory는 비어 있고 등록 Linux/Mac endpoint를 찾지 못했다. 접근 가능이라고 추정하지
않으며 실제 OS 지원 검증은 예정대로 RC의 사용자 gate로 남긴다. Git 이력 bundle 두 개는 D 사본의
SHA-256을 기존 값과 다시 대조했다.

### 6.3 e76 실제 준비 통과와 최종 결합부의 사전 교정

`e76bbcff439553a37c0a5ecfd1cc8cfacc5650cb`의 Actions
[37518444542 attempt 1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37518444542)은
plan·4 shard·aggregate 6 job 모두 SUCCESS다. 6개 ZIP을 같은 source/run/attempt의 권한·가용성·
서버 SHA-256과 대조해 `D:\w06\artifacts\e2`에 별도로 풀었다. 다운로드 receipt도 각각 보존했다.
이전 37516735316 실행은 최종 cancelled로 확인했으며 새 source 결과에 섞지 않았다.

첫 로컬 aggregate는 Core source SHA-256 불일치로 보드 접근 전에 중단됐다. 503개 Core 입력 중
`third_party/ArduinoCore-API.provenance.yml` 하나의 local LF와 Windows Actions CRLF 차이가 원인이었다.
메모리에서 그 파일만 CRLF로 바꾸면 CI digest
`333c2784f28191e39cd4779587ed09c3a5333036a4a84a4fe8e3406884c7d247`를 정확히 재현했다.
Git checkout-index로 얻은 실제 CRLF byte를 사용하고 원래 LF 파일은 별도 보존했다. Git clean-filter
blob은 HEAD의 `396e108aa86393994c95560086d575c404abaf90`와 같고 source/index는 clean이었다.
129개 native build record의 Core/board digest와 실제 validator를 다시 통과했다. record 편집,
SDK 변경 또는 validator 완화는 하지 않았다. 재발 방지는 해당 YAML의 CRLF를 repository attribute로
명시하는 방식이며 역사 transcript 원본은 변경하지 않는다.

e76에서 확인한 결과는 다음과 같다. 후속 수정 source의 PASS로 승계하지 않는다.

- local aggregate: 141 BUILD_ONLY / runtime 9 NOT_PROVIDED / total 150,
  aggregate SHA-256 `783ff0054c0826c5a4e876d72c9d969845e3cbca8712d07e955526d3dcb5a866`.
- checkout byte 정렬 후 clean Host: `D:\w06\e2\host-ci`, 61-suite / 522-test / skip 0 PASS.
- ecosystem client·peer: `D:\w06\e2\rt-ci\.build-stages`의 각 attempt-0001 build PASS.
- BAP 두 보드 sector flash: FLASH_PREPARED이며 duplex 반복 시험 PASS와 구분한다.
- runtime producer: cleanup→fresh→watcher idle export→ecosystem program/readback·third halt audit
  전체 PASS. cleanup/fresh 각각 세 역할 STOP·링크/scan/advertising/pending 0·serial close PASS.
  실제 보드 상태·이동 watcher 경로 검증은 이 실행에서 새로 얻었으며 옛 STOP을 복사하지 않았다.
- stage/49 group/soak는 아직 미실행이다. 최종 결합부 사전 점검 때문에 runtime 완료 직후 gate에서
  종료했다. `closure-integration-hold.txt`와 phase console을 보존했다.

긴 실기 이전에 다음 세 경계의 불일치를 확인했다. SDK나 무선 기능 실패가 아니다.

1. schema 2 matrix가 하위 attempt 폴더에 기록하는 결과를 closure가 인접 파일로만 받았다.
2. SDK 위험 참조를 group 폴더 기준으로 생성하고 bundle root 기준으로 검사했다.
3. 서로 독립 실행된 동일 campaign의 nonce/receipt가 같아야 한다고 가정했다.

수정은 원본을 root로 복사하거나 대표 PASS 하나만 택하는 우회가 아니다. Closure는 bundle 내부의
안전한 상대 경로를 받고 위험 schema 2는 모든 group 실행의 receipt/child/native를 보존한다.
registry 분모·순서를 강제하고 모든 조건을 검사하며 절대 경로·탈출·alias·link·hash drift는 거부한다.
새 회귀는 flat/nested 실제 파일 사슬, 독립 실행 두 개, 누락/중복/역순/malformed 행,
첫 미관측 조건 이후 잘못된 raw, 변조·link 거부와 49개 nested closure 참조를 검사한다.
집중 회귀 70개 PASS, verbose ID SHA-256은
`f71177f2bf26de8261b4c80d55979e45fc81f53610f26883b030d1e6ad455589`다.
Host 계약을 61-suite / 526-test로 갱신하고 새 clean exact 검증을 이어간다. W06 완료는 아니다.

추가 개발 Host는 `D:\w06\e2\dev-host-closure`에서 61-suite / 526-test / skip 0, 시험 실패 0이었다.
dirty source이므로 manifest 상태는 FAIL이며 clean exact Host를 대체하지 않는다. Git checkout-index의
`core.autocrlf=true/false` 두 조건에서 provenance 파일 SHA-256이 모두
`0577036b3e9f948df0bb2ef5076e229d485e01cbd7651d85685566ade3e1eef2`로 일치했다.
최종 risk/qualification/closure JSON도 공통 fsync·no-clobber 원자 확정 계층을 사용한다.

### 6.4 마감 commit과 비공개 원본 경계 — 구현 전 고정

`9ba24d06f4b8f96eaf3d84ece1dace4240e5d794`를 commit·push하고 `D:\w06\e3`에서 clean Host
61-suite / 526-test / skip 0, 두 ecosystem 역할 build와 세 보드 read-only halt/복원·radio idle을
확인했다. Actions 37536932027 attempt 1은 plan을 통과했으나 다음 마감 경계의 추가 교정이 필요해
취소를 요청했다. 이 실행의 부분 shard는 새 source의 build PASS로 사용하지 않는다.

마감까지의 전 경로를 다음 조건으로 닫은 뒤에만 다음 exact source를 고정한다.

1. S 바로 다음 단일 기록 commit C라는 경계는 유지한다. C의 명시적 문서 allowlist에는 현행
   v0.6.0 TODO·지원표·SDK 위험·qualification·303 계획도 포함한다. 번호가 바뀐 W06 완료 기록은
   허용하되 옛 302 인계, 완료 TODO, 구현/runner/target/SDK lock 변경은 허용하지 않는다.
2. readiness 단위 시험은 실제 저장 원장이 W06 완료여도 package·세 case·집계 수를 시험용
   in_progress fixture로 함께 초기화한다. 실제 저장 원장을 덮어쓰거나 PASS를 낮추는 기능이 아니다.
3. template 산출물의 `external-test-credential-evidence` 원본은 공개 저장소에 복사하지 않는다.
   실제 closure와 전체 raw bundle은 D에 보존한다. 공개 마감에는 source·closure hash와 전체 파일의
   상대 경로/size/hash 목록만 내보낸다. public index는 actual PASS 자체를 만들지 않는다.
4. C의 readiness 검사는 명시적으로 지정한 외부 bundle에서 index 전체의 실제 byte와 기존 strict
   closure를 모두 재검사한다. 원본 부재·hash/경로/link/분모 drift는 실패이며 metadata-only PASS,
   합성 record, private 원본의 공개 또는 누락을 허용하지 않는다. private bundle 위치는 환경 설정이며
   공개 파일에 credential·원시 UID·원본 byte를 넣지 않는다.
5. public export→원본 대조→S/C Git bridge→readiness 완료/세 PASS를 실제 Git 임시 저장소와
   파일 사슬 회귀로 함께 검사한다. 최종 구현 commit 뒤 새 plan/build/Host/runtime을 실행한다.

이 변경은 W06 마감 전용이다. 임의 ancestor의 PASS 승계나 HOST-W04 이후 착수 허가는 추가하지 않는다.

구현 후 집중 검사는 regression 75개·readiness 31개 PASS다. 공개 index 이동, raw 변조/누락/추가,
directory link, index/source/path/중복 key, 덮어쓰기·출력 경계와 실제 Git S→C를 검사했다.
시험 fixture의 physical oracle은 명시적으로 격리했고 실제 strict validator는 metadata-only
fixture의 export를 거부했다. 독립 readiness invocation에서 발견한 execution import 경로 오류도
교정해 재검증했다. 실제 W06 완료 PASS와는 별개의 개발 회귀이며 Host 계약은 61-suite / 534-test다.

`D:\w06\e3\dev-host-public-closure` 전체 개발 Host는 61-suite / 534-test / skip 0,
시험 실패 및 verbose count/hash 불일치 0이다. 미커밋 source이므로 manifest는 정상적으로 FAIL이며
새 clean exact 실행을 대체하지 않는다. `m33_contract.py --sdk-root C:/ncs/v3.4.0 --check`와
`git diff --check`도 통과했다. e3 Actions의 최종 상태는 cancelled이며 취소된 shard를 재사용하지 않는다.

### 6.5 전체 실행 입력의 사전 검증 — 2026-10-07

`9dbfad7e9bbb22b64e7b0445e3d32b0f09c1fa19`의 Actions 37541296721 attempt 1은 6개 job
SUCCESS이며 `D:\w06\e4`에서 clean Host 61-suite / 534-test, runtime producer, runtime 9개
결합, stage/validate 150개를 통과했다. 이 결과는 해당 source의 준비 증거이며 W06 완료는 아니다.

실기 전 49개 group의 실제 prepare→실행 validator를 모두 검사하자 다음 결함이 드러났다.

1. 현재 board inventory 생성기가 APP/AUX를 누락했다. 실제 USB serial의 hash와 interface
   x.3(APP) / x.1(AUX)를 대조해 별도 inventory를 만들었고 원본을 보존했다. 생성기도 같은 실제
   발견을 수행하고 불완전하거나 중복된 포트는 실기 전에 거부하도록 교정한다.
2. RADIO의 명시적 role probe와 특수 alias probe 생성이 중복됐다. 단일 옵션은 동일 역할에
   한 번만 생성하고 잘못된 중복·값 변경은 validator에서 계속 거부한다.
3. native profile의 초기 watcher와 후속 second_peer가 동일한 물리 보드를 사용하는 계약을
   argv validator가 반영하지 못했다. 두 phase의 hash를 함께 대조하고 역할 누락·중복·변조를 거부한다.

APP/AUX 보완 후 전체 사전 점검은 43 READY / 6 FAIL이었다. RADIO 3개 group과 profile 3개
group에서 위 두 실행 결합 결함이 반복됐으며 matrix 실기는 시작하지 않았다. 실패 입력·trace는
`D:\w06\e4\matrix-preflight-3`에 보존한다. 새 회귀는 48개 고유 campaign의 준비 argv와
board binding, 49개 전체 group의 prepare→validator를 연결해 검사한다. 실제 보드 실행이나
물리 PASS를 생성하는 회귀가 아니다. 모든 교정을 검증한 뒤 한 번에 commit하고 새 clean exact
plan/build/Host/runtime을 만든다. e4의 통과 결과를 변경 source에 승계하지 않는다.

장시간 profile의 상한도 사전 검토했다. 표준은 20회×2 phase, native는 20회×3 phase이며 각
phase는 세 보드의 program/readback을 실제 반복한다. 단일 phase가 분 단위인 현재 환경에서
모든 campaign에 같은 4시간 parent timeout을 적용하면 정상 chain도 중간에 잘릴 위험이 있다.
profile만 기존 runtime fixture의 phase 상한 1,800초를 phase 분모와 합산한다. 이는 예상 실행시간이
아니며 무한 대기가 아니다. 내부 halt/flash/명령/STOP 제한과 20회 분모는 그대로 두고, 다른
campaign의 4시간 상한은 유지한다. 준비 spec과 실행/완료 validator는 campaign별 상한을 함께 검사한다.

개발 검사에서 regression 75개·artifact 43개가 통과했고 전체 Host도 61-suite / 535-test /
skip 0, 개별 시험 실패 0이었다. dirty source manifest는 FAIL로 보존했으며 clean exact PASS가
아니다. 이후 phase 분모별 timeout과 상한 초과 거부를 포함한 48-campaign / 49-group 연결
시험을 다시 통과했다. 실제 새 생성기도 현재 세 보드의 APP/AUX 여섯 COM을 발견했다.
`m33_contract.py --sdk-root C:/ncs/v3.4.0 --check`와 `git diff --check`를 통과했다.
Actions plan에는 shard 이전 source-only 연결 회귀를 추가했다. 보드 결선/실기 PASS는 만들지 않는다.

`03c1b0d17fd0628957f98d99c3978e02f50aa48a`의 Actions 37553278983 attempt 1은 새 사전
검사의 첫 unittest stderr를 Windows PowerShell 5가 `NativeCommandError`로 처리해 실패했다.
시험 assertion 실패가 아니며 4개 shard는 모두 미착수/skipped다. plan이 생성되지 않아 aggregate의
download도 실패했다. 원본 job 로그는 `D:\w06\e5\ci-failure`에 보존한다. 해당 단계만 `pwsh`로
교정하며 Python 종료 코드를 명시적으로 확인하는 실패 gate는 유지한다. e5의 로컬 Host는 개별
535개 시험 실패가 없었지만 workflow 교정 중 source가 dirty가 되어 manifest FAIL이며 승계하지 않는다.
e5의 무거운 ecosystem build/runtime/matrix는 시작하지 않았다.
로컬 PowerShell 7과 NCS Python 3.12에서 같은 CI 명령의 전체 연결 시험 1개(내부 48/49 분모),
inventory 시험 2개를 통과했다. stderr를 숨기지 않고 로그를 보존하며 실제 비영 종료 코드는 실패한다.

`7afd5cefd37762310c37f15862389c4fd53ab352`의 Actions 37553673428 attempt 1은 정상적으로
시험 오류를 기록했으며 영문 Windows의 한국어 runner `--help` 출력 인코딩 문제를 드러냈다.
별도 패키지가 없는 D의 Python 3.12 venv에서 cp1252 출력의 `UnicodeEncodeError`를 재현했고,
UTF-8 환경에서는 48/49 연결 회귀가 통과했다. `_runner_interface`의 자식 환경과 출력 decode를
UTF-8로 명시하고 CI 사전 검사에도 같은 설정을 고정한다. 부모 환경이 cp1252여도 전체 dispatch
탐색이 성공하는 회귀를 추가했다. e6의 shard는 모두 미착수/skipped이며 무거운 로컬 build도
실행하지 않았다. e6 Host 535개 개별 시험 실패는 없지만 수정 중 dirty manifest FAIL로 보존한다.
교정 후 외부 패키지 없는 Python 3.12에서 regression 75개와 inventory 2개가 통과했고
readiness `--check`·`git diff --check`도 통과했다. 다음 exact source에서는 CI 사전 검사 성공을
확인한 뒤 build/runtime을 이어간다.

### 6.6 Twister 구성별 cache와 실패 원본 보존 — 구현 전 고정

`823c82025c588aaba447d08965b0770ddb4999a5`의 Actions 37554100228 attempt 1은 source-only
사전 검사를 통과했다. 로컬 `D:\w06\e7`의 clean Host 61-suite / 535-test / skip 0과
두 ecosystem role build도 PASS다. 다만 shard 1의 `twister-v0.5.0-122cb9f02024`에서
15개 중 `nucode.m30.pair.kdf.c`의 CMake configure가 실패했다. 나머지 14개는 build-only
통과했으며 action 전체는 FAIL이다. action에 포함된 M29 CoC의 기능 실패로 해석하지 않는다.

고정 SDK `zephyr/cmake/modules/extensions.cmake:1179`의 toolchain capability cache
`file(READ)`가 `Permission denied`를 반환했다. 원시 stdout/stderr와 job log를
`D:\w06\artifacts\e7` 및 `D:\w06\e7\ci-failure`에 보존했다. 기존 runner는 성공한
Twister scratch만 artifact root로 옮겨 실패한 구성의 build.log와 전체 오류 경로가 유실됐다.
어떤 프로세스가 파일을 점유했는지는 확인하지 못했으며, SDK 기능 위험이나 특정 백신을
원인으로 단정하지 않는다.

수정 범위는 다음과 같다.

1. 고정 SDK의 `zephyr_default.cmake` 및
   [공식 Zephyr CMake package 계약](https://docs.zephyrproject.org/latest/build/zephyr_cmake_package.html)을
   대조한 `ZephyrAppConfiguration_ROOT` hook으로 각 `APPLICATION_BINARY_DIR` 안에
   USER_CACHE_DIR / ToolchainCapabilityDatabase를 격리한다. 4 shard와 Twister jobs 2는 유지한다.
   공유 캐시 동시 접근은 제거하지만 관측되지 않은 원래 점유자를 확정하는 수정은 아니다.
2. Twister `--inline-logs`를 켜고, 정상 종료한 비영 exit의 scratch도 기존 link/탈출 검사를
   통과한 경우에만 artifact root로 옮긴다. 실패 상태는 그대로 유지한다. timeout/launch failure나
   안전하지 않은 link tree는 이동하지 않으며 합성 성공 record를 만들지 않는다.
3. 성공/비영 종료/timeout/외부 link 보존 회귀와 실제 고정 SDK의 두 구성 configure/build로
   cache 분리를 검사한 뒤 commit·push한다. 변경 source의 clean exact 실행은 새로 만들며
   e7의 Host/build PASS를 승계하거나 다른 run/attempt shard를 섞지 않는다.

확장한 build runner 회귀는 기존 두 누락도 발견했다. canonical Twister 목록에 M33 ecosystem의
client/peer 두 testcase가 없었고 Arduino v0.6.0 기대 목록에는 기존 m33_beacon이 없었다.
원본 testcase·runner와 대조해 목록을 맞췄으며 분모를 줄이거나 testcase를 제외하지 않았다.
이 11-test suite를 최종 Host에 포함해 새 계약은 62-suite / 546-test다. build runner 11개와
artifact 43개, regression 75개 집중 검사를 통과했다.

D source/C SDK의 로컬 Twister 사전 시도는 고정 SDK `twisterlib/testsuite.py`의
`os.path.relpath(realpath(suite_path), start=canonical_zephyr_base)`에서 두 drive를 처리하지
못해 configure 이전에 실패했다. cwd 교체만으로 해결할 수 없는 SDK 경계다. 원본
`D:\w06\e7\cache-configure.log`를 보존하고 SDK나 record를 고치지 않는다. exact Twister는
기존대로 D source/D SDK인 GitHub Actions에서 수행하며 로컬 수정 진단은 같은 M30 KDF
peripheral/central의 실제 west build 두 개를 직렬 실행한다. 이 개발 진단은 새 clean exact
Actions·Host·runtime을 대체하지 않는다.

실패한 upstream의 aggregate가 SDK cache 복원까지 수행한 뒤에야 중단되는 낭비도 확인했다.
aggregate의 첫 단계에서 plan/build 상태를 검사해 실패하면 checkout/download/setup 이전에
즉시 FAIL한다. 기존 150-slot 결합 직전의 검사는 방어적으로 유지하며 성공 gate를 완화하지 않는다.
Twister의 격리 Python에는 `-B`도 명시해 `-I`가 환경 변수의 bytecode 금지 설정을 무시해도
SDK 안에 새 pyc를 만들지 않도록 한다. 확인한 로컬 Twister pyc는 2026-10-04의 기존 파일이며
이번 진단에서 새로 생성됐다고 간주하거나 설치본에서 삭제하지 않았다.

구현 후 M30 KDF peripheral/central의 실제 직렬 west build 2/2가 통과했다. 각 구성의
81개 compiler capability 결과가 서로 다른 `D:\w06\e7\cache-build\<role>\.cache`에
생성됐음을 CMakeCache와 실제 파일로 확인했다. 원본 log·HEX hash·audit.json을 그 root에
보존한다. 미커밋 개발 build이므로 clean exact나 physical PASS로 승격하지 않는다. CMake hook의
누락/상대 binary path 두 입력도 실제 CMake에서 거부했고, 최종 집중 검사 11+43+75개와
readiness `--check`·`git diff --check`를 통과했다. 수정 source의 clean exact를 다음으로 고정한다.

### 6.7 Profile 전체 phase의 실제 파일 경로 연결 — 구현 전 고정

`33677a38d4fa88aa764b66a355d40162b9496f0f`를 commit·push하고 e8에서 clean Host
62-suite / 546-test / skip 0 및 세 보드 read-only halt/복원을 통과했다. Actions 37559619514
attempt 1도 사전 검사를 통과했다. 실기 예상시간을 점검하면서 다음 실행 결함을 추가 발견했다.
`campaign.cycle-01.fresh`와 `campaign.cycle-01.restored`에 `Path.with_suffix('.json')`를
적용하면 둘 다 `campaign.cycle-01.json`이 된다. 실제 phase runner는 기존 결과 덮어쓰기를
거부하므로 두 번째 phase에서 중단된다. validator용 fixture는 별도 hyphen 이름으로 만들어
이 실제 실행 결합을 검사하지 않았으며, 기존 3개 profile campaign Host가 놓친 이유다.

Actions는 shard SDK 준비 단계에서 취소했고 target build·HIL을 진행하지 않았다. 로컬 e8의
진행 중인 client CMake 하위 프로세스만 ancestry/command를 확인해 종료했다. 정상 wrapper가
남긴 failure.json·command/build log를 보존하며 peer build는 시작하지 않았다. 이 의도적인
중단을 SDK·firmware 결함으로 기록하지 않는다. e8 Host는 해당 source의 실제 PASS로 보존한다.

교정은 suffix를 교체해도 phase가 보존되는 명시 prefix, 실행 전 40/60개 전체 경로의 중복·기존
파일 검사, 실제 `execute_campaign`→40/60 phase→최종 validator를 연결하는 파일 기반 Host다.
점이 포함된 출력 이름, 뒤쪽 phase의 기존 JSON/transcript/sidecar, clean source drift도 검사한다.
단위 시험의 물리 backend만 fixture로 격리하며 physical PASS를 만들거나 20회 분모를 줄이지 않는다.
이 검사를 CI의 source-only 단계에도 넣어 다음 큰 build 이전에 실행한다.

추가 회귀를 먼저 실행해 standard/native 모두 cycle 1의 두 번째 phase 경로 충돌을 재현했다.
교정 후 별도 패키지가 없는 Python 3.12에서 4개 profile campaign 시험이 통과했다. 실제
실행기를 통과하는 40/60개 고유 JSON과 predecessor·마지막 validator, 각 family에서 source가
바뀐 후 40/60개 raw 보존과 aggregate 생성 거부, 마지막 phase의 JSON/transcript/image/build/
readback 및 기존 aggregate 파일을 덮어쓰지 않는 사전 중단을 포함한다. 물리 backend는 명시
fixture이므로 보드 PASS가 아니다. 새 Host 계약은 62-suite / 547-test다. e8 Actions의 최종
cancelled도 조회했고 취소된 build를 재사용하지 않는다.
후속 집중 검사 regression 75개·artifact 43개, readiness `--check`와 diff whitespace 검사도
통과했다. 등록된 campaign의 공통 output basename과 다른 M33 내부 prefix 경로도 검토했으며
동일한 suffix 교체 충돌은 profile의 위 세 phase 생성 지점에서 확인했다.

`39af839f9d520c724163e38f5a76a90d514ba2cd`의 e9 clean Host는 62/547 PASS다. Actions
37560940418은 새 파일 연결 시험의 Windows 8.3 경로 alias 비교에서 실패했다. 실제 파일은
같지만 fixture의 `RUNNER~1`과 실행기가 resolve한 `runneradmin` 경로를 문자열로 비교했다.
원본 job log는 `D:\w06\e9\ci-failure`에 보존한다. fixture root를 먼저 resolve하며 실제
file/hash/no-clobber 검사는 유지한다. plan의 실패로 shard는 skipped, aggregate는 조기 FAIL이고
로컬도 CI hold를 확인해 ecosystem build 전에 중단했다. 새 무거운 build/HIL 낭비는 없었다.

동시에 cache 격리의 sysbuild 전파도 고정 SDK source로 점검했다. 하위 image는
`SYSBUILD_CACHE`를 `basic_settings.cmake`에서 target property로 읽지만 application package
hook은 그보다 먼저 실행된다. command-line root뿐 아니라 공식 package-root 환경 변수로도
같은 경로를 전달해 모든 하위 CMake가 자기 APPLICATION_BINARY_DIR의 cache를 쓰게 한다.
SDK source는 수정하지 않으며 실제 MCUboot/app sysbuild configure에서 두 cache를 확인한다.

실제 고정 SDK의 `m30_mcuboot_hil` sysbuild configure가 통과했고 app/MCUboot 두 cache의
분리와 각 compiler capability 원본을 `D:\w06\e9\sysbuild-cache-audit.json`에 기록했다.
이는 CONFIGURE 진단이며 image build·physical PASS가 아니다. 비정규 parent 경로를 의도적으로
사용하는 profile 4개 회귀가 독립 Python 3.12에서 통과했고, build runner 11개·readiness
`--check`·diff 검사도 통과했다. 62/547 Host 분모와 test ID hash는 바뀌지 않는다.

### 6.8 서로 다른 Bluetooth 구성 사이의 orphan GATT 상태 — 구현 전 고정

`846f29935712e2d175402b932215a305695a4d26`의 Actions 37561785302 attempt 1은 6개 job
SUCCESS다. e10의 6 ZIP digest, 별도 4 shard 재집계 141 build, clean Host 62/547,
runtime producer·9 slot, stage/validate 150, 49 group 사전 검사를 통과했다. 실제 matrix는
11 group PASS 뒤 12번째 `signed_write`의 첫 sign session에서 중단했다. CoC는 PASS이며
peripheral `unexpected_disconnect` 19를 보존한다. W06 완료나 새 source의 PASS가 아니다.

`D:\w06\e10\signed-write-diagnosis`의 exact ELF 기반 read-only RAM 검사에서 양쪽 CSRK
hash가 일치하고 central local / peripheral remote counter가 1이었다. Peripheral attribute는
초기값 그대로이며 application write 수는 0, 같은 peer의 Client Supported Features는 robust
caching=1 / change-aware=0이었다. 고정 SDK의 `smp.c:bt_smp_sign_verify`와
`att.c:att_signed_write_cmd/att_write_rsp`, `gatt.c:bt_gatt_change_aware`에 따라 서명 검증 후
change-unaware command가 attribute handler 전에 폐기되는 경로와 일치한다. 단순 TX 지연이나
CSRK 불일치로 진단하지 않는다. 세 RADIO STATE는 Disabled였지만 SHORTS는 남아 있으므로
이 read-only 관측을 STOP·clock 해제 PASS로 승격하지 않는다.

고정 SDK `keys.c:keys_set`은 signing 등의 Kconfig에 따라 저장 key 크기·flags가 달라지면
native key만 폐기한다. `bt_keys_clear`는 CF를 지우지 않고 `bt_unpair(ANY)`는 현재 native
bond만 열거한다. 이전 GATT-cache image와 signing image의 구성이 다르며, 실패 raw의 최초
bond_count=0인데 CF가 남은 상태는 이 경계와 부합한다. 이전 boot의 branch를 추측만으로
실측했다고 적지 않으며, orphan 상태를 주입한 재현과 정상 삭제 대조로 수정 효과를 검증한다.

수정 범위는 `eraseAllBonds()`가 기본 identity의 orphan CF/CCC/SC peer도 bounded snapshot으로
수집한 뒤 정상 `bt_unpair(peer)`에 전달하도록 하는 것이다. SDK 저장 key 형식은 고정 source와
대조하고 잘못된 형식·수용량 초과·열거 실패는 삭제 시작 전에 거부한다. 다른 local identity,
application settings, SDK 자체는 변경하지 않는다. Mass erase, 캐시 기능 끄기, RAM awareness
강제, 대기시간 증가로 우회하지 않는다. 삭제 요청과 실제 영속 삭제 완료의 공개 구분도 유지한다.

Production 함수를 실행하는 Host 회귀로 orphan·중복·다른 identity·오류·overflow를 검사하고,
실제 두 role의 focused build/HIL에서 CF만 남은 시작 상태 및 20회 counter/replay/EATT를 확인한다.
실패 종료의 안전 정리 경로도 함께 점검한다. 관련 교정을 묶어 commit·push한 후 새 exact
plan/build/Host/runtime/matrix를 만들며 e10의 11 PASS는 원래 source의 역사로 보존한다.

실제 구성 전환 진단에서 signing image의 native key=0 / CF robust=1을 관측했고, 수정된
공개 삭제 API 뒤 및 다음 reboot 뒤 모두 key=0 / CF=0이었다. 수정 중인 두 image의
20회 signing reboot·21 signed write·replay 거부·EATT 2 bearer 각 1,000 operation이 통과했다.
`focused-signing-only/diagnostic.json`은 `source_clean=false`, `completion_eligible=false`이며
기존 846f299 또는 최종 source의 완료 증거로 승격하지 않는다. 마지막 3보드 software-reset/halt
격리를 확인했다. 원래 실패 firmware의 정상 STOP 성공으로 소급하지 않는다.

### 6.9 내부 reboot와 UART evidence 경계 — 구현 전 고정

앞선 cache seed 진단은 target의 정량 END 출력에도 불구하고 중앙 corruption reboot 직후
`0xff`가 REBOOT 앞에 붙어 strict parser에서 FAIL했다. 원본
`signed-write-diagnosis/focused-hil/cache-seed.central.log` 및 FAIL을 유지한다.
seed를 cache PASS로 바꾸지 않았고, 후속 signing 진단은 실제 RAM precondition을 독립 검사했다.

Cache 전용 시험 image는 영속 resume 복원 뒤 RF 재개를 보류하고 Host의 `RESUME?` / exact
nonce·core `RESUME` 교환을 기다리도록 한다. Host는 사전에 검증된 해당 role의 내부 reboot
record 뒤에서만 bounded UART reset framing(0x00/0xff, 최대 32 byte)을 허용하며 원시 bytes를
transcript에 그대로 남긴다. `RESUME_READY`는 실제 target 응답이고 재개 뒤 기존 정량 record는
동일하다. 일반 실행 구간 noise·잘못된 identity·중복 reboot·ASCII 오류·한도 초과는 실패한다.
초기화 실패 출력이나 missing handshake를 지우거나 합성 PASS로 대체하지 않는다.

Parser와 실제 collector의 경계·timeout·wrong nonce·일반 구간 binary 거부를 Host에서 검사하고
새 두 role focused build/HIL로 확인한 다음 §6.8 수정과 묶어 새 exact source를 만든다.

수정된 cache 두 role의 실제 west build와 실기 모두 통과했다. 20 reconnect·24 hash read·
20 cache restore·2 invalidation·1 corruption rejection·stale 0 및 양 role의 실제
`RESUME_READY`를 strict parser로 확인했다. 원시 transcript는
`D:\w06\e10\cache-boundary-diagnosis\focused-hil`에 보존한다. 종료 후 3보드의
software-reset/halt 격리도 확인했으며 이 진단 역시 dirty / completion-ineligible이다.
이번 성공 실기의 두 raw에는 비 ASCII byte가 없었다. Bounded 0xff/0x00 보존과 잘못된
구간 거부는 Host에서 주입해 검사한 결과이며, 실물 noise 주입 성공으로 표시하지 않는다.

Security Host는 원래 production C++에서 새 5개 subscenario가 실패하는 대조를 확인한 뒤
수정본에서 통과했다. 최종 canonical key 검사에는 `/0`·`/01`·범위 밖 identity·잘못된 주소의
삭제 전 거부를 추가했다. 고정 SDK가 쓰지 않는 alias를 mock만 삭제하는 우회는 허용하지 않는다.
독립 Python 3.12의 cache 회귀 26개, W06 연결 회귀 75개, artifact 회귀 43개,
readiness `--check`와 diff 검사가 통과했다. Cache parser 16개를 필수 Host에 연결해 현재
계약은 **63-suite / 564-test**이며, 새 clean exact 전체 Host의 결과는 별도로 생성한다.
