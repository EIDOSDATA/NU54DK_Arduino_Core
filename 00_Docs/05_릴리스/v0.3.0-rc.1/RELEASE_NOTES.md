# NU54DK Arduino Core v0.3.0-rc.1 릴리스 노트

> **Release Candidate입니다.** 현재 stable은 `v0.2.0`입니다. AC-02B·AC-03 physical HIL은
> 완료됐지만 package·public clean-room은 M22에서 별도로 검증하므로 알려진 제약을 확인하십시오.

## 주요 변경

### Arduino Core와 주변장치 호환 폭

- connector GPIO와 open-drain, level interrupt, `pulseIn()`/`pulseInLong()`,
  `shiftIn()`/`shiftOut()` 및 안전한 Arduino callback mask
- 고정 자원 소유권 manager와 runtime peripheral handover
- `Serial1`, 종료 상태의 `Wire.setPins()`와 `SPI.setPins()`
- AIN channel·ADC resolution, 동적 PWM resolution/frequency
- `tone()`/`noTone()`과 bundled Servo

AC-02B는 exact commit `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`의 3-wire fixture에서
Serial1, BQ25186 Wire, local SPI, ADC raw 0/3757과 A0 PWM 25%·75%를 통과했습니다. 이 결과를
다른 pin, 계측 정확도 또는 미지원 bus instance의 PASS로 확대하지 않습니다.

### Storage

- 1024-byte `EEPROM` facade
  - byte/proxy/iterator, `get()`/`put()`, `update()`
  - RAM mirror와 명시적 `commit()`
  - schema/길이/CRC-32가 있는 Settings/ZMS record
  - 손상 record 거부와 사용자 승인 기반 `reset()`
- 전용 32 KiB `LittleFS`
  - 비파괴 `begin(false)`가 기본
  - 명시적 `format()` 또는 선택적 `begin(true)`
  - `File` Stream, open/read/write/append/seek/flush/close
  - exists/remove/rename/mkdir/rmdir와 경로 traversal 거부
- `EEPROMPersistence`, `LittleFSPersistence` Arduino 예제

### BLE

- BLE Core/GAP advertising, scanning과 connection lifecycle
- 범용 GATT server/client, read/write/notify/indicate
- pairing, bonding, SMP
- BAS, DIS와 BLE HID keyboard 예제

M19~M21의 실제 검증 범위와 Windows HID 수동 확인은 기존 검증 기록을 따릅니다. BLE Mesh,
802.15.4/OpenThread/Matter 및 multiprotocol은 이 RC의 정식 지원 범위가 아닙니다.

## Package와 예제

| Profile | 예제 수 | 포함 범위 |
| --- | ---: | --- |
| `Standard peripherals` | 22 | NU54DK 17, Wire 1, SPI 1, Servo 1, EEPROM 1, LittleFS 1 |
| BLE profile | 7 | NUCODE BLE 6, NUCODE BLE Security 1 |
| 합계 | 29 | Arduino IDE의 bundled library 예제 |

## RRAM layout 변경

| Partition | 범위 | 크기 |
| --- | --- | ---: |
| slot 0 | `0x010000..0x0be000` | 696 KiB |
| slot 1 | `0x0be000..0x16c000` | 696 KiB |
| Arduino LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

Maximum Sketch size는 712704 byte입니다. `v0.2.0` image에서 RC로 Upload하면 application
partition 경계와 storage 사용법이 달라질 수 있으므로 중요한 데이터를 먼저 백업하고
[Migration](./MIGRATION.md)을 확인하십시오.

## 배포 방식

- Public prerelease tag: `v0.3.0-rc.1`
- 별도 RC Boards Manager index
- 두 번 독립 생성한 7개 공개 자산의 byte 재현성 검사
- 설치본 29개 예제 compile, 지정 CMSIS-DAP Upload 및 동일 PC 격리 clean-room gate
- Stable index와 `v0.2.0` 자산 불변 검사

실제 공개 여부와 PASS 범위는 [M22 검증 기록](<../../04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)을
기준으로 합니다.
