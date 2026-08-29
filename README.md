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
| 다음 목표 | `v0.2.0` — M12~M14 완료, M15 board/system API·HIL 검증 진행 중 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 지원 보드 | NU54DK / nRF54L15 CPUAPP |
| 공식 사용자 OS | Windows 10/11 x64 |
| 기본 업로드 | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 업로드 | 외장 SEGGER J-Link |
| v0.1 마일스톤 | M0~M11 완료 |
| v0.2 진행 | M12~M14 완료; M15 비-System-OFF 자동 HIL 2/2 PASS, SWD 격리 System OFF 결합 HIL NOT RUN |

v0.1.0에서는 Runtime, GPIO, 시간, Serial, GPIO interrupt, Wire/I2C, SPI, ADC, PWM,
Arduino CLI/IDE build, pyOCD upload/debug, cache와 Boards Manager 설치 경로를 검증했습니다.
세부 결과는 [제품 로드맵과 구현 마일스톤](<./00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md>)에
정리되어 있습니다.

현재 `main`에서는 M12 CI/CD, M13 profile·예제 UX와 M14 Core API·DTS 기반 Variant를
완료했습니다. `PIN_LED2..3` output/readback과 `PIN_BUTTON1..3`의 pull-up raw 상태 및
`FALLING`/`RISING`/`CHANGE` interrupt도 실제 NU54DK에서 통과했습니다. M15에서는
`NUCODE_NU54DK` board/system library와 예제·시험을 구현하고 있습니다. 자동 HIL은
System OFF를 제외한 identity·uptime·GRTC callback·Settings·WDT 범위로 한정합니다. System OFF는
온보드 debug-control 2연 `SW1`에서 `DISABLE_SWD`만 격리하고 UART 연결은 유지한 별도 결합
HIL에서 timed GRTC wake 다음 사용자 `SW0`/P1.13 wake 순서로 검증합니다. 이 결합 HIL은 아직
`NOT RUN`이므로 M15는 진행 중입니다.

비-System-OFF 자동 HIL은 Core `6898f7917348fab3c5cf54eec0756523e2c27d69`과 동일한 공식
CI HEX로 두 NU54DK에서 2/2 PASS했습니다. 이 결과에는 timed 또는 button System OFF wake가
포함되지 않습니다.

여기서 debug-control 2연 `SW1`은 Arduino 사용자 버튼 `SW1`/P1.09와 다른 물리 부품입니다.
System OFF HIL에서는 debug-control `SW1`의 `DISABLE_UART` 쪽을 전환하지 않아 온보드 UART를
유지합니다.

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
| `NUCODE NU54DK` | [Blink](./libraries/NUCODE_NU54DK/examples/Blink), [InterruptButton](./libraries/NUCODE_NU54DK/examples/InterruptButton), [AnalogReadA0](./libraries/NUCODE_NU54DK/examples/AnalogReadA0), [PWMFade](./libraries/NUCODE_NU54DK/examples/PWMFade), [SerialEcho](./libraries/NUCODE_NU54DK/examples/SerialEcho), [BoardInfo](./libraries/NUCODE_NU54DK/examples/BoardInfo), [WatchdogBasic](./libraries/NUCODE_NU54DK/examples/WatchdogBasic), [CounterAlarm](./libraries/NUCODE_NU54DK/examples/CounterAlarm), [SettingsStorage](./libraries/NUCODE_NU54DK/examples/SettingsStorage), [SystemOffWake](./libraries/NUCODE_NU54DK/examples/SystemOffWake) |
| `Wire` | [WirePmicId](./libraries/Wire/examples/WirePmicId) |
| `SPI` | [SPITransaction](./libraries/SPI/examples/SPITransaction) |

