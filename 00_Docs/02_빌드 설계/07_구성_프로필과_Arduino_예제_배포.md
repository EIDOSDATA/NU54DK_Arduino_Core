# 구성 프로필과 Arduino 예제 배포 — v0.2.0 정식 / v0.3.0 개발

| 항목 | 현재 계약 |
| --- | --- |
| profile | `standard`, `ble` |
| `v0.2.0` 정식 사용자 예제 | 4개 library, 총 14개 |
| 현재 RC 후보 | 8개 library, 총 29개; Standard 22 / BLE 7 |
| 기본 profile | `standard` |
| BLE feature ID | `nucode.ble.nus` |
| BLE config | `ble-nus.conf` |

Profile은 사용자가 먼저 선택하는 보드 수준 구성이고 feature는 Arduino가 실제 선택한 bundled
library에서 자동 해석하는 추가 구성이다. 실행 결과와 실기 증거는
[M13](<../04_검증 기록/15_M13_구성_프로필_검증.md>),
[M16](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)과
[M18](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>) 기록에 보존한다.

---

## 1. 디렉터리와 단일 원본

~~~text
variants/nu54dk/profiles/
├── standard/
│   ├── profile.json
│   ├── prj.conf
│   └── app.overlay
└── ble/
    ├── profile.json
    ├── prj.conf
    └── app.overlay

libraries/<Library>/
├── library.properties
├── examples/<Example>/<Example>.ino
└── zephyr/
    ├── feature.yml
    ├── *.conf
    └── *.overlay
~~~

공개 예제의 단일 원본은 `libraries/*/examples`다. 문서나 별도 root examples에 같은 sketch를
복사하지 않는다. 예제 폴더와 주 `.ino` 파일 이름은 정확히 같아야 한다.

`profile.json`과 `feature.yml`은 확장자와 무관하게 strict JSON 문법을 사용한다. 중복 key,
알 수 없는 field, 절대 경로, 상위 경로 탈출과 허용 목록 밖 feature ID는 거부한다.

---

## 2. Profile 계약

| ID | 메뉴 표시 | 기능 집합 | 용도 |
| --- | --- | --- | --- |
| `standard` | Standard peripherals | GPIO, Serial, Wire, SPI, ADC, PWM | 일반 Arduino sketch |
| `ble` | BLE NUS | standard 기능 + BLE | NUS peripheral/central |

두 profile 모두 board `nrf54l15dk/nrf54l15/cpuapp/nu54dk`, NCS `v3.4.0`과 각 profile의
`prj.conf`, `app.overlay`를 고정한다. `boards.txt`의 `도구 → Feature set` 메뉴가
`build.nu54_profile`을 다음처럼 설정한다.

~~~text
feature_set=standard → standard
feature_set=ble      → ble
~~~

---

## 3. Bundled library feature 계약

| Library | feature ID | 추가 conf/overlay | 호환 profile |
| --- | --- | --- | --- |
| `NUCODE_NU54DK` | `nucode.board` | `board-system.conf`, `board-system.overlay` | `standard`, `ble` |
| `Wire` | `nucode.wire` | 없음 | `standard`, `ble` |
| `SPI` | `nucode.spi` | 없음 | `standard`, `ble` |
| `NUCODE_BLE` | `nucode.ble.nus` | `ble-nus.conf`, overlay 없음 | `ble`만 |
| `NUCODE_BLE_Security` | `nucode.ble.security` | `ble-security.conf`, overlay 없음 | `ble`만 |
| `Servo` | `nucode.servo` | `servo.conf`, overlay 없음 | `standard`, `ble` |
| `EEPROM` | `nucode.eeprom` | `eeprom.conf`, overlay 없음 | `standard`, `ble` |
| `LittleFS` | `nucode.littlefs` | `littlefs.conf`, overlay 없음 | `standard`, `ble` |

현재 RC 후보 feature ID allowlist는 위 여덟 항목이다. 정식 `v0.2.0` archive는 앞의 네 항목만
가졌다는 역사 기록을 유지한다. BLE NUS feature manifest의 핵심 값은 다음과 같다.

~~~json
{
  "schema_version": 1,
  "id": "nucode.ble.nus",
  "requires": ["ble"],
  "conf": ["ble-nus.conf"],
  "overlays": [],
  "conflicts": ["radio"],
  "compatible_profiles": ["ble"]
}
~~~

`NUCODE_BLE`을 `standard` profile에서 사용하면 자동으로 BLE를 켜지 않고 명확히 실패한다.
사용자가 `ble` profile을 선택해야 한다.

---

## 4. Resolver와 cache 처리 순서

1. `prepare`가 선택 profile을 검증하고 provisional cache를 구성한다.
2. Arduino discovery/compile recipe가 선택한 sketch와 library source를 `record`한다.
3. `link`가 전달된 object에 대응하는 record만 수집한다.
4. source 경로로 사용한 bundled library를 식별한다.
5. 각 library의 `feature.yml`을 strict parsing하고 requires/conflicts/profile 호환성을 검사한다.
6. 선택 feature를 stable order로 합성해 `prj.conf`, overlay와 provenance를 만든다.
7. profile+feature가 포함된 final cache key로 context/record를 원자적으로 이관한다.
8. 결정적인 `sources.cmake`로 Zephyr/Ninja build를 실행한다.

사용하지 않은 library의 feature는 build에 들어가지 않는다. 동일한 profile이라도 선택 feature가
다르면 final cache identity가 다르다.

