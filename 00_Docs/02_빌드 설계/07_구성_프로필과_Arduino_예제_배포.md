# 구성 프로필과 Arduino 예제 배포 — v0.4.1 정식

| 항목 | 현재 계약 |
| --- | --- |
| `v0.4.1` 정식 profile | `standard`, `ble`, `fabric` |
| `v0.4.1` 정식 사용자 예제 | 9개 library, 총 30개; Standard 22 / BLE 7 / Fabric 1 |
| 이전 `v0.3.0` | `standard`, `ble`; 8개 library·예제 29개 |
| 기본 profile | `standard` |
| BLE feature ID | `nucode.ble.nus` |
| BLE config | `ble-nus.conf` |

위 수치는 현재 stable `v0.4.1`의 Windows 설치본 계약이다. `v0.5.0` 공개 전에는 새 BLE 예제를
포함한 최종 공개 예제 목록을 고정하고 Windows 10/11 x64 지원 행에서 목록 discovery와 독립
compile을 수행한다. Ubuntu/macOS는 [다중 Host 지원 계약](10_v0.5.0_다중_Host_지원_착수_계약.md)에
따라 후속 제품선에서 검증한다. 한 Host의 compile 결과를 다른 Host의 PASS로 합산하지 않는다.

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

공개 `.ino`에는 사용자가 읽고 수정할 수 있는 C++/`NUCODE_*` API의 설정·송수신·오류·종료 흐름을 둔다.
Zephyr 직접 호출은 library 구현 내부가 소유하며 개발 마일스톤 이름이나 시험 전용 oracle을 노출하지 않는다.

`profile.json`과 `feature.yml`은 확장자와 무관하게 strict JSON 문법을 사용한다. 중복 key,
알 수 없는 field, 절대 경로, 상위 경로 탈출과 허용 목록 밖 feature ID는 거부한다.

---

## 2. Profile 계약

| ID | 메뉴 표시 | 기능 집합 | 용도 |
| --- | --- | --- | --- |
| `standard` | Standard peripherals | GPIO, Serial, Wire, SPI, ADC, PWM | 일반 Arduino sketch |
| `adaptive` | Adaptive capabilities (experimental) | compiler probe·library manifest·role declaration의 합집합 | 기능별 최소 설정·소스 개발 경로 |
| `ble` | BLE NUS | standard 기능 + BLE | NUS, GAP/GATT, 보안·표준 profile |
| `fabric` | Peripheral Fabric (DAP UART disconnected) | GPIO, time, 직접 Fabric | v0.4.0에서 도입해 v0.4.1에 유지한 고급 주변장치 API |

모든 profile은 board `nrf54l15dk/nrf54l15/cpuapp/nu54dk`, NCS `v3.4.0`과 각 profile의
`prj.conf`, `app.overlay`를 고정한다. `boards.txt`의 `도구 → Feature set` 메뉴가
`build.nu54_profile`을 다음처럼 설정한다.

~~~text
feature_set=standard → standard
feature_set=adaptive → adaptive
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

단, 선택된 공통 profile/library 내부의 모든 기능과 정적 pool이 사용량에 맞게 제거된다는 뜻은
아니다. `M31-MEM-OPT`는 실제 ELF/map 기준으로 미사용 Core route·pin state·GATT/BLE pool을
감사하고 역할별 구성에 반영할 후속 구현이다. 현재의 설정 합성 기능과 최적화 완료를 구분한다.

### 4.1 후속 선언 기반 기본 profile

후속 최적화의 목표 기본 경로는 현재 `standard`/`ble`처럼 주변장치와 BLE 범용 기능을 먼저
모두 켜는 구성이 아니다. compiler-assisted capability probe, 선택 library의 feature manifest와
공개 role/capacity 선언의 합집합으로 최종 구성을 만든다.

