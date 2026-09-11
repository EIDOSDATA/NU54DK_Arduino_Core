# M22 v0.3.0-rc.3 릴리스 자동화

이 문서는 공급 종료된 RC의 역사적 실행 계약입니다. 아래 공개 순서는 현재 실행 지시가 아니며,
후속 v0.4.0 완료 절차는 [M27](M27_README.md), 현재 설치는 [릴리스 안내](../../00_Docs/05_릴리스/README.md)를 따릅니다.

`v0.3.0-rc.1`은 공개 뒤 clean-room 실행기가 Nordic installer 소유 leaf를 먼저
생성하는 결함으로 formal 검증을 중단한 불변 후보입니다. RC1 tag와 7개 자산은
교체하지 않습니다. RC2는 실행기를 교정해 전체 gate를 통과한 불변 후보이며, RC3는
loaderless application의 Devicetree·linker·Arduino maximum size를 일치시킨 새 후보입니다.
RC1과 RC2의 tag·자산은 변경하지 않고 RC3 전체 gate를 새 plan으로 다시 수행합니다.

이 문서는 `tools/release/m22_release.py`와 `m22_cleanroom.py`의 실행 경계와 순서를
고정한다. 두 도구는 Git tag 생성, push 또는 GitHub Release 생성을 직접 수행하지
않는다. GitHub CLI를 이용한 공개 작업은 이 도구 밖의 승인된 절차가 담당한다.

## 고정 순서

M22는 아래 순서를 바꾸지 않는다.

1. 최종 clean commit을 push한다.
2. `prepare`로 같은 commit에서 두 번 재현 build하고 `validate`한다.
3. `host`, `package-examples`, `rc-upload` fixed gate를 통과한다.
4. exact commit으로 annotated tag `v0.3.0-rc.3`를 만들고 push한다.
5. 아래 7개 파일만 포함한 **공개 prerelease**를 만든다.
6. 공개 URL을 사용해 `run-cleanroom`을 실행한다.
7. 네 gate evidence를 `finalize`로 결합한다.

Draft Release의 asset URL은 Arduino Boards Manager가 다운로드할 수 없으므로
clean-room보다 먼저 공개 prerelease가 존재해야 한다. 최종 evidence의
`publication.performed_by_this_tool=false`는 “RC가 비공개”라는 뜻이 아니라,
M22 Python 도구 자체가 GitHub 공개 작업을 수행하지 않았다는 뜻이다.

## 공개 asset allowlist

공개 prerelease에는 다음 7개 파일만 올린다.

- `nucode-nu54dk-zephyr-0.3.0-rc.3.zip`
- `nucode-nu54dk-zephyr-0.3.0-rc.3.CHECKSUMS.sha256`
- `nucode-nu54dk-zephyr-0.3.0-rc.3.license-inventory.json`
- `nucode-nu54dk-zephyr-0.3.0-rc.3.release-manifest.json`
- `nucode-nu54dk-zephyr-0.3.0-rc.3.THIRD_PARTY_NOTICES.md`
- `nucode-nu54dk-zephyr-0.3.0-rc.3.spdx.json`
- `package_nucode_nu54dk_rc_index.json`

로컬 `m22-rc3-plan.json`, gate evidence, log와 final evidence는 Release asset으로
올리지 않는다. stable index `package_nucode_nu54dk_index.json`도 RC asset이 아니다.
M22 당시 stable index 기준은 1,877 byte이고 SHA-256이
`5ae7fbe13f71c52950879064685694cf4b062557572f187e81476639724e5344`였다.
현행 validator는 후속 v0.3.0 최초 index와 공급 종료 후 catalog의 고정 identity도
허용한다. 2026-09-08 공급 종료 catalog는 1,126 byte, SHA-256
`97e842248772d1e19b4649574008b24b405bde092c2f9df98d115dc65b2f5b57`이었다.
현재 stable catalog는 0.4.0과 0.3.0을 제공하며 exact identity는
[125번 공개 기록](<../../00_Docs/04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)을 따른다.
허용 byte를 exact commit과 worktree 양쪽에서 확인하며 과거 plan의 기준을 바꾸지는 않는다.

## clean-room 정리 계약

same-PC clean-room은 `C:\NU54CI\M22` 아래에 새 `m22-...` run leaf를 만들고 모든
Arduino, NCS, toolchain, cache 경로를 그 leaf 아래로 격리한다.

- 성공하면 marker, 외부 evidence hash와 reparse point 부재를 검증한 뒤 **그 run
  leaf 하나만** 삭제한다.
- parent, sibling directory와 run leaf 밖의 evidence/log는 보존한다.
- 실패하면 조사할 수 있도록 run leaf를 보존한다.
- `finalize`는 exact leaf 삭제, 외부 evidence 보존, reparse 검사, marker 검사와
  공개 RC index/archive identity가 모두 evidence에 기록되어야만 통과한다.

최종 상태 `public-rc3-validated`는 공개 prerelease의 Boards Manager 설치,
29개 설치본 예제 build, exact UID 업로드, downgrade/upgrade, uninstall/reinstall 및
cleanup까지 완료되었다는 뜻이다.
