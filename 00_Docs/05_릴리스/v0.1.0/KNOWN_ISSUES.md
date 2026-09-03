# v0.1.0 알려진 제약

이 문서는 정식 `v0.1.0`에서 의도적으로 지원하지 않거나 의미가 제한된 항목을 공개한다.

## 지원 플랫폼과 설치

- Windows 10/11 x64만 공식 검증한다. Linux와 macOS는 공식 지원 대상이 아니다.
- NU54DK의 `nrf54l15dk/nrf54l15/cpuapp/nu54dk` qualifier만 지원한다.
- NCS v3.4.0, Zephyr 4.4.0, Toolchain bundle `dcbdc366a1`을 exact pin으로 사용한다.
- 첫 설치는 NCS와 Toolchain download 때문에 오래 걸리고 많은 디스크 공간을 사용한다.
- offline 설치와 인증 proxy는 공식 검증하지 않았다.
- Core uninstall은 공유 NCS와 Toolchain을 자동 삭제하지 않는다.
- stable index의 `main` URL은 최신 정식 version을 가리킨다. `v0.1.0`의 version 고정 snapshot은
  GitHub Release asset과 공개한 checksum을 사용한다. GitHub의 강제 Release immutability는 사용하지 않는다.

## 검증 증거 경계

- rc.2 공개 후 clean Windows Arduino IDE 설치·compile·실제 NU54DK upload·실행을 프로젝트
  소유자가 수동 확인했다.
- stable은 exact archive·index·checksum과 rc.2 대비 runtime fingerprint 동등성을 검증한다.
- rc.2 수동 HIL을 stable exact HIL PASS로 소급 표기하지 않는다.
- M6 버튼, M7 I2C/SPI/ADC/PWM의 세부 물리 시험은 각 마일스톤 기준선을 계승하며 release마다
  재계측하지 않는다.

## Arduino 의미 차이

- `Serial`은 native USB CDC가 아니라 Zephyr console의 DAP UART wrapper다.
- `Serial`은 115200 8N1에 제한되며 `Serial1`과 `SerialUSB`를 제공하지 않는다.
- `millis()`/`micros()`의 실제 장기 rollover와 PM/idle 전후 연속성은 장시간 실기로
  검증하지 않았다.
- Core debounce를 제공하지 않으며 ISR에서 blocking, heap, Serial과 delay를 허용하지 않는다.
- AVR register, `PROGMEM`, `PSTR`와 Harvard memory 의미를 모사하지 않는다.

## Peripheral 제약

- Arduino 논리 pin은 Variant capability table에 등록된 핀만 사용한다.
- `Wire`는 I2C22 P1.2/P1.3, 7-bit controller mode, 32-byte TX/RX, 100/400 kHz다.
  target/slave mode, `Wire1`, `requestFrom(..., false)`는 미지원이다.
- `SPI`는 SPI00 기본 instance이며 다중 SPI bus는 미지원이다.
- `analogRead()`는 A0/P1.12의 고정 12-bit raw 값이며 전압 정확도를 보증하지 않는다.
- `analogWrite()`는 P1.10의 20 ms·8-bit PWM이며 DAC가 아니다.

## v0.1 범위 밖

- Loader, LLEXT, runtime Sketch 교체
- MCUboot, UF2, drag-and-drop, OTA
- native USB CDC/HID, Keyboard, Mouse
- BLE Arduino API, Thread, Matter, 802.15.4 wrapper
- Wi-Fi/Ethernet, filesystem, EEPROM emulation, external flash library
- `tone()`, Servo, `pulseIn()`, `shiftIn()`/`shiftOut()`
- multi-board 및 임의 NCS/Zephyr version 선택

전체 API 상태는
[Arduino API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를 따른다.
