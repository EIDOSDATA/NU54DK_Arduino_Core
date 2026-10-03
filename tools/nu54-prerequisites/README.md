# Nordic prerequisite 설치 계약

새 Windows PC에서 Git, Python, MinGW-w64, Arduino CLI와 실물 보드까지 준비하는 전체 절차는
[Windows 개발환경 설정](<../../00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)을 따른다.
이 문서는 그중 Nordic prerequisite 설치기의 exact-pin 계약만 설명한다.

`post_install.bat`은 관리자 권한과 PATH 변경 없이 다음 고정 환경을 설치한다.

- `%USERPROFILE%\ncs\v3.4.0`
- `%USERPROFILE%\ncs\toolchains\dcbdc366a1`
- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\tools\nrfutil.exe`
- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\nrfutil` command 상태
- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json`
- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`

설치 도중 종료되면 `incomplete.json`과 단계별 log를 남긴다. 같은 설치기를 다시
실행하면 Nordic `sdk-manager`의 멱등 명령으로 설치를 재개한다. `pins.json`과 완료
marker, NCS/Zephyr revision 또는 Toolchain bundle이 다르면 Build Adapter는 package
build를 시작하지 않는다.

NCS v3.4.1이 공개돼도 현재 설치기의 v3.4.0 pin을 자동 갱신하지 않는다.
[v0.7.0 계획](../../00_Docs/TODO_v0.7.0.md)은 신기능 없이 3.4.1 전체 SDK 전환만 수행하며,
설치기·빌더·CI·package 전환은 SDK-W05에서 검증한다. 현재는 **0/6 미착수**로 기존 pin을 유지한다.
[변경·개발 영향 검토](<../../00_Docs/00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)와 exact
재검증이 필요하며, 다른 SDK의 수동 설치나 이 계획 문서만으로 지원 기준선이 변경되지는 않는다.

공식 nRF Util URL은 unversioned다. 내려받은 byte가 `pins.json`의 SHA-256과 다르면
자동으로 새 byte를 신뢰하지 않고 중단한다. upstream 변경을 검토하고 새 executable을
별도로 검증한 뒤 pin과 package version을 함께 갱신해야 한다.

## 설치 출력과 실패 판정

- 기존 `ready.json` 재사용 검증이 실패하면 **복구 안내는 stdout**에 표시하고 고정 환경의
  설치·복구를 계속한다. 이 사전 검증의 stderr는 console로 흘리지 않으며, 단계(phase),
  종료 code와 검증기 출력 원문은 설치 log에 남긴다. 복구 안내 자체는 최종 설치 실패가 아니다.
- 설치 byte·revision의 최종 검증이나 완료 marker 재검증이 실패하면 **stderr와 실패 종료
  code 1**을 유지하고 `incomplete.json`에 실패 단계와 log 위치를 남긴다. 오류를 숨기거나
  검증하지 않은 환경을 `ready`로 승인하지 않는다.
- 아래 수동 `verify-nordic.ps1` 검증은 실패 시 기존대로 stderr와 실패 종료 code를 반환한다.

이 출력 구분은 `v0.4.1`에서 처음 반영했으며 현재 지원 버전인
[v0.5.0](<../../00_Docs/05_릴리스/v0.5.0/README.md>)에도 유지한다. 지원 종료된 이전 package와
사용자 설치본을 교체하지 않으며, 이전 설치에 변경이 자동 적용됐다고 보지 않는다.

## 수동 검증

수동 검증은 다음처럼 실행한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\verify-nordic.ps1 `
  -PlatformRoot . `
  -Json
```