M13의 기존 예제 7개에 M15 board/system 예제 5개를 추가했습니다. 전체 12개 예제의
`arduino-cli lib examples` 열거와 compile gate는 M15 검증 과정에서 갱신 중입니다. 공개된
`v0.1.0` Boards Manager package는 예전 archive 구조이므로 IDE 메뉴 노출이 보장되지 않으며,
표준 예제 구조는 다음 릴리스에 포함됩니다.

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
- `standard` 구성 profile과 strict library feature resolver는 M13에서 구현했지만 공개
  `v0.1.0` package에는 없습니다. `v0.1.0`의 고급 주변장치 예제는 package 내부
  `prj.conf`와 `app.overlay`에 의존합니다.
- BLE, Thread, Matter, OTA/DFU, native USB와 filesystem Arduino wrapper는 v0.1.0에 없습니다.
- NU54DK의 모든 connector pin이 아직 Arduino 논리 pin으로 공개된 것은 아닙니다.
- `main`의 M15 PMIC write API는 매 boot 명시적 승인을 요구합니다. 배터리 전기 HIL은
  수행하지 않았고 실제 NTC 온도 보호는 지원하지 않으므로, 사용자가 자신의 배터리·전원
  조건에서 직접 검증해야 합니다.
- M15의 SWD 격리 timed GRTC wake와 사용자 SW0/P1.13 wake 결합 HIL은 아직 `NOT RUN`이며
  M15는 완료 상태가 아닙니다.

전체 목록은 [v0.1.0 알려진 제약](<./00_Docs/05_릴리스/12_v0.1.0_알려진_제약.md>)에서 확인할
수 있습니다.

## v0.2.0 진행 현황과 다음 작업

| 마일스톤 | 상태 | 작업 |
| --- | --- | --- |
| [M12](<./00_Docs/04_검증 기록/14_M12_CI_CD_기준선.md>) | **완료** | GitHub Actions software CI와 재현 build, self-hosted NU54DK HIL 경계 구축 |
| [M13](<./00_Docs/04_검증 기록/15_M13_구성_프로필_검증.md>) | **완료** | Arduino 예제 7개, `standard` profile과 strict library feature resolver |
| [M14](<./00_Docs/04_검증 기록/16_M14_Core_API와_Variant_기준선.md>) | **완료** | Core API·DTS Variant, 로컬·원격 software/runtime와 신규 pin 물리 HIL 통과 |
| [M15](<./00_Docs/04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>) | **진행 중** | 비-System-OFF 자동 HIL 2/2 PASS; SWD 격리 timed GRTC→사용자 SW0 결합 HIL NOT RUN |
| M16 | 대기 | 공식 Zephyr Bluetooth 기반 basic BLE library |
| M17 | 대기 | NCS v3.4.0 기능·예제 coverage 첫 묶음 |
| M18 | 대기 | v0.2.0 RC, clean Windows/HIL과 stable 공개 |

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
- [M12 CI/CD와 재현 build 기준선](<./00_Docs/04_검증 기록/14_M12_CI_CD_기준선.md>)
- [M13 구성 profile 및 예제 배포 검증](<./00_Docs/04_검증 기록/15_M13_구성_프로필_검증.md>)
- [M14 Core API와 Variant 기준선](<./00_Docs/04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [M15 NU54DK Board/System API 설계](<./00_Docs/03_펌웨어 설계/05_NU54DK_Board_System_API.md>)
- [M15 NU54DK Board/System 기준선](<./00_Docs/04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)
- [v0.1.0 릴리스 노트](<./00_Docs/05_릴리스/11_v0.1.0_릴리스_노트.md>)

## 작성자와 라이선스

작성자는 **NUCODE의 Quantum**입니다.

NUCODE가 작성한 코드는 [MIT License](LICENSE)를 적용합니다. Zephyr, nRF Connect SDK,
ArduinoCore-API와 보드 package 등 외부 구성요소에는 각각의 원 라이선스와 고지가 적용됩니다.
자세한 내용은 [third-party notices](./third_party/THIRD_PARTY_NOTICES.md)를 확인하십시오.