- `SPI.begin()`의 도달 가능한 사용은 SPI Kconfig·Devicetree·source·route를 활성화한다.
- include-only이고 실제 SPI API 사용과 library dependency가 없으면 SPI backend를 넣지 않는다.
- library 내부의 간접 SPI/Wire 요구는 해당 library manifest가 선언한다.
- BLE umbrella header는 모든 GAP/GATT/L2CAP/PAwR·최대 pool을 켜는 신호가 아니다.
- BLE 역할·connection/stream/ASE 상한은 검증된 공개 preset/declaration으로 보완한다.
- 판정 불가·누락·충돌은 명확히 실패하며 full profile로 자동 후퇴하지 않는다.

generic GATT는 용도에 따라 `ble-gatt-server-peripheral` 또는
`ble-gatt-client-central`을 선언한다. 전자는 client discovery/cache source와 Zephyr GATT client를,
후자는 local dynamic database/server source를 제외한다. server/client와 NUS를 한 image에서
모두 사용하는 호환 구성은 `ble-gatt-nus-dual-role`을 명시적으로 선택한다.
server notification·indication의 최대 동시 전송 수는 adaptive declaration의
`ble.gatt-tx-contexts`(1~128)로 지정한다. 두 종류가 하나의 bounded pool을 공유하고,
가득 차면 `busy`로 거부한다. 값을 생략한 호환 구성은 64개를 예약한다.

resolver 결과는 machine-readable `resolved-capabilities.json`으로 보존하고 생성 `prj.conf`, overlay,
source/init 선택과 cache identity가 모두 이를 따라야 한다. 기존 full 동작은 명시적
legacy/compatibility 선택지로 유지하되 차기 기본 경로의 완료 기준으로 쓰지 않는다. 공개 v0.4.1
package와 archive는 소급 변경하지 않는다. 설계와 검증 순서는
[M31 메모리 최적화 통합 설계](<../01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)를 따른다.

Sketch root의 `prj.conf`와 `app.overlay`는 전문가용 마지막 override로 허용한다. v0.4.1 공개 30개
예제는 이 sidecar에 의존하지 않으며 profile/library 내부 설정만으로 compile해야 한다.
임의 snippet, module 또는 CMake 주입은 공개 override 계약이 아니다.

### 4.2 상위 정책 preset과 전문가 직접 지정

사용자 선택은 다음 세 층으로 구분한다.

| 층 | 대상 사용자 | 입력 | 책임 |
| --- | --- | --- | --- |
| 자동 구성 | 일반 사용자 | `Adaptive capabilities` + Sketch/API/library/role 선언 | resolver가 Kconfig·Devicetree·source·capacity를 최소 합성 |
| 상위 정책 preset | 기능 조합을 명시하려는 사용자 | 향후 `Radio disabled`, `BLE`, `802.15.4`, `BLE + 802.15.4`와 controller/안테나 같은 Tools 메뉴 | 서로 배타적인 전역 정책과 검증된 조합을 선택하고, 세부 구성은 resolver에 위임 |
| 전문가 override | Zephyr/NCS 설정을 직접 조정하는 사용자 | Sketch root의 `prj.conf`, 필요할 때 `app.overlay` | 자동 결과 뒤에 명시 설정을 병합하되 최종 gate를 통과해야 함 |

상위 정책 preset은 `.conf`·overlay 조각을 무조건 넓게 켜는 두 번째 full profile이 아니다. 예를 들어
`BLE`은 radio family와 controller 정책을 고정할 뿐 central/peripheral/observer/broadcaster, GATT,
SMP, Audio 역할을 모두 켜지 않는다. 실제 API와 role이 요구한 세부 capability만 resolver가 추가한다.
`BLE + 802.15.4`도 공존 가능 controller·메모리·clock 조합이 검증된 뒤에만 메뉴로 공개한다.

전문가 경로는 현재 구현돼 있다. Sketch 주 `.ino`와 같은 폴더의 `prj.conf`는 template → profile →
선택 library/capability fragment 다음, 마지막 Kconfig 입력으로 합쳐진다. 같은 위치의 `app.overlay`도
생성 overlay 뒤에 합쳐진다. 두 파일의 내용 hash는 cache identity와 build provenance에 포함되므로
변경 뒤 이전 cache를 같은 구성으로 재사용하지 않는다.

