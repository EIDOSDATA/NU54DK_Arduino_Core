# v0.1.0 문제 해결

## Boards Manager에서 보이지 않음

Additional Boards Manager URLs에 다음 주소가 정확히 들어 있는지 확인하고 index를 갱신한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

RC·preview URL만 등록돼 있으면 `0.1.0`이 보이지 않는다.

## 설치가 오래 걸리거나 중단됨

첫 설치는 NCS v3.4.0과 Toolchain을 Nordic 공식 배포 경로에서 내려받으므로 오래 걸린다. 같은
사용자 계정에서 설치를 다시 실행하면 검증된 download와 완료 marker를 재사용한다. 설치된
platform의 `post_install.bat`도 일반 사용자 권한으로 다시 실행할 수 있다.

```text
%LOCALAPPDATA%\Arduino15\packages\nucode\hardware\zephyr\0.1.0\post_install.bat
```

## `invalid UTF-8` 설치 오류

이 오류는 회수된 rc.1의 Windows 출력 인코딩 결함이다. stable URL과 `0.1.0`을 사용한다.
rc.2부터 console, PowerShell과 native command 출력을 UTF-8로 고정했다.

## 컴파일은 되지만 Upload가 되지 않음

- data 통신 가능한 USB cable과 온보드 CMSIS-DAP V2 연결을 확인한다.
- 다른 pyOCD, debug server, Serial Monitor가 probe를 점유하지 않는지 확인한다.
- 기본 Upload probe는 `CMSIS-DAP (pyOCD)`다.
- probe가 여러 개면 정확한 probe ID를 명시한다.
- 외장 J-Link를 선택했다면 SEGGER J-Link Software를 별도로 설치해야 한다.

`nrfutil` runner는 Nordic DK 기준 동작이며 NU54DK의 온보드 CMSIS-DAP V2 기본 경로가 아니다.

## 보고할 정보

문제를 보고할 때 password, token과 전체 probe UID를 제거하고 다음을 포함한다.

- Arduino IDE/CLI version과 Windows version
- 설치 Core version `0.1.0`
- FQBN `nucode:zephyr:nu54dk`
- 전체 compile 또는 Upload 오류
- NCS `v3.4.0`, Toolchain bundle `dcbdc366a1` 검증 결과
- 사용 probe 종류와 pyOCD/J-Link version
