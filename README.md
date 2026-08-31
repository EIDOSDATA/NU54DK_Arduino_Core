# NU54DK Arduino Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stable: v0.2.0](https://img.shields.io/badge/stable-v0.2.0-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.2.0)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](https://github.com/nrfconnect/sdk-nrf)
[![Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml)
[![Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml)

NU54DK에서 Arduino Sketch를 **Loader 없이 전체 Zephyr firmware로 빌드**하는 Arduino Core입니다.
Sketch와 Arduino library를 nRF Connect SDK build graph에 통합해 ELF·HEX·BIN을 만들고,
온보드 CMSIS-DAP V2와 pyOCD로 업로드합니다.

| 항목 | 현재 기준 |
| --- | --- |
| 정식 버전 | [`v0.2.0`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.2.0) |
| 지원 보드 | NU54DK / nRF54L15 CPUAPP |
| Arduino FQBN | `nucode:zephyr:nu54dk` |
| SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 사용자 환경 | Windows 10/11 x64, Arduino IDE 2.x |
| 기본 업로드 | 온보드 CMSIS-DAP V2 + pyOCD |
| 정식 완료 범위 | M0~M18 / `v0.2.0` 정식 공개 |
| `v0.3.0` 개발 상태 | AC-01 자동 HIL PASS / M19·M20·M21 완료 — Windows 11 SecureKeyboard pairing·입력·bond 복원 PASS |
| 다음 작업 | AC-02 주변장치 호환성 → AC-03 Storage·library 호환성 → M22 통합 릴리스 |

## 빠른 시작

### 1. 준비물

- Windows 10/11 x64
- Arduino IDE 2.x — 정식 검증 버전은 2.3.10
- 인터넷 연결과 NCS/Toolchain을 저장할 디스크 공간
- NU54DK와 데이터 통신이 가능한 USB 케이블

관리자 권한, nRF Connect for Desktop 및 nRF Connect for VS Code는 필수 조건이 아닙니다.
Nordic prerequisite는 현재 Windows 사용자 영역에 설치됩니다.

### 2. Boards Manager URL 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 다음 주소를 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

이 주소는 이후 정식 버전도 표시하는 일반 업데이트 채널입니다. `v0.2.0`만 고정해 재현하려면
[v0.2.0 Release의 불변 index](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.2.0/package_nucode_nu54dk_index.json)를
사용할 수 있습니다.

### 3. Core 설치

1. `Tools → Board → Boards Manager`를 엽니다.
2. `NUCODE NU54DK Zephyr Boards`를 검색합니다.
3. 버전 `0.2.0`을 설치합니다.
4. post-install 실행 확인이 나오면 승인합니다.
5. NCS v3.4.0과 고정 Toolchain 설치가 끝날 때까지 기다립니다.

첫 설치는 Nordic SDK와 Toolchain을 내려받으므로 오래 걸릴 수 있습니다. 설치가 중단됐거나
prerequisite 검증이 실패하면 [문제 해결 문서](<./00_Docs/05_릴리스/v0.2.0/TROUBLESHOOTING.md>)를
확인하십시오.

### 4. 보드와 기능 구성 선택

일반 Blink를 빌드할 때는 다음 항목을 선택합니다.

| Arduino IDE 메뉴 | 선택 값 |
| --- | --- |
| `Tools → Board` | `NU54DK (nRF54L15, Zephyr)` |
| `Tools → Feature set` | `Standard peripherals` |
| `Tools → Upload probe` | `CMSIS-DAP (pyOCD)` |

BLE NUS 예제를 사용할 때만 `Feature set`을 `BLE NUS`로 바꿉니다. 사용자는 `prj.conf`나
Devicetree overlay를 직접 작성하지 않아도 됩니다.

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

NU54DK를 연결한 뒤 `Verify`, `Upload` 순서로 실행합니다. Arduino IDE가 Full Zephyr image를
빌드하고 pyOCD를 통해 기록합니다. 온보드 LED가 250 ms 간격으로 점멸하면 성공입니다.

## 업로드 Probe 선택

- CMSIS-DAP가 한 대면 `CMSIS-DAP (pyOCD)`가 UID 입력 없이 자동 선택합니다.
- 두 대 이상이면 임의의 첫 Probe를 선택하지 않습니다. `CMSIS-DAP with UID (pyOCD)`를
  선택하고 Upload가 요청하는 필드에 대상 Probe의 전체 UID를 입력합니다.
- UID는 COM 번호나 DAPLink 드라이브 문자가 아닙니다.
- 외장 J-Link는 `SEGGER J-Link`를 선택합니다. SEGGER Software, target VTref와 올바른 SWD
  연결이 별도로 필요하며, 실패해도 pyOCD로 자동 전환하지 않습니다.
- 일반 Upload는 mass erase 또는 recover를 자동 실행하지 않습니다.

Arduino CLI에서 명시적 CMSIS-DAP UID를 사용할 때는 compile과 upload에 같은 board option을
지정하고 upload field를 추가합니다.

```powershell
--board-options upload_probe=pyocd_uid `
--upload-field probe_id=<CMSIS-DAP-UID>
```

## 포함된 Arduino 예제

정식 package에는 Arduino IDE에서 바로 열 수 있는 예제 14개가 포함됩니다.

| 메뉴/Library | Feature set | 예제 |
| --- | --- | --- |
| [`NUCODE NU54DK`](./libraries/NUCODE_NU54DK/examples) | `Standard peripherals` | Blink, InterruptButton, AnalogReadA0, PWMFade, SerialEcho, BoardInfo, WatchdogBasic, CounterAlarm, SettingsStorage, SystemOffWake |
| [`Wire`](./libraries/Wire/examples) | `Standard peripherals` | WirePmicId |
| [`SPI`](./libraries/SPI/examples) | `Standard peripherals` | SPITransaction |
| [`NUCODE BLE`](./libraries/NUCODE_BLE/examples) | `BLE NUS` | NUSPeripheral, NUSCentral |

14개 예제는 릴리스 source와 공개 RC2 Boards Manager 설치본에서 14/14 compile gate를
통과했습니다.

현재 `main`의 `v0.3.0` 개발 트리는 GAP 2개, 범용 GATT 2개와 SecureKeyboard를 더한
**5개 library, 19개 예제**를 포함하며 Arduino CLI에서 19/19 compile을 통과했습니다. 이는 아직
공개 stable package의 예제 수를 19개로 변경했다는 뜻이 아닙니다. 설치된 `v0.2.0` package는
위의 14개를 제공합니다.

## v0.2.0 지원 범위

| 영역 | 상태 | 공개 범위 |
| --- | --- | --- |
| Runtime | 지원 | `setup()`, 반복 `loop()`, C++ 전역 객체 |
| Digital GPIO | 부분 지원 | `LED_BUILTIN`, `PIN_LED2`, `PIN_LED3` 출력·읽기; `PIN_BUTTON0..3` 입력·인터럽트 |
| Time | 부분 지원/의미 차이 | `millis()`, `micros()`, `delay()`, `delayMicroseconds()`, `yield()` |
| GPIO Interrupt | 부분 지원 | `RISING`, `FALLING`, `CHANGE`, attach/detach |
| Serial | 부분 지원 | DAP UART 기반 `Serial`, 115200 8N1 |
| Wire/I2C | 부분 지원 | I2C22, 100/400 kHz, 같은 주소의 보류 write→read repeated-start |
| SPI | 부분 지원 | SPI00, mode 0~3, Sketch 소유 CS; 4 MHz loopback 실기 검증 |
| ADC | 부분 지원 | `A0`/P1.12, 12-bit raw |
| PWM | 부분 지원 | `PIN_PWM0`/P1.10, 20 ms·8-bit |
| Board/System | 부분 지원 | Board identity, WDT, GRTC, Settings, System OFF, 제한 PMIC API |
| BLE | 부분 지원 | NUS Peripheral 또는 Central byte `Stream` |
| Upload/Debug | 지원 | pyOCD 기본, 외장 J-Link 선택 경로 |
| 구성·예제 | 지원 | `Standard peripherals`, `BLE NUS`, Arduino IDE 예제 제공 |

Wire repeated-start는 같은 주소에 대한 `endTransmission(false)` 뒤
`requestFrom(..., true)` 조합만 지원합니다. `requestFrom(..., false)`, Wire target/slave,
Wire1과 자동 bus arbitration은 현재 범위 밖입니다.

정확한 함수별 상태와 Arduino 의미 차이는
[Arduino API 지원 범위](<./00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를
기준으로 합니다.

## 주요 제약과 안전 주의

- 공식 사용자 환경은 현재 Windows 10/11 x64입니다.
- NCS/Toolchain은 Core ZIP에 재배포하지 않고 Nordic 공식 배포에서 설치합니다.
- 정식 기능 구성은 `Standard peripherals`와 `BLE NUS`입니다. 임의 Kconfig·overlay 조합은
  전문가용 경로이며 Arduino 호환이나 제품 지원을 보장하지 않습니다.
- Serial1, native USB, OTA/DFU와 Arduino filesystem wrapper는 지원하지 않습니다.
- BLE는 NUS RX write/TX notify 기반 byte Stream만 지원합니다. 범용 GATT, read, indication,
  bonding, SMP, HID와 multiprotocol은 `v0.2.0` 범위 밖입니다.
- Thread, Matter와 IEEE 802.15.4는 M17 build feasibility 기록만 있으며 `v0.2.0` 정식 지원
  기능이 아닙니다.
- 모든 connector pin을 Arduino 논리 pin으로 공개한 것은 아닙니다. `PIN_LED1`은 PWM 소유
  출력이므로 일반 Digital GPIO 목록에 포함하지 않습니다.
- 32-bit 시간 rollover, 긴 delay 경계와 저전력 전후 시간 연속성은 제품 보증 범위가 아닙니다.
- GPIO interrupt callback은 ISR에서 실행됩니다. callback 안에서 blocking, heap 할당,
  `Serial`, `delay()`를 사용하지 마십시오.
- System OFF 검증 시 active debugger/SWD가 저전력 상태와 reset cause를 방해할 수 있습니다.
  Flash 뒤 debug session을 종료하고 필요한 경우 SWD를 격리해야 합니다.
- PMIC write는 매 boot 명시적 승인이 필요합니다. 배터리 전기 HIL은 실행하지 않았으며 실제
  NTC 온도 보호는 지원하지 않습니다. 사용자가 자신의 배터리·전원 조건에서 직접 검증해야 합니다.

전체 목록은 [v0.2.0 알려진 제약](<./00_Docs/05_릴리스/v0.2.0/KNOWN_ISSUES.md>)을 확인하십시오.

## 검증 상태

`v0.2.0`은 다음 검증을 완료한 정식 릴리스입니다.

- Windows Boards Manager 설치, `0.1.0 ↔ 0.2.0` upgrade/downgrade와 uninstall
- 공개 RC2 설치본의 Arduino 예제 14/14 compile 및 pyOCD Upload 경로
- RC2 이전 기준선의 GPIO·시간·Serial·Interrupt·I2C·SPI·ADC·PWM 실기/회귀 검증
- 기존 M16 및 RC2 기준선의 두 NU54DK BLE NUS Peripheral/Central 양방향 통신
- Windows Arduino와 고정 Nordic 컨테이너 재현 빌드

RC 후보의 실기 결과, stable runtime 동등성 및 정식 공개 경계는
[v0.2.0 정식 릴리스 공개 기록](<./00_Docs/04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)에
보존합니다. RC tag와 자산은 역사적 검증 자료이며 신규 설치에는 stable `v0.2.0`을 사용합니다.
Stable exact ZIP에서 RC2의 모든 물리 HIL을 다시 실행한 것은 아닙니다. Stable 승격 근거는
RC2 실기 결과, 같은 runtime payload와 stable 공개 설치 수명주기입니다.

## 로드맵

| 버전 | 마일스톤 | 상태 | 범위 |
| --- | --- | --- | --- |
| `v0.1.0` | M0~M11 | 완료 | Core 기반, 기본 API, 주변장치, 업로드·패키징 |
| `v0.2.0` | M12~M18 | 완료 | CI/CD, Profile·예제, Board/System, BLE NUS, 정식 공개 |
| `v0.3.0` | AC-01 | **자동 검증 완료** | Core·GPIO·시간 Arduino Compatibility exact-commit HIL PASS |
| `v0.3.0` | AC-02~AC-03 | 미착수 | 주변장치·timing output, Storage facade와 대표 library 호환성 |
| `v0.3.0` | M19 | **자동 검증 완료** | BLE Core/GAP 두 보드 advertise·scan·연결·재연결 HIL PASS |
| `v0.3.0` | M20 | **자동 검증 완료** | 범용 GATT 두 보드 read/write/notify/indicate HIL PASS |
| `v0.3.0` | M21 | **완료** | Core `065d4f5` exact 두 보드 RF HIL + `d1902b1` Windows 11 pairing·HID 입력·bond 복원 PASS |
| `v0.3.0` | M22 | 대기 | AC-01~03과 M19~21을 통합한 package·RC/stable gate |
| `v0.4.0` | M23~M26 | 계획 | Storage·Crypto, MCUboot·DFU, TF-M·복구 |
| `v0.5.0` | M27~M30 | 계획 | Radio Profile, IEEE 802.15.4·ESB, OpenThread |
| `v0.6.0` | M31~M34 | 계획 | Matter 기반, Application Template, Commissioning HIL |

세부 완료 조건과 지원 선언 경계는 [전체 구현 로드맵](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)과
[v0.3.0 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)에서
관리합니다.

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

Loader, LLEXT와 별도 Sketch ABI는 사용하지 않습니다. 고급 사용자는 고정 NCS v3.4.0과 선택한
기능 구성 범위에서 Zephyr/NCS API를 직접 사용할 수 있지만, 이 경로를 Arduino 호환 API나
정식 제품 지원으로 간주하지 않습니다.

## 저장소 복제

```powershell
git clone --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
cd NU54DK_Arduino_Core
git submodule status
```

이미 clone했다면 다음 명령으로 보드 package를 받습니다.

```powershell
git submodule update --init --recursive
```

보드 정의는 [Nucode01/NU54DK_Zephyr_DTS](https://github.com/Nucode01/NU54DK_Zephyr_DTS)를
단일 원본으로 사용합니다. Core 작업에서는 `board_package/NU54DK_Zephyr_DTS` 내부를 수정하지
않습니다.

## 문서

- [전체 문서 안내](./00_Docs/README.md)
- [Boards Manager 설치와 패키징](<./00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [Arduino 구성 Profile과 예제 배포](<./00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [Arduino API 지원 범위](<./00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [BLE 보안과 표준 Profile API](<./00_Docs/03_펌웨어 설계/09_BLE_보안과_표준_Profile_API.md>)
- [M21 BLE 보안·Windows HID 검증](<./00_Docs/04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)
- [전체 구현 로드맵](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)
- [v0.2.0 릴리스 문서](<./00_Docs/05_릴리스/v0.2.0/README.md>)
- [v0.2.0 알려진 제약](<./00_Docs/05_릴리스/v0.2.0/KNOWN_ISSUES.md>)
- [문제 해결](<./00_Docs/05_릴리스/v0.2.0/TROUBLESHOOTING.md>)
- [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)

## 작성자와 라이선스

작성자는 **NUCODE의 Quantum**입니다.

NUCODE가 작성한 코드는 [MIT License](LICENSE)를 적용합니다. Zephyr, nRF Connect SDK,
ArduinoCore-API와 보드 package 등 외부 구성요소에는 각각의 원 라이선스와 고지가 적용됩니다.
자세한 내용은 [third-party notices](./third_party/THIRD_PARTY_NOTICES.md)를 확인하십시오.