마지막 입력이라는 것은 안전 검사를 우회한다는 뜻이 아니다. `adaptive`에서 resolver가 요구한 필수
Kconfig를 `n`으로 바꾸거나 연결·ISO stream·bond 같은 검증된 capacity를 낮추면 최종 `.config`
대조에서 명시적으로 실패해야 한다. Kconfig dependency가 거부한 조합, 지원하지 않는 controller/role,
board에서 사용할 수 없는 장치, code/storage partition 침범도 실패한다. 임의 CMake·source/module 주입,
검증되지 않은 partition 숫자 변경은 이 공개 고급 계약에 포함하지 않는다.

따라서 직접 지정의 권장 용도는 로그 수준, 검증된 buffer 상한의 상향, application 고유 Zephyr option,
허용된 장치 property처럼 자동 판정에 없는 추가 요구다. 자동으로 선택된 필수 기능을 강제로 끄거나
검증되지 않은 자원 축소로 빌드만 통과시키는 용도가 아니다. 최종 artifact에는 자동 판정과 override의
출처, 최종 `.config`·Devicetree hash를 함께 남긴다. builder의 정적 자원 감사에는 source manifest·
ELF·linker map·adaptive capability 결과 hash, FLASH/RAM 사용량과 headroom, 상위 RAM symbol 32개도
포함된다. adaptive image는 75%에서 경고하고 85% 이상을 실패 처리하며, 비활성 기능 전용 queue처럼
명시된 금지 symbol이 ELF에 남아도 실패한다. 이 검사는 사용자 override에도 동일하게 적용된다.

### 4.3 메모리 layout의 별도 선택 축

`v0.4.1`의 세 profile은 같은 loaderless 기본 layout을 사용한다. Application은
`0x000000..0x16c000`의 1,490,944 byte(1,456 KiB), LittleFS와 Settings/ZMS는 RRAM 끝의
32 KiB와 36 KiB다. Feature set 선택은 메모리 layout을 암묵적으로 바꾸지 않는다.

`v0.5.0` 개발 M30은 BLE DFU용 최소 MCUboot·signed update·rollback 기반과 별도
`secure_ble_dfu` profile을 구현했다. 개발 Tools 메뉴의 `Secure BLE DFU (MCUboot)`는
sysbuild와 maximum size `729088` byte를 선택한다. 설치·지원 v0.4.1의 위 세 profile에는 포함되지 않는다.

`v0.6.0` M36은 이 최소 기반을 여러 layout·update transport로 확장하는 후속 계획이다.
고급 `Tools → Memory layout`을 제공할 때에는 검증된 preset이 feature set과 별개의 명시적
입력이 되고, fixed partition, linker 경계, Arduino maximum size와 cache identity가 함께
바뀌어야 한다. 현재는 임의 숫자나 Sketch `app.overlay` 하나만으로 partition을 바꾸는 구성을
정식 지원하지 않는다. M30은 W01~W08 8/8·test ID 10/10과 실제 전원 차단 12/12를 완료했고
M36은 미착수다. 완료·인계 조건은 [v0.5.0 착수 계획](../TODO_v0.5.0.md)과
[문서 전면검토·개선 마일스톤](<../01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)을 따른다.

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

### 개발 `main`의 추가 예제

2026-09-21 정비 기준 개발 소스는 **library 16개·`.ino` 113개**다. 이는 source 발견 수이며,
각 예제의 build/runtime 완료는 별도로 집계한다. M31-W02는 설치본 ISO 11예제·11역할,
W03은 Audio 11개 묶음을 완료했고 DF·CS는 미완료다. 실제 경로와 단계별 증거는
[M31 readiness](../../variants/nu54dk/m31-ble-readiness.json)와 [M31 TODO](../TODO_M31.md)를 따른다.

