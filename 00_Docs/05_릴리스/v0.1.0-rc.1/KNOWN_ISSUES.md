# v0.1.0-rc.1 알려진 제약

> **회수됨:** 이 문서는 `v0.1.0-rc.1` 공개 당시 승인된 제약을 보존한다. 공개 후 Arduino
> IDE `post_install` 완료 응답에서 invalid UTF-8 gRPC 오류가 발생할 수 있음을 확인했으며,
> 설치 자체는 완료됐을 수도 있지만 결과 표시를 신뢰할 수 없어 배포를 중단했다. 새 설치에는
> `v0.1.0-rc.2`를 사용한다. [배포 중단 기록](WITHDRAWAL.md)

이 문서는 release candidate에서 의도적으로 지원하지 않거나 의미가 제한된 항목을 사용자에게
노출한다. API 이름이나 header가 존재해도 아래 범위를 넘어서는 지원을 의미하지 않는다.

## 지원 플랫폼

- Windows 10/11 x64만 검증했다. Linux와 macOS는 공식 지원 대상이 아니다.
- NU54DK의 `nrf54l15dk/nrf54l15/cpuapp/nu54dk` qualifier만 지원한다.
- NCS v3.4.0, Zephyr 4.4.0, Toolchain bundle `dcbdc366a1`을 exact pin으로 사용한다.
- Arduino IDE GUI 화면 조작 자체는 독립 자동화하지 않았다. clean-PC 증거는 같은
  package/index backend를 사용하는 Arduino CLI `1.5.2-rc.1`로 수집했다. 공개 뒤에는
  Arduino IDE bundled backend 1.5.1의 격리 환경에서 RC index 수집과
  `nucode:zephyr` `0.1.0-rc.1` 검색까지 추가로 통과했다.

## 설치와 배포

- 첫 설치는 NCS와 Toolchain download 때문에 오래 걸리고 많은 디스크 공간을 사용한다.
- Core ZIP은 Nordic NCS/Toolchain/nRF Util/pyOCD/J-Link를 재배포하지 않는다. 공식 download와
  사용자 영역 설치를 사용한다.
- offline 설치와 인증 proxy는 공식 검증하지 않았다.
- Core uninstall은 공유 NCS와 Toolchain을 자동 삭제하지 않는다.
- stable package index와 `v0.1.0` stable Release는 사람의 법률·출시 승인 전까지 존재하지 않는다.
- clean Windows install/upgrade/downgrade/uninstall/reinstall 및 pyOCD 10회 내구 반복은 RC와
  동일한 runtime payload의 Windows-safe preview `0.0.96`/`0.0.97`로 수행했다. exact RC ZIP은
  최종 원격 M11 gate에서 고정 package compile과 pyOCD 1회+UART READY로 직접 검증해
  PASS했다. 다만 clean lifecycle 전체를 RC version으로 다시 실행한 것은 아니다.
- `0.0.94`/`0.0.95`는 PowerShell 5.1 runner 수정 전 preflight에서 실패한 immutable
  preview이므로 clean lifecycle 또는 M11 계승 증거로 인정하지 않는다.

## RC에서 다시 실행하지 않는 물리 시험

- exact RC HIL gate는 Upload 경로와 부팅 후 UART READY만 확인한다.
- M6 버튼 GPIO edge, M7 BQ25186 I2C, A0 ADC, P1.10 PWM과 SPI00 loopback의 세부 물리 시험은
  해당 마일스톤의 커밋된 검증 기록을 동결해 참조하며 RC마다 다시 실행하지 않는다.
- 따라서 RC Upload PASS를 센서·버스·아날로그 전기 특성의 재계측 결과로 해석하면 안 된다.

## Arduino 의미 차이

- `Serial`은 target native USB CDC가 아니라 Zephyr console의 DAP UART wrapper다.
- `Serial`은 115200 8N1에 제한되며 `Serial1`과 `SerialUSB`를 제공하지 않는다.
- `millis()`/`micros()`의 실제 장기 rollover 및 PM/idle 전후 연속성은 장시간 실기로 검증하지
  않았다.
- Core debounce를 제공하지 않으며 ISR에서 blocking, heap, Serial과 delay 사용을 허용하지 않는다.
- C++ exception/RTTI의 compile/link 구성은 있어도 실제 throw·heap 의미를 지원 완료로 선언하지
  않는다.
- AVR register, `PROGMEM`, `PSTR`, Harvard memory 의미를 모사하지 않는다.

## Peripheral 제약

- Arduino 논리 pin은 Variant capability table에 등록된 핀만 사용한다.
- `Wire`는 I2C22 P1.2/P1.3, 7-bit controller mode, 32-byte TX/RX, 100/400 kHz다.
  target/slave mode, `Wire1`, `requestFrom(..., false)`는 미지원이다.
- `SPI`는 SPI00 기본 instance다. 다른 Zephyr client와 bus-wide 동시 사용은 application이
  직렬화해야 한다. 다중 SPI bus는 미지원이다.
- `analogRead()`는 A0/P1.12의 고정 12-bit raw 값이며 전압 정확도를 보증하지 않는다.
- `analogWrite()`는 P1.10의 20 ms·8-bit PWM이며 DAC가 아니다. 주파수와 resolution 변경 API는
  미지원이다.

## v0.1 범위 밖

- Loader, LLEXT, runtime Sketch 교체
- MCUboot, UF2, drag-and-drop, OTA
- native USB CDC/HID, Keyboard, Mouse
- BLE Arduino API, Thread, Matter, 802.15.4 wrapper
- Wi-Fi/Ethernet transport, filesystem, EEPROM emulation, external flash library
- `tone()`, Servo, `pulseIn()`, `shiftIn()`/`shiftOut()`
- multi-board 및 임의 NCS/Zephyr version 선택

전체 항목별 상태는
[Arduino API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)가 단일 기준이다.
