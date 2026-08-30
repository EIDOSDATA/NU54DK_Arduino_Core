# NU54DK Arduino Core v0.2.0 릴리스 문서

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.2.0-INDEX-001 |
| 대상 후보 | `v0.2.0-rc.2` |
| 현재 상태 | **RC2 교정 완료 — package·public RC 재검증 진행** |
| M18 최종 상태 | `rc2-validation-in-progress` |
| 현재 정식 버전 | `v0.1.0` 유지 |
| 공식 사용자 OS | Windows 10/11 x64 |
| 지원 보드 | NU54DK / `nucode:zephyr:nu54dk` |
| 작성자 | Quantum / NUCODE |

`v0.2.0-rc.2`는 M12부터 M17까지의 구현과 RC1 공개 설치본 검증에서 발견한 수정사항을 묶는
`v0.2.0` 후속 release candidate다.
M18 자동화는 exact clean commit에서 package와 문서를 동결하고 GitHub의 **Draft +
Prerelease metadata**를 가진 내부 Release object와 asset까지만 준비한다. Draft는 실제 Git tag를
만들지 않은 untagged 상태일 수 있고, 일반 공개 Release나 정식 `v0.2.0`이 아니다.

프로젝트 소유자는 먼저 별도의 clean Windows에서 exact ZIP을 격리된 Sketchbook hardware
staging에 추출해 14개 package 사용자 예제 열거, 대표 예제 compile, CMSIS-DAP/pyOCD 실제
NU54DK upload와 실행을 확인한다. 이 단계는 Boards Manager 설치 완료가 아니다. staged 결과를
승인해 Draft를 public RC로 전환한 뒤 공개 RC index의 Boards Manager 설치·`post_install`
end-to-end를 별도로 검증하고 다시 승인해야 stable을 검토한다. 그때까지 일반 사용자는 공개
stable `v0.1.0`을 사용한다.

## 1. Exact 기반

| 구성 | 고정 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Board repository | `https://github.com/Nucode01/NU54DK_Zephyr_DTS` |
| Core repository | `https://github.com/EIDOSDATA/NU54DK_Arduino_Core` |

M18 plan과 evidence manifest가 최종 Core commit, 위 board gitlink, package asset의 byte 크기와
SHA-256을 고정한다. 이 문서에는 아직 생성되지 않은 commit이나 artifact hash를 추정해
기록하지 않는다.

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
| Untagged GitHub Draft object와 asset 생성 | M18 자동화의 마지막 변경 단계; 실제 Git tag 생성 없음 |
| Remote Draft ID·asset 재다운로드와 SHA-256 확인 | M18 자동 검증 |
| RC1 공개 Boards Manager 설치·실기 | **완료 — 교정 항목 2건 발견** |
| RC2 package·Draft·asset 생성 | **재검증 진행** |
| RC2 공개 Boards Manager 설치·`post_install` end-to-end | **public RC 전환 뒤 별도 검증 대기** |
| `v0.2.0` stable 공개 | **별도 사용자 승인 없이는 실행하지 않음** |

GitHub Draft asset은 일반 공개 download URL에서 받을 수 없다. 따라서 Draft 상태의 clean
Windows 시험은 인증된 계정으로 받은 exact ZIP과 sidecar를 새 Sketchbook의 격리된
`hardware/nucode/zephyr` staging에 수동 추출해 사용한다. `%LOCALAPPDATA%\Arduino15`를 직접
수정하거나 아직 구현되지 않은 자동 staging script가 있다고 가정하지 않는다. Draft index
URL을 일반 Boards Manager 설치 URL이라고 안내하거나 stable root index를 RC 자산으로
업로드하지 않는다.

## 4. 공개 경계

- `v0.1.0` tag, Release와 `package_nucode_nu54dk_index.json`은 계속 정식 공개 기준선이다.
- Draft의 `v0.2.0-rc.2` 이름은 예약 metadata이며 실제 Git tag가 존재한다는 뜻이 아니다.
- `v0.2.0-rc.2`는 candidate이며 `latest` Release가 아니다.
- RC는 별도 `package_nucode_nu54dk_rc_index.json`을 사용한다.
- M18 Draft 생성은 `v0.1.0` stable index, stable tag 또는 기존 Release를 수정하지 않는다.
- Draft를 public Prerelease 또는 stable로 전환하는 작업은 프로젝트 소유자의 별도 승인 사항이다.

## 5. Draft 단계 clean Windows staged 검증

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

## 6. Public RC 전환 뒤 Boards Manager 검증

프로젝트 소유자가 staged 결과를 승인해 Draft를 public RC로 전환한 뒤 다음을 별도 clean
Windows에서 수행한다.

1. 공개 RC index를 Additional Boards Manager URLs에 등록한다.
2. Core와 candidate prerequisite가 없는 시작 상태를 확인한다.
3. Arduino IDE/CLI로 `0.2.0-rc.2`를 설치하고 `post_install` 완료 응답을 확인한다.
4. board/Feature set/14개 예제 열거, standard/BLE compile와 실제 pyOCD upload를 다시 확인한다.
5. `v0.1.0 → RC` upgrade, RC→`v0.1.0` downgrade, uninstall/reinstall lifecycle을 확인한다.
6. 알려진 제약, license inventory, SBOM과 결과를 프로젝트 소유자가 검토한다.
7. 이 별도 결과를 승인한 뒤에만 `v0.2.0` stable 공개를 결정한다.

외부 Adafruit LSM6DS3TR-C compatibility fixture와 Zephyr/NCS direct-build fixture는 위 14개
package 사용자 예제에 포함되지 않는다. 이들을 Arduino IDE 예제 메뉴에서 찾지 못하는 것은
누락이 아니다.