이전 2026-09-15 검토한 `8c311d9a…`의 `0.4.1-dev` 소스 트리에는 12개 library와 60개 `.ino`가 있었다.
정식 v0.4.1 예제 30개에 M28 11개, M29 15개, M30 profile 예제 4개가 추가된 snapshot이다.
`NUCODE_BLE_DFU`는 별도 library이며 새 `.ino`를 더하지 않는다. 이 수를 v0.4.1 설치본의 제공 수로
표시하지 않는다. M28·M29·M30은 완료했지만 v0.5.0 package 공개는 아직 아니다.

| 개발 추가 범위 | Library와 선택 방식 | 검증 진입점 |
| --- | --- | --- |
| M28 GAP/link/periodic/PAwR/privacy 11개 | `NUCODE_BLE`, `feature_set=ble` | `run_smoke.py --tests m28` |
| M29 GATT·descriptor·CoC·mixed 9개 | `NUCODE_BLE`, `feature_set=ble` | `run_smoke.py --group v0.5.0` |
| M29 GATT cache 2개 | `NUCODE_BLE_Security`, `nucode.ble.security` | 같은 v0.5.0 group |
| M29 Signed Write 2개 | `NUCODE_BLE_LegacySigning`, `nucode.ble.legacy_signing` | 같은 v0.5.0 group; deprecated legacy opt-in |
| M29 EATT 2개 | `NUCODE_BLE_EATT`, `nucode.ble.eatt` | 같은 v0.5.0 group; experimental opt-in |
| M30 profile 4개 | `NUCODE_BLE_Security`, `feature_set=ble` | `run_smoke.py --tests m30` |
| M30 secure DFU build 조건 | 기존 `HeartRate` 예제, `feature_set=secure_ble_dfu` | `run_smoke.py --tests m30secure`; 저장소 밖 signing key 필요 |

