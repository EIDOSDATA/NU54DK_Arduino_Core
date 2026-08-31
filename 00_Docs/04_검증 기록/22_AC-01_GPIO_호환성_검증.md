# AC-01 connector GPIO와 Arduino 호환 API 검증

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VER-AC01-GPIO-001 |
| 문서 개정 | 0.2 |
| 상태 | 구현·host·production target build 완료, 물리 loopback 재확인 뒤 exact-commit HIL 대기 |
| 최종 갱신일 | 2026-08-31 |
| 대상 | `v0.3.0` AC-01 |
| 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 1. 목적과 판정 경계

AC-01은 기존 LED/button 역할을 임의의 범용 GPIO로 바꾸지 않고, Arduino profile이 명시적으로
소유하는 connector GPIO 두 개에 호환 API를 추가한다. 이 기록은 source 구현, 장치 없는 계약,
production target build와 P2.5↔P2.6 GPIO HIL, SW0 실제 GPIOTE HIL의 경계를 분리한다.

이 문서의 현재 판정은 다음과 같다.

| 계층 | 현재 결과 |
| --- | --- |
| source/host 계약 | PASS, 9 tests |
| NU54DK production contract build | PASS |
| NU54DK AC-01 HIL image build | PASS |
| SW0 P1.13 level IRQ·callback mask 실기 | PASS — open-drain 자기구동, 수동 버튼 조작 없음 |
| P2.5↔P2.6 exact-commit 실기 | BLOCKED — 연결된 선이 두 UID 모두에서 LOW로 관찰되지 않아 fixture 재확인 필요 |
| 정식 `v0.3.0` 지원 선언 | 아직 아님 |

Dirty working tree에서 만든 image의 flash 성공을 최종 증적으로 사용하지 않는다. Runner가 요구하는
Core·application·board source digest와 exact commit을 만족하려면 먼저 전체 변경을 commit하고 같은
source에서 pristine build해야 한다.

## 2. connector 역할과 ownership

`dts/nucode/nu54dk-arduino-connectors.dtsi`는 다음 두 역할만 Arduino profile에 추가한다.

| Arduino 역할 | 논리 ID | DTS alias | nRF54L15 GPIO | ownership | capability |
| --- | ---: | --- | --- | --- | --- |
| `PIN_GPIO0`, `D10` | 10 | `nucode-gpio0` | P2.5 | `connector_gpio` | input, output, open-drain |
| `PIN_GPIO1`, `D11` | 11 | `nucode-gpio1` | P2.6 | `connector_gpio` | input, output, open-drain |

`standard`와 `ble` profile이 같은 DTSI를 한 번씩 include한다. Alias 두 개가 모두 있을 때
`NUM_DIGITAL_PINS=12`, `NUM_DIGITAL_CAPABLE_PINS=9`가 된다. Profile DTS가 없는 legacy/expert
target에서는 기존 10/7 범위를 유지한다. Variant C++은 물리 번호를 복제하지 않고 생성된 alias의
`gpio_dt_spec`만 소비한다.

Board package gitlink는 수정하지 않는다. Connector 역할은 Arduino profile에만 필요한 정책이므로
Core module DTS와 binding이 소유한다. Board pinctrl과의 host 검사는 P2.5/P2.6이 현재 활성
peripheral 신호와 충돌하지 않는지 확인한다.

nRF54L15 CPUAPP에서 GPIOTE20은 P1, GPIOTE30은 P0만 처리하며 P2에는 GPIOTE instance가 없다.
따라서 P2.5/P2.6에는 `interrupt` capability를 노출하지 않고
`digitalPinToInterrupt(PIN_GPIO0/PIN_GPIO1)`은 `NOT_AN_INTERRUPT`를 반환한다. P2 interrupt를
software polling으로 가장하지 않는다.

## 3. 구현 계약

### 3.1 Digital과 open-drain

- `OUTPUT_OPENDRAIN`은 `open_drain` capability가 있는 connector 역할에만 적용한다.
- `LOW`는 line을 low로 구동하고 `HIGH`는 high-Z로 release한다.
- Output latch를 mode 전환 때 보존한다.
- Board LED처럼 open-drain capability가 없는 역할은 `unsupported`로 거부한다.

