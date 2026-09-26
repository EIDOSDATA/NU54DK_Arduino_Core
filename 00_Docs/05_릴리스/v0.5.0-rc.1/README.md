# NU54DK Arduino Core v0.5.0-rc.1

`v0.5.0-rc.1`은 **Windows 10/11 x64용 공개 Release Candidate**입니다.
새 Bluetooth 기능을 시험할 수 있지만 정식 stable·지원 기준은 계속
[v0.4.1](../v0.4.1/README.md)입니다. RC는 stable root catalog에 넣지 않습니다.

- [GitHub Pre-release와 다운로드](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0-rc.1)
- [변경점](RELEASE_NOTES.md) · [이전/복귀](MIGRATION.md) · [검증 범위](TESTING.md)
- [알려진 제한](KNOWN_ISSUES.md) · [문제 해결](TROUBLESHOOTING.md)

## Arduino IDE 설치

1. Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 아래 RC URL을 추가합니다.
2. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`의 **0.5.0-rc.1**을 명시적으로 선택합니다.
3. Post-install 실행 확인을 승인하고 최종 `Nordic prerequisite installation PASS`를 확인합니다.
4. `NU54DK (nRF54L15, Zephyr)` 보드를 선택하고 예제의 Feature set을 맞춥니다.
5. 처음에는 `Standard peripherals`의 `Blink`를 Verify·Upload합니다.
   이후 고급 예제는 폴더 내 설정 파일과 README를 함께 사용합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.1/package_nucode_nu54dk_rc_index.json
```

설치에는 인터넷 연결과 SDK·Toolchain을 위한 디스크 공간이 필요합니다.
NCS v3.4.0과 Windows toolchain `dcbdc366a1`을 사용하며 임의의 다른 SDK로 바꾸지 않습니다.
한 Arduino data directory에서 같은 core의 stable과 RC를 전환하므로 기존 스케치·설정은 별도로 보존합니다.

## Arduino CLI 설치

PowerShell에서 사용할 수 있는 명령입니다. 설치 작업을 실행하는 예시이며 검증 결과 자체는 아닙니다.

```powershell
$RcIndex = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.1/package_nucode_nu54dk_rc_index.json"
arduino-cli core update-index --additional-urls $RcIndex
arduino-cli core install nucode:zephyr@0.5.0-rc.1 --additional-urls $RcIndex --run-post-install
arduino-cli core list
```

목록에 `nucode:zephyr 0.5.0-rc.1`이 표시되는지 확인합니다.
기본 FQBN은 `nucode:zephyr:nu54dk`이며
[프로필·예제 안내](<../../02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)에서 예제별 구성을 확인합니다.
`NU54DK.coreVersion()`의 `0.4.1-dev`는 개발 소스 식별자이고 설치 패키지 버전이 아닙니다.

## 공개 package identity

| 항목 | 고정 값 |
| --- | --- |
| Package / tag | `0.5.0-rc.1` / `v0.5.0-rc.1` |
| Source commit | `7786984a186980f6220271cd506636e4564bc55d` |
| SDK | NCS v3.4.0 / Zephyr 4.4.0 |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 설치 예제 | 16개 library · 113개 |
| ZIP SHA-256 | `e4e2932620e93a2af9bd5477b61e42bd835be24d8a10b34e3811906dd2df5e4f` |

정확한 자산 목록·크기·hash·공개 다운로드 결과는
[공개 기록](<../../04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)과 Release의 manifest·checksums를 따릅니다.
후속 브랜치 이력 정리나 문서 보완은 이 tag·source·공개 자산을 바꾸지 않습니다.

## 사용 범위

RC는 지원 역할 안의 ISO·LE Audio·CTE 송신·CS/RAS와 오류·복구를 검증했습니다.
제품 SDC의 DF IQ RX·AoD, 외장 Audio hardware, 상용 peer 및 모든 기능의 동시 조합까지
검증했다는 뜻은 아닙니다. 설치 전 [Known issues](KNOWN_ISSUES.md)를 확인하십시오.
