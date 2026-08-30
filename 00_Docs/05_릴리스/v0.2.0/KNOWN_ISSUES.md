# NU54DK Arduino Core v0.2.0 알려진 제약

> **상태: v0.2.0 정식 릴리스.** 이 문서는 API 이름이나 compile 결과를 실제 hardware
> 지원보다 넓게 해석하지 않기 위한 공개 경계다.

| 항목 | 고정 값 |
| --- | --- |
| 공식 사용자 OS | Windows 10/11 x64 |
| Board/FQBN | NU54DK / `nucode:zephyr:nu54dk` |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain | `dcbdc366a1` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

## 1. Release와 설치 상태

- `v0.2.0`은 RC1 실기 검증에서 발견한 다중 CMSIS-DAP 선택과 NUS 예제 로그 간섭을
  RC2에서 교정하고 공개 설치본 gate를 통과한 runtime을 정식 승격한 버전이다.
- 공개 RC index를 사용한 Boards Manager 설치와 `post_install`, 14개 예제 compile, 명시 UID
  upload 및 UART READY는 PASS다.
- RC2 설치본 NUS Peripheral/Central의 startup과 양방향 고유 payload 원문 연속 수신은 PASS며
  RC1 상태 로그 삽입은 재현되지 않았다.
- 이번 공개 예제 transparent bridge HIL은 M16의 frame boundary·disconnect/reconnect 전문
  HIL 전체를 다시 실행한 결과가 아니다.
- RC1과 RC2의 tag·자산은 각각 불변 기록이며 stable 자산으로 덮어쓰지 않는다.
- 일반 사용자는 stable index의 `v0.2.0`을 사용한다. `v0.1.0`은 downgrade용으로 함께 보존한다.
- Windows 이외의 Linux/macOS package 설치는 공식 지원·검증 대상이 아니다.
- 첫 설치는 고정 NCS와 Toolchain을 받기 때문에 오래 걸리고 많은 디스크 공간이 필요하다.
- offline 설치, 인증 proxy와 기업 TLS inspection 환경은 공식 검증하지 않았다.
- Core 제거는 여러 Core version이 공유할 수 있는 NCS와 Toolchain을 자동 삭제하지 않는다.

## 2. Firmware 구조

- Loader, LLEXT와 runtime Sketch 교체를 제공하지 않는다.
- Sketch를 바꿀 때마다 Zephyr application 전체를 다시 compile/link하고 flash한다.
- MCUboot, UF2, drag-and-drop, OTA와 application-only hot swap은 지원하지 않는다.
- 임의 NCS/Zephyr/toolchain version 선택과 NU54DK 이외의 multi-board 지원은 범위 밖이다.
- 사용자가 package 안의 bundled board DTS를 별도 checkout과 섞거나 덮어쓰는 구성을 지원하지 않는다.

## 3. Arduino API 의미 차이

- `Serial`은 native USB CDC가 아니라 온보드 CMSIS-DAP의 DAP UART를 사용하는 Zephyr console
  wrapper이며 115200 8N1이 기준이다.
- `Serial1`, `SerialUSB`, native USB CDC/HID, Keyboard와 Mouse를 제공하지 않는다.
- Core debounce를 제공하지 않으며 ISR 안에서 blocking, heap, `Serial`과 `delay()`를 사용하면 안 된다.
- AVR register, `PROGMEM`, `PSTR`와 Harvard memory 의미를 모사하지 않는다.
- `millis()`/`micros()`의 32-bit 장기 rollover와 PM/idle 전후 연속성을 장시간 실기로 재검증하지 않았다.
- `tone()`, Servo, `pulseIn()`, `shiftIn()`/`shiftOut()`, Wi-Fi/Ethernet, filesystem과 EEPROM
  emulation은 지원하지 않는다.

## 4. Peripheral 제약

- Arduino 논리 pin은 NU54DK Variant capability table에 등록된 핀만 사용한다.
- `Wire`는 I2C22 P1.2/P1.3의 7-bit controller mode, 32-byte TX/RX와 100/400 kHz 범위다.
  target/slave mode, `Wire1`과 `requestFrom(..., false)`는 미지원이다.
- `SPI`는 SPI00 기본 instance다. 다중 SPI bus와 자동 bus arbitration은 미지원이다.
- `analogRead()`는 A0/P1.12의 고정 12-bit raw 값이며 전압 정확도를 보증하지 않는다.
- `analogWrite()`는 P1.10의 20 ms·8-bit PWM이며 DAC가 아니다. 주파수와 resolution 변경 API는 없다.

## 5. Board/System과 PMIC 경계

- Board identity, reset, watchdog, GRTC alarm, Settings storage와 System OFF API는 NU54DK 전용이다.
- System OFF 실기에서는 active debugger/SWD 연결이 reset cause와 저전력 상태를 방해할 수 있다.
  Flash 뒤 SWD session을 종료하고 필요한 경우 probe의 SWD를 물리적으로 분리해 검증한다.
- BQ25186 write API는 같은 boot의 RAM에만 유지되는 명시적 승인과 register watchdog 정책을
  요구한다. reset 뒤 승인은 자동 복원되지 않는다.
- API로 충전 전압·전류, recharge threshold, SYS regulation, register watchdog와 ship/shutdown
  요청을 구성할 수 있지만 실제 배터리 전기 HIL은 수행하지 않았다.