Sketch root의 `prj.conf`와 `app.overlay`는 전문가용 마지막 override로 허용한다. 공개 14개
예제는 이 sidecar에 의존하지 않으며 profile/library 내부 설정만으로 compile해야 한다.
임의 snippet, module 또는 CMake 주입은 공개 override 계약이 아니다.

---

## 5. v0.2.0 사용자 예제 14개

| Library | 예제 |
| --- | --- |
| `NUCODE_NU54DK` | `AnalogReadA0`, `Blink`, `BoardInfo`, `CounterAlarm`, `InterruptButton`, `PWMFade`, `SerialEcho`, `SettingsStorage`, `SystemOffWake`, `WatchdogBasic` |
| `Wire` | `WirePmicId` |
| `SPI` | `SPITransaction` |
| `NUCODE_BLE` | `NUSPeripheral`, `NUSCentral` |

앞의 12개 예제는 `standard` profile에서, NUS 2개는 `ble` profile에서 compile한다. 예제는
각 library가 source, 설정 요구사항, 문서와 검증을 함께 소유한다.

### 5.1 v0.3.0-rc.1 후보 29개

| Library | 예제 |
| --- | --- |
| `NUCODE_NU54DK` | `AnalogChannels`, `AnalogReadA0`, `AnalogResolution`, `Blink`, `BoardInfo`, `CounterAlarm`, `DynamicPWM`, `InterruptButton`, `PWMFade`, `Serial1RuntimePins`, `SerialEcho`, `SettingsStorage`, `SPI00RuntimePins`, `SystemOffWake`, `ToneOutput`, `WatchdogBasic`, `WireRuntimePins` |
| `Wire` | `WirePmicId` |
| `SPI` | `SPITransaction` |
| `Servo` | `Sweep` |
| `NUCODE_BLE` | `CustomGattCentral`, `CustomGattPeripheral`, `GAPCentral`, `GAPPeripheral`, `NUSCentral`, `NUSPeripheral` |
| `NUCODE_BLE_Security` | `SecureKeyboard` |
| `EEPROM` | `EEPROMPersistence` |
| `LittleFS` | `LittleFSPersistence` |

AC-02B가 추가한 8개는 `AnalogChannels`, `AnalogResolution`, `DynamicPWM`, `Serial1RuntimePins`,
`SPI00RuntimePins`, `ToneOutput`, `WireRuntimePins`, `Servo/Sweep`다. 기존 개발 예제 19개는 Arduino
CLI 19/19 compile을 통과했다. 새 8개도 고정 source snapshot에서 8/8 compile을 통과했고 설치
예제에 AC-03의 EEPROMPersistence와 LittleFSPersistence를 더해 총 29개다. M22는 Standard 22개와
BLE 7개를 고정 목록으로 전체 clean package compile한다.

두 profile은 AC-02B runtime DTS를 포함하고 `Serial1`, Wire, SPI, ADC와 PWM을 활성화한다.
`Servo`는 실제 Sketch가 library를 선택했을 때 `nucode.servo` feature로 PWM22를 추가한다.
Wire target/callback/no-STOP, `Wire1`, `SPI1`은 profile을 선택해도 활성화되지 않는다.

---

## 6. 배포와 자동 검증

정식 `v0.2.0` Boards Manager ZIP은 profile 두 개, feature manifest 네 개와 예제 14개를
포함한다. 현재 `v0.3.0-rc.1` source/package 후보는 feature manifest 여덟 개와 예제 29개를 같은 상대
경로로 보존해야 한다. Arduino IDE/CLI가 설치된 Core에서 library별 예제를 같은 이름으로 열거해야 한다.

자동 gate는 다음을 검사한다.

- profile/feature schema, allowlist, 경로 안전성과 conflict
- 예제 폴더/`.ino` 이름 및 현재 RC 후보 29개 discovery
- standard/ble 대표 7개 예제 compile과 feature provenance
- 공개 예제에 `prj.conf`, `app.overlay` sidecar가 없는지
- source package와 Boards Manager archive의 예제 집합 일치

정식 `v0.2.0` gate가 보장한 범위는 **공개 설치본 14개 예제의 discovery와 14/14 compile**이다.
M22는 고정 lock 목록과 package archive가 일치하는지 확인하고 설치본 29개를 모두 compile한다.
AC-03 두 예제는 `standard`와 `ble` profile build 입력을 각각 별도 smoke로 검사한다.

외부 Arduino library 호환성은 bundled feature allowlist에 자동 편입하지 않고 M17의 고정된
별도 gate로 검증한다.

---

## 7. 관련 구현과 기록

- [`boards.txt`](../../boards.txt)
- [`standard` profile](../../variants/nu54dk/profiles/standard/profile.json)
- [`ble` profile](../../variants/nu54dk/profiles/ble/profile.json)
- [`NUCODE_BLE` feature](../../libraries/NUCODE_BLE/zephyr/feature.yml)
- [M13 구성 프로필 검증](<../04_검증 기록/15_M13_구성_프로필_검증.md>)
- [M15 Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)
- [M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)
- [M17 NCS 기능과 예제 coverage](<../04_검증 기록/19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
- [AC-02B Peripheral/Analog runtime 기준선](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)
- [Arduino Storage API](<../03_펌웨어 설계/10_Arduino_Storage_API.md>)
- [AC-03 Storage와 Library 호환성 기준선](<../04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>)
