# NU54DK Board/System API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-M15-BOARD-SYSTEM-001 |
| 문서 개정 | 1.3 |
| 문서 상태 | **M15 완료** — 자동 HIL 2/2와 SWD 격리 System OFF 결합 HIL PASS |
| 적용 제품 버전 | `v0.2.0` |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 범위

M15는 NU54DK에 종속된 board identity, reset, watchdog, GRTC, 내부 settings 저장소,
System OFF와 BQ25186 전원 관리 기능을 `NUCODE_NU54DK` Arduino library 안에 캡슐화한다.
일반 사용자는 `prj.conf`나 Devicetree overlay를 직접 편집하지 않고 `<NUCODE_NU54DK.h>`와
전역 객체 `NU54DK`를 사용한다.

이 library는 Arduino portable API가 아니다. 물리 장치와 pin의 단일 원본은 계속
`board_package/NU54DK_Zephyr_DTS`이며, Core 저장소는 보드 DTS를 복제하거나 수정하지 않는다.

## 2. 구성과 소유권

```text
Sketch
  ↓ <NUCODE_NU54DK.h>, NU54DK 전역 객체
NUCODE_NU54DK BoardSystem facade
  ├─ Zephyr hwinfo / watchdog / settings / poweroff
  ├─ NCS v3.4.0 고정 GRTC adapter
  └─ Arduino Wire를 통한 제한된 BQ25186 adapter
       ↓
NU54DK DTS와 standard profile
```

`libraries/NUCODE_NU54DK/zephyr/feature.yml`은 library가 선택되면 다음 입력을 자동 병합한다.

- `board-system.conf`: HWINFO, watchdog, poweroff, PM device, flash, ZMS와 settings
- `board-system.overlay`: DTS alias `watchdog0`가 가리키는 `wdt31` 활성화
- `wire` feature 의존성: BQ25186 접근에 기존 Arduino `Wire` backend 사용

BQ25186 Devicetree child node는 계속 `status = "disabled"`다. Zephyr charger driver를
자동 활성화하거나 초기화 시점의 register write를 유발하지 않는다.

## 3. 공개 진입점과 오류 계약

공개 객체는 다음 하나다.

```cpp
#include <NUCODE_NU54DK.h>

NU54DK.boardModel();
```

모든 실패 가능한 호출은 `nucode::nu54dk::Error`를 반환한다. `lastError()`는 마지막 안정
오류 분류를, `lastDriverError()`는 원래 Zephyr 또는 I2C 오류 번호를 보존한다. ISR에서
mutex, I2C, settings 또는 전원 상태를 변경하는 API를 호출하면 `invalid_context`로 거부한다.
하드웨어나 driver가 지원하지 않는 동작을 software fallback 성공으로 바꾸지 않는다.

## 4. Board identity, reset과 uptime

| API | 의미 |
| --- | --- |
| `boardModel()` | NU54DK board package와 일치하도록 Core가 고정한 모델 문자열 |
| `boardTarget()` | build에 사용한 Zephyr board target |
| `socName()` | build의 SoC 이름 |
| `ncsVersion()` / `zephyrVersion()` / `coreVersion()` | 고정 compatibility identity |
| `deviceId()` | `hwinfo_get_device_id()`의 raw 값을 16진 문자열로 복사 |
| `resetReport()` | reset cause와 하드웨어 지원 mask를 함께 반환 |
| `clearResetCause()` | 누적 reset cause latch 제거 |
| `uptimeMilliseconds()` | 현재 boot 이후 64-bit uptime |

`deviceId()`는 제조사가 UUID 유일성을 보장하는 사용자 계정 식별자가 아니다. Reset cause는
지원 mask 밖의 bit를 지원 기능처럼 해석하지 않는다.

## 5. Watchdog

`watchdogBegin(timeout_ms)`, `watchdogFeed()`와 `watchdogStop()`은 DTS `watchdog0` alias의
실제 Zephyr watchdog driver를 사용한다. 같은 객체가 시작한 channel만 feed하며 중복 시작,
시작 전 feed와 잘못된 timeout을 명시적으로 거부한다. `watchdogStop()`은 하드웨어와 driver가
중지를 지원할 때만 성공하며, 실패를 성공으로 가장하지 않는다.

Watchdog reset 자체를 의도적으로 발생시키는 예제는 기본 예제에 포함하지 않는다.
`WatchdogBasic`은 5초 timeout을 시작하고 1초마다 feed하는 정상 경로만 보여 준다.

## 6. GRTC counter와 alarm

