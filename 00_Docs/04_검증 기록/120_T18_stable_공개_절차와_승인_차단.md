# T18 stable 공개 절차와 승인 차단

> 이 기록의 지원 상태·후보·다음 단계는 작성 당시 기준입니다. 이후 QDEC20/21 지원 범위와
> 영향 재검증은 [124번](124_T22전_QDEC_지원_범위_재확정.md), 최종 승인·공개·T24/T25 완료는
> [125번](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)에 있습니다. 당시 판정과 artifact identity는 그대로 보존합니다.

## 결론

**T18 공개 절차 준비는 완료했습니다. 실제 tag·GitHub Release·stable index 공개는 실행하지
않았고 T22 프로젝트 소유자 승인 전 HOLD입니다.**

`m27_stable_release.py`는 RC→stable 준비와 공개를 다음 다섯 명령으로 분리합니다.

| 명령 | 상태 변경 | 필수 입력과 역할 |
| --- | --- | --- |
| `prepare` | 로컬 새 출력 경로만 생성 | exact clean commit, 모든 기술 gate, 같은 commit의 RC plan |
| `validate-plan` | 없음 | stable plan·RC·readiness·artifact byte 재검증 |
| `publication-dry-run` | 없음 | exact T22 승인과 원격 main·tag·Release 부재 검사 |
| `publish-release` | GitHub tag·Release·asset 생성 | dry-run 전체 통과 뒤에만 실행 |
| `publish-index` | stable root index commit·push | 공개 asset 재다운로드·byte 대조 뒤 별도 실행 |

## 구현한 차단 조건

- 과거 `0.1.0`~`0.3.0` stable allowlist에는 `0.4.0`을 영구 추가하지 않습니다. 패키저는 exact
  commit을 입력받은 현재 프로세스에서만 미공개 stable 후보를 구성합니다.
- 잘못된 stable 형식, 이미 등록된 version, 40자리 소문자 SHA-1이 아닌 commit을 거부합니다.
- M27 readiness의 비인간 technical gate 15개가 모두 `passed`가 아니면 stable `prepare`를
  시작하지 않습니다.
- 같은 exact commit의 `0.4.0-rc.1` plan을 다시 검증하고 stable의 정규화 runtime payload
  SHA-256이 RC와 다르면 중단합니다.
- stable package 2회의 ZIP·checksum·SBOM·license inventory·manifest·notices가 byte-identical인지
  확인합니다.
- 현재 stable index의 byte identity를 plan에 묶고, 기존 platform record는 보존하면서 `0.4.0`
  record 하나만 추가한 다음 index schema를 다시 검증합니다.
- T22 승인 JSON은 stable plan SHA-256·version·target commit·프로젝트 소유자 역할을 모두 exact로
  지정해야 합니다. 승인 파일이 없거나 다르면 외부 명령을 한 번도 호출하지 않습니다.
- 기존 원격 tag 또는 Release가 있으면 새 Release를 만들지 않습니다. stable index 게시 전에는
  공개 asset 전체를 새 임시 경로에 다시 받아 size·SHA-256·byte를 로컬 plan과 대조합니다.
- Release와 index 게시를 분리해 공개 asset을 덮어쓰지 않습니다. index는 검증된 Release 뒤에만
  별도 commit으로 갱신합니다.

## 자동 검증

다음 T18 관련 단위·계약 검사는 PASS했습니다.

```text
python -B -m unittest tests.host.test_m27_stable_release tests.host.test_m27_release tests.host.test_r13_package_modules -v
Ran 23 tests
OK (skipped=1)

python -B tools/release/m27_stable_release.py contract
M27_STABLE_CONTRACT_PASS=1;PUBLICATION_ALLOWED=0
```

skip 1건은 변경 중 worktree가 의도적으로 dirty여서 기존 M27 clean-check 성공 경로만 생략한
조건부 검사입니다. 잘못된 version/commit, technical gate 누락, 승인 hash 불일치, 승인 전 외부
명령 미호출, 기존 tag 차단과 Release/index 분리를 별도 unit으로 확인했습니다.

전체 회귀 결과도 모두 PASS했습니다.

```text
python -B tools/ci/run_m12_gate.py host
M12_GATE_PASS=host

python -B tools/ci/run_m12_gate.py contract
M12_GATE_PASS=contract            # 46 tests

python -B tools/ci/run_m12_gate.py inventory
M23_INVENTORY_PASS=instances:75
M24_SERIAL_CONTRACT_PASS=blocks:5;identities:23;profiles:23;onboard:7;fixture:16
M26_SYSTEM_CONTRACT_PASS=capabilities:16;unknown:0
M12_GATE_PASS=inventory

python -B tools/ci/run_m12_gate.py docs
Markdown UTF-8/local-link PASS: 240 files
M12_GATE_PASS=docs

python -B tools/ci/run_m12_gate.py package
Ran 21 tests
OK
M12_GATE_PASS=package

python -B tools/format/run_cpp_style.py --clang-format <LLVM clang-format 22.1.8>
CPP_STYLE_FILES=423; FAILED=0; WRITE=0

git diff --check
PASS
```

Host의 환경 의존적 설치본 발견과 변경 중 dirty worktree 검사는 조건부 skip될 수 있지만, T18
승인 차단 unit과 나머지 회귀에는 실패가 없습니다. R14/T19에서는 커밋·푸시 뒤 clean exact
source에서 release gate를 다시 실행합니다.

## 물리 작업과 공개 상태

- 새 결선 검사·flash·보드 신호 구동: 없음
- tag 생성·GitHub Release 생성·stable root index 변경: 없음
- 현재 공개 stable: `v0.3.0`
- 다음 단계: R14/T19 exact RC 고정과 전체 software 회귀
- 자동 진행 경계: T21까지 기술 작업을 계속하며, T22 승인과 T23 공개는 사용자 응답 없이 실행하지 않음
