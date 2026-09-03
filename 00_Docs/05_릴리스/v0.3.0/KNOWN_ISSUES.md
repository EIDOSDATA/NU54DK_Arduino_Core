# NU54DK Arduino Core v0.3.0 알려진 제약

이 문서는 `v0.3.0`의 API 이름이나 compile 결과를 실제 검증 범위보다 넓게 해석하지 않기 위한
지원 경계입니다.

## Firmware, memory와 Upload

- Loader, LLEXT, UF2, OTA와 Sketch-only hot swap을 제공하지 않습니다.
- Sketch마다 전체 Zephyr image를 compile, link하고 flash합니다.
- 기본 loaderless application 최대 크기는 1,490,944 byte입니다.
- MCUboot/DFU dual-slot, signed update와 rollback은 이 버전에 없습니다.
- 임의 partition override는 정식 지원하지 않습니다.
- 기본 Upload는 CMSIS-DAP V2 + pyOCD입니다. 여러 probe에서는 UID를 명시해야 합니다.
- 일반 Upload는 mass erase 또는 recover를 자동 실행하지 않습니다.

## GPIO와 주변장치

- Variant capability에 없는 pin과 P2 interrupt는 지원하지 않습니다.
- 기본 `Serial`은 115200 8N1 Zephyr console wrapper이며 baud/pin hardware를 소유하지 않습니다.
- `Serial1` TX는 polling 방식이며 승인된 UART30 route에 한정됩니다.
- `noInterrupts()`/`interrupts()`는 Arduino GPIO callback을 마스킹하며 모든 system IRQ를
  전역 차단하지 않습니다.
- Wire target/slave, `requestFrom(..., false)`, `Wire1`과 자동 bus arbitration은 미지원입니다.
- `SPI1`, SPI peripheral mode와 SPI peripheral `attachInterrupt()`는 미지원입니다.
- ADC는 raw code이며 전압 정확도·선형성 calibration을 제품 보증하지 않습니다.
- PWM, tone과 Servo는 공유 hardware, period와 pin ownership 충돌을 거부할 수 있습니다.
- Servo motor 전원은 GPIO에서 공급하지 마십시오.

## Storage

- EEPROM은 1,024-byte RAM mirror이며 `commit()` 전 변경은 reset 때 사라집니다.
- 손상된 EEPROM record는 자동 초기화하지 않습니다. `reset()`은 데이터 삭제 작업입니다.
- LittleFS는 내부 전용 32 KiB이며 SD, QSPI 또는 외부 flash를 대신하지 않습니다.
- `LittleFS.format()`과 `begin(true)`는 기존 filesystem 내용을 삭제할 수 있습니다.
- 열린 file은 최대 4개이며 모든 ESP/Adafruit FS 확장을 제공하지 않습니다.
- Storage API는 ISR에서 사용하지 않습니다.
- 암호화, secure storage, 전원 차단 원자성 또는 flash 수명 보증을 제공하지 않습니다.

## BLE

- BLE 결과는 NU54DK 간 HIL과 Windows 11 HID 시험 범위에 한정됩니다.
- BLE Mesh, ISO, Channel Sounding, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은
  지원하지 않습니다.
- HID 예제는 OS pairing UI와 실제 입력을 사람이 확인해야 합니다.
- Pairing/bonding API는 Bluetooth qualification, 보안 인증 또는 모든 OS interoperability를
  뜻하지 않습니다.

## Board/System과 PMIC

- `NU54DK.coreVersion()`은 이 release에서도 역사적 문자열 `0.2.0-dev`를 반환합니다. 배포
  identity는 Boards Manager 설치 version과 release manifest를 기준으로 확인하십시오.
- PMIC write는 매 boot RAM-only 승인과 register policy 확인이 필요합니다.
- 배터리 충전·온도 보호의 전기 HIL은 사용자의 실제 전원·배터리 조건에서 수행해야 합니다.
- Active SWD/debugger는 System OFF와 reset cause를 방해할 수 있습니다.
- Thread, Matter와 IEEE 802.15.4 과거 build feasibility는 사용자 runtime 지원 선언이 아닙니다.
- Windows 이외의 package 설치는 공식 검증 대상이 아닙니다.

## 버전 지원

신규 수정과 문제 재현은 `v0.3.0`만 대상으로 합니다. `v0.1.0`, `v0.2.0`과 모든 RC는
역사적·비지원 상태지만, 공개 tag와 자산은 감사 및 downgrade를 위해 불변으로 보존합니다.