`hardwareCounterTicks()`와 `hardwareCounterFrequency()`는 software timer가 아닌 GRTC
hardware counter의 절대 tick과 주파수를 반환한다. `alarmAfterMicroseconds()`는 최대 24시간의
one-shot alarm 하나를 예약하며 `cancelAlarm()`으로 취소한다.

GRTC 만료 ISR은 사용자 callback을 직접 실행하지 않는다. ISR은 `k_work`만 제출하고 callback은
Zephyr system work queue 문맥에서 실행된다. callback에서는 긴 blocking 작업을 피해야 한다.
callback과 Sketch `loop()` 사이에 값을 공유한다면 `volatile`만 사용해서는 안 되며 mutex,
atomic 또는 message queue처럼 C++ 동시성을 보장하는 수단이 필요하다.

이 backend는 NCS v3.4.0의 `z_nrf_grtc_*` API에 격리되어 있다. NCS/Zephyr를 변경하면 공개
Arduino API가 같더라도 adapter를 다시 검토하고 target 검증을 수행한다.

## 7. Settings/ZMS 저장소

`storageBegin()`, `storagePut()`, `storageGet()`과 `storageRemove()`는 보드의 기존
`storage_partition`을 Settings/ZMS backend로 사용한다.

| 항목 | 제한 |
| --- | --- |
| namespace | `nucode/` 고정 |
| key | 1~48자, 영문·숫자·`_`·`-`·`.`만 허용 |
| value | 1~256 byte |
| 손상 처리 | 자동 erase를 강제하는 `SETTINGS_ZMS_FORCE_MOUNT` 사용 안 함 |

이 API는 EEPROM byte 주소 호환층이나 일반 filesystem이 아니다. Flash wear, 전원 차단 시점과
제품별 데이터 migration은 Sketch가 별도로 설계해야 한다.

## 8. System OFF와 wake

`enterSystemOffOnButton()`은 DTS의 active-low `sw0..3` 중 하나를 level-active wake source로
설정한 뒤 즉시 System OFF로 진입한다. `enterSystemOffAfter()`는 GRTC 상대 wake를 설정한 뒤
즉시 System OFF로 진입한다. 성공하면 두 API 모두 반환하지 않으며 준비 오류가 있을 때만
`Error`를 반환한다.

Wake 준비와 System OFF 진입을 별도 공개 호출로 나누지 않는다. 특히 NCS GRTC wake 준비 뒤에는
지연 없이 System OFF로 들어가야 하므로, Sketch가 두 단계 사이에서 임의 작업을 실행하거나
준비된 channel을 유실할 수 없도록 하나의 원자적인 공개 동작으로 묶었다.

`SystemOffWake` 예제는 부팅 직후 자동으로 전원을 끄지 않는다. Serial Monitor에서 `BUTTON`
또는 `TIMER` 명령을 받은 뒤에만 wake source를 준비하고 System OFF에 진입한다.

M15 자동 HIL image와 runner는 System OFF에 진입하지 않는다. 자동 범위는 board identity와
uptime, GRTC one-shot callback, Settings reset persistence, WDT 정상 동작과 reset 경계다.
GRTC alarm callback의 성공을 timed System OFF wake 성공으로 확대하지 않는다.

Core `6898f7917348fab3c5cf54eec0756523e2c27d69`의 동일한 공식 CI HEX로 두 NU54DK에서 이
비-System-OFF scope를 2/2 통과했다. `timed_system_off_wake`와
`button_system_off_wake`는 두 실행 모두 수행하지 않았다.

System OFF는 공식 CI image를 사용하는 후속 수동 결합 HIL에서 검증한다. Image를 기록하고
UART를 준비한 뒤 온보드 debug-control 2연 `SW1`의 `DISABLE_SWD` 쪽만 격리 위치로 전환한다.
`DISABLE_UART` 쪽은 전환하지 않아 UART 연결을 유지한다. 이 debug-control `SW1`은 Arduino
사용자 버튼 `SW1`/P1.09와 다른 물리 부품이다.

결합 HIL은 GRTC timed wake와 `RESET_CLOCK`을 먼저 확인하고, 이어서 다시 System OFF에 진입해
사용자 SW0/P1.13 wake와 `LOW_POWER_WAKE`를 확인한다. Active SWD가 만든 reset cause `32`
(`RESET_DEBUG`)는 fixture contamination 진단이며 두 wake source의 PASS로 인정하지 않는다.
Core `c47239d954c45fd173d8d1393e3ea5c9c86e111a`의 공식 CI image로 한 SWD-only 격리
세션에서 timed wake `2062 ms`/cause `2048`과 SW0 wake `20406 ms`/cause `128`을 순서대로
통과했다. 따라서 2026-08-30 기준 M15 완료 조건을 충족했다.

