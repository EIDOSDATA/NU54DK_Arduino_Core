# NU54DK Arduino Core v0.3.0-rc.3 알려진 제약

> 이 문서는 RC3의 공개 기능을 실제 검증보다 넓게 해석하지 않기 위한 경계입니다.

## 1. RC와 Release 상태

- 현재 stable은 `v0.2.0`입니다. `v0.3.0-rc.3`는 production stable이 아닙니다.
- RC1과 RC2의 tag·자산은 역사적으로 고정돼 있으며 RC3 byte로 교체하지 않습니다.
- RC3의 고정 gate와 공개 설치본 29/29 compile은 통과했습니다. clean-room Upload 중 사용자
  reset으로 자동 lifecycle tail은 미실행이며 stable 공개 전 별도 lifecycle에서 판정합니다.
- RC3 검증 완료도 자동으로 `v0.3.0` stable 공개를 뜻하지 않습니다.

## 2. Firmware, memory와 Upload

- Loader, LLEXT, UF2, OTA와 Sketch-only hot swap을 제공하지 않습니다.
- Sketch마다 전체 Zephyr image를 compile, link하고 flash합니다.
- 기본 loaderless application 최대 크기는 1,490,944 byte(1,456 KiB)입니다.
- LittleFS 32 KiB와 Settings/ZMS 36 KiB는 application 범위 밖 RRAM 끝에 유지됩니다.
- RC3에는 사용자가 임의 slot 크기를 입력하는 Tools 메뉴가 없습니다.
- Sketch `app.overlay`가 병합되더라도 code partition, linker, Arduino maximum size와 storage
  migration을 함께 검증하지 않은 layout은 지원하지 않습니다.
- MCUboot/DFU dual-slot과 signed update·rollback은 `v0.4.0` M24 범위입니다.
- 기본 Upload는 CMSIS-DAP V2 + pyOCD이며 여러 probe에서는 명시적 UID 경로를 사용합니다.
- 일반 Upload는 mass erase 또는 recover를 자동 실행하지 않습니다.

## 3. GPIO와 주변장치

- Variant capability에 없는 pin과 P2 interrupt를 지원으로 합성하지 않습니다.
- 기본 `Serial`은 115200 8N1 Zephyr console wrapper이며 baud/pin hardware를 소유하지 않습니다.
- `Serial1` TX는 polling 의미 차이를 유지합니다.
- Wire target/slave, `requestFrom(..., false)`, `Wire1`과 자동 bus arbitration은 미지원입니다.
- `SPI1`과 SPI peripheral mode는 미지원입니다.
- ADC는 raw code이며 전압 정확도·선형성 calibration을 제품 보증하지 않습니다.
- PWM, tone과 Servo는 공유 hardware, period와 pin ownership 충돌을 fail-closed로 거부할 수
  있습니다.
- Servo motor 전원은 GPIO에서 공급하지 말고 적합한 외부 전원과 공통 GND를 사용합니다.

선행 UART/I2C HIL은 `Serial1`의 승인된 UART30 보조 VCOM route와 온보드 BQ25186 read-only
경로를 검증한 결과입니다. 임의 UART pin, Wire target mode, 모든 외부 sensor와 전기 조건의
제품 인증으로 확대하지 않습니다.

## 4. Storage

- EEPROM은 1024-byte RAM mirror이며 `commit()` 전 변경은 reset 또는 전원 차단 때 사라집니다.
- EEPROM record 손상은 자동 초기화하지 않습니다. `reset()`은 데이터 삭제 작업입니다.
- LittleFS는 내부 전용 32 KiB이며 SD, QSPI 또는 외부 flash를 대신하지 않습니다.
- `LittleFS.format()`과 `begin(true)`는 기존 filesystem 내용을 삭제할 수 있습니다.
- 열린 file은 최대 4개입니다. 모든 ESP/Adafruit FS 확장과 directory iterator를 제공하지 않습니다.
- Storage API는 ISR에서 사용하지 않습니다.
- EEPROM CRC와 LittleFS는 암호화, secure storage, 전원 차단 원자성 또는 수명 보증이 아닙니다.

## 5. BLE

- M19~M21 기능은 NU54DK 간 HIL과 Windows HID 검증 범위에 한정됩니다.
- BLE Mesh, ISO, Channel Sounding, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은 범위
  밖입니다.
- BLE HID 예제는 Windows Bluetooth UI의 pairing과 실제 입력을 사람이 확인해야 합니다.
- Pairing과 bonding API는 Bluetooth qualification, 보안 인증 또는 모든 OS interoperability를
  뜻하지 않습니다.

## 6. Board/System과 PMIC

- PMIC write는 매 boot RAM-only 승인과 register policy 확인이 필요합니다.
- 충전 전압·전류, recharge, SYS regulation, ship/shutdown과 실제 배터리 온도 보호의 전기
  검증은 사용자 배터리·전원 조건에서 별도로 수행해야 합니다.
- Active SWD/debugger는 System OFF와 reset cause를 방해할 수 있습니다.

## 7. 설치와 장기 기능

- 첫 Nordic prerequisite 설치는 크고 오래 걸릴 수 있습니다.
- Core uninstall은 공유 NCS와 Toolchain을 자동 삭제하지 않습니다.
- IEEE 802.15.4, OpenThread와 Matter는 과거 build feasibility 결과만 있으며 RC3 사용자
  지원이 아닙니다.
- NUCODE sensor wrapper를 제공하지 않으며 외부 sensor library compile을 runtime 지원으로
  확대하지 않습니다.
