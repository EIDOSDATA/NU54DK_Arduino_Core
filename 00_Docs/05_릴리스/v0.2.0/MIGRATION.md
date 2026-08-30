# NU54DK Arduino Core v0.2.0 마이그레이션

> **배포 상태: v0.2.0 정식 릴리스.** stable index에서 `0.2.0`을 설치한다. RC1·RC2 전용
> index는 검증 이력이며 신규 설치에 사용하지 않는다.

| 항목 | 값 |
| --- | --- |
| 대상 | `v0.1.0`, `v0.2.0-rc.1`, `v0.2.0-rc.2` 또는 v0.2 source build 사용자 |
| 도착 version | `0.2.0` |
| Board/FQBN | `NU54DK (nRF54L15, Zephyr)` / `nucode:zephyr:nu54dk` |
| 공식 OS | Windows 10/11 x64 |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain | `dcbdc366a1` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

## 1. Stable index로 전환

Arduino IDE의 **Additional Boards Manager URLs**에 다음 주소를 한 줄로 등록한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

RC 전용 URL을 등록했던 사용자는 stable URL을 추가한 뒤 `v0.2.0-rc.1` 또는
`v0.2.0-rc.2` URL을 제거한다. 기존 stable URL을 쓰던 `v0.1.0` 사용자는 URL을 바꿀 필요가
없다. RC tag와 자산은 삭제하지 않지만 신규 설치 경로로 권장하지 않는다.

## 2. `0.2.0` 설치와 기본 확인

1. Arduino IDE, Serial Monitor, debugger와 실행 중인 pyOCD/J-Link process를 닫는다.
2. Additional Boards Manager URLs에 stable index를 등록하고 index를 갱신한다.
3. `NUCODE NU54DK Zephyr Boards`의 `0.2.0`을 명시적으로 선택해 설치한다.
4. IDE를 재시작하고 `NU54DK (nRF54L15, Zephyr)`를 선택한다.
5. Tools의 Feature set을 `Standard peripherals`로 두고 Blink를 clean compile·upload한다.
6. BLE를 시험할 때만 Feature set을 `BLE NUS`로 바꾸고 NUS 예제를 clean compile한다.

Arduino CLI에서는 다음과 같이 설치한다.

```powershell
$StableIndex = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json'
arduino-cli config add board_manager.additional_urls $StableIndex
arduino-cli core update-index
arduino-cli core install nucode:zephyr@0.2.0 --run-post-install
arduino-cli board details --fqbn nucode:zephyr:nu54dk
```

이전 버전의 build output은 재사용하지 않고 첫 compile은 새 build directory에서 수행한다.
여러 CMSIS-DAP가 연결된 Arduino CLI upload는 다음처럼 대상 UID를 전달한다.

```powershell
arduino-cli upload --fqbn nucode:zephyr:nu54dk `
  --build-path <build-path> `
  --board-options upload_probe=pyocd_uid `
  --upload-field probe_id=<CMSIS-DAP-UID> `
  <sketch-path>
```

같은 `build-path`를 만든 compile에도 `--board-options upload_probe=pyocd_uid`를 사용해야 한다.

`v0.1.0`, RC2와 `v0.2.0`은 NCS v3.4.0과 Toolchain bundle `dcbdc366a1`을 사용한다. 사용자 영역의 exact
설치와 완료 marker가 유효하면 installer가 대용량 prerequisite를 재사용할 수 있으므로 먼저
NCS/Toolchain directory를 삭제하지 않는다.

## 3. 기존 Sketch 이동

기본 GPIO, 시간, Serial, interrupt, Wire, SPI, ADC와 PWM Sketch는 `Standard peripherals`에서
먼저 build한다. v0.2는 다음 공개 library를 추가한다.

- `<NUCODE_NU54DK.h>`: board identity/reset, watchdog, GRTC, Settings storage, System OFF와
  승인 기반 BQ25186 API
- `<NUCODE_BLE.h>`: `BLESerial` NUS Peripheral/Central Stream