- 충전 완료·재충전, 입력 전원 제거 후 ship/shutdown, 배터리 chemistry/용량과 NTC 온도 보호는
  사용자의 실제 회로·배터리 조건에서 검증해야 한다.
- `hasBatteryTemperatureProtection()`은 `false`이며 이 릴리스는 실제 배터리 온도 보호를 지원하지 않는다.
- PMIC semantic test나 register readback을 배터리 안전성·충전 인증으로 해석하면 안 된다.

## 6. BLE NUS 경계

- `BLESerial`은 한 image에서 Peripheral 또는 Central 역할 하나만 사용한다.
- 지원 transport는 NUS RX write와 TX notification을 사용하는 byte `Stream`이다.
- 임의 GATT service/characteristic 생성, GATT read, indication, bonding, SMP, HID와 보안 UI는
  지원하지 않는다.
- Thread/Matter/802.15.4와 BLE의 multiprotocol coexistence는 지원하지 않는다.
- 두 NU54DK NUS echo/reconnect HIL 통과를 일반 BLE interoperability 인증으로 확대하지 않는다.
- RC2의 `NUSPeripheral` 예제는 `received` event를 별도 상태 로그로 출력하지 않는다. 수신 byte와
  같은 `Serial`을 사용하는 응용은 자신의 진단 로그가 payload에 섞이지 않도록 동일한 원칙을
  지켜야 한다.

## 7. Sensor와 Crypto 경계

- Core는 NUCODE sensor wrapper 또는 bundled sensor library를 제공하지 않는다.
- M17의 Adafruit LSM6DS3TR-C 결과는 외부 library와 dependency를 고정한 compatibility Sketch의
  compile/link PASS뿐이다. 해당 source와 Sketch는 14개 package 사용자 예제에 포함되지 않는다.
- LSM6DS3TR-C 초기화, 실제 I2C/SPI 측정, interrupt, FIFO와 전원 mode HIL은 실행하지 않았다.
- Zephyr sensor direct-build fixture의 compile 성공은 특정 sensor runtime 지원 선언이 아니다.
- NCS Crypto RNG는 공식 보드와 NU54DK direct build만 통과했다. Arduino crypto wrapper,
  entropy 품질 평가와 semantic/HIL을 제공하지 않는다.

## 8. IEEE 802.15.4, OpenThread와 Matter

세 항목은 모두 `deferred`이며 `v0.2.0`의 지원 기능이 아니다.

| 항목 | M17 결과 | 지원하지 않는 범위 |
| --- | --- | --- |
| IEEE 802.15.4 PHY test | 공식 보드 build PASS, NU54DK NVMC symbol/type/instance 오류 | NU54DK radio runtime과 Arduino wrapper |
| OpenThread CLI | 공식 보드와 NU54DK build PASS | network join, radio HIL, commissioning과 Arduino facade |
| Matter template | 공식 보드 build PASS, NU54DK `factory_data_partition` 누락 | product partition, factory data, commissioning과 Arduino API |

OpenThread build PASS를 Thread 지원 선언으로 사용하지 않는다. 802.15.4와 Matter의 NU54DK
build 실패를 임의 DTS/partition patch로 숨기지 않았으며 board submodule도 변경하지 않았다.

## 9. Upload와 debug 경계

- 기본 Upload는 온보드 CMSIS-DAP V2와 pyOCD다. `nrfutil`은 NU54DK 기본 runner가 아니다.
- CMSIS-DAP가 하나면 기본 `CMSIS-DAP (pyOCD)` 경로가 UID 입력 없이 자동 선택한다.
- CMSIS-DAP가 여러 개 연결되면 임의 첫 probe를 선택하지 않는다. 먼저
  `CMSIS-DAP with UID (pyOCD)`를 선택한 뒤 Upload의 `CMSIS-DAP unique ID` 필드에 대상 UID를
  명시해야 한다. 이 값은 COM port가 아니다.
- 외장 J-Link는 SEGGER J-Link Software, target VTref와 올바른 SWD wiring이 필요한 선택 경로다.
- J-Link 선택 실패 시 pyOCD로 자동 fallback하지 않는다.
- 일반 Upload는 mass erase/recover를 자동 실행하지 않는다. 보호 상태 복구와 전체 erase는 별도
  고위험 유지보수 작업이다.

## 10. 검증 증거의 해석

- M12~M17의 완료는 각 단계에서 선언한 software/build/HIL 범위에만 적용된다.
- package example compile은 실제 sensor, PMIC, radio 또는 저전력 HIL을 대신하지 않는다.
- M18 remote Draft ID와 asset SHA-256 검증은 clean Windows staged 실행 또는 public
  Boards Manager 설치를 대신하지 않는다.
- RC2 public Boards Manager 설치본의 PASS 범위는 `post_install`, 14/14 compile, 명시 UID
  upload, UART READY와 NUS 공개 예제 양방향 transparent bridge·로그 회귀다.
- stable exact ZIP의 runtime payload는 RC2와 byte-equivalent한지 별도로 검증하며, 공개
  `0.1.0`→`0.2.0` upgrade·downgrade·uninstall 수명주기를 정식 공개 기록에 고정한다.
