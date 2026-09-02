# NU54DK Arduino Core v0.3.0-rc.3 릴리스 노트

> **Release Candidate 문서입니다.** 현재 production stable은 `v0.2.0`입니다.

## RC3 교정 목적

RC1과 RC2는 향후 MCUboot/DFU를 예상해 boot 영역과 696 KiB application slot 두 개를
Devicetree에 선언하고 Arduino maximum Sketch size를 712,704 byte로 표시했습니다. 그러나 해당
RC에는 실제 MCUboot, update 또는 rollback 경로가 없었고 Zephyr linker도 선언한 slot 0을
application FLASH 경계로 사용하지 않았습니다.

RC3는 이 불일치를 다음처럼 교정합니다.

- Loaderless application을 reset vector `0x000000`에서 시작
- LittleFS와 Settings/ZMS 직전 `0x16c000`까지 1,490,944 byte(1,456 KiB) 제공
- 사용하지 않는 boot reservation과 slot 1을 기본 layout에서 제거
- `CONFIG_USE_DT_CODE_PARTITION=y`로 Devicetree code partition을 linker 경계에 연결
- Build Adapter가 generated DTS와 linker map의 origin/size 불일치를 fail-closed로 거부
- 시작 주소가 0인 mapped partition에서도 pyOCD가 존재하지 않는 legacy
  `CONFIG_FLASH_LOAD_OFFSET`을 조회하지 않도록 absolute-address HEX upload 경로를 고정
- Arduino maximum Sketch size를 `1490944` byte로 일치

공개 RC1/RC2 tag, archive와 당시 문서는 변경하지 않습니다. 이 변경은 같은 RC2 자산을
덮어쓰는 수정이 아니라 새 RC3 identity입니다.

## RRAM layout

| 영역 | 범위 | 크기 |
| --- | --- | ---: |
| Loaderless application | `0x000000..0x16c000` | 1,490,944 byte / 1,456 KiB |
| Arduino LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

CPUAPP RRAM 1,524 KiB 가운데 영구 저장소 68 KiB를 제외한 전체를 기본 application이 사용합니다.
LittleFS와 Settings/ZMS 주소는 RC2와 동일합니다. 일반 Upload가 mass erase를 하지 않아도
version 전환 전에는 중요한 데이터를 백업해야 합니다.

RC3가 제공하는 layout은 위 기본값 하나입니다. MCUboot/DFU dual-slot과 signed update·rollback은
`v0.4.0` M24에서 검증된 고급 Memory layout preset으로 제공할 계획입니다. 임의 byte 입력 또는
Sketch overlay만으로 partition을 바꾸는 경로는 RC3 정식 지원 범위가 아닙니다.

## 이어받은 Arduino 기능

### Core와 주변장치

- Connector GPIO, open-drain, level interrupt와 `pulseIn()`/`pulseInLong()`
- `shiftIn()`/`shiftOut()`과 Zephyr-safe callback mask
- 고정 자원 소유권 manager와 runtime peripheral handover
- `Serial1`, 종료 상태 `Wire.setPins()`와 `SPI.setPins()`
- AIN channel·ADC resolution과 동적 PWM resolution/frequency
- `tone()`/`noTone()`과 bundled Servo

선행 AC-02B exact `0b7f892` 3-wire HIL에서 다음을 확인했습니다.

| 경로 | 실기 결과 |
| --- | --- |
| UART | `Serial1` UART30의 CMSIS-DAP 보조 VCOM 송수신, `end()`/`rebegin()` PASS |
| I2C | `Wire` I2C22로 BQ25186 `0x6A`의 `0x0C == 0x41` read-only 확인, 100/400 kHz repeated-start와 `end()`/`rebegin()` PASS |
| SPI | DUT P2.2↔P2.4 4 MHz local loopback PASS |
| ADC/PWM | A0/P1.12 raw 0/3757 뒤 같은 pin을 PWM20으로 넘겨 25%·75% capture PASS |

I2C 결과는 Wire controller 경로의 검증이며 target/slave mode나 모든 외부 sensor 호환을 뜻하지
않습니다. UART 결과도 승인된 UART30 route와 보조 VCOM 조건에 한정합니다.

### Storage

- Settings/ZMS 위 1024-byte `EEPROM` facade와 명시적 `commit()`
- 전용 32 KiB `LittleFS`, 비파괴 `begin(false)`와 명시적 format
- `EEPROMPersistence`, `LittleFSPersistence` 예제
- 선행 exact 두 보드 HIL의 reset 영속성, 손상 거부, 명시적 복구와 cleanup PASS

### BLE

- BLE Core/GAP advertising, scanning과 connection lifecycle
- 범용 GATT server/client, read/write/notify/indicate
- Pairing, bonding과 SMP
- BAS, DIS와 BLE HID keyboard 예제

BLE Mesh, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은 이 RC의 지원 범위가 아닙니다.

## Package와 예제

| Profile | 예제 수 | 포함 범위 |
| --- | ---: | --- |
| `Standard peripherals` | 22 | NU54DK 17, Wire 1, SPI 1, Servo 1, EEPROM 1, LittleFS 1 |
| BLE profile | 7 | NUCODE BLE 6, NUCODE BLE Security 1 |
| 합계 | 29 | Arduino IDE bundled library 예제 |

RC3 exact archive의 재현성, 설치본 29/29 compile, 실제 Upload와 공개 URL clean-room 결과는
RC3 공개 검증 기록에서 확정합니다. Build-only나 선행 RC evidence를 새 package PASS로 확대하지
않습니다.
