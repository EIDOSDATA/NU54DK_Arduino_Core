# NU54DK Arduino Core v0.3.0-rc.2 릴리스 후보

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.3.0-rc.2-INDEX-001 |
| 대상 버전 | `v0.3.0-rc.2` / package version `0.3.0-rc.2` |
| 채널 | 별도 RC Boards Manager index를 사용하는 Public GitHub Prerelease |
| 현재 정식 버전 | `v0.2.0` |
| 공식 사용자 OS | Windows 10/11 x64 |
| 지원 보드 | NU54DK / `nucode:zephyr:nu54dk` |
| 현재 상태 | **RC2 공개 검증 완료 — v0.3.0 stable 승격 대기** |
| 작성자 | Quantum / NUCODE |

`v0.3.0-rc.2`는 `v0.3.0-rc.1`의 공개 package 기능을 이어받아 M22 전체 공개 설치
수명주기를 다시 검증한 교정 후보입니다. RC1에서 확인된 문제는 동일 PC 격리
clean-room 도구가 Nordic SDK와 Toolchain 설치 대상 leaf를 먼저 만든 데서 발생했습니다.
일반 사용자 package의 firmware 또는 API 결함으로 판정된 것은 아닙니다.

RC2 Public Prerelease와 7개 고정 자산은
[GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0-rc.2)에
공개됐습니다. 설치본 예제 29/29, 실제 pyOCD Upload, 공개 URL clean-room lifecycle·cleanup 및
stable index 불변 검증을 통과했습니다. RC2는 검증된 시험 후보이며 production stable은 계속
`v0.2.0`입니다.

## 문서

- [Release notes](./RELEASE_NOTES.md): RC2 교정 범위와 이어받아 검증한 기능
- [Testing](./TESTING.md): 공개 GitHub 자산, Arduino IDE 설치와 시험 절차
- [Migration](./MIGRATION.md): Stable 또는 RC1에서 RC2로 이동하고 복귀하는 절차
- [Known issues](./KNOWN_ISSUES.md): 검증된 범위의 알려진 제약과 제외 경계
- [Troubleshooting](./TROUBLESHOOTING.md): 설치·build·upload·storage·BLE 진단

## 고정 기술 기반

| 구성 | 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| Loader | 사용하지 않음 — Sketch를 포함한 전체 Zephyr image |
| Upload 기본 경로 | 온보드 CMSIS-DAP V2 + pyOCD |

Core commit `bb7a4eace689af707ea429a1911e4cb98da97329`과 board package gitlink
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`를 RC2 package plan에 고정했습니다. 정확한 tag,
자산과 evidence는 [M22 RC2 검증 기록](<../../04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)을
따릅니다. RC1의 commit이나 evidence를 RC2 값으로 복사하지 않았습니다.

## 검증된 Package 구성

- Arduino library 8개
- 설치 예제 29개: Standard 22개, BLE 7개
- EEPROM mirror 1024 byte
- 전용 LittleFS 32 KiB: `0x16c000..0x174000`
- Settings/ZMS 36 KiB: `0x174000..0x17d000`
- Application slot 각 696 KiB, maximum Sketch size 712704 byte
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 경로

위 구성은 두 번의 독립 package 생성에서 byte-for-byte 일치했고, 실제 공개 archive 설치본으로
예제 29/29 compile과 Blink Upload를 확인했습니다. Core ZIP SHA-256은
`b52e39c7aa9e550624a556487cb7b6e537f551c4fbd833e7a61cf28aa91e15f6`입니다.

## RC1과 RC2의 관계

RC1의 tag와 공개 자산은 변경하거나 RC2 byte로 덮어쓰지 않습니다. RC1의 local fixed gate와
public clean-room 실패는 [RC1 clean-room 검증 중단 기록](../v0.3.0-rc.1/CLEANROOM_ABORT.md)에
보존합니다.

RC2는 다음 항목을 새 identity로 다시 실행해 모두 통과했습니다.

1. Exact clean Core commit과 board gitlink 확정
2. 두 번의 독립 package 생성과 byte 재현성 확인
3. Host, 설치본 29개 예제와 지정 UID Upload fixed gate
4. 새 annotated tag와 정확히 7개 자산의 Public Prerelease
5. 공개 RC2 URL 기반 동일 PC 격리 clean-room
6. 네 gate evidence 결합과 exact run leaf cleanup 확인

## 공개 경계

1. `v0.3.0-rc.2`는 prerelease이며 생산용 stable 선언이 아닙니다.
2. RC2는 해당 tag의 `package_nucode_nu54dk_rc_index.json`만 사용합니다.
3. Stable `package_nucode_nu54dk_index.json`, `v0.2.0` tag와 자산을 수정하지 않습니다.
4. RC2 tag와 자산도 공개 뒤 덮어쓰지 않습니다. 추가 수정이 필요하면 다음 RC를 만듭니다.
5. RC1 gate evidence를 RC2 PASS로 상속하지 않습니다.
6. RC2 final evidence SHA-256은 `eeb4727425afbc6ee5eb8fceccf5cc07cd91e70cb4cf9993a6f496251cd6e461`입니다.
