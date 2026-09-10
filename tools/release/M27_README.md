# M27 v0.4.0-rc.1 비공개 릴리스 준비

현재 개발 상태·검증 범위·다음 작업은 [v0.4.0 TODO](<../../00_Docs/TODO_v0.4.0.md>)에서 관리합니다.

M27 도구는 `v0.4.0-rc.1` package를 두 번 독립 생성해 ZIP·checksum·SBOM·license inventory와
notices가 byte-identical인지 검증하고 RC index와 HOLD plan을 만든다. 기존 M11/M18/M22 도구와
공개 `v0.1.0`~`v0.3.0` package allowlist는 수정하지 않는다.

아래 RC 명령은 비공개 후보를 준비합니다. T18에서 추가한 stable 도구로 T21 비공개 stable
산출물과 최종 검사를 완료했습니다. T22 승인은 아직 없으므로 T23 공개 권한을 뜻하지 않습니다.

이 도구에는 tag, push, GitHub Release, stable index 갱신이나 공개 명령이 없다. M24~M26 physical
gate, Boards Manager 전체 수명주기와 프로젝트 소유자 승인이 모두 PASS가 되기 전에는 plan의
`publication_allowed`가 항상 `false`다.

## 계약 확인

```powershell
python tools/release/m27_release.py contract
```

## Exact clean commit에서 후보 산출물 준비

출력 디렉터리는 비어 있어야 하며 저장소 밖의 새 경로를 권장한다.

```powershell
python tools/release/m27_release.py prepare `
  --repository C:\Users\eidos\GitHub\NU54DK_Arduino_Core `
  --output-dir C:\nu54-m27-rc1 `
  --commit HEAD
```

성공해도 결과는 `M27_RELEASE_PREPARE_HOLD=1`이다. 생성되는
`m27-release-plan.json`은 두 package build의 재현성과 남은 blocker를 기록한다.

## 기존 plan 재검증

```powershell
python tools/release/m27_release.py validate-plan `
  --plan C:\nu54-m27-rc1\m27-release-plan.json
```

## 현행 비공개 후보의 예제 검증

공개 Boards Manager 설치 전에는 생성된 ZIP을 격리 Arduino data 디렉터리에 직접 staging하고,
현재 lock에 고정된 예제 30개와 설치본의 발견 목록을 대조해 전부 compile한다. 이 단계는 기존
Arduino15와 공개 index를 수정하지 않으며 upload도 수행하지 않는다.

```powershell
python tools/release/m27_staged_candidate.py `
  --archive C:\nu54-m27-rc1\artifacts\nucode-nu54dk-zephyr-0.4.0-rc.1.zip `
  --workspace C:\nu54-m27-stage `
  --arduino-cli "C:\Program Files\Arduino CLI\arduino-cli.exe" `
  --ncs-root C:\Users\eidos\ncs\v3.4.0 `
  --toolchain-root C:\Users\eidos\ncs\toolchains\dcbdc366a1 `
  --prerequisite-state-root "$env:LOCALAPPDATA\NUCODE\NU54DK_Arduino_Core\prerequisites" `
  --workers 4