Feature set은 사용자가 `prj.conf`나 overlay를 편집하지 않도록 검증된 설정을 선택한다.
기존 Sketch directory에 v0.1 build output, CMake cache 또는 수동 복사한 DTS를 가져오지 않는다.
Boards Manager archive에 exact NU54DK board package가 포함되므로 별도 Git submodule을 설치하거나
package board file을 덮어쓰지 않는다.

`BLESerial`을 사용하는 Sketch는 `BLE NUS`를 선택해야 한다. 하나의 image에서 Peripheral과
Central을 동시에 시작하지 않는다. 범용 GATT나 보안 API를 기대하는 기존 BLE library는
v0.2.0의 NUS wrapper로 자동 변환되지 않는다.

## 4. 사용자 예제와 내부 fixture 구분

v0.2.0의 Arduino IDE 사용자 예제는 14개다.

- NUCODE NU54DK 10개: `Blink`, `SerialEcho`, `InterruptButton`, `AnalogReadA0`, `PWMFade`,
  `BoardInfo`, `WatchdogBasic`, `CounterAlarm`, `SettingsStorage`, `SystemOffWake`
- Wire/SPI 2개: `WirePmicId`, `SPITransaction`
- NUCODE BLE 2개: `NUSPeripheral`, `NUSCentral`

M17의 Adafruit LSM6DS3TR-C compatibility Sketch, Zephyr sensor direct, NCS Crypto RNG,
802.15.4, OpenThread와 Matter build fixture는 package 사용자 예제가 아니다. 이를 사용하려면
upstream source와 개별 Zephyr/NCS 구성을 이해해야 하며, Core가 runtime 지원을 보증하지 않는다.

## 5. `v0.1.0`으로 downgrade

v0.2.0에서 문제가 발생하면 같은 stable index의 `0.1.0`으로 돌아갈 수 있다.

1. Arduino IDE, Serial Monitor와 모든 probe process를 닫는다.
2. stable index가 Additional Boards Manager URLs에 등록돼 있는지 확인한다.
3. Boards Manager에서 `0.1.0`을 명시적으로 설치한다.
4. 과거 RC 전용 URL이 남아 있고 더 이상 필요 없으면 Additional Boards Manager URLs에서 제거한다.
5. IDE를 재시작하고 build output을 새로 만든 뒤 Blink를 compile/upload한다.

`v0.1.0`에는 M15 Board/System과 M16 BLE NUS API가 없으므로 `<NUCODE_NU54DK.h>`,
`<NUCODE_BLE.h>`, `NU54DK` 또는 `BLESerial`을 사용하는 Sketch는 그대로 compile되지 않는다.
해당 호출을 제거하거나 RC와 별도 branch로 관리한다. Downgrade Upload는 일반적으로 target의
사용자 Settings 영역을 자동 지우지 않으므로 저장 데이터 형식 호환을 추정하지 않는다.

## 6. 제거

1. Arduino IDE의 Boards Manager에서 설치된 `NUCODE NU54DK Zephyr Boards` version을 제거한다.
2. RC와 stable index가 모두 필요 없으면 Additional Boards Manager URLs에서 각각 제거한다.
3. IDE를 재시작해 board가 더 이상 선택되지 않는지 확인한다.

Core 제거는 Sketch와 사용자 library를 삭제하지 않는다. 공유 NCS와 Toolchain도 의도적으로
남긴다. 다른 NU54DK Core version이 사용 중이지 않고 재다운로드 비용을 감수할 때만 사용자
영역 prerequisite를 별도로 정리한다. package directory나 NCS tree를 일부만 수동 삭제해
혼합 상태를 만들지 않는다.

## 7. Migration 후 확인

- 선택 version이 `0.2.0` 또는 의도한 `0.1.0`인지 확인한다.
- FQBN이 `nucode:zephyr:nu54dk`인지 확인한다.
- Feature set과 Upload probe를 다시 확인한다.
- 새 build directory에서 compile한다.
- CMSIS-DAP/pyOCD Upload 뒤 DAP UART 115200 8N1로 firmware 출력을 확인한다.
- PMIC와 System OFF 예제는 알려진 전기·SWD 제약을 읽은 뒤 실행한다.
