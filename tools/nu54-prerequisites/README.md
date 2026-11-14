# Nordic prerequisite 설치 계약

2026-11-14 현행 상태: **Host6/8·HOST-W07 C5 검증 예산 교정 중**. C4 대표8빌드·실기11단계는 통과했고 CI software9·prerequisite3·build6개가 성공했다. native Windows shard5는 positive25 PASS 후 negative 준비120초 timeout으로 실패했다. C4 전체빌드는 cold37개 완료 후 통제 종료로 보존하며, C5 유한 예산300초 교정 뒤 새 exact 검증을 진행한다. [source별 결과](<../../00_Docs/04_검증 기록/327_HOST_W07_C4_실기_통과와_C5_거부_검증_예산_교정.md>). W06 실제 PASS46·수락3·FAIL 보존, #29 분석 유예, w06 PAUSED를 유지한다.

v0.6.0 HOST-W04 설치 범위는 같은 H4 source의 native 세 OS 설치·재검증으로 완료했다.
HOST-W06을 마감하고 HOST-W07을 준비하며 OS별 고정 자산과 공통 Python backend는
[Host별 설치 안내](<../../00_Docs/02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)와
[`platform-pins.json`](platform-pins.json)을 따른다. 구현·CI 진행과 사용자 실기 `NOT_RUN`은
[Host 원장](../../variants/nu54dk/host-readiness.json)에서 구분한다. 아래 Windows stable 계약은 보존한다.
새 공통 설치기는 SDK archive를 안전하게 추출하고 원형 VERSION을 바꾸지 않은 채 명시 version으로 등록한다.
읽기 전용 `host-doctor.py`는 시스템 의존 패키지와 비식별 serial·선택적 CMSIS-DAP 열거 결과를 기록한다.
처음 실패·원인·교정 검증은 [312번](<../../00_Docs/04_검증 기록/312_HOST_W04_최초_CI_실패와_교정_검증.md>)을 따른다.

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

공식 nRF Util 실행 파일은 버전과 빌드 식별자가 포함된 URL로 고정한다.
후속 Host 구현에서는 `platform-pins.json`의 공식 core8.2.1 archive도 SHA-256 검증 후
bootstrap 입력으로 지정한다. launcher와 core의 별도 고정을 Windows 설치 경로에도 적용한다.
현재 executable `1.4.1-f15ff58`의 byte와 SHA-256은 기존 pin을 유지하며,
별도로 version을 판정하는 core `8.2.1`과 sdk-manager `1.16.1`도 유지한다.
[Nordic의 특정 버전 설치 안내](https://docs.nordicsemi.com/r/bundle/nrfutil/page/guides/installing.html/installing-a-specific-version-of-nrf-util)에 따라
최신 파일을 가리키는 unversioned URL을 설치 입력으로 사용하지 않는다.
내려받은 byte가 `pins.json`의 SHA-256과 다르면 자동으로 신뢰하지 않고 중단한다.
실제 도구 version이나 byte를 바꾸는 경우에는 별도 검토·검증과 명시적인 pin·package version 갱신이 필요하다.

Native 0.6.0 시험 package의 초기 Python·notice와 실제 Boards Manager CI는
[native package 설계](<../../00_Docs/02_빌드 설계/14_native_Boards_Manager_package와_CI.md>)를 따른다.
시스템 Python/Git fallback을 허용하지 않으며 공개 allowlist는 변경하지 않는다.

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

`host-check.py`는 installed build manifest와 SHA identity에 결합한 Serial·ELF debug·Blink GPIO·NUS pair 검증 진입점입니다. 장치 조작 없는 `inventory`와 실기를 구분하며 [RC1 절차](<../../00_Docs/02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)를 따릅니다.
