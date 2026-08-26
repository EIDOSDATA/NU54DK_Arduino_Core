# M3 GPIO, 시간과 Scheduler 기준선

| 항목 | 내용 |
| --- | --- |
| 검증 결과 | **CONDITIONAL GO** — clean revision과 GPIO·시간 로컬 HIL 통과, 잔여 계측·자동 시험 대기 |
| 검증일 | 2026-08-26 (Asia/Seoul) |
| 작성자 | Quantum / NUCODE |
| 대상 구조 | Loader/LLEXT 없는 Native Full Zephyr 정적 이미지 |
| 대상 보드 | NU54DK |
| Zephyr 보드 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Core 기준 revision | `a8d62ea75fef57cdf166738eb45ad4f61e0eaa9c` (clean) |
| 보드 package 기준 revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` (clean, 읽기 전용) |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 compiler | Arm GCC 14.3.0, C++17, exception·RTTI 비활성 |
| 기본 연결 | 온보드 CMSIS-DAP V2 + pyOCD |

> 상위 gitlink와 서브모듈 HEAD는 위 보드 revision으로 일치한다.
> `NU54DK_Zephyr_DTS`는 읽기 전용 빌드 입력으로 사용했고, M3 pristine 재검증 중
> 서브모듈 내부 파일을 수정하지 않았다.

---

## 1. 목적과 판정 범위

M3는 M2의 `setup()`/`loop()` runtime 위에 다음 첫 Arduino 수직 경로를 만든다.

1. NU54DK 보드 Devicetree의 `led0`와 `sw0` alias를 Arduino 논리 핀으로 변환한다.
2. `pinMode()`, `digitalWrite()`와 `digitalRead()`를 Zephyr GPIO backend로 실행한다.
3. `millis()`, `micros()`, `delay()`, `delayMicroseconds()`와 `yield()`를 Zephyr 시간원과
   scheduler에 연결한다.
4. 빠르게 반환하는 `loop()`가 Zephyr thread와 idle에 미치는 영향을 실측해 기본 정책을
   결정한다.
5. Core 비활성 앱과 필수 DTS alias 누락을 negative build로 검증한다.

M3는 전체 NU54DK 핀맵, interrupt, Serial, Wire, SPI, ADC, PWM, ArduinoCore-API 공통 타입,
`.ino` 전처리와 Arduino CLI를 지원 완료로 선언하지 않는다.

---

## 2. 구현 기준선

### 2.1 공개 API와 빌드 선택

`cores/arduino/Arduino.h`는 M3에서 다음 최소 공개 계약을 제공한다.

- `pin_size_t`, `PinStatus`, `PinMode`
- `pinMode()`, `digitalWrite()`, `digitalRead()`
- `millis()`, `micros()`, `delay()`, `delayMicroseconds()`, `yield()`
- `setup()`, `loop()`와 `variant.h`

공개 시간·GPIO 함수는 C linkage를 사용한다. Sketch의 `setup()`과 `loop()`는 C++ 함수다.
M3는 ArduinoCore-API source를 아직 vendor하거나 link하지 않으며, 그 revision 고정과 공통
class 도입은 M4 범위다.

| Kconfig | M3 동작 |
| --- | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | 전체 Arduino runtime opt-in |
| `CONFIG_NUCODE_ARDUINO_GPIO` | digital GPIO와 Variant source 포함, 기본 `y` |
| `CONFIG_NUCODE_ARDUINO_TIME` | 시간 API와 nRF54 backend 포함, 기본 `y` |
| `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK` | `loop()` 반환 뒤 한 tick sleep, 기본값 |
| `CONFIG_NUCODE_ARDUINO_LOOP_YIELD` | 같은 priority thread에 양보 |
| `CONFIG_NUCODE_ARDUINO_LOOP_NONE` | Core의 반환 후 scheduler 개입 없음 |

### 2.2 NU54DK Variant

Variant는 물리 GPIO 번호를 복제하지 않고 외부 보드 package의 생성된 Devicetree만
사용한다.

| Arduino 논리 핀 | 값 | Devicetree 원본 | M3 capability |
| --- | ---: | --- | --- |
| `LED_BUILTIN` | 0 | `DT_ALIAS(led0)` | digital input + output |
| `PIN_BUTTON0` | 1 | `DT_ALIAS(sw0)` | digital input |

`NUM_DIGITAL_PINS`는 2다. `variant.cpp`는 alias의 status와 `gpios` 속성을 compile time에
검사하고 `gpio_dt_spec`을 생성한다. Core source에는 P0/P1/P2 controller 또는 물리 pin
번호가 없다. 현재 보드 package의 `led0`는 P2.9이며, 그 물리 값의 단일 원본은 보드
DTS다.

### 2.3 GPIO 의미와 현재 제한

- `LOW`와 `HIGH`는 전기적 raw level이다. `GPIO_ACTIVE_LOW`를 Arduino 값 반전에 사용하지
  않고 `gpio_pin_set_raw()`와 `gpio_pin_get_raw()`를 호출한다.
- pull-up/down 선택은 `pinMode()`가 소유한다. DTS의 pull flag를 Arduino mode에 조용히
  합치지 않는다.
- `OUTPUT`은 nRF54에서 실제 output level을 다시 읽을 수 있도록 input path도 함께
  활성화한다.
- M3 GPIO API는 thread 문맥 전용이다. ISR 호출은 안전한 no-op 또는 `LOW`이며 private
  `GpioError::invalid_context`로 기록한다.
- 범위 밖 pin, 잘못된 mode/value, 미준비 device와 driver errno는 private atomic 상태에
  보존한다. 공개 진단 API와 자동 log는 아직 없다.
- `digitalWrite()`는 `pinMode(..., OUTPUT)` 성공 뒤에만 허용한다. input 상태의
  `digitalWrite(HIGH)` pull 전환, pin ownership, peripheral 충돌 검사와
  `OUTPUT_OPENDRAIN`은 아직 구현하지 않았다.

### 2.4 nRF54 시간 backend

| Arduino API | M3 backend |
| --- | --- |
| `millis()` | `k_uptime_get_32()` |
| `micros()` | `(k_cycle_get_64() - z_nrf_grtc_timer_startup_value_get())`를 `k_cyc_to_us_floor64()`로 변환한 하위 32 bit |
| `delay(0)` | `k_can_yield()`가 참일 때 guarded `k_yield()` |
| `delay(ms)` | 64-bit uptime deadline, `INT32_MAX` 이하 sleep chunk와 조기 기상 재시도 |
| `delayMicroseconds(us)` | 1초 이하 chunk로 나눈 `k_busy_wait()` |
| `yield()` | `k_can_yield()` 확인 뒤 `k_yield()` |

nRF54 GRTC counter는 애플리케이션 시작 시 0으로 초기화되지 않으므로 `micros()`는 Zephyr가
보존한 startup cycle 값을 뺀다. `millis()`와 `micros()`는 timer ISR에서 읽을 수 있다.
반면 `delay()`와 `yield()`는 yield 불가능 문맥에서 no-op이며 `delayMicroseconds()`는 ISR에서
no-op이다. 시간 API의 금지 문맥 오용을 기록하는 진단 상태는 M3에 없다.

---

## 3. 재현 명령

NCS v3.4.0 Toolchain 환경을 활성화한 PowerShell에서 실행한다.

```powershell
$NcsRoot = "C:/ncs/v3.4.0"
$CoreRoot = (Resolve-Path ".").Path
$BoardRoot = Join-Path $CoreRoot "board_package/NU54DK_Zephyr_DTS"
$Board = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"