### 3.2 level interrupt

- `LOW`와 `HIGH`는 raw electrical level이다.
- 최초 assert에서 callback을 한 번 전달한 뒤 hardware interrupt를 disable한다.
- Delayable work가 1 ms 간격으로 deassert를 확인하고 latch와 trigger를 재무장한다.
- Level을 계속 hold하는 동안 callback storm을 만들지 않는다.
- `detachInterrupt()`와 pin mode 변경은 진행 중 callback과 재무장 work를 정리한다.
- 이 계약은 GPIOTE가 있는 P0/P1 역할에 적용한다. AC-01 실기는 SW0 P1.13을 input-connected
  open-drain으로 구성해 실제 pad→GPIOTE20 event를 자동 생성한다.
- 자기구동 HIGH는 능동 출력이 아니라 high-Z release이고 LOW만 sink한다. 시험 중 SW0를 사람이
  누르지 않으며, 완료·실패 경로 모두 release→detach→input-only 순서로 복원한다.

### 3.3 `noInterrupts()`와 `interrupts()`

실제 Zephyr 전역 IRQ를 끄지 않는다. Arduino Core가 등록한 GPIO callback 전달과 해당 hardware
trigger만 일시 중지한다. 따라서 kernel tick, UART, BLE와 다른 driver interrupt는 계속 동작한다.

- 첫 호출 thread가 mask ownership을 갖는다.
- 같은 thread의 중첩 호출만 허용한다.
- 마지막 복원 전까지 callback을 전달하지 않는다.
- Mask 중 assert된 level은 마지막 복원 뒤 raw 상태를 확인하고 disable/configure로 재무장한다.
- 다른 thread의 복원, 짝이 없는 복원과 nesting overflow는 진단 오류로 거부한다.

### 3.4 pulse와 shift

- `pulseIn()`과 `pulseInLong()`은 input mode와 raw LOW/HIGH만 허용한다.
- 64-bit hardware cycle을 deadline으로 사용하며 timeout은 `0`을 반환한다.
- `pulseInLong()`은 polling 64회마다 같은 우선순위 thread에 `k_yield()`한다.
- `shiftIn()`/`shiftOut()`은 data와 clock의 mode, 서로 다른 핀과 두 bit order를 검사한다.
- API는 thread 문맥 전용이며 protocol bus, 주파수 또는 외부 계측 정확도를 보증하지 않는다.

## 4. 자동 검증

### 4.1 Host와 negative tests

```powershell
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
& $Python -I tests\host\test_ac01_contract.py
& $Python -I tests\hil\nu54dk\test_ac01_gpio_hil.py
```

| 시험 | 결과 | 주요 경계 |
| --- | ---: | --- |
| `test_ac01_contract.py` | 4/4 PASS | P2.5/P2.6 단일 mapping, pinctrl 충돌 없음, 두 profile, 안전한 IRQ backend |
| `test_ac01_gpio_hil.py` | 5/5 PASS | exact 8-line protocol, 순서·중복·누락 거부, pulse 범위, heartbeat, UID/fixture 명시 |

Target ztest `tests/zephyr/ac01_contract`는 다음 negative 의미도 build한다.

- output mode 핀에서 `pulseIn()` → `wrong_mode`
- 잘못된 pulse state → `invalid_value`
- 같은 data/clock의 `shiftOut()` → `ownership_conflict`
- 짝이 없는 `interrupts()` → `interrupt_restore_without_disable`
- Board LED의 `OUTPUT_OPENDRAIN` → `unsupported_capability`

### 4.2 Production target build

`tests/zephyr/ac01_contract`와 `tests/zephyr/ac01_hil`을 Core module과 clean board package를 사용해
`nrf54l15dk/nrf54l15/cpuapp/nu54dk`로 build했다. 두 image 모두 link와 HEX 생성을 완료했다.
빌드 중 보인 `NRF_PLATFORM_LUMOS` deprecated warning은 NCS 3.4.0의 기존 target 경고이며 AC-01
source 오류가 아니다.