선택형 두 library는 모두 `ble` profile에서만 사용하며, header를 포함하지 않은 기본 BLE build에
signing/EATT를 강제로 켜지 않는다. M29의 실제 예제명과 완료·잔여 상태는
[M29 계약의 예제 목록](<../01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md#8-개발-예제와-남은-예제>)을 따른다.

---

## 7. 관련 구현과 기록

### M31 v0.5.0과 후속 제품선의 예제 구현·검증 TODO

현재 공개 30개와 개발 snapshot 수치는 위의 고정 시점 기준이다. 다음 표는 단계별 예제 계약이다.
M31-W02/W03은 완료했고 나머지는 진행 중 또는 계획이며 공개 v0.4.1 설치 목록과 구분한다. 상세 feature·role은
[전체 Bluetooth 기능·예제 계약](<../01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)과
[M31](../TODO_M31.md)·[M32](../TODO_M32.md)·[M33](../TODO_M33.md) TODO에서 추적한다.
M31-W08까지의 예제 정합화와 Windows package·설치·RC gate를 v0.5.0에서 마감한다.
M32·M33의 추가 기능·예제와 Ubuntu/macOS 지원은 후속 제품선이며 배포 버전은 미정이다.

| 소유 단계 | 반드시 제공/판정할 예제 묶음 |
| --- | --- |
| M31-W02 — 완료 | CIS central/peripheral, BIS broadcaster/receiver, combined ISO·time sync·recovery; [설치본 11예제·11역할 증거](<../04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) |
| M31-W03 — 완료 | BAP unicast/broadcast·PACS/ASCS, BASS assistant/delegator, CAP·CSIP·PBP, volume/input/microphone/media/call 제어, TMAP/GMAP/HAP; [11/11 완료 감사](<../04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>) |
| M31-W04~W05 | AoA CTE TX의 connected/connectionless 예제, DF RX/IQ 적용성, CS initiator/reflector·RAS·복구 |
| M31-W07~W08 및 v0.5.0 공개 gate | M31까지의 설치 role 예제·제공 경로/제한·Windows package·설치·RC 마감 |
| M32-W02~W05 | power/path loss·subrate/SCA/timing, multi-set/identity/filter/EAD/coding, LLPM/QoS/event/time sync·확장 역할 budget |
| M32-W06~W10 | Mesh node/provisioner·model·Mesh 1.1·BLOB/DFU, 802.15.4/ESB 단독 peer와 승인된 공존 |
| M33-W02~W04 | OTS/OTC·ANS·CTS·HTS·CSC/RSCS·CGMS·BMS, iBeacon/Eddystone/BTHome, Fast Pair·ANCS/AMS, HCI/DTM profile/template |
| M33-W05~W08 — 후속 제품선 | 추가 role 예제·ARF-04A·후속 기능 회귀·설치·지원표 마감 |

- [ ] 예제명·폴더·주 `.ino` 이름, upstream path/test ID·license·작성 역할과 제공 route를 원장에 고정한다.
- [ ] 입문용 최소 예제 → 상대 역할 예제 → 오류/종료/복구 예제를 연결한다. 한 sketch의 role 선택 방식도 허용한다.
- [ ] 목표·보드 수·profile/FQBN·설정·실행 순서·예상 Serial 출력·실험적 제한을 예제 README에 적는다.
- [ ] 공개 wrapper 예제는 검증된 feature/profile으로 설정하고, 고급 direct/template의 sidecar는 명시적으로
  opt-in한다. v0.4.1의 기존 30개 sidecar-free 계약과 새 고급 template 계약을 혼합하지 않는다.
- [ ] `setup()/loop()` 사용·buffer 수명·timeout·error 처리·STOP/해제와 한국어 Doxygen/Allman/4칸 스타일을 검증한다.
- [ ] 자동 실행 경로는 버튼 입력을 Serial 명령/역할 설정으로 재현한다. GPIO 전기 동작이 본질인 예제는
  실제 연결 route·설정·사용법을 구현하고 실물 검증을 사용자 후속으로 남긴다. 단순 Serial 대체로 물리 PASS를 주장하지 않는다.
- [ ] source/native target/Arduino compile·설치 discovery·role runtime·negative·외부 peer 상태를 각각 기록한다.
- [ ] M31-W08과 v0.5.0 공개 gate에서 설치 archive의 예제 집합·설정·upstream provenance를
  이번 릴리스 원장과 대조한다. M32/M33의 추가 예제는 후속 원장과 별도 검증한다.
- [ ] NU54DK의 board-only 기능은 합성 payload/PCM과 실제 무선 결과로 검증한다. 외장 Audio는
  M31, Apple/Google 신규 기능은 후속 M33의 채택 범위에서 구현·예제·설정/연결 안내·자동 검사를
  제공한다. 실물 운용·상호운용은 각 담당 제품선의 사용자 후속 NOT RUN·비차단으로 명시한다.
- [ ] DF 원시 IQ는 배열 없는 수신 후보를 먼저 조사·build하고 적용되면 2보드 수신을 검증한다.
  실제 각도 산출·안테나 전환 예제는 별도 외장 경로로 설명한다. 단일 안테나 IQ를 각도 검증으로 쓰지 않는다.
- [ ] Ubuntu/macOS 최종 실물 설치·USB·serial·debug는 사용자 담당이므로 역할별 명령·기대 출력·
  실패 증거 수집 안내를 해당 OS를 추가할 후속 릴리스 단계로 인계한다. HOST-W04~W08은 보류다.

M31-W01에서 구현한 sample parity 원장은 전체 SDK sample/test의 누락을 검사한다. 하나의 Arduino 예제가 여러
upstream case를 포괄하면 대응 case 전부를 명시하고, 발견 개수·적용 개수·build/runtime PASS 개수를
별도 집계한다. 예제 수를 늘리기 위한 내용 중복이나 빈 role template는 완료 산출물로 세지 않는다.

### 기존 구현 링크

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
