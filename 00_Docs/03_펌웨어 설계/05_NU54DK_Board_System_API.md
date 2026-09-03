# NU54DK Board/System API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-M15-BOARD-SYSTEM-001 |
| 문서 개정 | 2.0 |
| 문서 상태 | `v0.3.0` 정식 계약 |
| 적용 제품 버전 | `v0.3.0` |
| 최종 갱신일 | 2026-09-03 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 범위

`v0.2.0`은 NU54DK에 종속된 board identity, reset, watchdog, GRTC, 내부 settings 저장소,
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
- feature 의존성 `gpio`, `serial`, `wire`, `adc`, `pwm`: Board/System 예제와 공개 facade가 사용하는
  표준 backend를 함께 활성화하며, BQ25186 접근은 기존 Arduino `Wire` backend를 사용

BQ25186 Devicetree child node는 계속 `status = "disabled"`다. Zephyr charger driver를
자동 활성화하거나 초기화 시점의 register write를 유발하지 않는다.

## 3. 공개 진입점과 오류 계약

공개 객체는 다음 하나다.

```cpp
#include <NUCODE_NU54DK.h>

NU54DK.boardModel();
```

모든 실패 가능한 호출은 `nucode::nu54dk::Error`를 반환한다. `lastError()`는 마지막 안정
오류 분류를 보존한다. `lastDriverError()`는 일반 Zephyr driver 오류를 보존하지만,
`pmicReadRegister()`와 `pmicWriteRegister()`의 Wire 실패는 세부 I2C 오류를 그대로 노출하지 않고
`-EIO`로 축약한다. ISR에서 mutex, I2C, settings 또는 전원 상태를 변경하는 API를 호출하면
`invalid_context`로 거부한다. 하드웨어나 driver가 지원하지 않는 동작을 software fallback
성공으로 바꾸지 않는다.

## 4. Board identity, reset과 uptime

| API | 의미 |
| --- | --- |
| `boardModel()` | NU54DK board package와 일치하도록 Core가 고정한 모델 문자열 |
| `boardTarget()` | build에 사용한 Zephyr board target |
| `socName()` | build의 SoC 이름 |
| `ncsVersion()` / `zephyrVersion()` | 고정 compatibility identity |
| `coreVersion()` | 구현은 역사적 문자열 `0.2.0-dev`를 반환하므로 배포 identity로 사용하지 않음; 설치 version과 release manifest를 기준으로 확인 |
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
제품별 데이터 migration은 Sketch가 별도로 설계해야 한다. `v0.3.0`의 AC-03은 같은
Settings/ZMS에 독립 `arduino/eeprom` record를 두는 1024-byte EEPROM facade와 별도
`0x16c000..0x174000` 32 KiB LittleFS를 구현했다. 두 facade의 API·파괴적 복구·검증 경계는
[Arduino Storage API](./10_Arduino_Storage_API.md)가 소유하며, RC 검증 결과를 stable `v0.2.0`
지원으로 소급하지 않는다.

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

자동 HIL과 System OFF 결합 HIL은 역할을 분리한다. System OFF 검증은 image 기록과 UART 준비를
마친 뒤 온보드 debug-control switch의 `DISABLE_SWD` 쪽만 격리하고 UART는 유지한다. 이 switch는
Arduino 사용자 버튼과 다른 부품이다. GRTC timed wake와 사용자 버튼 wake는 모두 검증 완료했다.

Exact image, reset cause, 시간, transcript와 commit은
[M15 NU54DK Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)만
소유한다. GRTC alarm callback 성공을 System OFF wake 성공으로 확대하지 않는다.

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

## 10. 예제와 검증

| 경로 | 목적 |
| --- | --- |
| `BoardInfo` | identity, device ID와 reset report |
| `WatchdogBasic` | watchdog begin/feed 정상 경로 |
| `CounterAlarm` | GRTC counter와 work-queue callback |
| `SettingsStorage` | 내부 partition boot count |
| `SystemOffWake` | 명시적 BUTTON/TIMER System OFF 진입 |
| `tests/host/test_m15_board_system_contract.py` | 공개 API·구성·PMIC 안전 경계 |
| `tests/zephyr/m15_board`, `tests/zephyr/m15_hil`, `tests/zephyr/m15_wake` | production build, 일반 HIL과 System OFF image |
| `tests/hil/nu54dk/m15_auto.py`, `tests/hil/nu54dk/m15_system_off.py` | 실제 보드 protocol과 evidence 생성 |

최종 실행 결과와 exact commit은
[M15 NU54DK Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)에
기록한다.

## 11. 현재 완료 경계

`v0.2.0`은 다음 범위를 완료했다.

- 공개 API와 오류·context negative 시험 통과
- Arduino 예제 compile/discovery와 production NU54DK target build 통과
- board identity, software/watchdog reset, uptime, watchdog stop/expiry, GRTC alarm과
  settings의 비-System-OFF 자동 HIL 결과 확보
- debug-control `SW1`에서 `DISABLE_SWD`만 격리하고 UART를 유지한 상태에서 GRTC timed
  System OFF wake와 `RESET_CLOCK`을 실제 보드에서 확인
- 같은 결합 HIL에서 사용자 SW0/P1.13 System OFF wake와 `LOW_POWER_WAKE`를 확인
- PMIC battery electrical HIL은 `NOT RUN`과 사용자 책임으로 계속 명시
- 실제 NTC 온도 보호를 미지원으로 유지

PMIC 전기 HIL은 승인된 범위 제외이며 해당 API를 전기적으로 검증된 완전 지원으로 표시하지
않는다. `v0.3.0`의 AC-01 자동 검증과 M19·M20·M21 구현·검증은 완료됐으며 Board/System 계약은
이 BLE 단계들의 변경 대상이 아니다. 완료된 AC-03 storage facade는 `nucode/` namespace,
BLE bond와 고정 partition 소유권을 깨지 않는 회귀 증거를 제공한다. 현재 개발 상태와
검증 링크는 [v0.3.0 마일스톤](<../01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)에서
관리한다.