두 scenario `nucode.ac01.contract`, `nucode.ac01.gpio_hil`은
`tools/ci/run_zephyr_build.py`의 고정 build-only suite에도 포함했다. CI contract test는 둘 중
하나가 빠지면 실패한다.

최종 commit 뒤에는 다음 명령으로 pristine build를 다시 수행한다.

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$env:Path = "C:\ncs\toolchains\dcbdc366a1\opt\bin;$env:Path"
$Build = "$env:TEMP\nu54dk-ac01-gpio-hil"

Push-Location $NcsRoot
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $Build `
  "$CoreRoot\tests\zephyr\ac01_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DZEPHYR_EXTRA_MODULES=$CoreRoot"
Pop-Location
```

## 5. 실기 fixture와 자동 runner

한 대의 NU54DK에서 P2.5와 P2.6을 점퍼 한 가닥으로 연결한다. 두 번째 보드, 외부 pull-up,
logic analyzer와 오실로스코프는 필요 없다. Open-drain release에는 P2.6 내부 pull-up을 사용한다.
Level IRQ와 callback mask는 별도 배선 없이 같은 보드의 SW0 P1.13 자기구동으로 검증한다.

`tests/zephyr/ac01_hil`은 다음 exact token을 순서대로 출력한다.

1. fixture identity
2. open-drain LOW/release
3. SW0 P1.13 LOW level 최초·hold·rearm
4. SW0 P1.13 HIGH level 최초·hold·rearm
5. short/long pulse와 timeout
6. shift output/input
7. SW0 P1.13 nested callback mask, scheduler heartbeat와 held-level restore
8. 최종 PASS

`tests/hil/nu54dk/ac01_gpio_hil.py`는 두 보드 오선택을 막기 위해 `--board-id`를 필수로 받는다.
Core와 board revision, source digest, NCS/Zephyr revision, target, image와 transcript SHA-256을
evidence JSON으로 결합한다. Mass erase와 recover는 요청하지 않는다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\ac01_gpio_hil.py" `
  --hex "$Build\ac01_hil\zephyr\zephyr.hex" `
  --board-id "<시험할 CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --acknowledge-loopback `
  --evidence "$CoreRoot\build\ac01\hil\ac01-gpio.evidence.json"
```

### 5.1 pre-commit fixture 진단

2026-08-31 dirty preflight image로 두 CMSIS-DAP UID를 각각 시험했다. 두 보드 모두 부팅과 READY
token은 정상이나 `OPEN_DRAIN_LOW_READ`에서 P2.6이 HIGH로 남았다. 어느 보드에서도 한 보드 내부
loopback 또는 두 보드 교차 방향의 LOW 전달이 관찰되지 않았다. 이 결과는 exact-commit PASS
증거가 아니며, 현재 점퍼가 실제 동일 보드 P2.5↔P2.6에 꽂혀 있는지 확인해야 한다는 진단이다.

SW0 자기구동 전용 preflight에서는 다음 항목이 실제 보드에서 통과했다.

- LOW: first=1, held=1, rearmed=2
- HIGH: first=1, held=1, rearmed=2
- nested mask: masked=0, nested=0, restored=1, heartbeat_delta=10

이 과정에서 마지막 `interrupts()`가 assert된 level을 복원할 때 masked ISR storm이 생기는 문제를
발견했다. Mask된 level ISR이 hardware trigger를 즉시 disable하고 최종 복원에서 one-shot으로
재무장하도록 Core를 수정한 뒤 위 실기 결과를 얻었다.

## 6. 남은 완료 조건

1. 전체 AC-01과 병렬 작업을 한 commit에 포함한다.
2. 해당 exact commit에서 AC-01 HIL image를 pristine rebuild한다.
3. 한 보드 내부의 P2.5↔P2.6 점퍼 위치를 재확인한 뒤 runner를 실행한다.
4. 최종 PASS transcript/evidence의 revision, UID, SHA-256과 측정값을 이 기록에 추가한다.
5. 그 뒤 roadmap/API 상태를 AC-01 완료로 승격한다.

현재 source·host·target build 결과를 실기 PASS로 확대하지 않는다.
