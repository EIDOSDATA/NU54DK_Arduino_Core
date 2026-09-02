# GitHub v0.3.0-rc.3 설치와 시험

> `v0.3.0-rc.3`는 production stable이 아닌 공개 Release Candidate입니다. 아래 불변
> per-tag index를 사용하십시오.

## 1. GitHub RC 자산 확인

| 목적 | URL |
| --- | --- |
| Release 페이지 | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0-rc.3> |
| Boards Manager RC index | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.3/package_nucode_nu54dk_rc_index.json> |
| Core archive | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.3/nucode-nu54dk-zephyr-0.3.0-rc.3.zip> |

Release 페이지가 `Pre-release`로 표시되고 다음 7개 자산이 있는지 확인합니다.

1. `nucode-nu54dk-zephyr-0.3.0-rc.3.zip`
2. `nucode-nu54dk-zephyr-0.3.0-rc.3.CHECKSUMS.sha256`
3. `nucode-nu54dk-zephyr-0.3.0-rc.3.license-inventory.json`
4. `nucode-nu54dk-zephyr-0.3.0-rc.3.release-manifest.json`
5. `nucode-nu54dk-zephyr-0.3.0-rc.3.THIRD_PARTY_NOTICES.md`
6. `nucode-nu54dk-zephyr-0.3.0-rc.3.spdx.json`
7. `package_nucode_nu54dk_rc_index.json`

RC ZIP의 SHA-256은 같은 Release의 checksum 파일과 비교합니다.

```powershell
Get-FileHash .\nucode-nu54dk-zephyr-0.3.0-rc.3.zip -Algorithm SHA256
Get-Content .\nucode-nu54dk-zephyr-0.3.0-rc.3.CHECKSUMS.sha256
```

값이 다르면 설치하지 말고 파일을 다시 내려받습니다. 공개 뒤 tag나 자산을 수정하지 않습니다.

## 2. Arduino IDE에 RC3 index 추가

