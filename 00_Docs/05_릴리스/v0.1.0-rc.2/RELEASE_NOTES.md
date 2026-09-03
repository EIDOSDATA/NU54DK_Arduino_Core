# NU54DK Arduino Core v0.1.0-rc.2 릴리스 노트

> **공개 완료:** `v0.1.0-rc.2` tag와 GitHub Prerelease는
> 2026-08-28T12:14:28Z에 공개했다. 공개 자산을 다시 내려받아 SHA-256을 대조하고 Arduino
> IDE 2.3.10 backend의 실제 gRPC 설치 완료 응답을 확인했다. 공개 후 별도 clean Windows의
> Arduino IDE 2.3.10에서 compile과 실제 NU54DK upload·실행도 수동 검증했다.

`v0.1.0-rc.2`는 Loader 없이 Sketch와 Zephyr를 하나의 정적 firmware로 만드는 NU54DK 전용
두 번째 release candidate다. 정식 `v0.1.0`이 아니다.

## rc.1 이후 변경

- `post_install.bat`이 PowerShell을 시작하기 전에 Windows console code page를 UTF-8로
  고정한다.
- Nordic prerequisite PowerShell runner가 console input/output과 native command 출력
  인코딩을 BOM 없는 UTF-8로 고정한다.
- 설치·검증 runner의 SHA-256 계산을 .NET 구현으로 바꿔 Windows PowerShell module 자동
  로드 상태에 의존하지 않는다.
- 설치 runner 출력이 UTF-8로 decode 가능한지 검증하는 host 회귀를 추가한다.
- release automation의 허용 version, tag, package와 고정 gate를 `0.1.0-rc.2`로 올린다.
- rc.1 artifact를 수정하거나 덮어쓰지 않고 Release와 tag를 삭제하며 검증 이력만 보존한다.

이 교정은 Arduino IDE 2.3.10에서 platform 설치가 실제 끝난 뒤에도 gRPC가
`string field contains invalid UTF-8`을 반환해 실패로 보이던 경로를 대상으로 한다.
firmware runtime, NU54DK DTS, pin mapping, Arduino API와 upload protocol의 의도된 기능
범위는 바꾸지 않는다.

## 주요 기능

- NCS v3.4.0 / Zephyr 4.4.0 기반 Native Full Zephyr build
- Arduino CLI/IDE 공용 `nucode:zephyr:nu54dk` platform recipe
- Arduino `setup()`/`loop()` runtime, 다중 `.ino` 탭, 자동 prototype과 library discovery
- Arduino API와 Zephyr API를 한 Sketch에서 함께 사용
- GPIO, 시간·delay, `String`, `Print`, `Stream`, DAP UART `Serial`과 GPIO interrupt
- I2C `Wire`, SPI, A0 ADC와 P1.10 PWM
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 Upload/debug
- persistent Zephyr build cache, ccache, lock/LRU와 손상 복구
- Boards Manager package, SPDX SBOM, license inventory와 사용자 영역 Nordic 설치

## 검증 및 공개 identity

rc.1의 commit, hash나 evidence를 rc.2 값으로 복사하지 않았다.

| 항목 | 공개 결과 |
| --- | --- |
| rc.2 source commit | `f290930bf1b23134a4c383669efce76f626cacbe` |
| Board package commit | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 자동 gate | package integrity, host, Arduino fixed-package, Zephyr, documentation **5/5 PASS** |
| Arduino IDE post-install 완료 경로 | 공개 index·ZIP, Arduino CLI 1.5.1 gRPC `PlatformInstall` **PASS** |
| Archive | 761,689 byte, SHA-256 `40885577f1e27db216e792bcd61a78fdbed6b42706336d8eedc79c8dd23fd9ff` |
| RC index | 1,150 byte, SHA-256 `5db331457ad49ab66a816c242d1fd0b2e39ba085b4f5bc2438c41907c8868cdd` |
| tag와 GitHub Prerelease | `v0.1.0-rc.2`, 2026-08-28T12:14:28Z 공개 |
| 공개 자산 재다운로드 | 8개 자산 크기·SHA-256 전부 일치 |
| rc.1 원격 상태 | GitHub Release와 원격·로컬 tag 삭제 완료 |
| 공개 후 clean Windows 실사용 | Arduino IDE 2.3.10 설치·보드 선택·compile·실제 NU54DK upload·실행 **수동 PASS** |

rc.2 공개 시점에는 새 RC2 byte의 `hil_rc_pyocd`, 기존 M10 범위를 가져오는 `hil_pyocd`,
`clean_windows`를 시험 장치 미연결과 원격 PC 오프라인으로 재실행하지 않았다. 당시 이를
PASS로 기록하거나 HOLD evidence manifest를 공개하지 않았다. RC1과 RC2 archive는 모두
125개 파일이고 변경된 파일은
`platform.txt`, `post_install.bat`, `install-nordic.ps1`, `verify-nordic.ps1`뿐이므로 firmware,
DTS, pin mapping과 Upload 구현은 동일하다.

## 공개 후 clean Windows 실사용 검증

프로젝트 소유자는 공개 rc.2 package를 별도 clean Windows PC의 Arduino IDE 2.3.10에 설치한
뒤 `NU54DK (nRF54L15, Zephyr)`를 선택해 Sketch compile, 실제 NU54DK upload와 실행을
확인했다. compile 결과는 FLASH 55,216 byte(3%), RAM 16,301 byte(6%)였다.

이 결과는 프로젝트 소유자의 수동 acceptance다. rc.2 공개 시점에 생성하지 않은 strict M11
evidence manifest를 소급 생성하거나 자동 gate 8/8로 표현하지 않는다. 자동 5/5와 수동
clean Windows·실기 결과의 상세 경계는
[M11 rc.2 공개 후 수동 검증 기록](<../../04_검증 기록/12_M11_v0.1.0_rc2_공개_후_수동_검증.md>)에
보관한다. 이 후속 검증으로 M11을 완료하고 `v0.1.0`을 후속 정식판으로 확정했다. 정식판은
[v0.1.0 릴리스 노트](../v0.1.0/RELEASE_NOTES.md)의 별도 stable ZIP·index·tag·Release를
사용한다. rc.2 Prerelease와 자산은 역사적 검증 기록으로 변경하지 않는다.

기존 rc.1 M11 gate 8/8은
[역사적 기준선](<../../04_검증 기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)에 보존한다.
rc.2 공개 판정은 새 artifact의 gate 결과만 사용한다.

## 업데이트 주의사항

회수된 rc.1에서 rc.2로 이동할 때 NCS/Toolchain 디렉터리를 먼저 삭제하지 않는다. exact pin과
완료 marker가 일치하면 공유 prerequisite를 재사용할 수 있다. Arduino build output은 새
version에서 다시 생성한다. 자세한 절차는
[rc.2 마이그레이션 안내](MIGRATION.md)를 따른다.

## 감사와 라이선스

NUCODE 자체 작성 코드는 MIT License다. ArduinoCore-API, NU54DK board package, Zephyr/NCS와
외부 Nordic 도구에는 각 원본 라이선스와 고지가 적용된다. artifact의 license inventory는
법률 자문을 대신하지 않는다.
