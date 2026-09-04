# M27 v0.4.0-rc.1 비공개 릴리스 준비

M27 도구는 `v0.4.0-rc.1` package를 두 번 독립 생성해 ZIP·checksum·SBOM·license inventory와
notices가 byte-identical인지 검증하고 RC index와 HOLD plan을 만든다. 기존 M11/M18/M22 도구와
공개 `v0.1.0`~`v0.3.0` package allowlist는 수정하지 않는다.

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

## 비공개 후보 package 29개 예제 검증

공개 Boards Manager 설치 전에는 생성된 ZIP을 격리 Arduino data 디렉터리에 직접 staging하고,
그 설치본에서 발견한 예제 29개를 전부 compile한다. 이 단계는 기존 Arduino15와 공개 index를
수정하지 않으며 upload도 수행하지 않는다.

```powershell
python tools/release/m27_staged_candidate.py `
  --archive C:\nu54-m27-rc1\artifacts\nucode-nu54dk-zephyr-0.4.0-rc.1.zip `
  --workspace C:\nu54-m27-stage `
  --arduino-cli "C:\Program Files\Arduino CLI\arduino-cli.exe" `
  --ncs-root C:\Users\eidos\ncs\v3.4.0 `
  --toolchain-root C:\Users\eidos\ncs\toolchains\dcbdc366a1 `
  --prerequisite-state-root "$env:LOCALAPPDATA\NUCODE\NU54DK_Arduino_Core\prerequisites"
```

성공 표식은 `M27_STAGED_CANDIDATE_PASS=29`이며 workspace 안에 package별 build와
`m27-package-examples.json`, `m27-staged-candidate.json` 증적을 남긴다.

Physical evidence를 확보한 뒤에는
`variants/nu54dk/v0.4.0-release-readiness.json`의 각 gate를 exact evidence와 함께 갱신하고,
frozen RC commit에서 host·docs·전체 v0.4.0 Zephyr·package·Boards Manager gate를 다시 실행한다.
Stable 공개 자동화는 모든 gate가 PASS가 된 별도 변경에서 추가한다.