## 9. BQ25186 PMIC 안전 경계

### 9.1 기본 동작

`pmicBegin()`은 `MASK_ID(0x0C)`를 읽어 Device ID 하위 nibble이 `0x1`인지 확인한다.
register를 쓰지 않으며 시작할 때마다 write 승인을 해제한다. 첫 I2C transaction은 BQ25186의
register watchdog을 시작할 수 있으므로 읽기 전용 사용도 이 효과를 인지해야 한다.

읽기 API는 status, 충전 enable 설정, 충전 전압·전류, SYS regulation과 PMIC register
watchdog mode를 제공한다. `charging_enabled`는 `CHG_DIS` register 설정을 나타내며 실제 배터리가
현재 충전 중이거나 안전하게 충전 가능한지를 보증하지 않는다. `complete_or_disabled` 상태는
datasheet의 단일 raw 상태가 charge done과 host disable을 함께 나타내므로
`charging_enabled`와 같이 해석해야 한다. 정의 범위 밖 VBAT code는 datasheet의 실제 regulation
상한인 4650 mV로 제한해 보고한다.

### 9.2 명시적 쓰기 승인

모든 PMIC 변경 API는 같은 boot의 RAM에만 유지되는 다음 승인을 먼저 요구한다.

```cpp
NU54DK.pmicAuthorizeWrites(
    nucode::nu54dk::PmicWriteAuthorization::
        acknowledge_unverified_battery_hardware);
```

reset 후 승인은 자동 복원되지 않는다. `pmicRevokeWrites()`로 즉시 해제할 수 있다. 공개 raw
register read/write API는 제공하지 않으며, 허용된 field만 read-modify-write하여 reserved bit를
보존한다. 승인 확인, watchdog 정책 확인과 read-modify-write는 같은 mutex 임계구역에서
수행하므로 승인 해제와 register write가 경쟁하지 않는다.

첫 I2C 접근 뒤 BQ25186 register watchdog이 동작할 수 있으므로, 영속적인 충전·SYS 설정에는
다음 순서를 강제한다.

```cpp
NU54DK.pmicBegin();
NU54DK.pmicAuthorizeWrites(
    nucode::nu54dk::PmicWriteAuthorization::
        acknowledge_unverified_battery_hardware);
NU54DK.pmicSetRegisterWatchdog(
    nucode::nu54dk::PmicRegisterWatchdog::disabled);
// 필요한 충전·SYS 설정
NU54DK.pmicRevokeWrites();
```

`pmicBegin()` 또는 재승인을 호출하면 watchdog 정책 확인 상태도 해제된다. 따라서 각 승인에서
`pmicSetRegisterWatchdog()`를 먼저 호출하지 않으면 충전·SYS 설정은
`configuration_required`로 거부된다. `seconds_160_restore_register_defaults`는 160초 뒤 모든
R/W register를 기본값으로 복원하고, 다른 두 timed 값은 각각 160초 또는 40초 hardware reset을
요청한다. 주기적인 I2C 서비스 없이 설정을 유지하려면 `disabled`를 명시해야 한다.

| 변경 API | 허용 범위 |
| --- | --- |
| 충전 전압 | 3500~4650 mV, 10 mV 단위 |
| 충전 전류 | 5~35 mA는 1 mA 단위, 40~1000 mA는 10 mA 단위 |
| 충전 enable | enable / disable |
| 재충전 문턱 | 100 mV / 200 mV |
| SYS regulation | BQ25186 `SYS_REG[7:5]` 열거값 |
| PMIC register watchdog | 160초 뒤 register 기본값 복원, 160초 hardware reset, 40초 hardware reset, disabled |
| 전원 상태 요청 | shutdown / ship mode 진입 요청 |

### 9.3 검증하지 않은 전기 동작

현재 시험 장비에는 배터리가 연결되지 않았다. 따라서 다음 항목은 **battery electrical HIL
NOT RUN**이며 사용자가 자신의 배터리, 전원, 온도 조건과 제품 안전 요구사항에 맞춰 직접
검증해야 한다.

- 실제 충전 전압과 충전 전류
- 충전 완료와 재충전 전환
- `SYS_REG` 변경 후 rail 전압
- 입력 전원 제거 뒤 shutdown과 ship mode의 실제 전원 상태·복구 경로
- 장시간 동작과 발열·배터리 안전

