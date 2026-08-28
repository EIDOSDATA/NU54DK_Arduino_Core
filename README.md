# NU54DK Arduino Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stable: v0.1.0](https://img.shields.io/badge/stable-v0.1.0-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.1.0)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](https://github.com/nrfconnect/sdk-nrf)
[![Author: Quantum](https://img.shields.io/badge/Author-Quantum%20%40%20NUCODE-blueviolet.svg)](#작성자와-라이선스)

NU54DK에서 **Loader 없이 전체 Zephyr firmware를 빌드하는** Arduino Core입니다. Arduino
Sketch와 library를 nRF Connect SDK의 build graph 안에 넣어 ELF/HEX/BIN을 만들고, 보드의
온보드 CMSIS-DAP V2와 pyOCD로 바로 업로드합니다.

## 현재 상태

| 항목 | 상태 |
| --- | --- |
| 현재 정식 버전 | [`v0.1.0`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.1.0) |
| 다음 목표 | `v0.2.0` — CI/CD, IDE 예제, 구성 profile, board/system API, basic BLE |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 지원 보드 | NU54DK / nRF54L15 CPUAPP |
| 공식 사용자 OS | Windows 10/11 x64 |
| 기본 업로드 | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 업로드 | 외장 SEGGER J-Link |
| v0.1 마일스톤 | M0~M11 완료 |

v0.1.0에서는 Runtime, GPIO, 시간, Serial, GPIO interrupt, Wire/I2C, SPI, ADC, PWM,
Arduino CLI/IDE build, pyOCD upload/debug, cache와 Boards Manager 설치 경로를 검증했습니다.
세부 결과는 [제품 로드맵과 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)에
정리되어 있습니다.

## Arduino IDE로 설치

### 준비물

- Windows 10/11 x64
- Arduino IDE 2.x — 정식 검증 버전은 2.3.10
- 인터넷 연결과 NCS/Toolchain을 저장할 여유 공간
- 실제 업로드 시 NU54DK와 데이터 통신 가능한 USB 케이블

관리자 권한, nRF Connect for Desktop 또는 nRF Connect for VS Code는 필수 조건이 아닙니다.
Nordic prerequisite는 현재 사용자 영역에 설치됩니다.

### 1. Boards Manager URL 추가

Arduino IDE에서 `File → Preferences → Additional Boards Manager URLs`에 다음 주소를 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

### 2. Core 설치

1. `Tools → Board → Boards Manager`를 엽니다.
2. `NUCODE NU54DK Zephyr Boards`를 검색합니다.
3. 버전 `0.1.0`을 설치합니다.
4. post-install 실행 확인이 나오면 승인합니다.
5. NCS v3.4.0과 Toolchain 설치가 끝날 때까지 기다립니다.

첫 설치는 Nordic SDK와 Toolchain을 내려받기 때문에 시간이 오래 걸릴 수 있습니다. 설치가
중단되어도 같은 Core를 다시 설치하거나 package의 `post_install.bat`을 다시 실행하면 검증된
파일은 재사용됩니다.

### 3. 보드와 업로드 경로 선택

1. `Tools → Board`에서 `NU54DK (nRF54L15, Zephyr)`를 선택합니다.
2. `Tools → Upload probe`에서 `CMSIS-DAP (pyOCD)`를 선택합니다.
3. NU54DK를 USB로 연결합니다.
4. Sketch를 검증한 뒤 Upload 버튼을 누릅니다.

외장 J-Link를 사용할 때만 `SEGGER J-Link`를 선택합니다. J-Link software는 이 package에
포함되지 않으므로 SEGGER 공식 설치본이 별도로 필요합니다.

### 4. 첫 Blink

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

`Verify` 후 `Upload`를 누르면 Full Zephyr image가 빌드되고 pyOCD를 통해 기록됩니다.

## 예제

현재 `main`의 예제는 Arduino 표준 platform library 구조로 정리되어 있습니다.

| Arduino 예제 메뉴 | 포함 예제 |
| --- | --- |
| `NUCODE NU54DK` | [Blink](./libraries/NUCODE_NU54DK/examples/Blink), [InterruptButton](./libraries/NUCODE_NU54DK/examples/InterruptButton), [AnalogReadA0](./libraries/NUCODE_NU54DK/examples/AnalogReadA0), [PWMFade](./libraries/NUCODE_NU54DK/examples/PWMFade), [SerialEcho](./libraries/NUCODE_NU54DK/examples/SerialEcho) |
| `Wire` | [WirePmicId](./libraries/Wire/examples/WirePmicId) |
| `SPI` | [SPITransaction](./libraries/SPI/examples/SPITransaction) |

이 구조는 `arduino-cli lib examples`에서 열거되도록 자동 시험합니다. 공개된 `v0.1.0`
Boards Manager package는 예전 archive 구조이므로 IDE 메뉴 노출이 보장되지 않으며, 표준 예제
구조는 다음 릴리스에 포함됩니다.

## v0.1.0 지원 범위

| 영역 | 상태 | 주요 범위 |
| --- | --- | --- |
| Runtime | 지원 | `setup()`, 반복 `loop()`, C++ 전역 객체 |
| Digital GPIO | 부분 지원 | `LED_BUILTIN`, `PIN_BUTTON0`, GPIO read/write |
| Time | 지원/의미 차이 | `millis`, `micros`, `delay`, `delayMicroseconds`, `yield` |
| Interrupt | 부분 지원 | `RISING`, `FALLING`, `CHANGE`, attach/detach |
| Serial | 부분 지원 | Zephyr console UART 기반 `Serial`, 115200 8N1 |
| Wire/I2C | 부분 지원 | I2C22, 100/400 kHz, repeated-start |
| SPI | 부분 지원 | SPI00, mode 0~3, 4 MHz 실기 loopback, Sketch 소유 CS |
| ADC | 부분 지원 | `A0`/P1.12, 고정 12-bit raw |
| PWM | 부분 지원 | `PIN_PWM0`/P1.10, 고정 20 ms·8-bit |
| Upload/debug | 지원 | pyOCD 기본, J-Link 선택 경로 |

정확한 API별 상태와 의미 차이는
[Arduino API 지원 범위](<./00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를
기준으로 합니다.

## 알려진 제약

- 공식 사용자 환경은 현재 Windows 10/11 x64입니다.
- NCS/Toolchain은 Core ZIP에 재배포하지 않고 Nordic 공식 배포에서 별도로 설치합니다.
- `v0.1.0` package의 예제 파일은 archive에 있지만 Arduino IDE `파일 → 예제`의 표준 library
  구조가 아니어서 메뉴 노출이 보장되지 않습니다. main에서 구조를 교정했으며 다음 배포에
  포함합니다.
- 일반 사용자를 위한 구성 profile은 v0.2.0 M13에서 구현합니다. v0.1의 고급 주변장치 예제는
  내부적으로 `prj.conf`와 `app.overlay`를 사용합니다.
- BLE, Thread, Matter, OTA/DFU, native USB와 filesystem Arduino wrapper는 v0.1.0에 없습니다.
- NU54DK의 모든 connector pin이 아직 Arduino 논리 pin으로 공개된 것은 아닙니다.

전체 목록은 [v0.1.0 알려진 제약](<./00_Docs/05_릴리스/12_v0.1.0_알려진_제약.md>)에서 확인할
수 있습니다.

## 다음 작업

| 순서 | 마일스톤 | 작업 |
| ---: | --- | --- |
| 1 | M12 | GitHub Actions software CI와 self-hosted NU54DK HIL 경계 구축 |
| 2 | M13 | Arduino IDE 예제 열거, curated profile과 library feature resolver |
| 3 | M14 | v0.1 API 부채, logical pin과 diagnostic 정리 |
| 4 | M15 | `NUCODE_NU54DK` board/system library |
| 5 | M16 | 공식 Zephyr Bluetooth 기반 basic BLE library |
| 6 | M17 | NCS v3.4.0 기능·예제 coverage 첫 묶음 |
| 7 | M18 | v0.2.0 RC, clean Windows/HIL과 stable 공개 |

자세한 완료 기준은 [v0.2.0 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)과
[NCS 기능·예제 지원 매트릭스](<./00_Docs/01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md>)를
따릅니다.

## 개발 환경에서 사용

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

## 구조

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

Loader, LLEXT나 별도 Sketch ABI는 사용하지 않습니다. 고급 사용자는 같은 image에서 Zephyr와
NCS 공개 API를 직접 사용할 수 있습니다.

## 문서

- [전체 문서 안내](./00_Docs/README.md)
- [아키텍처 결정](<./00_Docs/00_사전 리서치/01_개발_방식_비교_및_아키텍처_결정.md>)
- [Arduino 구성 프로필과 예제 노출 결정](<./00_Docs/00_사전 리서치/02_Arduino_구성_프로필과_예제_노출_결정.md>)
- [저장소 구조와 소유권](<./00_Docs/01_아두이노 코어 설계/01_저장소_폴더_구조.md>)
- [제품 로드맵과 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)
- [v0.2.0 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/05_v0.2.0_구현_마일스톤.md>)
- [Boards Manager 설치와 패키징](<./00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)
- [구성 프로필과 Arduino 예제 배포](<./00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [v0.1.0 릴리스 노트](<./00_Docs/05_릴리스/11_v0.1.0_릴리스_노트.md>)

## 작성자와 라이선스

작성자는 **NUCODE의 Quantum**입니다.

NUCODE가 작성한 코드는 [MIT License](LICENSE)를 적용합니다. Zephyr, nRF Connect SDK,
ArduinoCore-API와 보드 package 등 외부 구성요소에는 각각의 원 라이선스와 고지가 적용됩니다.
자세한 내용은 [third-party notices](./third_party/THIRD_PARTY_NOTICES.md)를 확인하십시오.
