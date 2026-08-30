# NU54DK Arduino Core v0.2.0 릴리스 문서

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.2.0-INDEX-001 |
| 대상 후보 | `v0.2.0-rc.2` |
| 현재 상태 | **RC2 Public Prerelease 공개·설치본 gate PASS** |
| M18 최종 상태 | `rc2-public-validation-pass-awaiting-stable-approval` |
| 현재 정식 버전 | `v0.1.0` 유지 |
| 공식 사용자 OS | Windows 10/11 x64 |
| 지원 보드 | NU54DK / `nucode:zephyr:nu54dk` |
| 작성자 | Quantum / NUCODE |

`v0.2.0-rc.2`는 M12부터 M17까지의 구현과 RC1 공개 설치본 검증에서 발견한 수정사항을 묶는
`v0.2.0` 후속 release candidate다. exact commit의 package와 12개 asset은 GitHub Public
Prerelease로 공개됐다. 격리 Boards Manager 설치·`post_install`, 설치본 예제 14/14 compile,
Blink 명시 UID upload와 대응 UART READY까지 PASS했다.

RC2 설치본의 두 보드 BLE NUS 공개 예제는 startup과 Peripheral↔Central 고유 payload 원문
연속 수신을 양방향으로 통과했고 RC1 상태 로그 삽입이 재현되지 않았다. 이 transparent bridge
HIL은 기존 M16의 frame boundary·disconnect/reconnect 전문 HIL과 범위를 구분한다. 이 RC는
정식 `v0.2.0`이나 GitHub `latest`가 아니며, 일반 stable은 계속 `v0.1.0`이다.

## 1. Exact 기반

| 구성 | 고정 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Board repository | `https://github.com/Nucode01/NU54DK_Zephyr_DTS` |
| Core repository | `https://github.com/EIDOSDATA/NU54DK_Arduino_Core` |
| RC2 tag/commit | `v0.2.0-rc.2` / `1c5dcecfc0dba2ef25e06963dcba61c63f454db9` |
| Public Release | `https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.2.0-rc.2` |
| Asset 수 | 12 |
| RC index SHA-256 | `fa73f3ba34ecfc84984aa836f423cb0d31a2ce56518fac6c56b99ec8dd70f89b` |
| RC2 ZIP SHA-256 | `753712094ff2500d8ab4b6184a27b2a0ad44bfece0236bd3788d01cd9c1ad7af` |

M18 plan, evidence manifest와 공개 Release asset이 최종 Core commit, 위 board gitlink,
package asset의 byte 크기와 SHA-256을 고정한다.

## 2. 문서 구성

- [릴리스 노트](./RELEASE_NOTES.md): M12~M17의 추가 기능과 검증 경계
- [알려진 제약](./KNOWN_ISSUES.md): 지원하지 않거나 수동 검증이 남은 항목
- [마이그레이션](./MIGRATION.md): 설치, 업그레이드, downgrade와 제거
- [문제 해결](./TROUBLESHOOTING.md): Boards Manager, build, pyOCD와 J-Link 진단

위 네 파일은 GitHub Draft Release에 독립 asset으로 복사된다. 각 문서는 저장소의 상대 link에
의존하지 않고 단독으로 읽을 수 있게 작성한다. 이 `README.md`는 저장소 내 문서 안내이며
Draft asset allowlist에는 포함하지 않는다.

## 3. 자동화 범위와 수동 승인 경계

| 단계 | 상태와 책임 |
| --- | --- |
| M12~M17 구현·회귀 | 완료; 세부 결과는 각 마일스톤 기준선에 보존 |
| package/SBOM/license/checksum 생성 | M18 exact commit에서 자동 실행 |
| 두 번 독립 package 생성과 byte 비교 | M18 자동 gate |
| Untagged GitHub Draft object와 asset 생성 | 완료; public 전환 전 내부 단계로 보존 |
| Remote Draft ID·asset 재다운로드와 SHA-256 확인 | 완료 |
| RC1 공개 Boards Manager 설치·실기 | **완료 — 교정 항목 2건 발견** |
| RC2 package·Draft·asset 생성과 Public Prerelease 전환 | **완료 — tag commit 및 12개 asset 확인** |
| RC2 공개 Boards Manager 설치·`post_install` | **PASS** |
| RC2 설치본 예제 compile | **14/14 PASS** |
| RC2 설치본 명시 UID upload·UART READY | **PASS** |
| RC2 설치본 BLE NUS 양방향 transparent bridge·로그 회귀 | **PASS** |
| `v0.2.0` stable 공개 | **별도 사용자 승인 없이는 실행하지 않음** |