`pmicRequestShutdown()`과 `pmicRequestShipMode()`는 BQ25186의 해당 전원 상태를 요청한다.
USB/VIN 입력 전원이 있으면 입력 제거 시 진입하고, 입력이 이미 없으면 register write 직후
즉시 진입해 함수의 성공 경로가 반환되지 않을 수 있다. 실제 진입·복구 조건은 입력 전원과
hardware 구성을 함께 검증해야 한다. 요청 bit가 register watchdog에 의해 기본값으로 복원되는
것을 막기 위해 두 API도 현재 승인에서 watchdog 정책을 먼저 명시해야 한다.

NU54DK 회로에는 이 API가 사용할 실제 배터리 NTC 입력이 없으므로
`hasBatteryTemperatureProtection()`은 항상 `false`다. 실제 배터리 온도 보호는 미지원이다.
PMIC write API의 존재나 software semantic test를 전기적 안전성 PASS로 해석하면 안 된다.

## 10. 예제와 검증 계층

| 경로 | 목적 | 현재 상태 |
| --- | --- | --- |
| `BoardInfo` | identity, device ID와 reset report | 구현됨, 비-System-OFF 자동 HIL 2/2 PASS |
| `WatchdogBasic` | watchdog begin/feed 정상 경로 | 구현됨, stop·expiry reset 자동 HIL 2/2 PASS |
| `CounterAlarm` | GRTC counter와 work-queue callback | 구현됨, callback 자동 HIL 2/2 PASS; timed System OFF wake PASS |
| `SettingsStorage` | 내부 partition boot count | 구현됨, reset persistence 자동 HIL 2/2 PASS |
| `SystemOffWake` | 명시적 BUTTON/TIMER 명령 | 구현됨, timed GRTC→사용자 SW0 System OFF 결합 HIL PASS |
| `tests/host/test_m15_board_system_contract.py` | 공개 API·구성·PMIC 안전 경계 | Software Gates run `33295587578` SUCCESS |
| `tests/zephyr/m15_board` | production target compile/link와 안전한 read 상태 | 공식 CI build SUCCESS |
| `tests/zephyr/m15_hil` | identity·reset·GRTC callback·Settings·WDT 비-System-OFF 자동 HIL image | 공식 CI build SUCCESS, 두 보드 HIL 2/2 PASS |
| `tests/zephyr/m15_wake` | SWD 격리 timed GRTC→사용자 SW0 결합 HIL image | Reproducible Builds run `33295588535` SUCCESS, 물리 HIL PASS |
| `tests/hil/nu54dk/m15_auto.py` | nonce 기반 비-System-OFF 자동 HIL과 비파괴 복구 | 두 보드 실기 2/2 PASS |
| `tests/hil/nu54dk/m15_system_off.py` | timed GRTC와 SW0 wake 결합 protocol·증적 | Core `c47239d954c4`에서 물리 HIL PASS |

최종 실행 결과와 exact commit은
[M15 NU54DK Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)에
기록한다.

## 11. M15 완료 경계

M15를 완료하려면 다음 조건이 모두 충족되어야 한다.

- 공개 API와 오류·context negative 시험 통과
- Arduino 예제 compile/discovery와 production NU54DK target build 통과
- board identity, software/watchdog reset, uptime, watchdog stop/expiry, GRTC alarm과
  settings의 비-System-OFF 자동 HIL 결과 확보
- debug-control `SW1`에서 `DISABLE_SWD`만 격리하고 UART를 유지한 상태에서 GRTC timed
  System OFF wake와 `RESET_CLOCK`을 실제 보드에서 확인
- 같은 결합 HIL에서 사용자 SW0/P1.13 System OFF wake와 `LOW_POWER_WAKE`를 확인
- PMIC battery electrical HIL은 `NOT RUN`과 사용자 책임으로 계속 명시
- 실제 NTC 온도 보호를 미지원으로 유지

PMIC 전기 HIL은 프로젝트 소유자가 승인한 M15 범위 제외이므로 M15 완료를 차단하지 않는다.
대신 해당 API는 전기적으로 검증된 완전 지원으로 표시하지 않는다.

Core `c47239d954c45fd173d8d1393e3ea5c9c86e111a`에서 위 비-System-OFF 자동 HIL과
System OFF 결합 HIL 조건을 모두 충족했다. M15는 **완료**이며 다음 구현 단계는 M16 basic BLE다.
