# NU54DK Arduino Core v0.3.0-rc.1 릴리스 후보

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.3.0-rc.1-INDEX-001 |
| 대상 버전 | `v0.3.0-rc.1` / package version `0.3.0-rc.1` |
| 채널 | Public GitHub Prerelease + 별도 RC Boards Manager index |
| 현재 정식 버전 | `v0.2.0` |
| 공식 사용자 OS | Windows 10/11 x64 |
| 지원 보드 | NU54DK / `nucode:zephyr:nu54dk` |
| 상태 | M22 RC 공개·clean-room 검증용 후보; stable 승격 아님 |
| 작성자 | Quantum / NUCODE |

`v0.3.0-rc.1`은 Arduino Compatibility AC-01~AC-03과 BLE M19~M21을 하나의 package로
통합해 공개 설치 경로를 검증하기 위한 후보입니다. Stable index와 현재 정식 `v0.2.0`은 이
RC를 공개해도 변경하지 않습니다.

## 문서

- [Release notes](./RELEASE_NOTES.md): 추가 기능과 package 구성
- [Testing](./TESTING.md): GitHub RC 자산, Arduino IDE 설치, compile·upload·기능 확인
- [Migration](./MIGRATION.md): `v0.2.0`에서 RC로 이동하고 되돌리는 방법
- [Known issues](./KNOWN_ISSUES.md): RC에서 반드시 구분해야 할 미확정·제외 범위
- [Troubleshooting](./TROUBLESHOOTING.md): 설치·build·upload·storage·BLE 진단

## 고정 기술 기반

| 구성 | 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Loader | 사용하지 않음 — Sketch를 포함한 전체 Zephyr image |

## Package 구성

- Arduino library 8개
- 설치 예제 29개: Standard 22개, BLE 7개
- EEPROM mirror 1024 byte
- 전용 LittleFS 32 KiB: `0x16c000..0x174000`
- Settings/ZMS 36 KiB: `0x174000..0x17d000`
- Application slot 각 696 KiB, maximum Sketch size 712704 byte
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 경로

RC의 exact tag commit, 공개 asset 크기·SHA-256, clean-room 및 검증 결과는 공개 실행이 끝난 뒤
[M22 검증 기록](<../../04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)에 고정합니다.
공개 전에는 문서의 URL을 PASS 증거로 해석하지 마십시오.

## 공개 경계

1. `v0.3.0-rc.1`은 prerelease이며 생산용 stable 선언이 아닙니다.
2. RC는 `package_nucode_nu54dk_rc_index.json`만 사용합니다.
3. Stable `package_nucode_nu54dk_index.json`과 `v0.2.0` 자산은 수정하지 않습니다.
4. RC tag와 자산은 공개 뒤 덮어쓰지 않습니다. 수정이 필요하면 다음 RC를 만듭니다.
5. AC-02B와 AC-03은 exact `0b7f892`의 물리 HIL을 통과했습니다. RC package·public
   clean-room PASS는 M22 final evidence가 생긴 뒤에만 선언합니다.