west -z "$NcsRoot/zephyr" build `
  --pristine always `
  --no-sysbuild `
  -b $Board `
  -s "$CoreRoot/samples/zephyr/blink" `
  -d "$CoreRoot/build/m3-blink" `
  -- `
  "-DBOARD_ROOT=$BoardRoot" `
  "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

west -z "$NcsRoot/zephyr" build `
  --pristine always `
  --no-sysbuild `
  -b $Board `
  -s "$CoreRoot/samples/zephyr/gpio_input_smoke" `
  -d "$CoreRoot/build/m3-gpio-input" `
  -- `
  "-DBOARD_ROOT=$BoardRoot" `
  "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

west -z "$NcsRoot/zephyr" build `
  --pristine always `
  --no-sysbuild `
  -b $Board `
  -s "$CoreRoot/samples/zephyr/runtime_timing" `
  -d "$CoreRoot/build/m3-runtime-timing" `
  -- `
  "-DBOARD_ROOT=$BoardRoot" `
  "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

west -z "$NcsRoot/zephyr" flash `
  -d "$CoreRoot/build/m3-blink" `
  --dev-id <PROBE_UID>
```

일반 flash에는 `--erase`나 recover를 사용하지 않는다. `<PROBE_UID>`는 공개 문서에 실제
장치 식별값으로 치환해 commit하지 않는다.

---

## 4. Clean build와 산출물

세 M3 sample을 최종 source에서 각각 pristine build했다. 유일한 공통 경고는 보드/NCS의
deprecated `NRF_PLATFORM_LUMOS`이며 Core compile 또는 link 오류는 아니다.

| build | 결과 | FLASH | RAM | ELF 크기 |
| --- | --- | ---: | ---: | ---: |
| `m3-blink` | 274/274, PASS | 30,728 B | 6,856 B | 1,142,736 B |
| `m3-gpio-input` | 274/274, PASS | 31,048 B | 6,888 B | 1,146,616 B |
| `m3-runtime-timing` | 276/276, PASS | 34,720 B | 12,936 B | 1,311,760 B |

### 4.1 최종 산출물 SHA-256

| build | 파일 | 크기 | SHA-256 |
| --- | --- | ---: | --- |
| Blink | `zephyr.elf` | 1,142,736 B | `00784B02C4148BAC37BA2304C84A4DB6F130456306B1C65250D4396B81B081F4` |
| Blink | `zephyr.hex` | 86,499 B | `AB2D489BF5BF0CE3EAEA3ABB8C2E5D08ADEB6760FFB54B693C473BE115CB7F0E` |
| Blink | `zephyr.bin` | 30,728 B | `958A29601D1A551374912CDF918531A90CDF03986D18BC712237989731115FC7` |
| GPIO input | `zephyr.elf` | 1,146,616 B | `41BF6F1092F486A03726912D91B22F0050F5E437805BC5B255CE97E3259A3616` |
| GPIO input | `zephyr.hex` | 87,407 B | `C84F2C42BA5DA8658744C22A9ADE03E7E461AF95F23417EEA83203C3CCFEC3DC` |
| GPIO input | `zephyr.bin` | 31,048 B | `13BF75724BE22FC46CB702518A2C33D9F745B367E99A5D938F77B042DF9C5A71` |
| Runtime timing | `zephyr.elf` | 1,311,760 B | `31209CBF2D90A982A1FA3491EDB5E65D81DD30E4BFA2CBBF5A3343099777E44B` |
| Runtime timing | `zephyr.hex` | 97,733 B | `EF62E4394C32016DC09C2F16B0DD68FE837351554B5F14072D819DB660FA5944` |
| Runtime timing | `zephyr.bin` | 34,720 B | `4BEA5C1DE7B1830A944C8288B873B0C2A2AB280D594117861013880087B84B6C` |

clean revision의 provenance를 반영하면서 ELF hash는 바뀌었지만 세 HEX/BIN hash는 기존
실기에서 사용한 image와 동일하다. 따라서 아래 HIL은 현재 flashable firmware byte와
직접 연결된다. 이번 재검증 자체는 build-only이며 장치에 다시 flash하지 않았다.

세 성공 build의 `runners.yaml`은 모두 flash/debug 기본 runner를 `pyocd`로 생성하고,
pyOCD 인자는 `--dt-flash=y`와 `--target=nrf54l`만 포함한다.

### 4.2 Link와 증분 build

Core archive에서 `pinMode`, `digitalWrite`, `digitalRead`, `millis`, `micros`, `delay`,
`delayMicroseconds`, `yield`의 C symbol 전체를 확인했다. 각 최종 ELF에서는 section GC에
따라 해당 Sketch가 사용한 API만 남으며, 세 ELF의 합집합에서 전체 API를 확인했다.
`setup()`과 `loop()`는 Sketch가 소유하는 C++ symbol이며 Core의 `main`과 함께 하나의 ELF에
정적으로 링크된다. LLEXT와 별도 Loader는 없다.

변경 없는 세 rebuild는 모두 provenance 확인 target 한 건만 실행했다. C/C++ compile,
archive 생성과 ELF/HEX/BIN link는 0건이며 산출물 hash가 유지되었다. 이는 엄밀한
`ninja: no work to do`는 아니지만 코드 산출물 관점의 no-op이다.

M3에서 provenance 입력에 `variants/nu54dk`를 추가했다. 이제 Core revision dirty 판정과
`core_source_sha256`은 `cores`, `variants`, `zephyr`의 실제 Core 입력을 함께 추적한다.
Variant 임시 파일을 추가하면 live SHA-256이 바뀌고, 파일을 제거하면 원래 값으로
복원되는 것을 확인했다. 임시 파일은 시험 뒤 삭제했다.

---

## 5. GPIO 실기 결과

### 5.1 Arduino Blink

`samples/zephyr/blink`는 Zephyr GPIO API를 직접 호출하지 않고 다음 Arduino API만 쓴다.

```cpp
pinMode(LED_BUILTIN, OUTPUT);
digitalWrite(LED_BUILTIN, HIGH);
delay(250);
digitalWrite(LED_BUILTIN, LOW);
delay(250);
```

기존 HIL에서 CMSIS-DAP V2/pyOCD 경로로 사용자가 NU54DK LED의 지속적인 점멸을
확인했다. 현재 clean HEX는 그 image와 동일하며 이번 갱신에서는 다시 flash하지 않았다.

### 5.2 버튼 입력

`samples/zephyr/gpio_input_smoke`는 `PIN_BUTTON0`을 `INPUT_PULLUP`으로 구성한다. 버튼을
놓으면 raw `HIGH`, 누르면 raw `LOW`이며, 누른 동안 LED에 raw `HIGH`를 요청한다. 사용자가
`BUTTON 1`을 누르고 놓을 때 LED가 정상적으로 꺼지고 켜지는 것을 확인했다. 사용자는
관찰한 LED를 P1.14로 식별했지만, 해당 firmware의 `LED_BUILTIN` 생성 경로는
`DT_ALIAS(led0)` → `led0` → P2.9이다. P1.14는 보드 DTS의 `led3`이므로 실물 LED
식별은 후속 전용 핀 식별 HIL에서 재확인한다.

sample에는 다음 self-check도 포함된다.

- output으로 구성한 LED의 실제 readback
- `NUM_DIGITAL_PINS` 범위 밖 pin의 no-op/`LOW` 정책
- invalid pin 호출 전후 LED 상태 보존

버튼 연동 loop는 위 self-check가 모두 통과한 뒤에만 진입한다. 따라서 버튼에 따른
LED 반응은 self-check PASS의 간접 제어 흐름 oracle이다. 다만 저전력 대기 중인 target을
CMSIS-DAP가 안정적으로 halt하지 못해
`nu54_m3_gpio_input_trace` RAM 값은 회수하지 못했다. 따라서 버튼·LED 경로는 **육안 HIL
PASS**, self-check 결과는 **간접 PASS**, 각 세부 값의 debugger trace는
**EVIDENCE MISSING**으로 구분한다.

기존 GPIO HIL에서 동일 HEX의 compare/skip과 실행을 확인했다. 현재 clean GPIO HEX
SHA-256도 그 image와 동일하다.

---

## 6. 시간과 Scheduler 실측

`samples/zephyr/runtime_timing`은 측정 자체에 Core 반환 후 개입이 섞이지 않도록
`CONFIG_NUCODE_ARDUINO_LOOP_NONE=y`를 사용하고 네 동작을 각각 400 ms 측정한다.

아래 추적값은 기존 pyOCD HIL에서 `nu54_m3_runtime_timing_trace` RAM을 읽어 확보했다.
이번 clean 기준선 갱신에서는 RAM trace를 다시 회수하지 않았다. 현재 기준 transport는
CMSIS-DAP V2이며 V1 우선 옵션을 사용하지 않는다. 재현 가능한 CMSIS-DAP V2 trace 절차는
M8 debugger/HIL 단계에서 다시 기록하고 보드 package의 runner 설정은 변경하지 않는다.

### 6.1 시간 API 결과

| 항목 | 실측 |
| --- | ---: |
| 최종 trace | `PASS`, `failure=0` |
| `delay(20)`의 `millis()` 경과 | 20 ms |
| `delay(20)`의 `micros()` 경과 | 20,084 us |
| `delayMicroseconds(1000)` 경과 | 1,026 us |
| timer ISR의 `millis()`/`micros()` 읽기 | 1,582회 |

이 값은 firmware 내부 GRTC/Zephyr 시간원으로 시작과 끝을 읽은 결과다. 외부 logic analyzer
또는 oscilloscope에 의한 절대 정확도 검증은 아니다. 실제 32-bit rollover, 장시간 drift,
저전력 상태 전후 연속성과 `INT32_MAX`/1초 chunk 경계도 아직 별도 시험하지 않았다.

### 6.2 공정성 결과

| 400 ms 단계 | `loop()` | 같은 priority worker | 낮은 priority worker | timer ISR | system workqueue | idle 비율 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| busy spin | 177,986 | 0 | 0 | 390 | 40 | 0% |
| `yield()` | 66,937 | 371 | 0 | 391 | 40 | 0% |
| 한 kernel tick sleep | 4,048 | 368 | 368 | 390 | 40 | 85.53% |
| `delay(1)` | 368 | 367 | 367 | 391 | 39 | 96.71% |

busy spin에서도 interrupt와 system workqueue는 진행했지만 같은 priority worker, 낮은
priority worker와 idle은 진행하지 못했다. `yield()`는 같은 priority worker만 진행시켰고
낮은 priority와 idle은 여전히 0이었다. 한 tick sleep부터 두 worker와 idle이 모두
진행했다.

따라서 M3의 기본값은 `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK`으로 확정했다. 최대
반복률이 필요한 사용자는 `YIELD` 또는 `NONE`을 선택할 수 있지만 낮은 priority Zephyr
작업과 idle의 공존 책임을 애플리케이션이 져야 한다.

---

## 7. Negative 회귀

### 7.1 Core 비활성 앱

Zephyr `samples/hello_world`에 Core module과 NU54DK `BOARD_ROOT`를 전달하되
`CONFIG_NUCODE_ARDUINO_CORE`를 켜지 않고 pristine build했다.

| 확인 항목 | 결과 |
| --- | --- |
| build | 263/263, PASS |
| module 발견 | `CONFIG_ZEPHYR_NUCODE_ARDUINO_CORE_MODULE=y` |
| Core/GPIO/TIME 설정 | 비활성 |
| Core·Variant C++ compile | 0건 |
| Core archive와 live record | 없음 |
| ELF Arduino symbol | 0개 |
| `main` 소유자 | 애플리케이션 `main.c.obj` |
| FLASH / RAM | 30,224 B / 5,800 B |

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| `zephyr.elf` | 1,159,120 B | `CA5779A0B0D69B4AD010E766BD4AD7D732E890F1F20B81E07E87A8DDDEDAA098` |
| `zephyr.hex` | 85,096 B | `E700B202855D509911277594C844DFC2C4BD9F3589125328559FD5C95EF84C8A` |
| `zephyr.bin` | 30,224 B | `4A34BD35DF89DDFB62C543BC7A4A2D978B1ADA8FB024593B2ED52701FD995B00` |

### 7.2 필수 `led0` alias 누락

읽기 전용 보드 package를 유지한 채 Blink에 다음 임시 overlay를 적용해 `led0` alias를
삭제한 pristine build는 의도대로 실패했다.

```dts
/ {
    aliases {
        /delete-property/ led0;
    };
};
```

최종 진단은 다음 한 가지 Core 오류로 수렴했다.

```text
error: #error "NU54DK Arduino Variant에는 활성화된 led0 alias가 필요합니다."
```

실패용 overlay는 검증 뒤 제거했으며 정상 sample이나 보드 package를 변경하지 않았다.
NCS v3.4.0 Windows에서 기존 build tree에 overlay를 추가해 CMake를 재구성하면 generated
Kconfig string quoting 경고가 먼저 발생할 수 있어, 이 negative test도 pristine build가
재현 기준이다.

---

## 8. 알려진 제한과 후속 검증

| 항목 | M3 상태와 후속 조치 |
| --- | --- |
| revision 기준 | Core `a8d62ea75fef`, 보드 `fe65f2f0880b` clean provenance와 pristine artifact hash를 확보했다. 보드 서브모듈은 읽기 전용이다. |
| provenance | 표준 `build_info.yml`은 configure 시점 snapshot이고 `nucode_arduino_core_build.yml`은 매 build의 live record다. 증분 source 변경 후 두 값이 다를 수 있으며 최종 image는 pristine build와 artifact SHA-256으로 고정한다. |
| LED 물리 식별 | generated DTS의 `led0`는 P2.9이지만 사용자는 반응 LED를 P1.14로 식별했다. LED별 전용 HIL로 재확인한다. |
| GPIO RAM trace | 버튼·LED 육안 HIL과 self-check 제어 흐름은 PASS지만 세부 trace 값은 미회수다. M8 debugger/HIL 자동화에서 보완한다. |
| 외부 timing 계측 | 내부 GRTC 측정만 통과했다. logic analyzer/oscilloscope로 period와 busy wait 정확도를 검증한다. |
| rollover와 긴 대기 | compile-time modulo 계산만 있으며 실제 32-bit rollover, `INT32_MAX` sleep 및 긴 busy-wait는 NOT RUN이다. |
| 저전력 연속성 | GRTC 기반 `micros()`의 PM 상태 전후 연속성과 drift는 NOT RUN이다. |
| GPIO 동시성 | M3는 thread-only이며 여러 thread의 같은 pin 경쟁, ownership과 peripheral 충돌은 미구현이다. |
| Interrupt | `attachInterrupt()`/`detachInterrupt()`와 ISR digital GPIO 계약은 M3 범위 밖이다. |
| Twister/ztest | west-native clean/negative와 로컬 HIL은 통과했지만 자동 test suite는 아직 없다. |
| Arduino CLI/IDE | `.ino`, library discovery, Build Adapter와 Actions upload는 M5 이후 범위다. |
| 외장 J-Link | runner metadata는 생성되지만 실제 외장 J-Link flash/debug HIL은 M8까지 미검증이다. |
| nRF54 내부 symbol | `z_nrf_grtc_timer_startup_value_get()`는 Zephyr 내부 API이므로 NCS 업그레이드 때 compile과 의미를 다시 검증한다. |

---

## 9. M3 판정

| 완료 기준 | 결과 | 증거 |
| --- | --- | --- |
| DTS 기반 최소 Variant | 통과 | `led0`/`sw0` 두 descriptor, 물리 pin 하드코딩 없음 |
| Arduino Blink build·실행 | 통과 | clean HEX가 기존 CMSIS-DAP V2/pyOCD HIL image와 동일; 이번 갱신에서 flash 미수행 |
| GPIO input 실기 | 조건부 통과 | BUTTON 1에 따른 LED 전환 확인; generated DTS는 P2.9, 사용자 식별은 P1.14로 서로 달라 재확인 필요; 내부 RAM trace는 미회수 |
| 시간 API 기본 동작 | 통과 | delay/busy-wait/ISR trace `PASS`, `failure=0` |
| Zephyr scheduler 공존 정책 | 통과 | 네 400 ms 단계 실측과 기본 one-tick 결정 |
| Core 비활성 회귀 | 통과 | Core compile/archive/symbol 0개 |
| 필수 DTS alias negative | 통과 | pristine build가 명시적인 한국어 compile error로 expected fail |
| 변경 없는 rebuild | 기존 회귀 통과 | 이번 기준선 갱신은 pristine build만 수행 |
| 공개 재현 가능한 revision | 통과 | clean Core·보드 revision과 source/artifact SHA-256 확보 |

**결정 게이트: CONDITIONAL GO.** M3의 GPIO·시간 수직 경로와 기본 scheduler 정책은
실제 NU54DK에서 성립했고 clean HEX/BIN이 기존 HIL image와 동일함을 확인했다. clean
revision 고정은 완료됐으므로 더 이상 GO 전환 대기 항목이 아니다. 남은 조건은 LED 물리
식별, GPIO trace 자동화, 외부 전압·시간 계측, runtime rollover, PM/idle과 ztest/Twister
회귀다. 이들은 M4 착수를 막지 않지만 M3 최종 GO 전환 전에는 완료해야 한다.
