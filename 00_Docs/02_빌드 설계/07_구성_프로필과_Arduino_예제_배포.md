# 구성 프로필과 Arduino 예제 배포 — v0.4.1 정식

| 항목 | 현재 계약 |
| --- | --- |
| `v0.4.1` 정식 profile | `standard`, `ble`, `fabric` |
| `v0.4.1` 정식 사용자 예제 | 9개 library, 총 30개; Standard 22 / BLE 7 / Fabric 1 |
| 이전 `v0.3.0` | `standard`, `ble`; 8개 library·예제 29개 |
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
├── ble/
│   ├── profile.json
│   ├── prj.conf
│   └── app.overlay
└── fabric/
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
| `ble` | BLE NUS | standard 기능 + BLE | NUS, GAP/GATT, 보안·표준 profile |
| `fabric` | Peripheral Fabric (DAP UART disconnected) | GPIO, time, 직접 Fabric | v0.4.0에서 도입해 v0.4.1에 유지한 고급 주변장치 API |

세 profile 모두 board `nrf54l15dk/nrf54l15/cpuapp/nu54dk`, NCS `v3.4.0`과 각 profile의
`prj.conf`, `app.overlay`를 고정한다. `boards.txt`의 `도구 → Feature set` 메뉴가
`build.nu54_profile`을 다음처럼 설정한다.

~~~text
feature_set=standard → standard
feature_set=ble      → ble
feature_set=fabric   → fabric
~~~

`fabric`은 v0.4.0에서 도입해 v0.4.1에 유지한 정식 profile입니다. 직접 nrfx IRQ와 peripheral block을 소유하므로 standard
singleton을 함께 활성화하지 않습니다. P1.4~P1.7을 route로 쓰려면 보드의 DAP UART가 물리적으로
분리돼 있어야 합니다.

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
| `NUCODE_Peripheral_Fabric` | `nucode.peripheral.fabric` | `peripheral-fabric.conf`, overlay 없음 | `fabric`만 |

정식 `v0.4.1`은 위 아홉 feature를 제공합니다. `NUCODE_Peripheral_Fabric`은 T16에서 추가한
정식 경로이며 이전 v0.3.0의 여덟 feature와 archive는 소급 변경하지 않습니다.
`v0.2.0` archive가 앞의 네 항목만 가졌다는 사실도 해당 버전의 역사 기록으로 유지합니다.
BLE NUS feature manifest의 핵심 값은 다음과 같습니다.

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

Sketch root의 `prj.conf`와 `app.overlay`는 전문가용 마지막 override로 허용한다. v0.4.1 공개 30개
예제는 이 sidecar에 의존하지 않으며 profile/library 내부 설정만으로 compile해야 한다.
임의 snippet, module 또는 CMake 주입은 공개 override 계약이 아니다.

### 4.1 메모리 layout의 별도 선택 축

`v0.4.1`의 세 profile은 같은 loaderless 기본 layout을 사용한다. Application은
`0x000000..0x16c000`의 1,490,944 byte(1,456 KiB), LittleFS와 Settings/ZMS는 RRAM 끝의
32 KiB와 36 KiB다. Feature set 선택은 메모리 layout을 암묵적으로 바꾸지 않는다.

향후 `v0.5.0` M30에서 BLE DFU용 최소 MCUboot·signed update·rollback 기반을 먼저
설계·검증한다. 제한된 고정 layout과 제공 경로(profile 또는 application template)를 선택하는
단계이며, 아직 새 profile·feature·Tools 메뉴를 제공하지 않는다.

`v0.6.0` M36은 이 최소 기반을 여러 layout·update transport로 확장하는 후속 계획이다.
고급 `Tools → Memory layout`을 제공할 때에는 검증된 preset이 feature set과 별개의 명시적
입력이 되고, fixed partition, linker 경계, Arduino maximum size와 cache identity가 함께
바뀌어야 한다. 현재는 임의 숫자나 Sketch `app.overlay` 하나만으로 partition을 바꾸는 구성을
정식 지원하지 않는다. M30과 M36 모두 미착수이며, M30 착수·인계 조건은
[v0.5.0 착수 계획](../TODO_v0.5.0.md)을 따른다.

