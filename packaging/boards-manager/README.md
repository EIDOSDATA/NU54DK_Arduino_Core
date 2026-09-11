# NU54DK Boards Manager 패키징

v0.4.0 완료 상태·검증 범위는 [v0.4.0 완료 TODO](<../../00_Docs/TODO_v0.4.0.md>)에서 관리합니다.

| 항목 | 내용 |
| --- | --- |
| 현재 stable | `v0.4.0` |
| Stable index | `package_nucode_nu54dk_index.json` |
| Stable source | `ad829439e570c7510fce2f8cc7252e5b9ef32b04` |
| Stable ZIP | 2,630,374 byte / SHA-256 `6629963fc618419135b4fc0c1240fa84fa1db95fad03b92add798bbacf0c9189` |

이 디렉터리의 도구는 지정한 Git commit과 board submodule을 입력으로 사용해 Arduino
Boards Manager ZIP, index, checksum, release manifest, SPDX SBOM, license inventory와
third-party notices를 재현 가능하게 생성합니다.

## 내부 책임과 호환 진입점

`nu54_package.py`는 기존 CLI와 Python 함수·상수 이름을 유지하는 진입점입니다.
동일 디렉터리의 `nu54_package_impl`만 명시적으로 로드하므로 외부 CWD나 PYTHONPATH의
동명 모듈에 의존하지 않습니다. `python -I`에서도 같은 방식으로 동작합니다.
CLI의 표준 출력과 진단은 Windows 언어 설정과 무관하게 UTF-8을 사용합니다.

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

역사 버전의 build allowlist와 archive identity는 재현·감사를 위해 유지합니다. 이는 공개 공급
목록이 아닙니다. 역사 도구는 해당 original SHA/원본 자산을 입력으로 사용하며, 종료한 Release를
재공개하지 않습니다. 자세한 내용은 [106번 기록](<../../00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따릅니다.

## 고정 stable identity

| 버전 | Source commit | ZIP 크기 | ZIP SHA-256 |
| --- | --- | ---: | --- |
| `0.1.0` | `5dbc5e37270e477d21f578dd877f4b5226b44a0d` | 760,412 | `722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6` |
| `0.2.0` | `41fc44e452d2b6eef4b46307af6c277499f8d2d5` | 932,376 | `1c2b4dddd6da0c1530f9d32630ec7d5b5285cff28c826a9a95c864226aeaea6e` |
| `0.3.0` | `94ee3fec29ba9f86835b6cb3d96ab13ce2cf8c11` | 1,660,169 | `138740bcf6c458992fdb5c8eb81d6110d28b0baee18c68f5d8cb050e2e0e1ecc` |
| `0.4.0` | `ad829439e570c7510fce2f8cc7252e5b9ef32b04` | 2,630,374 | `6629963fc618419135b4fc0c1240fa84fa1db95fad03b92add798bbacf0c9189` |

`STABLE_RELEASE_COMMITS`는 source와 packaging tool이 모두 해당 exact commit에 있을 때만 같은
stable 이름의 build를 허용합니다. `PUBLISHED_STABLE_ARCHIVE_IDENTITIES`는 통합 index에 넣는
과거 ZIP을 최신 allowlist로 재해석하지 않고 공개 byte로 검증합니다.

## 버전별 생성 경로

| 대상 | 사용할 절차 |
| --- | --- |
| 비공개 `v0.4.0-rc.1` 후보 | [M27 prepare](../../tools/release/M27_README.md) |
| 정식 `v0.4.0` | [완료 TODO](../../00_Docs/TODO_v0.4.0.md)와 [125번 기록](<../../00_Docs/04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>); 공개 완료 |
| 이미 공개한 stable | 아래 exact tag 감사 절차 |

현재 `main`에서 `-Version 0.3.0 -Commit HEAD` 또는 `-Version 0.4.0 -Commit HEAD`로 새 package를
만들지 않습니다. 두 version은 위 고정 source에서만 생성 가능한 공개 버전입니다. 생성기는 산출물을 자동 게시하지 않으며, 새 version의
공개는 이중 재현·Host·문서·package·lifecycle·HIL gate와 소유자의 최종 승인 뒤 별도 수행합니다.

## 공개 v0.3.0 감사 예시

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
