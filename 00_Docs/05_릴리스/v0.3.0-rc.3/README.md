# NU54DK Arduino Core v0.3.0-rc.3 릴리스 후보

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.3.0-rc.3-INDEX-001 |
| 대상 버전 | `v0.3.0-rc.3` / package version `0.3.0-rc.3` |
| 채널 | 별도 RC Boards Manager index를 사용하는 Public GitHub Prerelease |
| 현재 정식 버전 | `v0.2.0` |
| 공식 사용자 OS | Windows 10/11 x64 |
| 지원 보드 | NU54DK / `nucode:zephyr:nu54dk` |
| 현재 상태 | 공개 검증 수용 / `v0.3.0` stable 인계 기준 |
| 작성자 | Quantum / NUCODE |

`v0.3.0-rc.3`는 RC2에서 발견한 RRAM 표시와 실제 linker 경계의 불일치를 교정하는 후보입니다.
Loader가 없는 현재 실행 구조에 맞춰 사용하지 않던 boot reservation과 두 번째 image slot을 기본
layout에서 제거했습니다. Application은 저장소를 제외한 RRAM 전체인
`0x000000..0x16c000`, 1,490,944 byte(1,456 KiB)를 사용합니다.

LittleFS 32 KiB와 Settings/ZMS 36 KiB의 주소는 RC2와 동일하게 유지합니다. MCUboot/DFU
dual-slot은 실제 update·rollback 기능과 함께 `v0.4.0` M24의 검증된 고급 Memory layout으로
제공할 계획이며 RC3 기본값에는 포함하지 않습니다.

## 문서

- [Release notes](./RELEASE_NOTES.md): RC3 교정 범위와 이어받은 기능
- [Testing](./TESTING.md): GitHub 자산, Arduino IDE 설치와 시험 절차
- [Migration](./MIGRATION.md): Stable/RC2에서 RC3로 이동하고 복귀하는 절차
- [Known issues](./KNOWN_ISSUES.md): 지원 경계와 제외 범위
- [Troubleshooting](./TROUBLESHOOTING.md): 설치·build·upload·memory·storage·BLE 진단

## 고정 기술 기반

| 구성 | 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| Loader | 사용하지 않음 — Sketch를 포함한 전체 Zephyr image |
| Upload 기본 경로 | 온보드 CMSIS-DAP V2 + pyOCD |

RC3 exact Core commit, board package gitlink, tag, archive와 evidence는
[M22 RC3 검증·stable 인계 기록](<../../04_검증 기록/31_M22_v0.3.0_rc3_검증과_stable_인계.md>)에
고정했습니다. RC1·RC2 tag와 자산은 변경하거나 RC3 byte로 덮어쓰지 않습니다.

## RC3 기본 RRAM 계약

| 영역 | 범위 | 크기 |
| --- | --- | ---: |
| Loaderless application | `0x000000..0x16c000` | 1,490,944 byte / 1,456 KiB |
| Arduino LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

Arduino maximum Sketch size는 `1490944` byte입니다. Standard와 BLE profile 모두
`CONFIG_USE_DT_CODE_PARTITION=y`를 사용하고, Build Adapter는 생성된 Devicetree code partition과
실제 linker map의 FLASH origin/length가 같은지 artifact 공개 전에 검사합니다.

이 계약은 **기본 loaderless layout 하나**를 뜻합니다. RC3에는 임의 slot 크기 입력 메뉴나
MCUboot/DFU dual-slot preset이 없습니다. 향후 고급 layout도 partition·linker·Arduino size·storage
migration을 하나의 검증 단위로 제공하며 overlay 한 파일만 바꿔 정식 지원을 주장하지 않습니다.

## 이어받은 Package 구성과 실기 기준선

- Arduino library 8개
- 설치 예제 29개: Standard 22개, BLE 7개
- EEPROM mirror 1024 byte
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 경로
- AC-02B exact `0b7f892` 3-wire HIL
  - `Serial1` UART30 보조 VCOM 송수신과 `end()`/`rebegin()` PASS
  - `Wire` I2C22에서 온보드 BQ25186 `0x6A`, register `0x0C == 0x41` read-only
    100/400 kHz repeated-start와 `end()`/`rebegin()` PASS
  - Local SPI loopback, ADC raw 0/3757과 A0 ADC→PWM 25%/75% handover PASS
- AC-03 exact 두 보드 EEPROM/LittleFS 영속성·손상 거부·복구·정리 PASS

위 AC-02B·AC-03 결과는 선행 exact revision의 실기 증거입니다. RC3 package 검증은 새 source의
memory contract, 전체 예제 compile와 실제 Upload를 별도 gate로 실행하며 과거 PASS를 새 archive
동일성으로 합성하지 않습니다.

## 공개 경계

1. `v0.3.0-rc.3`는 prerelease이며 production stable 선언이 아닙니다.
2. RC3는 해당 tag의 `package_nucode_nu54dk_rc_index.json`만 사용합니다.
3. Stable index, `v0.2.0`과 과거 RC tag·자산을 수정하지 않습니다.
4. RC3 tag와 자산도 공개 뒤 덮어쓰지 않습니다. 추가 수정이 필요하면 새 RC를 만듭니다.
5. RC3 공개 검증 완료 뒤에도 별도 stable package/lifecycle과 프로젝트 소유자 승인이 필요합니다.
