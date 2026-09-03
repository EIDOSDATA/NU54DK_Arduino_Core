# v0.1.0-rc.2 알려진 제약

> **공개 완료:** 이 제약 목록은 2026-08-28에 공개한 `v0.1.0-rc.2` 기준이다. 공개 index와
> ZIP을 사용한 Arduino IDE 2.3.10 backend 설치 완료 경로를 검증했다. 공개 후 별도 clean
> Windows의 compile과 실제 NU54DK upload·실행도 프로젝트 소유자가 수동 확인했다.

이 문서는 release candidate에서 의도적으로 지원하지 않거나 의미가 제한된 항목을 공개한다.
API 이름이나 header가 존재해도 아래 범위를 넘어서는 지원을 의미하지 않는다.

## 지원 플랫폼

- Windows 10/11 x64만 검증 대상으로 한다. Linux와 macOS는 공식 지원 대상이 아니다.
- NU54DK의 `nrf54l15dk/nrf54l15/cpuapp/nu54dk` qualifier만 지원한다.
- NCS v3.4.0, Zephyr 4.4.0, Toolchain bundle `dcbdc366a1`을 exact pin으로 사용한다.
- Arduino IDE GUI 클릭 자체는 자동화하지 않았다. 대신 IDE 2.3.10 내장 Arduino CLI 1.5.1
  daemon에 실제 gRPC `PlatformInstall`을 호출해 공개 ZIP 다운로드, 한글 `post_install`
  메시지, 설치 완료와 최종 `result {}`를 검증했다.

## 설치와 배포

- 첫 설치는 NCS와 Toolchain download 때문에 오래 걸리고 많은 디스크 공간을 사용한다.
- Core ZIP은 Nordic NCS/Toolchain/nRF Util/pyOCD/J-Link를 재배포하지 않는다. 공식
  download와 사용자 영역 설치를 사용한다.
- offline 설치와 인증 proxy는 공식 검증하지 않았다.
- Core uninstall은 공유 NCS와 Toolchain을 자동 삭제하지 않는다.
- 후속 정식 버전은 `v0.1.0`이다. 신규 설치는 stable index를 사용하며 rc.2 index와
  Prerelease는 당시 검증 이력으로 유지한다.
- rc.1은 `post_install` gRPC UTF-8 오류로 회수됐다. 설치가 완료됐을 수 있어도 새 설치나
  downgrade 대상으로 사용하지 않는다.
- rc.2 공개 시점에는 probe가 연결되지 않았고 별도 clean Windows PC가 오프라인이어서 새
  RC2 byte의 pyOCD HIL 두 범위와 clean Windows 전체 lifecycle을 재실행하지 않았다. 공개
  후에는 별도 clean Windows의 Arduino IDE 설치·compile·실제 NU54DK upload·실행을 수동
  검증했다. 다만 공개 시점에 생성하지 않은 strict M11 evidence manifest는 소급 생성하지
  않았으므로 이 결과를 rc.2 자동 gate 8/8로 해석하지 않는다.
- RC1 대비 배포 archive의 변경은 version 표기와 prerequisite 설치 스크립트 세 개뿐이다.
  firmware·DTS·핀·Upload byte 범위는 변경하지 않았지만, 이는 누락된 RC2 HIL을 PASS로
  대체한다는 의미가 아니다.

## RC마다 다시 실행하지 않는 물리 시험

- release HIL gate는 Upload 경로와 부팅 후 UART READY를 중심으로 확인한다.
- M6 버튼 GPIO edge, M7 BQ25186 I2C, A0 ADC, P1.10 PWM과 SPI00 loopback의 세부 물리 시험은
  해당 마일스톤의 커밋된 검증 기록을 참조한다.
- 따라서 RC Upload PASS를 센서·버스·아날로그 전기 특성의 재계측으로 해석하지 않는다.

## Arduino 의미 차이

- `Serial`은 target native USB CDC가 아니라 Zephyr console의 DAP UART wrapper다.
- `Serial`은 115200 8N1에 제한되며 `Serial1`과 `SerialUSB`를 제공하지 않는다.
- `millis()`/`micros()`의 실제 장기 rollover 및 PM/idle 전후 연속성은 장시간 실기로
  검증하지 않았다.
- Core debounce를 제공하지 않으며 ISR에서 blocking, heap, Serial과 delay를 허용하지 않는다.
- C++ exception/RTTI의 compile/link 구성은 실제 throw·heap 의미의 지원 선언이 아니다.
- AVR register, `PROGMEM`, `PSTR`와 Harvard memory 의미를 모사하지 않는다.

## Peripheral 제약

- Arduino 논리 pin은 Variant capability table에 등록된 핀만 사용한다.
- `Wire`는 I2C22 P1.2/P1.3, 7-bit controller mode, 32-byte TX/RX, 100/400 kHz다.
  target/slave mode, `Wire1`, `requestFrom(..., false)`는 미지원이다.
- `SPI`는 SPI00 기본 instance다. 다른 Zephyr client와 bus-wide 동시 사용은 application이
  직렬화해야 하며 다중 SPI bus는 미지원이다.
- `analogRead()`는 A0/P1.12의 고정 12-bit raw 값이며 전압 정확도를 보증하지 않는다.
- `analogWrite()`는 P1.10의 20 ms·8-bit PWM이며 DAC가 아니다. 주파수와 resolution 변경
  API는 미지원이다.

## v0.1 범위 밖

- Loader, LLEXT, runtime Sketch 교체
- MCUboot, UF2, drag-and-drop, OTA
- native USB CDC/HID, Keyboard, Mouse
- BLE Arduino API, Thread, Matter, 802.15.4 wrapper
- Wi-Fi/Ethernet transport, filesystem, EEPROM emulation, external flash library
- `tone()`, Servo, `pulseIn()`, `shiftIn()`/`shiftOut()`
- multi-board 및 임의 NCS/Zephyr version 선택

전체 API 상태는
[Arduino API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를 따른다.
