# NU54DK Arduino Core v0.3.0 릴리스 노트

`v0.3.0`은 `v0.2.0` 이후 Arduino 호환 API, 동적 주변장치 route, BLE, storage와 package
검증을 확장한 정식 릴리스입니다. 공개 `v0.3.0-rc.3`의 검증된 runtime payload를 그대로
stable package로 승격했습니다.

## Arduino와 주변장치

- Connector GPIO capability, `OUTPUT_OPENDRAIN`, level interrupt
- `pulseIn()`, `pulseInLong()`, `shiftIn()`, `shiftOut()`
- Zephyr-safe `noInterrupts()`/`interrupts()` GPIO callback mask
- `Serial1` UART30 route와 `end()`/`begin()` 재초기화
- 종료 상태에서 적용하는 `Wire.setPins()`와 `SPI.setPins()`
- AIN5~AIN7, ADC resolution, PWM resolution/frequency
- `tone()`/`noTone()`과 bundled Servo library
- 고정 슬롯 기반 핀·주변장치 소유권 및 handover

지원은 Variant capability와 승인된 instance에 한정됩니다. Wire는 I2C controller, SPI는 SPI00
controller 범위이며 모든 Arduino 주변장치 instance나 mode를 제공하지 않습니다.

## BLE

- GAP advertising, scanning, connection과 reconnect lifecycle
- 범용 GATT server/client의 read, write, notify와 indicate
- pairing, bonding과 SMP
- BAS, DIS와 BLE HID keyboard 예제
- 기존 NUS Peripheral/Central byte Stream

BLE Mesh, ISO, Channel Sounding, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은 범위
밖입니다. BLE HIL은 NU54DK 두 대와 Windows 11 HID 검증 범위이며 전체 OS interoperability
인증을 뜻하지 않습니다.

## Storage

- Settings/ZMS 위 1,024-byte EEPROM mirror와 명시적 `commit()`
- 전용 32 KiB LittleFS, 비파괴 `begin(false)`와 명시적 format
- reset 영속성, 손상 거부, 명시적 복구와 cleanup HIL

EEPROM CRC와 LittleFS는 암호화, secure storage, 전원 차단 원자성 또는 flash 수명 보증이
아닙니다. 중요한 데이터는 version 이동 전에 백업하십시오.

## Memory와 build

RC1/RC2의 사용하지 않던 boot reservation과 논리 696 KiB dual-slot을 기본 layout에서
제거했습니다. Loaderless application은 `0x000000..0x16c000` 1,490,944 byte를 사용하고,
LittleFS와 Settings/ZMS는 RRAM 끝의 기존 주소를 유지합니다.

Build Adapter는 generated Devicetree code partition, linker map과 Arduino maximum Sketch size가
같은지 fail-closed로 검사합니다. Standard와 BLE profile은 같은 기본 memory layout을 씁니다.

## Package와 검증

- Arduino library 8개
- 설치 예제 29/29 compile
- 독립 stable package build 두 번의 전체 산출물 byte 일치
- RC3/stable runtime payload SHA-256 일치
- 격리 Boards Manager upgrade·downgrade·uninstall 수명주기
- 설치본 Blink compile과 NU54DK CMSIS-DAP/pyOCD upload
- annotated `v0.3.0` tag와 7개 불변 Release asset

정확한 commit, hash, 실행 경계와 공개 결과는
[v0.3.0 정식 공개 기록](<../../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)에
고정합니다.
