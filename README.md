# NU54DK Arduino Core

NU54DK의 **nRF54L15를 Arduino IDE에서 개발하는 오픈소스 Core**입니다.
`setup()`/`loop()`와 Arduino API로 시작하고, BLE·LE Audio·Channel Sounding과
인스턴스별 DMA 제어까지 확장할 수 있습니다. Sketch, 선택한 library와 Zephyr를 하나의
firmware로 빌드하고 온보드 CMSIS-DAP으로 업로드합니다.

[![Stable: v0.4.1](https://img.shields.io/badge/stable-v0.4.1-blue.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.4.1)
[![RC: v0.5.0-rc.1](https://img.shields.io/badge/RC-v0.5.0--rc.1-orange.svg)](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0-rc.1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![NCS: v3.4.0](https://img.shields.io/badge/NCS-v3.4.0-00A9CE.svg)](tools/ci/ncs-3.4.0.lock.json)

[버전 선택](#버전-선택) · [빠른 시작](#빠른-시작) · [지원 기능](#지원-기능) · [예제](#예제) · [문서](#문서) · [기여](CONTRIBUTING.md)

| 보드 | 사용자 환경 | 기반 SDK | 기본 업로드 |
| --- | --- | --- | --- |
| NU54DK · nRF54L15 CPUAPP | Windows 10/11 x64 · Arduino IDE 2.x / CLI | NCS v3.4.0 · Zephyr 4.4.0 | CMSIS-DAP V2 + pyOCD |

## 버전 선택

| 채널 | 버전 | 포함 범위 | 예제 |
| --- | --- | --- | ---: |
| **Stable — 일반 사용·지원 기준** | [v0.4.1](<00_Docs/05_릴리스/v0.4.1/README.md>) | Arduino 주변장치·Peripheral Fabric·기본 BLE·Storage | 30 |
| **공개 RC — 새 기능 시험** | [v0.5.0-rc.1](<00_Docs/05_릴리스/v0.5.0-rc.1/README.md>) | Stable 기능 + 확장 BLE·보안/DFU·ISO·LE Audio·CTE 송신·CS/RAS | 113 |

두 채널 모두 Windows용입니다. RC는 별도 Boards Manager URL로 설치하는 공개 후보이며,
정식 `v0.5.0`은 아직 공개하지 않았습니다. 이전 버전은 지원·catalog 공급이 종료됐고
[릴리스 이력](<00_Docs/05_릴리스/README.md>)으로 보존합니다.

## 빠른 시작

### 1. Core 설치

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 사용할 채널을 추가합니다.

**Stable v0.4.1**

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

**공개 RC v0.5.0-rc.1**

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.1/package_nucode_nu54dk_rc_index.json
```

`Boards Manager`에서 **NUCODE NU54DK Zephyr Boards**를 검색하고 `0.4.1` 또는
`0.5.0-rc.1`을 명시적으로 선택해 설치합니다. Post-install 실행 확인을 승인하고 최종
`Nordic prerequisite installation PASS`를 확인합니다.

첫 설치는 SDK와 Toolchain을 내려받으므로 인터넷 연결·디스크 공간과 시간이 필요합니다.
관리자 권한이나 별도 nRF Connect for Desktop/VS Code·Git·Python 설치는 필수가 아닙니다.
RC 설치·CLI 명령·stable 복귀 방법은 [RC 설치 안내](<00_Docs/05_릴리스/v0.5.0-rc.1/README.md>)에 있습니다.

### 2. 보드와 기능 선택

보드는 `NU54DK (nRF54L15, Zephyr)`, 한 대의 온보드 probe를 쓸 때는
`Upload probe → CMSIS-DAP (pyOCD)`를 선택합니다. `Tools → Feature set`은 예제에 맞춥니다.

| Feature set | 사용할 때 | 제공 버전 |
| --- | --- | --- |
| `Standard peripherals` | GPIO·Serial·Wire·SPI·ADC·PWM·Storage; 기본 선택 | Stable·RC |
| `BLE NUS` | NUS·GAP/GATT·보안과 BLE 예제의 지정 구성 | Stable·RC |
| `Peripheral Fabric (DAP UART disconnected)` | 인스턴스·DMA 직접 제어; 공유 DAP UART 핀 조건 확인 | Stable·RC |
| `Adaptive capabilities (experimental)` | Sketch와 역할 선언에 맞춘 최소 기능 구성; 실험적 선택 | RC |
| `Secure BLE DFU (MCUboot)` | 서명된 BLE update; 전용 layout·키 설정 필요 | RC |
| `BLE Audio external I/O (DAP UART disconnected)` | 외장 Audio I/O 예제의 전용 구성·결선 | RC |

RC도 기본값은 `standard`입니다. 고급 예제의 `nucode-build.json`, `prj.conf`, `app.overlay`는
예제 폴더와 함께 유지하고, 역할·보드 수·profile은 각 예제 README를 따릅니다.
CLI의 기본 FQBN은 `nucode:zephyr:nu54dk`입니다.

### 3. Blink 업로드

데이터 통신 가능한 USB cable로 NU54DK를 연결합니다.
`File → Examples → NUCODE NU54DK → Blink`를 열고 `Standard peripherals`에서
**Verify → Upload**를 실행합니다. 온보드 LED가 250 ms 간격으로 점멸하면 기본 경로가 정상입니다.

첫 빌드는 SDK 전체 구성을 준비하므로 이후 증분 빌드보다 오래 걸립니다. Serial 예제는
대응하는 DAP UART COM port를 **115200 8N1**로 엽니다. `Serial`은 native USB CDC가 아닙니다.
Probe가 여러 대면 [업로드·디버그 안내](<00_Docs/02_빌드 설계/05_업로드와_디버그.md>)에 따라 대상을 지정합니다.

## 지원 기능

### Stable v0.4.1과 RC의 공통 기능

| 영역 | 제공 범위 |
| --- | --- |
| Arduino 기본 | GPIO·interrupt·시간·delay·pulse, `String`·`Print`·`Stream` |
| Serial·Wire·SPI | DAP UART `Serial`, UART30 `Serial1`, I2C22 master `Wire`, SPI00 controller `SPI`; runtime pin route |
| Analog·출력 | ADC 채널·resolution, 동적 PWM, `tone()`, Servo |
| Storage | EEPROM facade 1,024 byte, 내부 LittleFS 32 KiB, Settings/ZMS |
| 기본 BLE | NUS, GAP Central/Peripheral, 범용 GATT, pairing·bonding, BAS·DIS·HID keyboard |
| Board·System | Board identity, watchdog, GRTC, System OFF와 timer/button wake |
| Peripheral Fabric | UARTE·SPIM/SPIS 00/20/21/22/30, TWIM/TWIS 20/21/22/30; SAADC·PWM·timer/event·PDM·I2S·QDEC·TEMP·watchdog 직접 제어 |

`Wire` target/slave·`Wire1`, `SPI` peripheral·`SPI1`은 일반 Arduino API에 없습니다.
직접 인스턴스 제어는 `fabric` profile과 `<NUCODE_Peripheral_Fabric.h>`를 사용합니다.
QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event 경로를 지원하며,
반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.

### 공개 RC에서 추가된 기능

| 기능군 | RC 제공 범위 |
| --- | --- |
| GAP·Link·Privacy | Central 최대 1개 + Peripheral 최대 1개, 총 2-link; 확장·주기 광고, PAST·PAwR, privacy/RPA |
| GATT·L2CAP | Long/reliable GATT, descriptor·authorization·cache, LE CoC; 선택형 Signed Write·EATT |
| 보안·Profile·DFU | Link별 보안·OOB·bond 관리, 추가 표준 profile, 별도 MCUboot secure BLE DFU |
| ISO·LE Audio | CIS/BIS·암호화·시간 동기, LC3, BAP/CAP/CSIP/PBP, Audio 제어와 TMAP/GMAP/HAP 역할 예제 |
| Direction Finding | 제품 SDC의 connectionless AoA CTE 송신·별도 Zephyr LL opt-in의 연결형 CTE response; 제품 SDC IQ RX·AoD는 미지원 |
| Channel Sounding | Initiator/reflector, RAS, raw/거리 결과와 오류·재접속 경로 |

Stable의 BLE 동시 연결은 1개입니다. 위 RC 기능과 역할별 한계는
[RC Release notes](<00_Docs/05_릴리스/v0.5.0-rc.1/RELEASE_NOTES.md>)와 각 예제 안내를 따릅니다.
Signed Write는 deprecated legacy opt-in, EATT와 adaptive는 experimental opt-in입니다.

### 사용 범위와 제한

- 지원 보드는 NU54DK의 nRF54L15 CPUAPP이며 Ubuntu/macOS 사용자 설치는 아직 지원하지 않습니다.
- LE Audio는 보드 간 합성 PCM/LC3·프로토콜 경로를 검증했습니다. 외장 마이크·스피커·상용 peer의
  실제 운용은 미검증이며 정밀 음질·거리·각도 보정을 보증하지 않습니다.
- ISO·Audio·DF·CS의 모든 기능을 한 image에서 동시에 사용하는 구성과 모든 주변장치 조합을 보증하지 않습니다.
- Native USB·Wi-Fi·Ethernet·Thread·Matter·Mesh는 이 두 배포판의 지원 범위가 아닙니다.
- 실제 결선은 [P2/P4 핀맵](<00_Docs/01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)을 확인합니다.
  Storage format/reset은 데이터를 지우며, GPIO interrupt callback에서는 blocking·heap 할당·`Serial`·`delay()`를 사용하지 않습니다.

세부 제한은 [Stable Known issues](<00_Docs/05_릴리스/v0.4.1/KNOWN_ISSUES.md>)와
[RC Known issues](<00_Docs/05_릴리스/v0.5.0-rc.1/KNOWN_ISSUES.md>)에서 확인할 수 있습니다.

## 예제

Stable에는 **9개 library·30개 예제**, 공개 RC에는 **16개 library·113개 예제**가 포함됩니다.
Arduino IDE의 `File → Examples`에서 열거나 다음 경로에서 코드를 확인할 수 있습니다.

| 해보고 싶은 것 | 시작할 예제 | 채널 |
| --- | --- | --- |
| LED·보드 정보 | [Blink](libraries/NUCODE_NU54DK/examples/Blink) · [BoardInfo](libraries/NUCODE_NU54DK/examples/BoardInfo) | Stable·RC |
| 통신·핀 변경 | [Serial1RuntimePins](libraries/NUCODE_NU54DK/examples/Serial1RuntimePins) · [WireRuntimePins](libraries/NUCODE_NU54DK/examples/WireRuntimePins) · [SPI00RuntimePins](libraries/NUCODE_NU54DK/examples/SPI00RuntimePins) | Stable·RC |
| BLE 통신·보안 | [NUSPeripheral](libraries/NUCODE_BLE/examples/NUSPeripheral) · [NUSCentral](libraries/NUCODE_BLE/examples/NUSCentral) · [SecureKeyboard](libraries/NUCODE_BLE_Security/examples/SecureKeyboard) | Stable·RC |
| 저장·저전력 | [LittleFSPersistence](libraries/LittleFS/examples/LittleFSPersistence) · [SystemOffWake](libraries/NUCODE_NU54DK/examples/SystemOffWake) | Stable·RC |
| 직접 주변장치 제어 | [FabricCapabilities](libraries/NUCODE_Peripheral_Fabric/examples/FabricCapabilities) | Stable·RC |
| 두 link·CoC | [MixedRoleLinks](libraries/NUCODE_BLE/examples/MixedRoleLinks) · [L2capCocClient](libraries/NUCODE_BLE/examples/L2capCocClient) | RC |
| ISO·LE Audio | [ISO 역할 안내](libraries/NUCODE_BLE_ISO/examples/README.md) · [Audio 역할 안내](libraries/NUCODE_BLE_Audio/examples/README.md) | RC |
| CTE 송신·거리 측정 | [Direction Finding](libraries/NUCODE_BLE_DirectionFinding/examples/README.md) · [RasInitiator](libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator/README.md) · [RasReflector](libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector/README.md) | RC |

전체 목록과 profile은 [예제 배포 안내](<00_Docs/02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)를
따릅니다. RC의 Windows 설치 예제 **113/113 compile**과 공개 다운로드·설치·재설치 결과는
[RC Testing](<00_Docs/05_릴리스/v0.5.0-rc.1/TESTING.md>)에 있습니다. Compile 결과와 실제 보드 검증 범위를 구분해 기록합니다.

## 문서

| 찾는 내용 | 안내 |
| --- | --- |
| 설치·마이그레이션·문제 해결 | [Stable 문서](<00_Docs/05_릴리스/v0.4.1/README.md>) · [RC 문서](<00_Docs/05_릴리스/v0.5.0-rc.1/README.md>) |
| API·핀·설계 | [전체 문서 목차](00_Docs/README.md) · [API 지원 범위](<00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>) |
| Core 개발·검사·기여 | [기여 안내](CONTRIBUTING.md) · [Windows 개발환경](<00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>) |
| 현재 개발 상태·다음 작업 | [HANDOFF](00_Docs/HANDOFF.md) · [RC2 교정 계획](00_Docs/TODO_v0.5.0-RC2.md) · [v0.5.0 TODO](00_Docs/TODO_v0.5.0.md) |
| 실기·배포 근거 | [검증 기록](<00_Docs/04_검증 기록/README.md>) · [릴리스 이력](<00_Docs/05_릴리스/README.md>) |

현재 개발 브랜치는 `main`에서 분기한 `0.5.0-RC2`이며, 통합한 `0.5.0-RC1` 브랜치는 별도로
보존합니다. M28~M31과 메모리 최적화 P0~P2, Windows RC1 공개 검증은 완료했고, RC2에서는
예제 설정·Upload probe·UTF-8 진단·Verify 진행 표시를 교정합니다. RC2 공개와 정식 v0.5.0은
각각 별도 승인 대상입니다.
이번 main 통합·이력 정리는 새 릴리스가 아닙니다. Stable v0.4.1의 설치 목록·공개 자산과
RC tag의 원래 source `7786984a186980f6220271cd506636e4564bc55d`는 바꾸지 않았습니다.
공개 패키지 재현에는 branch HEAD 대신 release tag·manifest를 사용합니다. 기존 checkout의
안전한 전환은 [기여 안내](CONTRIBUTING.md#이력-정리-뒤-기존-checkout), 통합 근거는
[270번 기록](<00_Docs/04_검증 기록/270_main_RC_통합_Squash와_문서_동기화.md>)을 따릅니다.

`NU54DK.coreVersion()`의 `0.4.1-dev`는 소스 식별 문자열입니다. 실제 설치 버전은
Boards Manager·`arduino-cli core list`·release manifest에서 확인합니다.

## 문제 보고와 기여

[GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)에 설치 버전,
Windows·Arduino IDE/CLI 버전, Feature set, 최소 Sketch, 기대/실제 동작과 첫 오류 로그를 남겨주세요.
실물 문제에는 보드 수·역할·결선을 함께 적고 인증 정보와 원시 probe UID는 제거합니다.
수정과 검증 절차는 [CONTRIBUTING](CONTRIBUTING.md)을 따릅니다.

## 작성자와 라이선스

**NUCODE의 Quantum**이 개발합니다. NUCODE 작성 코드는 [MIT License](LICENSE)를 적용합니다.
외부 구성요소의 라이선스와 고지는 [Third-party notices](third_party/THIRD_PARTY_NOTICES.md)를 확인하세요.
