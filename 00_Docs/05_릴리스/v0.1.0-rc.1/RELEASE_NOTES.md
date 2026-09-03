# NU54DK Arduino Core v0.1.0-rc.1 릴리스 노트

> **회수된 Release Candidate:** 공개 뒤 Arduino IDE 2.3.10에서 `post_install` 출력이 gRPC
> UTF-8 문자열로 직렬화되지 않는 결함을 확인했다. 관찰된 재현에서는 설치가 실제 완료됐지만
> IDE가 설치 실패를 표시했다. `v0.1.0-rc.1`은 배포 중단·회수하며 아래 검증 결과는 당시
> artifact의 역사적 증거로만 보존한다. 자세한 내용은
> [배포 중단 기록](WITHDRAWAL.md)을 따른다.

`v0.1.0-rc.1`은 Loader 없이 Sketch와 Zephyr를 하나의 정적 firmware로 만드는 NU54DK 전용
첫 release candidate다. 정식 `v0.1.0`이 아니다. 프로젝트 소유자가 RC의 공개 정보,
라이선스 판단, 알려진 제약과 공개를 승인했으며 stable 공개는 별도 승인 대상이다.

현재 기술 판정은 **M9·M10·M11 완료**, exact RC 필수 gate **8/8 PASS**와
`ready-for-human-approval`이다. 검증 source는
`4a4b1ece622b155ff7300a46bca304df9adfc797`이며, 세부 identity와 evidence checksum은
[M11 릴리스 후보 기준선](<../../04_검증 기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)에 고정했다.
승인 후 [`v0.1.0-rc.1` GitHub Prerelease](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.1.0-rc.1)를
게시하고 9개 asset의 GitHub digest와 재다운로드 SHA-256을 검증했다.

## 주요 기능

- NCS v3.4.0 / Zephyr 4.4.0 기반 Native Full Zephyr build
- Arduino CLI/IDE 공용 `nucode:zephyr:nu54dk` platform recipe
- 고정된 NU54DK DTS board package를 archive 내부에 포함
- Arduino `setup()`/`loop()` runtime과 다중 `.ino` 탭, 자동 prototype, library discovery
- Arduino API와 Zephyr API를 한 Sketch에서 직접 함께 사용
- GPIO, `millis()`/`micros()`/delay, `String`, `Print`, `Stream`
- DAP UART 기반 `Serial`, GPIO edge interrupt
- I2C `Wire`, SPI, A0 ADC, P1.10 PWM
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 Upload/debug
- 결정적 persistent Zephyr build cache, ccache, lock/LRU 및 손상 복구
- Boards Manager package, checksum, SPDX SBOM, license inventory와 사용자 영역 Nordic 설치

## 검증 범위

- host contract/regression test
- NU54DK target ztest/Twister compile 및 HIL
- Arduino CLI 고정 package의 Blink, library, configuration, negative, parallel 및 M6·M7·M8·M9·M11 회귀
- exact RC ZIP으로 빌드한 HEX의 pyOCD 비파괴 Upload 1회와 UART
  `NUCODE_M8_UPLOAD_READY` 확인
- RC와 같은 runtime source fingerprint를 가진 Windows-safe preview의 clean Windows install,
  compile, pyOCD 10회 Upload, upgrade, downgrade, uninstall, reinstall
- archive/index checksum과 exact Core·board revision provenance

이 RC의 `m11-rc-plan.json`과 gate별 evidence를 결합한
`m11-rc-evidence-manifest.json`은 필수 gate 8/8 PASS, 누락·실패 0개를 기록했다. 상태는
`ready-for-human-approval`이며 이후 프로젝트 소유자의 RC 공개 승인을 적용했다. 이 승인은
stable 공개를 자동 승인하지 않는다. source/archive가 바뀌거나 필수 gate가 빠진 다른
후보는 `hold`다.

clean Windows 수명주기는 최종 M10 run에서 `0.0.96`→`0.0.97` preview로 검증했다. importer는 두 preview와
RC가 같은 package runtime source fingerprint를 갖고 M10 target runner byte도 동일한지
검사한다. 따라서 이 증거를 RC ZIP 자체를 clean PC에 직접 설치한 GUI 검증으로 과장하지
않는다. RC 전용 index, 고정 RC package의 compile 회귀와 RC HEX 1회 pyOCD+UART HIL은 최종
원격 M11 gate에서 별도로 검증해 PASS했다. M10 이후 RC commit에는 문서·시험·release automation 경로 변경만 허용하며
package runtime byte가 바뀌면 preview evidence import를 거부한다.

`0.0.94`와 `0.0.95`는 PowerShell 5.1 runner 수정 전에 생성돼 Arduino CLI identity
preflight에서 실패한 immutable 이력이다. 두 preview의 증거는 M11에 계승하지 않는다.

## 호환성 기준

| 항목 | RC 기준 |
| --- | --- |
| 운영체제 | Windows 10/11 x64만 공식 검증 |
| 보드 | NU54DK, nRF54L15 CPUAPP qualifier 하나 |
| NCS | v3.4.0 exact revision |
| Zephyr | 4.4.0 exact revision |
| Toolchain | Nordic bundle `dcbdc366a1` |
| Arduino CLI clean-PC backend | `1.5.2-rc.1` exact binary |
| 기본 probe | 온보드 CMSIS-DAP V2 + bundled pyOCD |

## 업데이트 주의사항

preview에서 RC로 이동할 때 기존 build output을 재사용하지 않는다. 공유 Nordic prerequisite는
정확한 pin이 맞으면 재사용하지만 다른 NCS/Toolchain을 자동 선택하지 않는다. 자세한 절차는
[마이그레이션 안내](MIGRATION.md)와
[Boards Manager 설치 설계](<../../02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)를 따른다.

## 감사와 라이선스

NUCODE 자체 작성 코드는 MIT License다. ArduinoCore-API, NU54DK board package, Zephyr/NCS와
외부 Nordic 도구에는 각 원본 라이선스와 고지가 적용된다. RC artifact의 license inventory는
법률 자문을 대신하지 않으며 stable 공개 전에 최종 검토해야 한다.