1. Arduino IDE 2.x를 엽니다. 기준 version은 2.3.10입니다.
2. `File → Preferences`를 엽니다.
3. 과거 RC per-tag URL을 등록했다면 제거합니다.
4. 다음 RC3 URL을 추가합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.3/package_nucode_nu54dk_rc_index.json
```

5. `Tools → Board → Boards Manager`에서 `NUCODE NU54DK Zephyr Boards`를 검색합니다.
6. Version `0.3.0-rc.3`를 명시적으로 선택하고 설치합니다.
7. Post-install 실행을 승인하고 Nordic prerequisite 설치가 끝날 때까지 기다립니다.
8. Arduino IDE를 다시 시작합니다.

## 3. 보드와 Profile 확인

| Arduino IDE 메뉴 | 기본 선택 |
| --- | --- |
| Board | `NU54DK (nRF54L15, Zephyr)` |
| Feature set | `Standard peripherals` |
| Upload probe | `CMSIS-DAP (pyOCD)` — probe 한 대 |

Probe가 둘 이상이면 `CMSIS-DAP with UID (pyOCD)`를 선택해 시험 대상 UID를 입력합니다. 전체
UID는 공개 결과나 Issue에서 제거합니다.

## 4. 메모리 계약 시험

1. 빈 Sketch 또는 `Blink`를 `Standard peripherals`로 clean compile합니다.
2. Arduino 출력이 다음 maximum program storage를 표시하는지 확인합니다.

```text
Maximum is 1490944 bytes
```

3. 같은 Sketch를 BLE profile로 compile해 maximum 값이 동일한지 확인합니다.
4. Build log에 `[NU54:E_MEMORY_LAYOUT]`가 없고 ELF·HEX·BIN이 생성되는지 확인합니다.
5. 실제 NU54DK에 Blink를 Upload하고 reset 뒤 `0x000000`에서 정상 boot하는지 LED로 확인합니다.

712,704 byte가 표시되면 과거 RC가 선택됐거나 package cache가 갱신되지 않은 것입니다. 단순히
`boards.txt` 숫자만 고치지 말고 [Troubleshooting](./TROUBLESHOOTING.md)을 따릅니다.

## 5. 설치 예제 29개 확인

| Library | 수 | 예제 |
| --- | ---: | --- |
| NUCODE NU54DK | 17 | AnalogChannels, AnalogReadA0, AnalogResolution, Blink, BoardInfo, CounterAlarm, DynamicPWM, InterruptButton, PWMFade, Serial1RuntimePins, SerialEcho, SettingsStorage, SPI00RuntimePins, SystemOffWake, ToneOutput, WatchdogBasic, WireRuntimePins |
| Wire | 1 | WirePmicId |
| SPI | 1 | SPITransaction |
| Servo | 1 | Sweep |
| EEPROM | 1 | EEPROMPersistence |
| LittleFS | 1 | LittleFSPersistence |
| NUCODE BLE | 6 | CustomGattCentral, CustomGattPeripheral, GAPCentral, GAPPeripheral, NUSCentral, NUSPeripheral |
| NUCODE BLE Security | 1 | SecureKeyboard |

Standard 22개는 `Standard peripherals`, BLE 7개는 `BLE NUS`에서 compile합니다. 내부 CI/HIL
fixture는 Arduino IDE 예제가 아닙니다.

## 6. UART와 I2C 확인

RC3에서 API 구현은 RC2에서 바뀌지 않았지만 memory-layout 변경이 전체 image link에 영향을 주므로
대표 경로를 회귀 확인합니다.

### UART

1. `SerialEcho`를 Upload하고 기본 CMSIS-DAP VCOM을 115200 8N1로 열어 왕복을 확인합니다.
2. `Serial1RuntimePins`는 NU54DK 조립 상태에서 연결된 CMSIS-DAP 보조 VCOM을 사용합니다.
3. 예제 안내에 따라 송수신, `end()` 뒤 재시작과 다시 송수신을 확인합니다.

선행 AC-02B 실기는 UART30 보조 VCOM exact echo와 `end()`/`rebegin()`을 PASS했습니다. 보조
VCOM route는 보드 solder bridge/조립 조건에 따라 사용할 수 있으므로 실패 시 임의 GPIO로
바꾸기 전에 schematic과 [주변장치 API](<../../03_펌웨어 설계/03_주변장치_API.md>)를 확인합니다.

### I2C

1. `Wire → WirePmicId` 또는 `NUCODE NU54DK → WireRuntimePins`를 Upload합니다.
2. 기본 SDA P1.2, SCL P1.3과 온보드 BQ25186 address `0x6A`를 사용합니다.
3. 100 kHz와 400 kHz read-only transaction, repeated-start와 `end()`/`rebegin()` 결과를
   확인합니다.
4. ID register `0x0C`에서 `0x41`을 읽으면 선행 HIL과 같은 기본 경로입니다.

이 시험은 PMIC register를 쓰지 않으며 Wire target/slave, `requestFrom(..., false)`나 모든 외부
sensor를 검증하지 않습니다.

## 7. Storage와 BLE 확인

- Storage 시험 전 EEPROM, Settings와 LittleFS 데이터를 백업합니다.
- `EEPROMPersistence`에서 `commit()`과 reset 영속성을 확인합니다.
- `LittleFSPersistence`는 먼저 `begin(false)`로 mount하고, 데이터 삭제를 승인한 시험 보드에서만
  format합니다.
- BLE NUS/GAP/GATT 예제는 서로 다른 두 NU54DK 또는 검증 peer가 필요합니다.
- `SecureKeyboard`는 Windows Bluetooth UI의 pairing과 실제 key 입력을 사람이 확인합니다.

## 8. 결과 기록

- Core `0.3.0-rc.3`, Arduino IDE/CLI와 Windows version
- FQBN, Feature set과 예제 이름
- Compile PASS/FAIL, FLASH/RAM 사용량과 maximum `1490944` 표시
- Upload PASS/FAIL와 probe 종류 — 전체 UID 제거
- UART이면 VCOM 역할·baud·end/rebegin, I2C이면 address·속도·register·read 값
- Storage이면 reset 횟수와 데이터 삭제 승인 여부
- BLE이면 board 수, 역할과 pairing 상태

문제는 [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)에 보고할 수
있습니다. Stable로 복귀하려면 [Migration](./MIGRATION.md)을 따릅니다.
