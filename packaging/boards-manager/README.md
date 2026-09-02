# NU54DK Boards Manager 패키징 — v0.3.0 stable 공개 전 준비

| 항목 | 내용 |
| --- | --- |
| 현재 정식 버전 | **v0.2.0 정식 공개 완료** |
| 다음 개발 버전 | **v0.3.0 stable 공개 전 인계** |
| stable index | `package_nucode_nu54dk_index.json` |

이 디렉터리의 도구는 작업 트리가 아니라 지정한 Git commit만 입력으로 사용한다. 상위
저장소의 `board_package/NU54DK_Zephyr_DTS` gitlink가 가리키는 commit도 함께 펼쳐서
하나의 Arduino platform ZIP으로 만든다.

## 1. 공개된 stable 버전은 불변이다

공개된 `v0.1.0`과 `v0.2.0` ZIP, 부속 자산, Release와 stable index 항목은 **덮어쓰거나
다시 만들지 않는다**. 공개 뒤 같은 버전 이름으로 다른 source를 포장하는 조합은 금지한다.

`0.3.0`은 stable 패키지 생성 허용목록과 법률 승인 상태만 준비했다. 공개 commit·archive
identity는 아직 고정하지 않았고 root stable index도 변경하지 않았다. 다른 Windows PC에서
검증을 마친 뒤 exact public identity를 후속 commit에 기록한다.

```text
--version <이미 공개한 stable> --commit <다른 commit>
```

stable index에서 기존 항목의 URL, size와 checksum도 변경하지 않는다. 이후 버전은 새 Release와
새 버전 항목으로 추가하며, 장기 endpoint에는 최신 버전을 앞에 두고 이전 stable을 함께 보존한다.

## 2. 공개 stable 재현은 감사용으로만 수행한다

공개 stable을 로컬에서 재현·감사할 필요가 있으면 **source와 패키징 도구를 모두** 해당 tag의
exact commit으로 맞춘 별도 worktree에서 실행한다. `v0.1.0`은
`5dbc5e37270e477d21f578dd877f4b5226b44a0d`, `v0.2.0`은
`41fc44e452d2b6eef4b46307af6c277499f8d2d5`다. 현재 `main`의 도구로 과거 source를 다시
포장하는 것도 허용하지 않는다. 아래는 `v0.1.0` 감사 예시이며 `v0.2.0`은 tag·버전·경로를
함께 바꿔 별도 worktree에서 실행한다.

```powershell
git worktree add ..\NU54DK_Arduino_Core-v0.1.0-audit v0.1.0
Set-Location ..\NU54DK_Arduino_Core-v0.1.0-audit
git submodule update --init --recursive

.\packaging\boards-manager\build-stable.ps1 `
  -Version 0.1.0 `
  -Commit HEAD `
  -OutputDirectory .\build\boards-manager\v0.1.0-audit
```

이 결과는 로컬 감사 산출물이다. 공개 Release asset이나 저장소의 stable index를 교체하는
용도로 사용하지 않는다. 생성 결과는 공개 기록의 크기와 SHA-256에 대조한다.

```powershell
python .\packaging\boards-manager\nu54_package.py validate `
  --archive .\build\boards-manager\v0.1.0-audit\nucode-nu54dk-zephyr-0.1.0.zip `
  --expected-version 0.1.0

python .\packaging\boards-manager\nu54_package.py validate-index `
  --index .\build\boards-manager\v0.1.0-audit\package_nucode_nu54dk_index.json `
  --artifact-dir .\build\boards-manager\v0.1.0-audit
```

검증은 ZIP 경로 안전성, 단일 top-level 디렉터리, timestamp·mode·정렬, manifest 계약,
전체 checksum, SPDX JSON SBOM, 라이선스 원문 inventory, package index URL·크기·checksum을
모두 확인하며 하나라도 다르면 실패한다.

## 3. v0.2.0 패키징 원칙

`v0.2.0`은 공개 RC2의 검증된 runtime과 같은 version-independent payload를 사용하고, 정식
Release commit에서 별도 archive·checksum·SBOM·license inventory를 생성한다. stable index에는
`0.2.0`과 불변 `0.1.0` 항목을 최신순으로 함께 기록한다. 준비 중인 HEAD 산출물을 이전 버전으로
표시하거나 기존 Release에 업로드하지 않는다.

과거 `0.1.0` ZIP은 당시 source 허용목록으로 생성된 공개 자산이므로 최신 source 허용목록으로
재해석하지 않는다. 공개 크기 `760,412`와 SHA-256
`722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6`이 모두 일치할 때만
통합 stable index에 포함한다.

정식 공개 source commit `41fc44e452d2b6eef4b46307af6c277499f8d2d5`와 ZIP의 크기
`932,376`, SHA-256
`1c2b4dddd6da0c1530f9d32630ec7d5b5285cff28c826a9a95c864226aeaea6e`를
`STABLE_RELEASE_COMMITS`와 공개 archive identity에 고정했다. 이후 현재 `main`의 도구로 해당
stable을 재포장하지 않고, 감사가 필요하면 `v0.2.0` tag의 별도 worktree를 사용한다.

## 4. M10 preview 이력

다음 내용은 `v0.1.0` 정식 공개 전 M10 검증의 역사적 증거이며 현재 권장 빌드 대상이 아니다.

- clean Windows 검증 쌍은 Windows-safe preview `0.0.96`, `0.0.97`이었다.
- `0.0.90`~`0.0.93`은 Windows PowerShell 5.1, BAT/CMD 인코딩 또는 긴 build 경로 결함이
  확인된 실패 이력이며 공식 index에서 제외했다.
- `0.0.94`와 `0.0.95`는 PowerShell 5.1 runner의 비동기 Task 반환값이 success stream에
  섞여 Arduino CLI identity preflight에서 실패한 immutable 이력이다.
- 공개된 preview asset도 덮어쓰지 않으며 현재 stable index나 `v0.2.0` 기준선으로 사용하지
  않는다.

당시 생성된 ZIP은 `m10-preview-<version>` GitHub prerelease asset URL을 사용했다. 당시
license inventory의 법률 검토 상태 `required`는 preview 단계의 기록이다. `v0.1.0` 정식
공개본은 프로젝트 소유자의 최종 공개 승인을 완료했다.

## 5. 재배포와 라이선스 경계

NCS와 Nordic toolchain은 ZIP이나 index의 `tools` 항목으로 재배포하지 않는다. 보드
서브모듈은 저장소 최상위 `LICENSE`의 MIT 범위와 `boards/nucode/nu54dk/**` 파생 파일의
Apache-2.0 범위를 분리해 기록한다.

nRF Util, sdk-manager, NCS, Zephyr, Nordic toolchain, bundled pyOCD 및 선택형 J-Link는 ZIP에
포함하지 않는 외부 전제조건이다. 확인하지 않은 종합 라이선스를 추정하지 않고
`NOASSERTION`으로 유지한다.
