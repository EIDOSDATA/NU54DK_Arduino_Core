# NU54DK Boards Manager 패키징

| 항목 | 내용 |
| --- | --- |
| 현재 stable | `v0.3.0` |
| Stable index | `package_nucode_nu54dk_index.json` |
| Stable source | `94ee3fec29ba9f86835b6cb3d96ab13ce2cf8c11` |
| Stable ZIP | 1,660,169 byte / SHA-256 `138740bcf6c458992fdb5c8eb81d6110d28b0baee18c68f5d8cb050e2e0e1ecc` |

이 디렉터리의 도구는 지정한 Git commit과 board submodule을 입력으로 사용해 Arduino
Boards Manager ZIP, index, checksum, release manifest, SPDX SBOM, license inventory와
third-party notices를 재현 가능하게 생성합니다.

## 내부 책임과 호환 진입점

`nu54_package.py`는 기존 CLI와 Python 함수·상수 이름을 유지하는 진입점입니다.
동일 디렉터리의 `nu54_package_impl`만 명시적으로 로드하므로 외부 CWD나 PYTHONPATH의
동명 모듈에 의존하지 않습니다. `python -I`에서도 같은 방식으로 동작합니다.

| 내부 모듈 | 책임 |
| --- | --- |
| model / channels | SourceFile·오류·고정 계약, version/channel·공개 identity |
| inputs / serialization | exact Git·gitlink 입력·allowlist·byte 변환, JSON·hash·checksum |
| licenses / sbom / manifest | license·외부 prerequisite, SPDX 관계, runtime provenance |
| archive / validation | 결정적 ZIP·sidecar 생성, 실제 파일·metadata·공개 identity 검증 |
| index / build / cli | Boards Manager index, 생성·검증 orchestration, 인자·진단·종료 코드 |

생성 출력과 실제 archive 검증은 별도 책임입니다. public entrypoint, 인자, marker,
schema와 stable 재현 조건은 그대로 유지하며, 과거 tag의 재현은 그 tag의 원래 도구를 사용합니다.
R13의 본문·CLI·산출물 byte 비교는
[64번 기록](<../../00_Docs/04_검증 기록/64_R13_도구_정책_build_구조.md>)에서 추적합니다.

## 공개 stable은 불변

공개된 `v0.1.0`, `v0.2.0`, `v0.3.0`의 tag, ZIP, 부속 자산과 version별 index snapshot은
덮어쓰거나 다시 만들지 않습니다. Stable index는 최신순 `0.3.0`, `0.2.0`, `0.1.0`을
제공하며 이전 항목의 URL, 크기와 checksum을 유지합니다.

이전 버전은 신규 지원 대상이 아니지만, 재현성 감사와 검증된 downgrade를 위해 공개 자산과
index 항목을 삭제하지 않습니다. 새 릴리스는 새 version/tag/asset으로만 추가합니다.

## 고정 stable identity

| 버전 | Source commit | ZIP 크기 | ZIP SHA-256 |
| --- | --- | ---: | --- |
| `0.1.0` | `5dbc5e37270e477d21f578dd877f4b5226b44a0d` | 760,412 | `722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6` |
| `0.2.0` | `41fc44e452d2b6eef4b46307af6c277499f8d2d5` | 932,376 | `1c2b4dddd6da0c1530f9d32630ec7d5b5285cff28c826a9a95c864226aeaea6e` |
| `0.3.0` | `94ee3fec29ba9f86835b6cb3d96ab13ce2cf8c11` | 1,660,169 | `138740bcf6c458992fdb5c8eb81d6110d28b0baee18c68f5d8cb050e2e0e1ecc` |

`STABLE_RELEASE_COMMITS`는 source와 packaging tool이 모두 해당 exact commit에 있을 때만 같은
stable 이름의 build를 허용합니다. `PUBLISHED_STABLE_ARCHIVE_IDENTITIES`는 통합 index에 넣는
과거 ZIP을 최신 allowlist로 재해석하지 않고 공개 byte로 검증합니다.

## Stable package 생성

새 stable 공개 전 exact release commit의 깨끗한 worktree에서 실행합니다.

```powershell
.\packaging\boards-manager\build-stable.ps1 `
  -Version 0.3.0 `
  -Commit HEAD `
  -OutputDirectory C:\NU54DEV\stable\candidate `
  -VenvPath C:\NU54DEV\venv\host-3.12.10
```

`build-stable.ps1`은 기존 stable ZIP을 공개 identity로 검증하고 최신순 통합 index를 만듭니다.
생성 결과는 자동으로 게시되지 않습니다. 두 독립 output directory에서 실행한 모든 산출물의
byte가 일치하고 host/docs/package/lifecycle/HIL gate가 통과한 뒤에만 공개합니다.

## 공개 stable 감사

이미 공개한 stable 재현은 해당 tag의 별도 worktree에서만 수행합니다. 현재 `main`의 packaging
tool로 과거 source를 다시 포장하지 않습니다.

```powershell
git worktree add C:\NU54DEV\audit-v0.3.0 v0.3.0
Set-Location C:\NU54DEV\audit-v0.3.0
git submodule update --init --recursive
.\packaging\boards-manager\build-stable.ps1 `
  -Version 0.3.0 `
  -Commit HEAD `
  -OutputDirectory C:\NU54DEV\audit-output `
  -VenvPath C:\NU54DEV\venv\host-3.12.10
```

감사 결과는 위 고정 크기와 SHA-256에 대조하며 Release asset이나 root index를 교체하는 데
사용하지 않습니다.

## 검증 범위

생성기와 validator는 다음 항목을 fail-closed로 검사합니다.

- archive root, 경로 안전성, allowlist와 executable metadata
- `platform.txt` version과 exact Core/board revision
- profile/feature manifest와 Arduino 예제 집합
- checksum, release manifest, SPDX, license inventory와 notices
- channel별 index 파일명, URL, version 순서, archive 크기와 SHA-256
- 공개 stable의 exact commit 및 immutable ZIP identity

정식 공개 절차와 결과는
[v0.3.0 공개 기록](<../../00_Docs/04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)을
기준으로 합니다.

## 역사적 preview/RC

`0.0.91`~`0.0.97`, `v0.1.0-rc.1`/`rc.2`, `v0.2.0-rc.1`/`rc.2`와
`v0.3.0-rc.1`~`rc.3`은 신규 설치 channel이 아닙니다. 당시 tag, 자산과 문서는 실패·교정·승격
근거를 보존하는 immutable 이력입니다. Preview/RC index를 stable index로 합치거나 기존 자산을
새 byte로 교체하지 않습니다.
