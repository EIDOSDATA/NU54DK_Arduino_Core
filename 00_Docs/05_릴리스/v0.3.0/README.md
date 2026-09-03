# NU54DK Arduino Core v0.3.0

| 항목 | 내용 |
| --- | --- |
| 상태 | **현재 정식 릴리스** |
| Package | `nucode:zephyr@0.3.0` |
| Board/FQBN | NU54DK / `nucode:zephyr:nu54dk` |
| 공식 사용자 OS | Windows 10/11 x64 |
| Release source | `94ee3fec29ba9f86835b6cb3d96ab13ce2cf8c11` |
| Board source | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 작성자 | Quantum / NUCODE |

`v0.3.0`은 NU54DK용 loaderless Arduino Core의 현재 stable입니다. Sketch와 선택한 Arduino
library를 nRF Connect SDK v3.4.0/Zephyr 4.4.0의 전체 image로 빌드하며, 온보드
CMSIS-DAP V2와 pyOCD를 기본 업로드 경로로 사용합니다.

## 설치

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 다음 URL을 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 검색해 `0.3.0`을 설치한 뒤
`NU54DK (nRF54L15, Zephyr)` 보드를 선택합니다. 첫 설치는 고정 NCS와 Toolchain을 Nordic 공식
경로에서 내려받으므로 오래 걸릴 수 있습니다.

## 이 버전의 핵심

- Arduino library 8개와 설치 예제 29개: Standard 22개, BLE 7개
- Connector GPIO, open-drain, level interrupt, pulse/shift API
- `Serial1`, runtime `Wire.setPins()`/`SPI.setPins()`, 확장 ADC·PWM, `tone()`과 Servo
- BLE GAP, 범용 GATT, pairing/bonding, BAS, DIS와 HID keyboard 범위
- 명시적 `commit()`을 사용하는 1,024-byte EEPROM facade
- 전용 32 KiB RRAM partition을 사용하는 LittleFS
- 핀·주변장치 소유권 충돌을 동적 할당 없이 거부하는 runtime manager

함수 이름이 존재한다는 사실만으로 모든 pin, instance, mode 또는 외부 장치가 지원되는 것은
아닙니다. 정확한 범위는 [Arduino API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)와
[알려진 제약](./KNOWN_ISSUES.md)을 함께 확인하십시오.

## 기본 RRAM 계약

| 영역 | 범위 | 크기 |
| --- | --- | ---: |
| Loaderless application | `0x000000..0x16c000` | 1,490,944 byte / 1,456 KiB |
| Arduino LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

Arduino maximum Sketch size, Devicetree code partition과 실제 linker FLASH 경계는 모두
1,490,944 byte입니다. MCUboot/DFU dual-slot은 이 버전에 포함되지 않습니다.

## 고정 공개 자산

| 자산 | 크기 | SHA-256 |
| --- | ---: | --- |
| `nucode-nu54dk-zephyr-0.3.0.zip` | 1,660,169 | `138740bcf6c458992fdb5c8eb81d6110d28b0baee18c68f5d8cb050e2e0e1ecc` |
| `nucode-nu54dk-zephyr-0.3.0.CHECKSUMS.sha256` | 547 | `96f14d3a4b8ac347a172a70cf10150aaf78b1102241ae1e1db29271cbd6550d0` |
| `nucode-nu54dk-zephyr-0.3.0.license-inventory.json` | 15,715 | `30780f4f2dcd4ff4a7364c63256835f62786a96ded14d3033ef96df2ea1fcff7` |
| `nucode-nu54dk-zephyr-0.3.0.release-manifest.json` | 93,251 | `88570fc50bc9a5a76edf6ba5faf905adf1a36bc979da960d891aa23160451a71` |
| `nucode-nu54dk-zephyr-0.3.0.spdx.json` | 174,388 | `8b8fe2c938403aadf2b03c60a0c2f44c8197fefec2f0d44f6e47f1b1e4187411` |
| `nucode-nu54dk-zephyr-0.3.0.THIRD_PARTY_NOTICES.md` | 1,813 | `d748669517ba571923cd86fc7adee164945cdf3c36ba391510121c170507282d` |
| `package_nucode_nu54dk_index.json` | 2,630 | `14fe2eb10b4dd77a219d48060c32c21bdd97370f6d6f8be699d9118f8973e007` |

Stable ZIP의 version-independent runtime payload SHA-256은 RC3와 같은
`658b7014df7faa0dc96c16c6499bf5f4d568ddf8807196c08c6a4cf65e66e835`입니다.

## 문서

- [릴리스 노트](./RELEASE_NOTES.md)
- [마이그레이션](./MIGRATION.md)
- [설치·시험](./TESTING.md)
- [알려진 제약](./KNOWN_ISSUES.md)
- [문제 해결](./TROUBLESHOOTING.md)
- [정식 공개 검증 기록](<../../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)

## 이전 버전 정책

`v0.1.0`, `v0.2.0`과 모든 RC는 신규 수정·지원 대상에서 제외된 역사 버전입니다. 재현성과
검증 감사, 안전한 downgrade를 위해 이미 공개한 tag·Release asset과 stable index 항목은
삭제하거나 덮어쓰지 않습니다. 신규 설치와 문제 보고는 `v0.3.0`을 기준으로 합니다.
