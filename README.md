# NU54DK Arduino Core

**nRF54L15에서 Arduino Sketch를 실행하세요.**
NCS와 Zephyr를 기반으로 Sketch와 library를 하나의 firmware로 빌드하고,
온보드 CMSIS-DAP으로 업로드합니다. 별도 Loader는 필요하지 않습니다.

[![Stable: v0.4.0](https://img.shields.io/badge/stable-v0.4.0-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.4.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](https://github.com/nrfconnect/sdk-nrf)
[![Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml)
[![Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml)

[빠른 시작](#빠른-시작) · [지원 기능](#지원-기능) · [예제](#예제) · [문서](#문서) · [릴리스](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.4.0)

| 보드 | 개발 환경 | 기반 SDK | 업로드 |
| --- | --- | --- | --- |
| **NU54DK · nRF54L15 CPUAPP** | Windows 10/11 x64 · Arduino IDE 2.x | NCS v3.4.0 · Zephyr 4.4.0 | CMSIS-DAP V2 + pyOCD |

## 빠른 시작

### 1. Boards Manager에 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 아래 주소를 넣습니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

`Boards Manager`에서 **NUCODE NU54DK Zephyr Boards**를 찾아 **0.4.0**을 설치합니다.
post-install 실행 확인이 나오면 승인하고, NCS와 고정 Toolchain 설치가 끝날 때까지 기다립니다.

첫 설치에는 인터넷 연결과 SDK를 저장할 디스크 공간이 필요합니다. 관리자 권한이나
nRF Connect for Desktop/VS Code, 별도 Git·Python 설치는 필수가 아닙니다.

### 2. 보드와 기능 선택

보드는 `NU54DK (nRF54L15, Zephyr)`, Upload probe는 `CMSIS-DAP (pyOCD)`를 선택합니다.
`Tools → Feature set`은 Sketch에 맞춰 고릅니다.

| Feature set | 용도 |
| --- | --- |
| `Standard peripherals` | GPIO, Serial, Wire, SPI, ADC, PWM, Storage 등 일반 Arduino Sketch |
| `BLE NUS` | NUS와 GAP/GATT·보안·표준 BLE profile 예제 |
| `Peripheral Fabric (DAP UART disconnected)` | 인스턴스·DMA를 직접 제어하는 고급 API. DAP UART 분리 조건 준수 |

일반 사용자는 `prj.conf`나 Devicetree overlay를 직접 작성할 필요가 없습니다.
CLI의 기본 FQBN은 `nucode:zephyr:nu54dk`입니다.

### 3. Blink 업로드

데이터 통신이 가능한 USB cable로 NU54DK를 연결합니다.
`File → Examples → NUCODE NU54DK → Blink`를 열고 **Verify → Upload**를 실행합니다.
온보드 LED가 250 ms 간격으로 점멸하면 기본 경로가 정상입니다.

<details>
<summary>Blink Sketch 보기</summary>

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

</details>

설치·업로드가 막히면 [문제 해결](<00_Docs/05_릴리스/v0.4.0/TROUBLESHOOTING.md>)을 확인하세요.
여러 보드의 UID 지정과 외장 J-Link 사용은 [업로드·디버그 안내](<00_Docs/02_빌드 설계/05_업로드와_디버그.md>)에 있습니다.

## 지원 기능

### 일반 Arduino API

| 영역 | v0.4.0 지원 범위 |
| --- | --- |
| Runtime·GPIO·시간 | `setup()`/`loop()`, digital I/O, interrupt, `millis()`/`micros()`, delay와 pulse |
| Serial | DAP UART `Serial`, UART30 기반 `Serial1`와 runtime pin route |
| Wire·SPI | **부분 지원:** Wire는 I2C22 master, SPI는 SPI00 controller. 둘 다 runtime pin route 제공 |
| Analog·출력 | ADC 채널·resolution, 동적 PWM, `tone()`, Servo |
| Storage | EEPROM facade 1,024 byte, 내부 LittleFS 32 KiB, Settings/ZMS |
| BLE | NUS, GAP Peripheral/Central, 범용 GATT, pairing·bonding, BAS·DIS·HID keyboard |
| Board·System | Board identity, watchdog, GRTC, System OFF와 timed/button wake |

`Serial`은 native USB CDC가 아닙니다. Wire target/slave·`Wire1`, SPI peripheral·`SPI1`은
일반 Arduino API에서 제공하지 않습니다. 직접 인스턴스 제어는 아래 Fabric API를 사용합니다.

### Peripheral Fabric

`fabric` 기능 구성과 `#include <NUCODE_Peripheral_Fabric.h>`로 진입합니다.
이 구성은 기존 `standard`·`ble`의 singleton 주변장치를 함께 활성화하지 않습니다.

| 영역 | 직접 제어 범위 |
| --- | --- |
| Serial Fabric | UARTE·SPIM·SPIS **00/20/21/22/30**, TWIM·TWIS **20/21/22/30** |
| Analog·Event·Stream | SAADC, PWM, TIMER, GPIOTE/DPPI, PDM, I2S |
| QDEC·System | **QDEC20/21 지원**, TEMP·WDT30/31 |

QDEC는 기본 정·역회전과 SAMPLE/REPORT event 경로를 지원합니다.
동작 중 반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
각 인스턴스의 핀·DMA·공유 자원 조건은 [인스턴스 매트릭스](<00_Docs/01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>)와
[Serial Fabric 계약](<00_Docs/01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>)을 따릅니다.

> 반복 Serial personality handover와 모든 주변장치의 동시 조합은 보증하지 않습니다.
> 정밀 ADC 정확도·jitter·음질·신호 무결성은 기능시험 범위 밖입니다.
> 전체 공개 계약은 [API 지원 범위](<00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)와
> [알려진 제약](<00_Docs/05_릴리스/v0.4.0/KNOWN_ISSUES.md>)을 확인하세요.

## 예제

9개 library에 **30개 예제**가 포함됩니다: Standard 22개 · BLE 7개 · Fabric 1개.

| 해보고 싶은 것 | 시작할 예제 |
| --- | --- |
| LED와 보드 정보 | [Blink](libraries/NUCODE_NU54DK/examples/Blink), [BoardInfo](libraries/NUCODE_NU54DK/examples/BoardInfo) |
| 통신과 runtime pin 변경 | [Serial1RuntimePins](libraries/NUCODE_NU54DK/examples/Serial1RuntimePins), [WireRuntimePins](libraries/NUCODE_NU54DK/examples/WireRuntimePins), [SPI00RuntimePins](libraries/NUCODE_NU54DK/examples/SPI00RuntimePins) |
| Analog와 PWM | [AnalogChannels](libraries/NUCODE_NU54DK/examples/AnalogChannels), [DynamicPWM](libraries/NUCODE_NU54DK/examples/DynamicPWM) |
| BLE 통신·보안 | [NUSPeripheral](libraries/NUCODE_BLE/examples/NUSPeripheral), [CustomGattCentral](libraries/NUCODE_BLE/examples/CustomGattCentral), [SecureKeyboard](libraries/NUCODE_BLE_Security/examples/SecureKeyboard) |
| 영구 저장·저전력 | [LittleFSPersistence](libraries/LittleFS/examples/LittleFSPersistence), [SystemOffWake](libraries/NUCODE_NU54DK/examples/SystemOffWake) |
| Fabric capability 조회 | [FabricCapabilities](libraries/NUCODE_Peripheral_Fabric/examples/FabricCapabilities) |

전체 목록과 예제별 profile은 [예제 배포 안내](<00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)에 있습니다.
공개 package의 **30/30 예제 compile**, 대표 Blink Upload, 버전 전환·제거·재설치는
[정식 공개 검증 기록](<00_Docs/04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)에서 확인할 수 있습니다.
예제 build 통과와 각 주변장치의 실기 검증 범위는 별개로 기록합니다.

## 사용 전 확인

- 실제 결선은 [P2/P4 커넥터 핀맵](<00_Docs/01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)을 기준으로 합니다.
  Fabric의 DAP UART 분리 등 각 API의 전기적 선행조건을 지키세요.
- Native USB, OTA/DFU와 외부 filesystem은 지원하지 않습니다.
- Storage format/reset은 데이터를 지웁니다. 버전 이동 전에는 필요한 데이터를 백업하세요.
- GPIO interrupt callback에서 blocking·heap 할당·`Serial`·`delay()`를 사용하지 마세요.
- Servo는 적합한 외부 전원과 공통 GND를 사용하세요. PMIC write는 매 boot 명시적 승인이 필요합니다.
- Active debugger/SWD는 System OFF와 reset cause 관측에 영향을 줄 수 있습니다.

## 문서

| 찾는 내용 | 안내 |
| --- | --- |
| 설치·이전 버전에서 이동 | [Boards Manager 설치](<00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md>) · [마이그레이션](<00_Docs/05_릴리스/v0.4.0/MIGRATION.md>) |
| API·핀·설계 | [전체 문서 목차](00_Docs/README.md) · [API 지원 범위](<00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>) |
| 개발 환경·빌드 구조 | [Windows 개발환경](<00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>) · [Build Adapter](<00_Docs/02_빌드 설계/02_Build_Adapter_설계.md>) |
| 릴리스·검증·향후 계획 | [v0.4.0 릴리스 문서](<00_Docs/05_릴리스/v0.4.0/README.md>) · [완료 기록](00_Docs/TODO_v0.4.0.md) · [로드맵](<00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>) |
| 문제 보고 | [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues) |

### 소스에서 개발하기

Boards Manager 설치가 아닌 Core 개발 시에만 저장소와 submodule을 복제합니다.

```powershell
git clone --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
cd NU54DK_Arduino_Core
git submodule status
```

보드 정의의 원본은 [NU54DK_Zephyr_DTS](https://github.com/Nucode01/NU54DK_Zephyr_DTS)입니다.
Core 작업에서는 보드 submodule을 임의 수정하지 않습니다.
`NU54DK.coreVersion()`은 소스 식별자 `0.4.0-dev`를 반환합니다. 정식 설치본에서도 이 값은 같으며,
배포 버전 `0.4.0`은 Boards Manager·`platform.txt`·release manifest로 확인합니다.

## 작성자와 라이선스

**NUCODE의 Quantum**이 개발합니다. NUCODE 작성 코드는 [MIT License](LICENSE)를 적용합니다.
외부 구성요소의 라이선스와 고지는 [Third-party notices](third_party/THIRD_PARTY_NOTICES.md)를 확인하세요.
