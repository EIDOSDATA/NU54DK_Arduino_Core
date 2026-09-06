# NU54DK Arduino Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stable: v0.3.0](https://img.shields.io/badge/stable-v0.3.0-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](https://github.com/nrfconnect/sdk-nrf)
[![Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml)
[![Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml)

NU54DK에서 Arduino Sketch를 **Loader 없는 전체 Zephyr firmware**로 빌드하는 Arduino Core입니다.
Sketch와 Arduino library를 nRF Connect SDK build graph에 통합해 ELF·HEX·BIN을 만들고, 온보드
CMSIS-DAP V2와 pyOCD로 업로드합니다.

| 항목 | 현재 기준 |
| --- | --- |
| 정식 버전 | [`v0.3.0`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0) |
| 지원 보드 | NU54DK / nRF54L15 CPUAPP |
| Arduino FQBN | `nucode:zephyr:nu54dk` |
| SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 사용자 환경 | Windows 10/11 x64, Arduino IDE 2.x |
| 기본 업로드 | 온보드 CMSIS-DAP V2 + pyOCD |
| 기본 메모리 | Application 1,456 KiB + LittleFS 32 KiB + Settings/ZMS 36 KiB |
| 배포 구성 | Arduino library 8개, 설치 예제 29개 |

## 빠른 시작

### 1. 준비물

- Windows 10/11 x64
- Arduino IDE 2.x
- 인터넷 연결과 NCS/Toolchain을 저장할 디스크 공간
- NU54DK와 데이터 통신이 가능한 USB cable

관리자 권한, nRF Connect for Desktop과 nRF Connect for VS Code는 필수 조건이 아닙니다.

### 2. Boards Manager URL 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 다음 주소를 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

### 3. Core 설치

1. `Tools → Board → Boards Manager`를 엽니다.
2. `NUCODE NU54DK Zephyr Boards`를 검색합니다.
3. 버전 `0.3.0`을 설치합니다.
4. post-install 실행 확인이 나오면 승인합니다.
5. NCS v3.4.0과 고정 Toolchain 설치가 끝날 때까지 기다립니다.

첫 설치는 Nordic SDK와 Toolchain을 내려받으므로 오래 걸릴 수 있습니다. 문제가 생기면
[v0.3.0 문제 해결](<./00_Docs/05_릴리스/v0.3.0/TROUBLESHOOTING.md>)을 확인하십시오.

### 4. 보드와 기능 구성 선택

| Arduino IDE 메뉴 | 일반 Sketch | BLE Sketch |
| --- | --- | --- |
| `Tools → Board` | `NU54DK (nRF54L15, Zephyr)` | 동일 |
| `Tools → Feature set` | `Standard peripherals` | `BLE NUS` |
| `Tools → Upload probe` | `CMSIS-DAP (pyOCD)` | 동일 |

일반 사용자는 `prj.conf`나 Devicetree overlay를 직접 작성하지 않아도 됩니다.

### 5. 첫 Blink 업로드

`File → Examples → NUCODE NU54DK → Blink`를 열거나 다음 Sketch를 사용합니다.

```cpp
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
}

void loop()
{
    digitalWrite(LED_BUILTIN, HIGH);
    delay(250);
    digitalWrite(LED_BUILTIN, LOW);
    delay(250);
}
```

NU54DK를 연결한 뒤 `Verify`, `Upload` 순서로 실행합니다. 온보드 LED가 250 ms 간격으로
점멸하면 기본 경로가 정상입니다.

## 포함된 Arduino 예제

| Library | 예제 |
| --- | --- |
| [`NUCODE NU54DK`](./libraries/NUCODE_NU54DK/examples) | AnalogChannels, AnalogReadA0, AnalogResolution, Blink, BoardInfo, CounterAlarm, DynamicPWM, InterruptButton, PWMFade, Serial1RuntimePins, SerialEcho, SettingsStorage, SPI00RuntimePins, SystemOffWake, ToneOutput, WatchdogBasic, WireRuntimePins |
| [`Wire`](./libraries/Wire/examples) | WirePmicId |
| [`SPI`](./libraries/SPI/examples) | SPITransaction |
| [`Servo`](./libraries/Servo/examples) | Sweep |
| [`NUCODE BLE`](./libraries/NUCODE_BLE/examples) | CustomGattCentral, CustomGattPeripheral, GAPCentral, GAPPeripheral, NUSCentral, NUSPeripheral |
| [`NUCODE BLE Security`](./libraries/NUCODE_BLE_Security/examples) | SecureKeyboard |
| [`EEPROM`](./libraries/EEPROM/examples) | EEPROMPersistence |
| [`LittleFS`](./libraries/LittleFS/examples) | LittleFSPersistence |

정식 package에는 Standard profile 22개와 BLE profile 7개, 총 29개 예제가 들어 있습니다.
설치본 29/29 compile과 대표 Blink pyOCD upload를 정식 승격 gate에서 확인했습니다.

## 지원 범위

상태값은 다음 세 가지로만 구분합니다. `지원`은 `v0.3.0`이 선언한 범위를 구현·검증했다는
뜻이고, `부분 지원`은 해당 Arduino API군의 일부 instance나 mode만 제공한다는 뜻입니다.
`미지원`은 공개 API·예제·runtime 검증이 없는 범위입니다.

| 영역 | 상태 | 요약 |
| --- | --- | --- |
| Runtime | 지원 | `setup()`, 반복 `loop()`, C++ 전역 객체 |
| Digital GPIO | 지원 | Connector, LED, button과 open-drain GPIO |
| Time | 지원 | `millis()`, `micros()`, delay, `yield()`와 pulse API |
| GPIO Interrupt | 지원 | Edge·level interrupt와 Arduino callback |
| Serial | 지원 | DAP UART `Serial`과 UART30 기반 `Serial1` |
| Wire/I2C | 부분 지원 | I2C22 master controller와 runtime pin route |
| SPI | 부분 지원 | SPI00 controller와 runtime pin route |
| ADC | 지원 | 공개 analog input 채널과 resolution 변환 |
| PWM/Tone/Servo | 지원 | 동적 PWM, `tone()`과 bundled Servo |
| Storage | 지원 | EEPROM facade와 내부 LittleFS |
| BLE | 지원 | NUS, GAP/GATT, security와 표준 profile |
| Board/System | 지원 | Board identity, WDT, GRTC, Settings와 System OFF |
| Upload/Debug | 지원 | pyOCD 기본, 외장 J-Link 선택 경로 |

<details>
<summary>Core, GPIO, Time과 Serial 세부 범위</summary>

- Digital GPIO와 interrupt는 Variant capability에 등록된 connector·LED·button pin을 사용합니다.
- Level interrupt의 `LOW`/`HIGH`는 GPIOTE가 가능한 pin에서 지원합니다.
- `noInterrupts()`는 Arduino GPIO callback을 막지만 모든 Zephyr system IRQ를 전역 차단하지 않습니다.
- `Serial`은 DAP UART이며 native USB CDC가 아닙니다. `Serial1`은 승인된 UART30 pin route를
  사용합니다.

</details>

<details>
<summary>Wire, SPI, Analog와 Storage 세부 범위</summary>

- Wire는 I2C22 master, 100/400 kHz와 runtime pin 변경을 지원합니다. Target/slave,
  `requestFrom(..., false)`와 `Wire1`은 지원하지 않습니다.
- SPI는 SPI00, mode 0~3, Sketch 소유 chip-select와 runtime pin 변경을 지원합니다. `SPI1`과
  peripheral mode는 지원하지 않습니다.
- ADC는 공개 AIN 채널의 raw code와 resolution 변환을 제공합니다.
- PWM, tone과 Servo는 pin·period·hardware ownership 충돌이 없을 때 동적으로 할당됩니다.
- EEPROM facade는 1,024 byte, 내부 LittleFS partition은 32 KiB입니다.

</details>

<details>
<summary>BLE 세부 범위</summary>

- 지원: NUS Peripheral/Central, GAP Peripheral/Central, 범용 GATT, SMP pairing·bonding,
  BAS, DIS와 HID keyboard
- 미지원: BLE Mesh, ISO, Channel Sounding과 검증되지 않은 multiprotocol

</details>

<details>
<summary>Board/System과 Upload/Debug 세부 범위</summary>

- Board/System은 board identity, watchdog, GRTC, Settings/ZMS와 System OFF를 제공합니다.
- PMIC API는 승인된 register·field만 다루며 write는 매 boot 명시적으로 승인해야 합니다.
- CMSIS-DAP/pyOCD가 기본 Upload 경로입니다. 외장 J-Link는 별도 SEGGER Software, VTref와
  올바른 SWD 배선이 필요합니다.
- 일반 Upload는 mass erase나 recover를 자동 실행하지 않습니다.

</details>

전체 함수별 의미와 pin·mode·오류 계약은
[Arduino API 지원 범위](<./00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를 기준으로 합니다.

## 메모리 구조

| 영역 | 범위 | 크기 |
| --- | --- | ---: |
| Application | `0x000000..0x16c000` | 1,490,944 byte / 1,456 KiB |
| LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

Arduino maximum Sketch size, Devicetree code partition과 Zephyr linker가 같은 경계를 사용합니다.
MCUboot/DFU dual-slot과 signed update/rollback은 `v0.6.0` Security/Update 제품선의 계획 범위입니다.

## 업로드 Probe 선택

- CMSIS-DAP가 한 대면 `CMSIS-DAP (pyOCD)`가 자동 선택합니다.
- 두 대 이상이면 `CMSIS-DAP with UID (pyOCD)`를 선택하고 대상 UID를 명시합니다.
- UID는 COM 번호나 DAPLink drive 문자가 아닙니다.
- 외장 J-Link는 별도 SEGGER Software, VTref와 올바른 SWD 배선이 필요합니다.
- 일반 Upload는 mass erase 또는 recover를 자동 실행하지 않습니다.

Arduino CLI에서 명시적 CMSIS-DAP UID를 사용할 때는 compile과 upload에 같은 board option을
지정합니다.

```powershell
--board-options upload_probe=pyocd_uid `
--upload-field probe_id=<CMSIS-DAP-UID>
```

## 주요 제약과 안전 주의

- 공식 사용자 환경은 Windows 10/11 x64입니다.
- NCS와 Toolchain은 Core ZIP에 재배포하지 않고 Nordic 공식 배포에서 설치합니다.
- Loader, native USB, OTA/DFU와 외부 filesystem은 지원하지 않습니다.
- Storage의 format/reset은 데이터를 삭제할 수 있습니다. version 이동 전에 백업하십시오.
- GPIO interrupt callback 안에서 blocking, heap 할당, `Serial` 또는 `delay()`를 사용하지 마십시오.
- PWM, tone과 Servo는 pin·period·hardware ownership 충돌을 거부할 수 있습니다.
- Servo motor 전원은 GPIO가 아닌 적합한 외부 전원을 쓰고 공통 GND를 연결하십시오.
- BLE 지원은 명시한 GAP/GATT/security/profile 범위이며 전체 BLE interoperability 인증이 아닙니다.
- PMIC write는 매 boot 명시적 승인이 필요합니다. 실제 배터리 전기·온도 보호 검증은 사용자
  조건에서 별도로 수행해야 합니다.
- Active debugger/SWD는 System OFF와 reset cause를 방해할 수 있습니다.
- `NU54DK.coreVersion()`은 역사적 문자열 `0.2.0-dev`를 반환합니다. 배포 identity는 Boards
  Manager 설치 version과 release manifest로 확인하십시오.

전체 경계는 [v0.3.0 알려진 제약](<./00_Docs/05_릴리스/v0.3.0/KNOWN_ISSUES.md>)을 확인하십시오.

## 검증과 릴리스 정책

`v0.3.0`은 host/software/docs/package gate, 두 번의 독립 package 재현 build, RC3 runtime
payload 동등성, 격리 Boards Manager lifecycle, 설치 예제 29/29 compile과 실제 NU54DK upload를
통과했습니다. 정확한 identity와 실행 결과는
[v0.3.0 정식 공개 기록](<./00_Docs/04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)에
보존합니다.

`v0.1.0`, `v0.2.0`과 모든 RC는 신규 수정·지원 대상에서 제외합니다. 다만 공개 tag·Release
asset과 stable index 항목은 재현성, 감사와 downgrade를 위해 삭제하거나 덮어쓰지 않습니다.

## 로드맵

| 버전 | 상태 | 범위 |
| --- | --- | --- |
| `v0.1.0` | 역사적·비지원 | Core, 기본 API, build/upload와 package |
| `v0.2.0` | 역사적·비지원 | CI/CD, profile·예제, Board/System과 BLE NUS |
| `v0.3.0` | **현재 stable** | Arduino compatibility, 동적 peripheral/analog, BLE GAP/GATT/security/profile, storage |
| `v0.4.0` | 개발 중 | Peripheral 확장: M24 23개 serial personality 단독 기능 HIL PASS, analog/stream·동시성·soak·최종 release gate 대기 |
| `v0.5.0` | 계획 | Bluetooth LE 확장·ISO/LE Audio·Direction Finding·Channel Sounding·Mesh |
| `v0.6.0` | 계획 | Storage/Crypto, TF-M, 고급 memory layout와 secure update/recovery |
| `v0.7.0` | 계획 | Radio profile, IEEE 802.15.4, ESB와 OpenThread |
| `v0.8.0` | 계획 | Matter 기반, application template와 commissioning HIL |

`v0.4.0` 후보는 UART 4개·PMIC I2C 3개, 내부 ADC·event, TEMP·WDT30의
[온보드 시험](<./00_Docs/04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)을
통과했고, [UART Fixture 101](<./00_Docs/04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)과
[Fixture 102](<./00_Docs/04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>),
[Fixture 103](<./00_Docs/04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>)에서 UARTE00/20의 P2,
UARTE30의 P0와 UARTE20/21/22의 P1 route 양방향 데이터·DMA·RTS/CTS를 통과했습니다.
[SPI Fixture 201](<./00_Docs/04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>)에서는 P2↔P1의
SPIM/SPIS00·20·21·22, 2/4/8 MHz, Mode 0~3, MSB/LSB와 EasyDMA 18,169개 계획 벡터를 통과했습니다.
[SPI Fixture 202](<./00_Docs/04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>)에서는 P0↔P1의
SPIM/SPIS30·20·21·22에 대한 9,084개 계획 벡터를 통과했습니다.
[SPI Fixture 203](<./00_Docs/04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>)에서는 P1↔P1의
SPIM/SPIS20·21·22 전 조합 27,252개 계획 벡터를 통과했습니다.
[TWI Fixture 301](<./00_Docs/04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>)에서는 P1↔P0
TWIM/TWIS20·21·22·30의 기능 record 1,986개와 cleanup 2건을 통과해 T11 단독 기능 검증을
역사적 체크포인트로 완료했습니다. 이후 R00~R13 리팩토링과 전체 software gate는
[64번 기록](<./00_Docs/04_검증 기록/64_R13_도구_정책_build_구조.md>)으로 완료했습니다. 최종 source의
current-source T11은 exact 154324c의 Fixture 101 기능 1,644개를 통과했습니다. Fixture 102도 exact a49cc0d에서 822개를 통과했으며 다음은 Fixture 103 전원 OFF 결선 변경입니다.
사용자 확인과 T11 회귀 뒤 T12 analog·stream 및 전체 동시성·soak 통합 캠페인을 진행합니다.
정식 공개는 아직 완료되지 않았습니다.
검증은 온보드 자원과 두 NU54DK의 통신·합성 신호·capture를 기준으로 합니다. 정밀 계측과 외부
마이크·코덱·엔코더별 호환성·신호 품질은 보증 범위에 포함하지 않으며, 자세한 구분은
[코어 기능 검증 범위](<./00_Docs/04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)를 따릅니다.

## 동작 구조

```text
Arduino Sketch와 library
        ↓
Arduino CLI/IDE source discovery
        ↓
NU54 Build Adapter
        ↓
NCS v3.4.0 + Zephyr 4.4.0 전체 build graph
        ↓
ELF / HEX / BIN / map
        ↓
CMSIS-DAP V2 + pyOCD 또는 외장 J-Link
```

## 저장소 복제

Source 수정, host gate, Nordic Toolchain과 실물 HIL까지 준비하려면
[Windows 개발환경 설정](<./00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)을 먼저
확인하십시오. 일반 Arduino 사용자의 Boards Manager 설치에는 Git, MinGW 또는 별도 Python이
필요하지 않습니다.

```powershell
git clone --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
cd NU54DK_Arduino_Core
git submodule status
```

보드 정의는 [Nucode01/NU54DK_Zephyr_DTS](https://github.com/Nucode01/NU54DK_Zephyr_DTS)를
단일 원본으로 사용합니다. Core 작업에서는 `board_package/NU54DK_Zephyr_DTS` 내부를 수정하지
않습니다.

## 문서

- [전체 문서 안내](./00_Docs/README.md)
- [v0.4.0 실행 TODO·재개 체크포인트](./00_Docs/TODO_v0.4.0.md)
- [리팩토링 계획·운영·진행 체크리스트](<./00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md>)
- [v0.3.0 릴리스 문서](<./00_Docs/05_릴리스/v0.3.0/README.md>)
- [v0.3.0 마이그레이션](<./00_Docs/05_릴리스/v0.3.0/MIGRATION.md>)
- [v0.3.0 문제 해결](<./00_Docs/05_릴리스/v0.3.0/TROUBLESHOOTING.md>)
- [Arduino API 지원 범위](<./00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [Windows 개발환경 설정](<./00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)
- [Boards Manager 설치와 package](<./00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [제품 로드맵](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)
- [전 인스턴스·DMA·BLE 경쟁 기준](<./00_Docs/01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>)
- [M24 Serial Fabric 경로와 API 계약](<./00_Docs/01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>)
- [M23 Peripheral instance matrix](<./00_Docs/01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>)
- [검증 기록](<./00_Docs/04_검증 기록/README.md>)
- [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)

## 작성자와 라이선스

작성자는 **NUCODE의 Quantum**입니다. NUCODE가 작성한 코드는 [MIT License](LICENSE)를
적용합니다. 외부 구성요소에는 각 원 라이선스와 고지가 적용되며 자세한 내용은
[third-party notices](./third_party/THIRD_PARTY_NOTICES.md)를 확인하십시오.

2026-09-06 후속: [65번 기록](<./00_Docs/04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>)의 904 PASS·파일 정리를 보존한다. 이후 DAP UART 연결 전환 뒤 [66번 기록](<./00_Docs/04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에서 UART idle bias를 교정하고 온보드 18개 결과·BLE 3개 pair gate를 통과했다. 이후 사용자 결선 완료 확인에 따라 exact 154324c의 current-source T11 Fixture 101을 SWD 10 MHz로 실행해 기능 1,644개를 통과했다. 이후 exact a49cc0d의 Fixture 102 기능 822개를 SWD 10 MHz로 통과했다. 현재 Fixture 102 결선·DAP UART 분리·SWD 연결 상태이며 다음은 전원 OFF·Fixture 103 결선 변경과 새 사용자 확인이다.

Current-source T11 첫 UART 회귀의 exact 증거는 [67번 기록](<./00_Docs/04_검증 기록/67_T11_Fixture_101_current_source_UART_회귀.md>)에 연결한다. 전체 T11·T12~T15와 RC/공개는 미완료다.

Current-source Fixture 102의 exact a49cc0d·822 PASS와 다음 Fixture 103 결선은 [68번 기록](<./00_Docs/04_검증 기록/68_T11_Fixture_102_current_source_UART_회귀.md>)에 연결한다.
