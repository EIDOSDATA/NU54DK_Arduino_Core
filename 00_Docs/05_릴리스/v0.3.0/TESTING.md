# NU54DK Arduino Core v0.3.0 설치와 시험

## 기본 확인

1. Stable Boards Manager URL로 `nucode:zephyr@0.3.0`을 설치합니다.
2. `NU54DK (nRF54L15, Zephyr)`와 `Standard peripherals`를 선택합니다.
3. `Blink`를 clean compile하고 CMSIS-DAP/pyOCD로 upload합니다.
4. Arduino가 표시하는 maximum program storage가 1,490,944 byte인지 확인합니다.
5. 필요한 예제를 열어 해당 hardware와 profile에서 확인합니다.

## 설치 예제 29개

| Library | 예제 |
| --- | --- |
| `NUCODE_NU54DK` | AnalogChannels, AnalogReadA0, AnalogResolution, Blink, BoardInfo, CounterAlarm, DynamicPWM, InterruptButton, PWMFade, Serial1RuntimePins, SerialEcho, SettingsStorage, SPI00RuntimePins, SystemOffWake, ToneOutput, WatchdogBasic, WireRuntimePins |
| `Wire` | WirePmicId |
| `SPI` | SPITransaction |
| `Servo` | Sweep |
| `NUCODE_BLE` | CustomGattCentral, CustomGattPeripheral, GAPCentral, GAPPeripheral, NUSCentral, NUSPeripheral |
| `NUCODE_BLE_Security` | SecureKeyboard |
| `EEPROM` | EEPROMPersistence |
| `LittleFS` | LittleFSPersistence |

Standard profile 예제는 22개, BLE profile 예제는 7개입니다. 정식 승격 gate에서 설치된 package의
29개 예제를 모두 compile했으며 Blink를 실제 NU54DK에 pyOCD로 upload했습니다.

## Arduino CLI smoke test

```powershell
$StableIndex = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json'
$BuildPath = Join-Path $PWD 'build\blink'
$Sketch = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.3.0\libraries\NUCODE_NU54DK\examples\Blink"

arduino-cli core update-index --additional-urls $StableIndex
arduino-cli core install nucode:zephyr@0.3.0 --run-post-install --additional-urls $StableIndex
arduino-cli compile --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
arduino-cli upload --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
```

여러 CMSIS-DAP가 연결돼 있으면 compile과 upload에 같은 board option을 추가하고 upload field에
대상 UID를 지정합니다. UID를 log나 Issue에 공개하지 마십시오.

## 기능별 실기 주의

- UART/I2C/SPI/ADC/PWM/Servo는 문서의 승인 pin과 배선을 사용합니다.
- `WirePmicId`는 온보드 BQ25186을 read-only로 확인합니다.
- Storage 예제는 format/reset 전 데이터 삭제 범위를 확인합니다.
- BLE Central/Peripheral 시험은 두 보드 또는 호환 peer가 필요합니다.
- `SecureKeyboard`는 Windows pairing UI와 실제 key 입력 확인이 필요합니다.
- System OFF 시험 전 active debugger가 저전력·reset cause에 미치는 영향을 제거합니다.

검증 범위와 exact evidence는
[v0.3.0 정식 공개 기록](<../../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)을
기준으로 합니다.
