# NU54DK Arduino Core v0.3.0-rc.2 알려진 제약

> 이 문서는 RC2의 공개 기능 이름을 실제 검증보다 넓게 해석하지 않기 위한 경계입니다.

## 1. RC와 검증 상태

- 현재 stable은 `v0.2.0`입니다. `v0.3.0-rc.2`는 production stable이 아닙니다.
- RC2는 Public Prerelease로 공개됐고 exact Core commit, tag, 자산과 final evidence를 고정했습니다.
- RC1의 local fixed gate PASS를 RC2 PASS로 상속하지 않습니다.
- RC1 public clean-room 실패는 tagged release harness가 Nordic 설치 leaf를 먼저 만든 문제입니다.
  일반 Arduino package의 firmware/API 결함으로 판정된 것은 아닙니다.
- RC2 설치, 29개 예제 compile, 실제 pyOCD Upload와 public clean-room lifecycle·cleanup을
  M22 RC2 evidence로 PASS 판정했습니다.

## 2. Firmware와 Upload

- Loader, LLEXT, UF2, OTA와 Sketch-only hot swap을 제공하지 않습니다.
- Sketch마다 전체 Zephyr image를 compile, link하고 flash합니다.
- 기본 Upload는 CMSIS-DAP V2 + pyOCD입니다. 여러 probe에서는 명시적 UID 경로를 사용합니다.
- 일반 Upload는 mass erase 또는 recover를 자동 실행하지 않습니다.
- native USB CDC/HID는 제공하지 않습니다. BLE HID와 USB HID를 혼동하면 안 됩니다.

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

## 4. Storage

- EEPROM은 1024-byte RAM mirror입니다. `commit()` 전 변경은 reset 또는 전원 차단 때
  사라집니다.
- EEPROM record 손상은 자동 초기화하지 않습니다. `reset()`은 데이터 삭제 작업입니다.
- LittleFS는 내부 전용 32 KiB이며 SD, QSPI 또는 외부 flash를 대신하지 않습니다.
- `LittleFS.format()`과 `begin(true)`는 기존 filesystem 내용을 삭제할 수 있습니다.
- 열린 file은 최대 4개입니다. 모든 ESP/Adafruit FS 확장 함수와 directory iterator를 제공하지
  않습니다.
- Storage API는 ISR에서 사용하지 않습니다.
- EEPROM CRC와 LittleFS를 암호화, secure storage, 전원 차단 원자성 또는 수명 보증으로 해석하지
  않습니다.
- RC partition layout을 임의 overlay로 바꾸는 구성은 지원하지 않습니다.

## 5. BLE

- M19~M21 기능은 NU54DK 간 HIL과 Windows HID 검증 범위에 한정됩니다.
- BLE Mesh, ISO, Channel Sounding, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은 범위
  밖입니다.
- BLE HID 예제는 Windows Bluetooth UI의 pairing과 실제 입력을 사람이 확인해야 합니다.
- Pairing과 bonding API가 Bluetooth qualification, 보안 인증 또는 모든 OS interoperability를
  뜻하지 않습니다.

## 6. Board/System과 PMIC

- PMIC write는 매 boot RAM-only 승인과 register policy 확인이 필요합니다.
- 충전 전압·전류, recharge, SYS regulation, ship/shutdown과 실제 배터리 온도 보호의 전기
  검증은 사용자 배터리·전원 조건에서 별도로 수행해야 합니다.
- Active SWD/debugger는 System OFF와 reset cause를 방해할 수 있습니다.

## 7. 설치와 Release 경계

- RC2 index URL과 7개 자산은 Public Prerelease에 공개돼 있습니다.
- 첫 Nordic prerequisite 설치는 크고 오래 걸릴 수 있습니다.
- Core uninstall은 공유 NCS와 Toolchain을 자동 삭제하지 않습니다.
- RC1 tag와 자산은 RC2로 덮어쓰지 않으며, RC2도 공개 뒤 immutable artifact로 취급합니다.
- Stable index는 계속 `v0.2.0`과 `v0.1.0`만 제공하며 RC2 공개·검증 과정에서 변경하지 않았습니다.

## 8. 장기 기능

- IEEE 802.15.4, OpenThread와 Matter는 과거 build feasibility 결과만 있으며 이 RC의 사용자
  지원이 아닙니다.
- MCUboot/DFU, TF-M/secure storage, external flash와 radio coexistence는 후속 버전 범위입니다.
- NUCODE sensor wrapper를 제공하지 않으며 외부 sensor library compile을 runtime 지원으로
  확대하지 않습니다.
