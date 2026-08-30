# M18 v0.2.0-rc.2 Draft Release 자동화

이 도구는 exact clean commit에서 `0.2.0-rc.2` package와 RC index를 두 번 독립 생성해
byte 재현성을 확인하고, GitHub의 **Draft + prerelease metadata**를 가진 내부 Release object와
asset까지만 만든다. Draft의 `tagName`은 예약할 RC 이름이지만 실제 Git tag ref는 만들지 않아
untagged 내부 상태일 수 있다. 최종 상태는 항상 `awaiting-clean-windows-manual-validation`이다.
public RC 또는 stable 공개 명령은 의도적으로 제공하지 않는다.

## 1. 준비

구현과 릴리스 문서를 모두 commit·push하고 Core와 board submodule이 깨끗한 상태인지 확인한다.
릴리스 문서는 다음 네 경로가 기본값이다.

- `00_Docs/05_릴리스/v0.2.0/RELEASE_NOTES.md`
- `00_Docs/05_릴리스/v0.2.0/KNOWN_ISSUES.md`
- `00_Docs/05_릴리스/v0.2.0/MIGRATION.md`
- `00_Docs/05_릴리스/v0.2.0/TROUBLESHOOTING.md`

```powershell
$Commit = git rev-parse HEAD

python tools/release/m18_release.py prepare `
  --repo-root . `
  --output-dir build/m18/0.2.0-rc.2 `
  --commit $Commit
```

prepare는 같은 commit에서 archive, package metadata와 RC index를 두 번 생성하고 모든
artifact byte와 SHA-256을 비교한다. root stable index, `STABLE_VERSIONS`와 stable commit map을
변경하거나 asset 목록에 포함하면 실패한다. 기존 output을 덮어쓰지 않으므로 새 directory를
사용해야 한다.

네 문서 경로는 command line으로 바꿀 수 없다. repository URL, NCS/Zephyr/toolchain pin,
`0.1.0-rc.2` + `0.2.0-rc.1` + `0.2.0-rc.2` RC allowlist, RC/stable index 이름과 release asset 이름도
고정 계약이다. 공개 v0.1 stable root index는 1,125 byte 및 고정 SHA-256으로 보호한다.

## 2. 로컬 재검증

```powershell
python tools/release/m18_release.py validate `
  --plan build/m18/0.2.0-rc.2/m18-draft-plan.json
```

archive/index strict validator, exact Core·board revision, clean worktree, 문서와 SBOM·license·notice,
checksum, evidence manifest 및 exact asset allowlist를 다시 확인한다. 또한 exact commit에서 package
asset을 한 번 더 재빌드해 local plan의 byte와 비교하며, 예상 밖 file/directory/symlink를 모두
거부한다.

## 3. Untagged Draft Release object 생성

`gh auth status`가 성공하고 exact commit이 원격 저장소에 push된 뒤 명시적으로 실행한다.

```powershell
python tools/release/m18_release.py publish-draft `
  --plan build/m18/0.2.0-rc.2/m18-draft-plan.json
```

동일 local/remote tag 또는 Release가 있으면 실패한다. 도구는 `--force`나 `--clobber`를 사용하지
않는다. 생성 뒤 GitHub가 반환한 remote Draft ID, exact target commit, draft/prerelease metadata와
asset 이름·크기를 재조회하고 모든 asset을 임시 directory에 다시 내려받아 SHA-256을 검증한다.
이 단계는 실제 Git tag를 만들지 않으며 Draft를 public Prerelease로 전환하지 않는다.

이 단계 이후 clean Windows 사전 검증은 exact ZIP을 격리된 Arduino Sketchbook의
`hardware/nucode/zephyr` staging에 추출해 IDE 예제 열거, compile과 NU54DK upload를 확인한다.
이는 Boards Manager 설치나 `post_install` end-to-end PASS가 아니다. 프로젝트 소유자가 staged
결과를 승인해 Draft를 public RC로 전환한 뒤, 공개 RC index로 clean Windows Boards Manager
설치·`post_install` end-to-end를 별도로 검증한다. 그 결과를 다시 승인하기 전에는 stable을
공개하지 않는다.

## 4. Draft 재검증과 부분 생성 복구

`publish-draft`가 network 중단 뒤 실패했다면 곧바로 다시 생성하지 않는다. 다음 read-only 명령으로
기존 remote Draft ID, exact target commit, draft/prerelease metadata, asset allowlist와 재다운로드
SHA-256을 먼저 확인한다.

```powershell
python tools/release/m18_release.py verify-draft `
  --plan build/m18/0.2.0-rc.2/m18-draft-plan.json
```

검증이 통과하면 생성은 끝난 것이다. Draft가 일부 asset만 가진 경우 도구는 fail-closed로 중단하며
원격을 수정하지 않는다. GitHub UI에서 Draft ID와 exact target commit을 확인한 뒤 프로젝트 소유자가
부분 Draft object만 정리하고 `publish-draft`를 처음부터 다시 실행한다. 실제 RC Git tag는 Draft
단계에서 만들지 않는다. unexpected tag가 이미 존재하면 자동 삭제하지 않고 별도 충돌로 중단한다.
stable Release와 `v0.1.0` tag/index는 복구 대상이 아니다.

GitHub Draft asset은 일반 공개 download URL에서 제공되지 않으므로 Arduino Boards Manager URL로
Draft 자체의 설치 완료를 시험할 수 없다. clean Windows 사전 검증은 인증된 계정으로 exact ZIP과
sidecar를 내려받고 새 Sketchbook의 격리된 `hardware` staging에 수동 추출해 수행한다.
`%LOCALAPPDATA%\Arduino15`를 직접 수정하지 않으며, 아직 존재하지 않는 자동 staging script를
가정하지 않는다. 공개 RC 전환 뒤 Boards Manager 설치·`post_install` end-to-end를 별도로 통과하고
프로젝트 소유자가 승인해야 stable을 검토할 수 있다.
