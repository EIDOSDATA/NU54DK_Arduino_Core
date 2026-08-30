# NU54DK Arduino Core v0.2.0-rc.1 알려진 제약

> **상태: GitHub Draft 준비 완료 / clean Windows staged ZIP 검증 대기.** Draft는 실제 Git
> tag가 없는 내부 상태일 수 있다. 이 문서는 API 이름이나 compile 결과를 실제 hardware
> 지원보다 넓게 해석하지 않기 위한 공개 경계다. 최신 정식 버전은 계속 `v0.1.0`이다.

| 항목 | 고정 값 |
| --- | --- |
| 공식 사용자 OS | Windows 10/11 x64 |
| Board/FQBN | NU54DK / `nucode:zephyr:nu54dk` |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain | `dcbdc366a1` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

## 1. Release와 설치 상태

- `v0.2.0-rc.1`은 Draft candidate이며 아직 일반 공개 Boards Manager package가 아니다.
- Draft의 RC 이름은 예약 metadata이며 실제 Git tag가 생성됐다는 뜻이 아니다.
- GitHub Draft asset은 인증되지 않은 public download URL에서 받을 수 없다.
- Draft의 RC index URL을 Arduino IDE에 등록해 일반 사용자 설치가 된다고 안내하지 않는다.
- Draft 단계 clean Windows 검증은 exact ZIP을 새 Sketchbook의 격리된
  `hardware/nucode/zephyr` staging에 수동 추출한 뒤 14개 예제 열거, compile와 실제 NU54DK
  pyOCD upload까지만 확인한다. 이는 Boards Manager 설치·`post_install` end-to-end가 아니다.
- staged 결과를 프로젝트 소유자가 승인해 public RC로 전환한 뒤 공개 RC index로 별도 clean
  Windows Boards Manager 설치·`post_install`와 수명주기를 다시 검증한다. 이 결과의 별도
  승인 전에는 `v0.2.0` stable을 공개하지 않는다.
- `%LOCALAPPDATA%\Arduino15`에 Draft ZIP을 수동 복사·추출해 Boards Manager 설치를 가장하지 않는다.
- 일반 사용자는 공개 stable `v0.1.0`과 stable index를 계속 사용한다.
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
- `hasBatteryTemperatureProtection()`은 `false`이며 이 RC는 실제 배터리 온도 보호를 지원하지 않는다.
- PMIC semantic test나 register readback을 배터리 안전성·충전 인증으로 해석하면 안 된다.

## 6. BLE NUS 경계

- `BLESerial`은 한 image에서 Peripheral 또는 Central 역할 하나만 사용한다.
- 지원 transport는 NUS RX write와 TX notification을 사용하는 byte `Stream`이다.
- 임의 GATT service/characteristic 생성, GATT read, indication, bonding, SMP, HID와 보안 UI는
  지원하지 않는다.
- Thread/Matter/802.15.4와 BLE의 multiprotocol coexistence는 지원하지 않는다.
- 두 NU54DK NUS echo/reconnect HIL 통과를 일반 BLE interoperability 인증으로 확대하지 않는다.

## 7. Sensor와 Crypto 경계

- Core는 NUCODE sensor wrapper 또는 bundled sensor library를 제공하지 않는다.
- M17의 Adafruit LSM6DS3TR-C 결과는 외부 library와 dependency를 고정한 compatibility Sketch의
  compile/link PASS뿐이다. 해당 source와 Sketch는 14개 package 사용자 예제에 포함되지 않는다.
- LSM6DS3TR-C 초기화, 실제 I2C/SPI 측정, interrupt, FIFO와 전원 mode HIL은 실행하지 않았다.
- Zephyr sensor direct-build fixture의 compile 성공은 특정 sensor runtime 지원 선언이 아니다.
- NCS Crypto RNG는 공식 보드와 NU54DK direct build만 통과했다. Arduino crypto wrapper,
  entropy 품질 평가와 semantic/HIL을 제공하지 않는다.

## 8. IEEE 802.15.4, OpenThread와 Matter

세 항목은 모두 `deferred`이며 `v0.2.0-rc.1`의 지원 기능이 아니다.

| 항목 | M17 결과 | 지원하지 않는 범위 |
| --- | --- | --- |
| IEEE 802.15.4 PHY test | 공식 보드 build PASS, NU54DK NVMC symbol/type/instance 오류 | NU54DK radio runtime과 Arduino wrapper |
| OpenThread CLI | 공식 보드와 NU54DK build PASS | network join, radio HIL, commissioning과 Arduino facade |
| Matter template | 공식 보드 build PASS, NU54DK `factory_data_partition` 누락 | product partition, factory data, commissioning과 Arduino API |

OpenThread build PASS를 Thread 지원 선언으로 사용하지 않는다. 802.15.4와 Matter의 NU54DK
build 실패를 임의 DTS/partition patch로 숨기지 않았으며 board submodule도 변경하지 않았다.

## 9. Upload와 debug 경계

- 기본 Upload는 온보드 CMSIS-DAP V2와 pyOCD다. `nrfutil`은 NU54DK 기본 runner가 아니다.
- CMSIS-DAP가 여러 개 연결되면 임의 첫 probe를 선택하지 않고 명시적 선택을 요구한다.
- 외장 J-Link는 SEGGER J-Link Software, target VTref와 올바른 SWD wiring이 필요한 선택 경로다.
- J-Link 선택 실패 시 pyOCD로 자동 fallback하지 않는다.
- 일반 Upload는 mass erase/recover를 자동 실행하지 않는다. 보호 상태 복구와 전체 erase는 별도
  고위험 유지보수 작업이다.

## 10. 검증 증거의 해석

- M12~M17의 완료는 각 단계에서 선언한 software/build/HIL 범위에만 적용된다.
- package example compile은 실제 sensor, PMIC, radio 또는 저전력 HIL을 대신하지 않는다.
- M18 remote Draft ID와 asset SHA-256 검증은 clean Windows staged 실행 또는 public RC
  Boards Manager 설치를 대신하지 않는다.
- staged ZIP 결과와 public RC Boards Manager 결과는 서로 다른 검증 기록과 프로젝트 소유자
  승인으로 남긴다.
