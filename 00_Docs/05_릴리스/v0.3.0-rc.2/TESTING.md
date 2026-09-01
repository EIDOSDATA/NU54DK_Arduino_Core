# GitHub v0.3.0-rc.2 설치와 시험

> **현재 RC2는 공개 전입니다.** 아래 URL의 404와 Boards Manager에서 version이 보이지 않는
> 상태는 공개 전에는 정상입니다. 소유자가 Public Prerelease를 알리기 전에는 설치 시험을
> 시작하지 마십시오.

## 1. GitHub RC 자산 확인

공개 뒤 다음 고정 URL을 사용합니다.

| 목적 | URL |
| --- | --- |
| Release 페이지 | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0-rc.2> |
| Boards Manager RC index | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json> |
| Core archive | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/nucode-nu54dk-zephyr-0.3.0-rc.2.zip> |

Release 페이지가 `Pre-release`로 표시되고 다음 7개 자산만 있는지 확인합니다.

1. `nucode-nu54dk-zephyr-0.3.0-rc.2.zip`
2. `nucode-nu54dk-zephyr-0.3.0-rc.2.CHECKSUMS.sha256`
3. `nucode-nu54dk-zephyr-0.3.0-rc.2.license-inventory.json`
4. `nucode-nu54dk-zephyr-0.3.0-rc.2.release-manifest.json`
5. `nucode-nu54dk-zephyr-0.3.0-rc.2.THIRD_PARTY_NOTICES.md`
6. `nucode-nu54dk-zephyr-0.3.0-rc.2.spdx.json`
7. `package_nucode_nu54dk_rc_index.json`

RC ZIP이나 index를 직접 수정하지 마십시오. 공개 자산을 내려받은 같은 directory에서 다음처럼
checksum을 비교합니다.

```powershell
Get-FileHash .\nucode-nu54dk-zephyr-0.3.0-rc.2.zip -Algorithm SHA256
Get-Content .\nucode-nu54dk-zephyr-0.3.0-rc.2.CHECKSUMS.sha256
```

실제 SHA-256은 공개 Release 자산과 M22 RC2 검증 기록을 기준으로 합니다. 이 문서에는 예상
hash를 미리 적지 않습니다.

## 2. Arduino IDE에 RC2 index 추가

1. Arduino IDE 2.x를 엽니다. 기준 검증 version은 공개 gate에서 확정합니다.
2. `File → Preferences`를 엽니다.
3. RC1 per-tag URL을 등록했다면 제거하고 아래 RC2 URL로 교체합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json
```

4. Stable URL이 이미 있다면 그대로 둡니다.
5. `Tools → Board → Boards Manager`에서 `NUCODE NU54DK Zephyr Boards`를 검색합니다.
6. Version `0.3.0-rc.2`를 명시적으로 선택하고 설치합니다.
7. Post-install 실행 확인이 나오면 승인하고 Nordic prerequisite 설치가 끝날 때까지 기다립니다.
8. Arduino IDE를 다시 시작합니다.

설치 완료 후 Boards Manager에 `0.3.0-rc.2 installed`가 표시되는지 확인합니다. 첫 설치는 NCS와
Toolchain을 내려받으므로 오래 걸릴 수 있습니다. 기존의 검증된 같은 prerequisite가 있으면
재사용될 수 있습니다.

## 3. 보드와 Profile 확인

| Arduino IDE 메뉴 | 기본 선택 |
| --- | --- |
| Board | `NU54DK (nRF54L15, Zephyr)` |
| Feature set | `Standard peripherals` |
| Upload probe | `CMSIS-DAP (pyOCD)` — probe 한 대 |

Probe가 둘 이상이면 임의 자동 선택을 사용하지 말고 `CMSIS-DAP with UID (pyOCD)`를 선택해
시험 대상 UID를 입력합니다. UID를 결과 보고서나 공개 Issue에 그대로 올리지 마십시오.

## 4. 설치 예제 29개 확인

Arduino IDE의 `File → Examples`에서 다음 bundled library와 예제를 확인합니다.

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

Standard 예제는 22개, BLE 예제는 7개, 합계 29개입니다. 내부 CI/HIL fixture는 Arduino IDE
사용자 예제가 아니므로 메뉴에 나타나지 않습니다. Standard 예제는
`Feature set = Standard peripherals`, BLE 7개 예제는 `Feature set = BLE NUS`를 선택해
compile·upload합니다.

## 5. 기본 compile·upload 시험

1. `NUCODE NU54DK → Blink`를 엽니다.
2. `Verify`로 clean compile합니다.
3. NU54DK를 USB로 연결하고 `Upload`합니다.
4. Onboard LED가 점멸하는지 확인합니다.
5. `SerialEcho`를 Upload하고 CMSIS-DAP VCOM을 115200 8N1로 열어 왕복을 확인합니다.

Upload 실패 때 mass erase 또는 recover를 먼저 실행하지 말고
[Troubleshooting](./TROUBLESHOOTING.md)을 따릅니다.

## 6. Storage 시험

Storage 시험은 기존 데이터를 변경합니다. 중요한 EEPROM, Settings 또는 filesystem 데이터가 없는
시험 보드에서 진행하십시오.

### EEPROMPersistence

1. `Standard peripherals`에서 예제를 compile·upload합니다.
2. VCOM 115200 8N1에서 boot count 출력이 증가하는지 확인합니다.
3. 보드 reset 뒤 값이 유지되는지 확인합니다.
4. `commit()` 실패나 `EEPROMError`가 없는지 기록합니다.

### LittleFSPersistence

1. 예제를 compile·upload합니다.
2. 처음 mount가 실패하면 즉시 format하지 말고 출력과 기존 데이터 필요 여부를 확인합니다.
3. 데이터 삭제를 승인한 시험 보드에서만 예제 지침에 따라 명시적 format을 수행합니다.
4. Reset 뒤 file 기반 count가 유지되는지 확인합니다.

## 7. 주변장치·BLE 확인 경계

- 선행 AC-02B 3-wire fixture 결과를 사용자의 다른 wiring, 전원과 pin 조합에 확대하지 않습니다.
- BLE NUS/GAP/GATT 예제는 서로 다른 두 NU54DK 또는 해당 역할을 수행하는 검증 peer가
  필요합니다.
- SecureKeyboard는 Windows Bluetooth UI의 pairing과 실제 key 입력을 사람이 확인해야 합니다.
- 단일 예제 성공을 모든 pin, peer, OS와 profile의 제품 인증으로 확대하지 않습니다.

## 8. 결과 기록

Issue 또는 시험 기록에는 다음을 남깁니다.

- Core `0.3.0-rc.2`, Arduino IDE/CLI와 Windows version
- FQBN, Feature set과 예제 이름
- Compile PASS/FAIL, Flash/RAM 표시
- Upload PASS/FAIL와 사용한 probe 종류 — 전체 UID는 제거
- 실제 board 출력과 처음 실패한 단계
- Storage 시험이면 reset 횟수와 기존 데이터 삭제 승인 여부
- BLE/주변장치 시험이면 board 수, wiring, peer 역할과 전원 조건

RC2가 공개된 뒤 문제는 [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)에
보고할 수 있습니다. Stable로 복귀하려면 [Migration](./MIGRATION.md)의 downgrade 절차를
따릅니다.
