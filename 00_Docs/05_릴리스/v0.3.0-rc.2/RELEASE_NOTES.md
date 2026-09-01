# NU54DK Arduino Core v0.3.0-rc.2 릴리스 노트

> **공개 전 Release Candidate 문서입니다.** 현재 stable은 `v0.2.0`입니다. RC2 tag와
> 공개 자산, public clean-room과 final evidence는 아직 생성되지 않았습니다.

## RC2 교정 목적

RC1 public clean-room은 release harness가 Nordic SDK와 Toolchain 설치 대상 leaf를 먼저
생성해 `nrfutil sdk-manager`가 기존 directory를 거부하면서 중단됐습니다. RC2는 installer가
해당 leaf를 직접 생성하도록 clean-room layout 준비 범위를 교정하고, 이를 host 회귀로 고정한 뒤
전체 M22 gate를 새 identity로 다시 실행합니다.

- RC1 tag와 7개 공개 자산은 변경하지 않습니다.
- RC1 실패 evidence는 삭제하거나 RC2 PASS로 이름을 바꾸지 않습니다.
- RC2 package의 runtime payload가 RC1과 같다는 주장은 실제 manifest와 SHA-256 비교 전에는
  하지 않습니다.
- 일반 Arduino 설치 package의 firmware/API 결함이 확인됐다고 확대 해석하지 않습니다.

## 이어받는 기능 후보

### Arduino Core와 주변장치 호환 폭

- connector GPIO와 open-drain, level interrupt, `pulseIn()`/`pulseInLong()`
- `shiftIn()`/`shiftOut()`과 안전한 Arduino callback mask
- 고정 자원 소유권 manager와 runtime peripheral handover
- `Serial1`, 종료 상태의 `Wire.setPins()`와 `SPI.setPins()`
- AIN channel·ADC resolution과 동적 PWM resolution/frequency
- `tone()`/`noTone()`과 bundled Servo

이 기능의 선행 exact-commit HIL은 기존 검증 기록에 보존합니다. RC2 archive 설치본의 전체
compile과 Upload 결과는 M22 RC2 gate가 별도로 생성해야 합니다.

### Storage

- 1024-byte `EEPROM` facade
  - byte/proxy/iterator, `get()`/`put()`, `update()`
  - RAM mirror와 명시적 `commit()`
  - schema, 길이와 CRC-32가 있는 Settings/ZMS record
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
- pairing, bonding과 SMP
- BAS, DIS와 BLE HID keyboard 예제

BLE Mesh, IEEE 802.15.4, OpenThread, Matter와 multiprotocol은 이 RC의 정식 지원 범위가
아닙니다. Windows HID는 OS UI와 실제 입력을 사람이 확인하는 단계가 남습니다.

## Package와 예제

| Profile | 예제 수 | 포함 범위 |
| --- | ---: | --- |
| `Standard peripherals` | 22 | NU54DK 17, Wire 1, SPI 1, Servo 1, EEPROM 1, LittleFS 1 |
| BLE profile | 7 | NUCODE BLE 6, NUCODE BLE Security 1 |
| 합계 | 29 | Arduino IDE bundled library 예제 |

위 수는 RC2 package lock과 실제 archive가 일치하고 설치본 29/29 compile gate가 끝나야 검증
결과가 됩니다. 문서에 나열됐다는 사실만으로 PASS를 선언하지 않습니다.

## RRAM layout 후보

| Partition | 범위 | 크기 |
| --- | --- | ---: |
| slot 0 | `0x010000..0x0be000` | 696 KiB |
| slot 1 | `0x0be000..0x16c000` | 696 KiB |
| Arduino LittleFS | `0x16c000..0x174000` | 32 KiB |
| Settings/ZMS | `0x174000..0x17d000` | 36 KiB |

Maximum Sketch size 후보는 712704 byte입니다. Stable `v0.2.0`에서 RC2 image로 이동하면
application partition 경계와 storage 사용법이 달라질 수 있으므로 중요한 데이터를 먼저
백업하고 [Migration](./MIGRATION.md)을 확인하십시오.

## 배포 예정 방식

- 새 Public prerelease tag: `v0.3.0-rc.2`
- 해당 tag에 묶인 별도 RC Boards Manager index
- 두 번 독립 생성해 byte 재현성을 확인한 정확히 7개 공개 자산
- 설치본 29개 예제 compile과 지정 CMSIS-DAP Upload
- 공개 URL 기반 동일 PC 격리 clean-room 수명주기
- Stable index와 `v0.2.0` 자산 불변 검사

실제 공개와 PASS 범위는 [M22 RC2 검증 기록](<../../04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)에
실행 증거가 추가된 뒤에만 확정합니다.
