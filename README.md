# NU54DK Arduino Core

**NU54DK의 nRF54L15를 Arduino IDE에서 개발하는 오픈소스 Arduino Core입니다.**
익숙한 `setup()`/`loop()`와 Arduino API로 시작하고, BLE와 인스턴스별 DMA 제어까지
확장할 수 있습니다. Nordic nRF Connect SDK(NCS)와 Zephyr를 기반으로 Sketch·library·OS를
하나의 firmware로 빌드하며, 온보드 CMSIS-DAP으로 업로드합니다. 별도 Sketch Loader는 필요하지 않습니다.

[![Stable: v0.4.1](https://img.shields.io/badge/stable-v0.4.1-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.4.1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](https://github.com/nrfconnect/sdk-nrf)
[![Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-software-gates.yml)
[![Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml/badge.svg?branch=main)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/workflows/m12-reproducible-build.yml)

[현재 상태](#현재-상태) · [빠른 시작](#빠른-시작) · [지원 기능](#지원-기능) · [개발 중인 기능](#개발-중인-기능) · [예제](#예제) · [문서](#문서) · [문제 보고와 기여](#문제-보고와-기여)

| 보드 | 현재 정식 개발 환경 | 기반 SDK | 업로드 |
| --- | --- | --- | --- |
| **NU54DK · nRF54L15 CPUAPP** | Windows 10/11 x64 · Arduino IDE 2.x | NCS v3.4.0 · Zephyr 4.4.0 | CMSIS-DAP V2 + pyOCD |

위 행은 현재 stable `v0.4.1` 기준입니다. 다음 **v0.5.0은 M31 완료 후 Windows 10/11 x64로
릴리스할 계획**입니다. Ubuntu 24.04 이상 AMD64·macOS 26 이상 Apple Silicon은 후속 버전(미정)의
확장 범위이며, 해당 OS의 실제 설치·build·upload·수명주기 검증 후 지원으로 승격합니다.

## 현재 상태

| 구분 | 상태 | 사용할 때의 기준 |
| --- | --- | --- |
| 설치·지원 배포판 | **v0.4.1** | Boards Manager에서 제공하는 유일한 지원 버전. 아래 지원 기능·설치 예제의 기준 |
| 개발 소스 | `main`, 소스 식별자 `0.4.1-dev` | v0.5.0을 목표로 BLE 확장 개발 중. 배포판에 없는 API·예제가 포함됨 |
| M28 GAP·Link·Privacy | **8/8 완료** | 두·세 NU54DK 실기 완료. 개발 브랜치에 반영됐으며 v0.4.1에는 미포함 |
| M29 ATT/GATT·L2CAP | **8/8 완료** | 10/10 test ID, 세 보드 통합·회귀와 Windows/Intel GATT 상호운용 PASS |
| M30 보안·profile·최소 DFU | **8/8 완료** | 10/10 test ID, 실제 전원 차단 4지점 × 3회(12/12), 복구 실패·invalid image boot 0 |
| M31 ISO·Audio·DF·CS | **3/8 완료** | W01 원장·capability, W02 raw ISO, W03 LE Audio 11/11 완료. W04 DF·W05 CS 미완료, W06~W08 미착수 |
| 후속 다중 Host | **3/8 완료, 후속 보류** | HOST-W01~HOST-W03 공통 backend·resolver·launcher 완료. HOST-W04 이후는 사용자 지시로 보류 |
| v0.5.0 릴리스 | 미공개 | 메모리 최적화·M31 8/8과 Windows 패키지·설치·RC·공개 승인 gate 필요. M32/M33은 후속 버전 |

현재 개발 체크포인트는 **M31-W01~W03 완료**입니다. W02의 공개
ISO 예제 11개는 독립 개발 package에서 전수 빌드하고 같은 image로 두·세 보드
역할별 실기를 통과했습니다. [W02 완료 기록](<00_Docs/04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)과
[W03 완료 기록](<00_Docs/04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)에서 ISO·LE Audio의
완료 범위를, [M31 TODO](00_Docs/TODO_M31.md)에서 남은 DF·CS 및 통합 작업을 확인할 수 있습니다.
신규 범위는 [전체 Bluetooth 기능·예제 계약](<00_Docs/01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)에
따라 M31 8개·M32 12개·M33 8개 작업으로 관리합니다.
최신 완료 조건과 증거는 [v0.5.0 개발 계획](00_Docs/TODO_v0.5.0.md)에서 관리합니다.
위 CI 배지는 소프트웨어 검사 상태이며 보드 실기·상호운용·정식 릴리스 완료를 뜻하지 않습니다.

### 프로젝트의 구성

- **Arduino 사용 경로:** Boards Manager 설치, 기능 선택, 예제 Verify/Upload로 시작합니다.
- **Zephyr 기반 실행:** Sketch와 선택 기능을 함께 빌드합니다. 첫 설치와 최초 빌드는 SDK·툴체인을
  준비하므로 시간이 걸리며, 이후에는 증분 빌드와 캐시를 재사용합니다.
- **고급 주변장치 제어:** Peripheral Fabric API로 인스턴스·고정 DMA 버퍼·공유 자원을 명시적으로 다룹니다.
- **검증 근거 공개:** Host 시험, target build, 실제 보드 시험을 구분하고 source·조건·결과를 보존합니다.

지원 보드는 **NU54DK의 nRF54L15 CPUAPP**입니다. 다른 nRF54 보드는 지원 대상이 아닙니다.
Linux/macOS용 Arduino 설치는 현재 `v0.4.1`과 예정 `v0.5.0`의 지원 범위에 포함되지 않습니다.
Zephyr API 직접 사용이나 임의 외부 Arduino library의 빌드 가능성이 그 조합의 검증·제품 지원을
뜻하지는 않습니다. 정확한 Host 범위와 승격 절차는
[다중 Host 지원 계약](<00_Docs/02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 따릅니다.

## 빠른 시작

### 1. Boards Manager에 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 아래 주소를 넣습니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

`Boards Manager`에서 **NUCODE NU54DK Zephyr Boards**를 찾아 **0.4.1**을 설치합니다.
post-install 실행 확인이 나오면 승인하고, NCS와 고정 Toolchain 설치가 끝날 때까지 기다립니다.

Stable 목록은 지원 버전 **0.4.1 하나만** 제공합니다. 그 이전 stable·RC·preview는 지원하지
않으며, 과거 Release 자산은 재현성 감사를 위해서만 보존합니다.

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

설치·업로드가 막히면 [문제 해결](<00_Docs/05_릴리스/v0.4.1/TROUBLESHOOTING.md>)을 확인하세요.
여러 보드의 UID 지정과 외장 J-Link 사용은 [업로드·디버그 안내](<00_Docs/02_빌드 설계/05_업로드와_디버그.md>)에 있습니다.

## 지원 기능

### 일반 Arduino API

| 영역 | v0.4.1 지원 범위 |
| --- | --- |
| Runtime·GPIO·시간 | `setup()`/`loop()`, digital I/O, interrupt, `millis()`/`micros()`, delay와 pulse |
| Serial | DAP UART `Serial`, UART30 기반 `Serial1`와 runtime pin route |
| Wire·SPI | **부분 지원:** Wire는 I2C22 master, SPI는 SPI00 controller. 둘 다 runtime pin route 제공 |
| Analog·출력 | ADC 채널·resolution, 동적 PWM, `tone()`, Servo |
| Storage | EEPROM facade 1,024 byte, 내부 LittleFS 32 KiB, Settings/ZMS |
| BLE | **동시 연결 1개**, GAP Peripheral 또는 Central, NUS, 범용 GATT, pairing·bonding, BAS·DIS·HID keyboard |
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
> [알려진 제약](<00_Docs/05_릴리스/v0.4.1/KNOWN_ISSUES.md>)을 확인하세요.

## 개발 중인 기능

아래는 **`main`의 개발 상태와 후속 계획**입니다. v0.5.0은 M28~M31 범위이며 M32/M33은
후속 버전(미정)입니다. Boards Manager의 v0.4.1 지원표와 구분해서 읽어주세요.
PASS는 명시한 NU54DK 시험 조건에서의 결과이며 다른 제조사·OS peer 전체에 대한 보증은 아닙니다.

| 단계 | 구현·검증한 기능 | 남은 범위 |
| --- | --- | --- |
| M28 — 완료 | Central 최대 1개 + Peripheral 최대 1개, 총 2-link. Generation handle, 확장 광고·스캔, periodic 광고·sync·PAST, PAwR, privacy/RPA, link별 제어 | 해당 개발 계약 완료. OS별 상호운용·Bluetooth qualification·v0.5.0 공개는 별도 |
| M29 — 완료 | 512-byte long/reliable GATT, descriptor·authorization·read multiple, robust cache, LE CoC, Signed Write·EATT opt-in | 10/10 test ID와 세 보드 mixed-link·M19~M21/M28 회귀 PASS. Windows/Intel GATT 외 OS·adapter 전체는 미검증 |
| M30 — 완료 | link별 security·pairing, 유선 OOB·bond/privacy, profile 7개, MCUboot·secure BLE DFU, 세 보드 secure multi-link | W01~W08·10/10 test ID와 실제 전원 차단 12/12 PASS. NFC RF는 결정된 범위대로 NOT RUN |
| M31 — 3/8 완료 | W01 원장·capability, W02 raw ISO 11역할, W03 LE Audio 11개 하위 작업 완료 | 메모리 최적화 → DF·CS → 독립 image별 자원·수명주기·회귀 → 예제·마감·Windows 릴리스 gate |
| M32 — 계획 0/12 | 최신 LE 링크/광고·Nordic 확장, Mesh 1.1·DFU, 최소 radio·공존 | 기능·자원 preset·예제·2/3보드 HIL; HOST-W07 도구·절차 준비 |
| M33 — 계획 0/8 | 표준 service·beacon·ecosystem·HCI/DTM 예제, 전수 parity·Host·상호운용·릴리스 | 전체 예제 설치/build·실행 상태, 세 Host 증거·공개 gate |

Signed Write는 기본 OFF의 **deprecated legacy opt-in** (`NUCODE_BLE_LegacySigning`),
EATT는 기본 OFF의 **experimental opt-in** (`NUCODE_BLE_EATT`)입니다.
M29는 작업 묶음 **8/8**, 시험 ID **10/10 PASS**입니다. 이 완료를 v0.5.0 공개나 모든 OS의
Bluetooth 상호운용·qualification 완료로 해석하지 않습니다.

상세 계약과 제한은 [M28](<00_Docs/01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)·
[M29](<00_Docs/01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>),
실제 결과는 [M28 완료 기록](<00_Docs/04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)·
[M29 완료 기록](<00_Docs/04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)·
[M30 완료 기록](<00_Docs/04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)에서 확인할 수 있습니다.

## 예제

**v0.4.1 설치본**에는 9개 library와 **30개 예제**가 포함됩니다: Standard 22개 · BLE 7개 · Fabric 1개.
아래는 배포판에서도 사용할 수 있는 시작 예제입니다.

| 해보고 싶은 것 | 시작할 예제 |
| --- | --- |
| LED와 보드 정보 | [Blink](libraries/NUCODE_NU54DK/examples/Blink), [BoardInfo](libraries/NUCODE_NU54DK/examples/BoardInfo) |
| 통신과 runtime pin 변경 | [Serial1RuntimePins](libraries/NUCODE_NU54DK/examples/Serial1RuntimePins), [WireRuntimePins](libraries/NUCODE_NU54DK/examples/WireRuntimePins), [SPI00RuntimePins](libraries/NUCODE_NU54DK/examples/SPI00RuntimePins) |
| Analog와 PWM | [AnalogChannels](libraries/NUCODE_NU54DK/examples/AnalogChannels), [DynamicPWM](libraries/NUCODE_NU54DK/examples/DynamicPWM) |
| BLE 통신·보안 | [NUSPeripheral](libraries/NUCODE_BLE/examples/NUSPeripheral), [CustomGattCentral](libraries/NUCODE_BLE/examples/CustomGattCentral), [SecureKeyboard](libraries/NUCODE_BLE_Security/examples/SecureKeyboard) |
| 영구 저장·저전력 | [LittleFSPersistence](libraries/LittleFS/examples/LittleFSPersistence), [SystemOffWake](libraries/NUCODE_NU54DK/examples/SystemOffWake) |
| Fabric capability 조회 | [FabricCapabilities](libraries/NUCODE_Peripheral_Fabric/examples/FabricCapabilities) |

전체 목록과 예제별 profile은 [예제 배포 안내](<00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)에 있습니다.
기능 기준선의 **30/30 예제 compile**, 대표 Blink Upload와 수명주기 결과는
[v0.4.0 정식 공개 검증 기록](<00_Docs/04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)에,
v0.4.1 설치기·공개 package 회귀는 [v0.4.1 기록](<00_Docs/04_검증 기록/129_v0.4.1_설치기_유지보수_릴리스.md>)에 보존합니다.
예제 build 통과와 각 주변장치의 실기 검증 범위는 별개로 기록합니다.

`main`에는 다음 개발 예제도 있습니다. 소스에서 개발할 때 사용하며 v0.4.1 설치 예제에는 포함되지 않습니다.

| 개발 기능 | 예제 진입점 |
| --- | --- |
| 두 link·확장 광고 | [MixedRoleLinks](libraries/NUCODE_BLE/examples/MixedRoleLinks), [ExtendedAdvertising](libraries/NUCODE_BLE/examples/ExtendedAdvertising) |
| Periodic·PAST·PAwR | [PeriodicAdvertiser](libraries/NUCODE_BLE/examples/PeriodicAdvertiser), [PastSender](libraries/NUCODE_BLE/examples/PastSender), [PawrAdvertiser](libraries/NUCODE_BLE/examples/PawrAdvertiser) |
| Long/reliable GATT | [LongGattCentral](libraries/NUCODE_BLE/examples/LongGattCentral), [ReliableWriteCentral](libraries/NUCODE_BLE/examples/ReliableWriteCentral) |
| Cache·LE CoC | [GattCacheCentral](libraries/NUCODE_BLE_Security/examples/GattCacheCentral), [L2capCocClient](libraries/NUCODE_BLE/examples/L2capCocClient) |
| 세 보드 mixed GATT·CoC | [MixedGattCocLinks](libraries/NUCODE_BLE/examples/MixedGattCocLinks) — 같은 Sketch의 role을 바꿔 세 보드에 업로드 |
| 선택 Signed Write·EATT | [LegacySignedWriteCentral](libraries/NUCODE_BLE_LegacySigning/examples/LegacySignedWriteCentral), [EattCentral](libraries/NUCODE_BLE_EATT/examples/EattCentral) |
| Raw ISO | [ISO 예제와 역할 안내](libraries/NUCODE_BLE_ISO/examples/README.md) — CIS·BIS·암호화·시각 동기·combined 11역할 |
| LE Audio | [Audio 예제와 역할 안내](libraries/NUCODE_BLE_Audio/examples/README.md) — LC3·BAP·CAP·CSIP·PBP·제어 profile·TMAP/GMAP·HAP |

개발용 `adaptive` profile은 현재 총 33개 preset을 제공하며, ISO 11역할, Audio BAP 7역할,
HAP 2역할, Audio Control 2역할과 Media Control player/client 2역할을 역할별 최소 설정·소스로 해석합니다.
Media Control 공개 예제도 검증된 `nucode-build.json` sidecar를 제공하며, 기본 `standard` profile은
계속 full 호환 경로로 유지합니다.

송신/수신 역할에 맞는 짝 예제와 보드 수는 각 Sketch 주석과
[프로필·전체 예제 목록](<00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)을 따릅니다.

앞으로 고정 NCS v3.4.0의 nRF54L15 적용 Bluetooth 예제마다 Arduino wrapper·직접 API·검증된
profile·template 중 제공 경로를 배정합니다. 예제에는 보드 역할·설정·예상 출력·오류/복구를 포함합니다.
M31의 기본 수락은 보드 간 실제 프로토콜·합성 Audio 데이터·복구이며 정밀 RF·음질·거리/각도 보정은
필수 gate 밖입니다. 외부 장치와 실제 Host의 미검증 행은 별도로 공개합니다.

2026-09-16 최종 범위에서 Apple/Google 등 외부 ecosystem와 마이크·스피커·외장 장치는 사용 가능한
구현·예제·설정/연결 안내·자동 가능한 검사까지 제공하고 실제 운용·실물 검증은 사용자 후속입니다.
해당 미실행은 v0.5.0 개발·릴리스 차단이 아니며, 실물 호환성이 검증됐다고 표시하지 않습니다.
Apple/Google 기능의 신규 구현은 후속 M33 범위이며 v0.5.0에 포함됐다는 뜻이 아닙니다.
Ubuntu/macOS 실제 설치·USB·serial·debug는 해당 OS를 포함하는 후속 릴리스 단계에서 사용자가 검증합니다.
DF 원시 IQ는 안테나 배열 확보를 선행조건으로 삼지 않고 고정 controller별 수신 경로의 적용성부터
확인합니다. Zephyr LL connected RX 내부 진단에서 raw IQ 일부를 관찰했지만 안정 수신·정지 검증은
미완료입니다. 공개 API와 connectionless RX의 PASS로 확대하지 않습니다.
원인·잔여 범위는 [M31 TODO](00_Docs/TODO_M31.md)에 기록하며 실제 각도 산출과 구분합니다.

## 사용 전 확인

- 실제 결선은 [P2/P4 커넥터 핀맵](<00_Docs/01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)을 기준으로 합니다.
  Fabric의 DAP UART 분리 등 각 API의 전기적 선행조건을 지키세요.
- v0.4.1은 Native USB, OTA/DFU와 외부 filesystem을 지원하지 않습니다. 개발 source의 별도 secure BLE DFU는 M30에서 검증 완료했으며 v0.4.1 설치본에는 포함되지 않습니다.
- Storage format/reset은 데이터를 지웁니다. 버전 이동 전에는 필요한 데이터를 백업하세요.
- GPIO interrupt callback에서 blocking·heap 할당·`Serial`·`delay()`를 사용하지 마세요.
- Servo는 적합한 외부 전원과 공통 GND를 사용하세요. PMIC write는 매 boot 명시적 승인이 필요합니다.
- Active debugger/SWD는 System OFF와 reset cause 관측에 영향을 줄 수 있습니다.

## 문서

| 찾는 내용 | 안내 |
| --- | --- |
| 설치·이전 버전에서 이동 | [Boards Manager 설치](<00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md>) · [마이그레이션](<00_Docs/05_릴리스/v0.4.1/MIGRATION.md>) |
| API·핀·설계 | [전체 문서 목차](00_Docs/README.md) · [API 지원 범위](<00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>) |
| 개발 환경·빌드 구조 | [Windows 개발환경](<00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>) · [Build Adapter](<00_Docs/02_빌드 설계/02_Build_Adapter_설계.md>) |
| v0.5.0 Windows 릴리스·후속 Host 확장 | [v0.5.0 계획](00_Docs/TODO_v0.5.0.md) · [다중 Host 지원 계약](<00_Docs/02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |
| 릴리스·검증 | [v0.4.1 릴리스 문서](<00_Docs/05_릴리스/v0.4.1/README.md>) · [유지보수 기록](00_Docs/TODO_v0.4.1.md) |
| 현재 개발·다음 작업 | [M31 TODO](00_Docs/TODO_M31.md) · [v0.5.0 개발 계획](00_Docs/TODO_v0.5.0.md) · [개발 인계](00_Docs/HANDOFF.md) — M31-W01~W03 완료, 다음은 `M31-MEM-OPT` 메모리 최적화 |
| 이후 Bluetooth 전체 구현·예제 | [전체 기능 계약](<00_Docs/01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>) · [M32 TODO](00_Docs/TODO_M32.md) · [M33 TODO](00_Docs/TODO_M33.md) |
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
`NU54DK.coreVersion()`은 소스 식별자 `0.4.1-dev`를 반환합니다. 정식 설치본에서도 이 값은 같으며,
배포 버전 `0.4.1`은 Boards Manager·`platform.txt`·release manifest로 확인합니다.

SDK·Zephyr·툴체인·보드 revision은 [CI lock](tools/ci/ncs-3.4.0.lock.json)으로 고정합니다.
현재 개발 환경과 검사 명령은 [Windows 개발환경](<00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)과
[개발 인계](00_Docs/HANDOFF.md)를 따르세요. Linux/macOS 개발 절차는 구현·실증 전까지 사용자
설치 절차가 아니며 [후속 다중 Host 계약](<00_Docs/02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)으로
관리합니다. 계약 파일명은 기존 링크 보존을 위해 유지합니다.

## 문제 보고와 기여

[GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)에 아래 정보를 함께 적으면
설치 문제와 firmware 문제를 재현하기 쉽습니다.

- 설치 버전 또는 개발 branch commit, Host OS·architecture·Arduino IDE/CLI 버전, 선택한 Feature set.
- 문제가 재현되는 최소 Sketch와 기대 동작·실제 동작·재현 순서.
- Verify/Upload 오류 전문 또는 Serial 로그, 보드 수·역할·결선과 사용한 주변장치.

인증 정보와 개인 경로·원시 probe UID는 공개 로그에서 제거하세요. 코드·문서 기여는
[작업 지침](AGENTS.md)의 스타일·검증 규칙을 따르고, 변경 이유와 실제 수행한 검사를 함께 남겨주세요.
구현·build 통과를 실기 PASS로 기록하지 않으며, 검증하지 않은 조합은 명시합니다.

## 작성자와 라이선스

**NUCODE의 Quantum**이 개발합니다. NUCODE 작성 코드는 [MIT License](LICENSE)를 적용합니다.
외부 구성요소의 라이선스와 고지는 [Third-party notices](third_party/THIRD_PARTY_NOTICES.md)를 확인하세요.