Draft와 staged ZIP 절차는 공개 전 검증 경계의 역사로 보존한다. 현재 RC2는 공개 Release의
RC 전용 index로 설치할 수 있다. stable root index와 RC index는 계속 분리한다.

## 4. 공개 경계

- `v0.1.0` tag, Release와 `package_nucode_nu54dk_index.json`은 계속 정식 공개 기준선이다.
- [`v0.2.0-rc.2`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.2.0-rc.2)는
  실제 Git tag와 12개 asset을 가진 Public Prerelease다.
- `v0.2.0-rc.2`는 candidate이며 `latest` Release가 아니다. `latest`는 계속 `v0.1.0`이다.
- RC는 별도 `package_nucode_nu54dk_rc_index.json`을 사용한다.
- M18 RC 생성과 공개는 `v0.1.0` stable index, stable tag 또는 기존 Release를 수정하지 않았다.
- Public Prerelease를 stable로 승격하는 작업은 프로젝트 소유자의 별도 승인 사항이다.

## 5. 공개 전 Draft/staged 검증 경계

이 단계는 exact candidate ZIP의 Arduino platform 동작을 확인하지만 Boards Manager 설치 lifecycle과
`post_install` callback을 검증하지 않는다.

1. 기존 NU54DK Core와 분리된 Windows 10/11 x64 검증 환경과 새 Sketchbook을 사용한다.
2. exact ZIP과 checksum/manifest sidecar가 M18 plan/evidence와 일치하는지 확인한다.
3. ZIP의 top-level platform 내용을 새 Sketchbook의 `hardware/nucode/zephyr` 아래에 수동 추출한다.
4. Arduino IDE에서 `NU54DK (nRF54L15, Zephyr)`와 두 Feature set을 열거하는지 확인한다.
5. package 사용자 예제 14개가 `파일 → 예제`에 나타나는지 확인한다.
6. Blink, 대표 Board/System 예제와 NUS 역할 예제를 clean compile한다.
7. 온보드 CMSIS-DAP V2와 pyOCD로 실제 NU54DK에 upload하고 firmware 실행을 확인한다.
8. 이 결과를 `staged ZIP PASS`로만 기록하고 Boards Manager 설치 PASS라고 쓰지 않는다.

## 6. Public RC Boards Manager 검증

공개 RC index를 사용한 현재 결과는 다음과 같다.

1. 격리 Boards Manager 환경에서 `0.2.0-rc.2` 설치와 `post_install`을 통과했다.
2. 설치된 package 사용자 예제 14개를 모두 compile해 14/14 PASS를 확인했다.
3. `CMSIS-DAP with UID (pyOCD)` 경로로 설치본 Blink를 지정 보드에 upload했다.
4. 대응 UART에서 설치본 M8 image의 `NUCODE_M8_UPLOAD_READY`를 확인했다.
5. 실제 UID는 문서와 공개 evidence에 기록하지 않았다.
6. RC2 설치본 NUS Peripheral↔Central 고유 payload 원문 연속 수신과 RC1 상태 로그 삽입 회귀를
   양방향으로 통과했다.
7. 이번 공개 예제 HIL은 M16의 frame boundary·disconnect/reconnect 전문 HIL을 재실행한 것이 아니다.

공개 RC index와 ZIP SHA-256은 Exact 기반 표 및
[M18 공개 검증 기록](<../../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)에
고정한다. 프로젝트 소유자 승인 뒤에만 `v0.2.0` stable 공개를 결정한다.

외부 Adafruit LSM6DS3TR-C compatibility fixture와 Zephyr/NCS direct-build fixture는 위 14개
package 사용자 예제에 포함되지 않는다. 이들을 Arduino IDE 예제 메뉴에서 찾지 못하는 것은
누락이 아니다.