---

## 5. v0.4.1 사용자 예제 30개

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
| `NUCODE_Peripheral_Fabric` | `FabricCapabilities` |

Standard 22개, BLE 7개, Fabric 1개를 각 권장 profile에서 빌드한다. 예제의 source·설치본 발견
목록은 M27 lock과 대조하며 T20/T21·T24에서 설치본 전체 30개를 빌드했다. 이전 v0.3.0의 29개와
각 API의 도입 이력은 [v0.3.0 마일스톤](<../01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)을 따른다.

`standard`와 `ble`은 AC-02B runtime DTS를 포함하고 `Serial1`, Wire, SPI, ADC와 PWM을 활성화한다.
`Servo`는 실제 Sketch가 library를 선택했을 때 `nucode.servo` feature로 PWM22를 추가한다.
Wire target/callback/no-STOP, `Wire1`, `SPI1`은 profile을 선택해도 활성화되지 않는다.

---

## 6. 배포와 자동 검증

정식 `v0.4.1` Boards Manager ZIP은 profile 세 개, feature manifest 아홉 개와 예제 30개를
같은 상대 경로로 보존한다. Arduino IDE/CLI가 설치된 Core에서 library별 예제를 같은 이름으로
열거해야 한다.

자동 gate는 다음을 검사한다.

- profile/feature schema, allowlist, 경로 안전성과 conflict
- 예제 폴더/`.ino` 이름 및 정식 30개 discovery
- profile별 예제 compile과 feature provenance
- 공개 예제에 `prj.conf`, `app.overlay` sidecar가 없는지
- source package와 Boards Manager archive의 예제 집합 일치

이전 v0.2.0의 14개와 v0.3.0의 29개 예제 결과는 각 버전의 역사 기록으로 남는다.
AC-03 두 예제는 `standard`와 `ble` profile build 입력을 각각 별도 smoke로 검사한다.

v0.4.1 stable lock은 `NUCODE Peripheral Fabric/FabricCapabilities`를 더한 30개입니다. 이 예제는
`fabric` profile만 사용하고 sidecar 없이 빌드됩니다. QDEC20/21은 capability에서 `supported`이며,
연속 카운트에는 SAMPLE/REPORT event 경로를 사용합니다. T20/T21과 공개 후 T24에서 30개 전체
설치 package 검증을 완료했습니다.

외부 Arduino library 호환성은 bundled feature allowlist에 자동 편입하지 않고 M17의 고정된
별도 gate로 검증한다.

---

## 7. 관련 구현과 기록

- [`boards.txt`](../../boards.txt)
- [`standard` profile](../../variants/nu54dk/profiles/standard/profile.json)
- [`ble` profile](../../variants/nu54dk/profiles/ble/profile.json)
- [`fabric` profile](../../variants/nu54dk/profiles/fabric/profile.json)
- [`NUCODE Peripheral Fabric` feature](../../libraries/NUCODE_Peripheral_Fabric/zephyr/feature.yml)
- [`NUCODE_BLE` feature](../../libraries/NUCODE_BLE/zephyr/feature.yml)
- [M13 구성 프로필 검증](<../04_검증 기록/15_M13_구성_프로필_검증.md>)
- [M15 Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)
- [M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)
- [M17 NCS 기능과 예제 coverage](<../04_검증 기록/19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
- [AC-02B Peripheral/Analog runtime 기준선](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)
- [T16 Peripheral Fabric 설치 통합](<../04_검증 기록/118_T16_Peripheral_Fabric_설치_통합.md>)
- [Arduino Storage API](<../03_펌웨어 설계/10_Arduino_Storage_API.md>)
- [AC-03 Storage와 Library 호환성 기준선](<../04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>)