```

성공 표식은 `M27_STAGED_CANDIDATE_PASS=30`이며 workspace 안에 package별 build와
`m27-package-examples.json`, `m27-staged-candidate.json` 증적을 남긴다. 기본 4개 worker는 서로
분리된 build 경로를 사용하고 결과를 lock 순서로 다시 정렬한다.

30개는 T16 Peripheral Fabric 예제를 포함한 현행 후보 예제 집합이다. T20/T21에서 최종 설치본의
전체 예제를 다시 검증한다. 이 staging compile은 실제 Upload나
Boards Manager 설치·제거·재설치·버전 전환을 대신하지 않는다.

Physical evidence를 확보한 뒤에는
`variants/nu54dk/v0.4.0-release-readiness.json`의 각 gate를 exact evidence와 함께 갱신하고,
frozen RC commit에서 host·docs·전체 v0.4.0 Zephyr·package·Boards Manager gate를 다시 실행한다.
Stable 공개 절차의 준비·검사는 T18의 `m27_stable_release.py`로 분리했다. 준비 코드를 만들었다고
공개를 허용하지 않으며, 실제 tag·Release·index 쓰기는 모든 technical gate와 최종 사용자 승인을
확인한 T23에서만 수행한다.

## T18 stable 준비·공개 차단 계약

T18 도구 계약은 과거 stable allowlist에 `0.4.0`을 영구 추가하지 않고 확인할 수 있습니다.

```powershell
python tools/release/m27_stable_release.py contract
```

T19~T20 결과로 모든 기술 gate가 PASS한 뒤, exact RC plan과 같은 commit에서 T21의 비공개
stable package를 두 번 생성합니다. `00_Docs/05_릴리스/v0.4.0/`의 최종 사용자 문서도 같은
commit에서 읽습니다.

```powershell
python tools/release/m27_stable_release.py prepare `
  --repository C:\Users\eidos\GitHub\NU54DK_Arduino_Core `
  --output-dir C:\nu54-m27-stable `
  --commit <40자리-exact-commit> `
  --rc-plan C:\nu54-m27-rc1\m27-release-plan.json
```

성공 결과도 `M27_STABLE_PREPARE_HOLD=1`이며 다음을 모두 검사합니다.

- 잘못된 stable/RC version과 서로 다른 exact commit 거부
- 모든 비인간 technical gate의 PASS evidence 확인
- stable과 RC의 정규화 runtime payload SHA-256 일치
- ZIP·checksum·SBOM·license inventory·manifest·notices의 독립 2회 byte 재현
- 현재 stable index에 `0.4.0`이 없고 기존 record를 바꾸지 않은 새 index 생성
- 비어 있지 않은 출력 경로와 artifact 경로 이탈 거부

`publication-dry-run`, `publish-release`, `publish-index`는 모두 exact stable plan의 SHA-256과
commit을 지정한 T22 승인 JSON을 필수로 받습니다. 승인 파일이 없거나 한 technical gate라도
미완료이면 외부 명령에 도달하지 않습니다. `publication-dry-run`은 원격 `main`, tag와 Release
부재만 읽고 쓰지 않습니다. 실제 공개는 Release asset과 stable root index를 별도 명령으로
나눕니다. Release asset은 기존 tag/Release가 있으면 생성하지 않고, index는 공개 asset을 다시
다운로드해 size·SHA-256·byte를 대조한 뒤에만 별도 commit으로 push합니다.

T18에서는 위 실제 게시 명령을 실행하지 않습니다. T22의 명시적 소유자 승인 전에는 승인 JSON을
만들거나 두 게시 명령을 호출해서도 안 됩니다.

## T21 설치 stable 예제 검증

Stable archive를 격리 Boards Manager 환경에 설치한 뒤 아래 실행기로 설치본의 발견 목록과 M27
lock을 대조하고 예제 30개를 clean compile합니다. `--platform-root`는 개발 저장소가 아니라 실제
설치된 `0.4.0` 경로여야 합니다.

```powershell
python tools/release/run_m27_package_examples.py `
  --arduino-cli "C:\Program Files\Arduino CLI\arduino-cli.exe" `
  --package-version 0.4.0 `
  --config C:\nu54-m27-installed\arduino-cli.yaml `
  --platform-root C:\nu54-m27-installed\data\packages\nucode\hardware\zephyr\0.4.0 `
  --build-root C:\nu54-m27-installed\stable-examples `
  --ncs-root C:\ncs\v3.4.0 `
  --toolchain-root C:\ncs\toolchains\dcbdc366a1 `
  --cache-root C:\nu54-m27-installed\local\NU54\c `
  --forbid-root C:\source\NU54DK_Arduino_Core `
  --evidence C:\nu54-m27-installed\m27-stable-package-examples.json `
  --workers 4
```

성공 표식은 `M27_PACKAGE_EXAMPLES_PASS=30`, evidence type은
`installed-stable-package-examples`입니다. 이 compile은 실제 Upload를 대신하지 않으므로 T21에서는
설치본 Blink도 별도로 Upload했습니다. 결과는 [123번 기록](<../../00_Docs/04_검증 기록/123_T21_stable_패키지와_최종_검사.md>)에 있습니다.
