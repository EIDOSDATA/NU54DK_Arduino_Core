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

공식 nRF Util URL은 unversioned다. 내려받은 byte가 `pins.json`의 SHA-256과 다르면
자동으로 새 byte를 신뢰하지 않고 중단한다. upstream 변경을 검토하고 새 executable을
별도로 검증한 뒤 pin과 package version을 함께 갱신해야 한다.

수동 검증은 다음처럼 실행한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\verify-nordic.ps1 `
  -PlatformRoot . `
  -Json
```
