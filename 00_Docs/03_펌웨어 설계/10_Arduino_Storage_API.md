# NU54DK Arduino Storage API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-STORAGE-001 |
| 문서 개정 | 1.1 |
| 적용 버전 | `v0.3.0` stable |
| 현재 정식 버전 | `v0.3.0` |
| 구현 | `EEPROM`, `LittleFS` bundled library |
| 검증 상태 | AC-03 host/target/package와 exact 두 보드 영속성·복구 HIL PASS |
| 최종 갱신일 | 2026-09-03 |

## 1. 목적과 지원 경계

AC-03은 NU54DK의 내부 RRAM을 Arduino 사용자가 익숙한 `EEPROM`과 `LittleFS` API로 사용하게
한다. Loader나 별도 저장 daemon은 없으며 Sketch와 facade가 하나의 Zephyr image에 정적으로
링크된다.

- EEPROM은 Zephyr Settings/ZMS의 독립 key `arduino/eeprom`을 사용한다.
- LittleFS는 Settings와 겹치지 않는 전용 32 KiB partition을 사용한다.
- 두 facade는 thread 문맥에서만 blocking storage 작업을 허용한다.
- 외부 QSPI flash, SD, secure storage, 암호화와 power-fail 보증은 이 계약에 포함하지 않는다.
- API 이름이나 compile 성공을 임의 제3자 library 전체 호환으로 확대하지 않는다.

## 2. 기본 RRAM layout

| 영역 | 시작 | 끝(미포함) | 크기 | 역할 |
| --- | ---: | ---: | ---: | --- |
| `slot0_partition` | `0x000000` | `0x16c000` | 1,490,944 byte / 1,456 KiB | Loaderless 단일 application image |
| `arduino_fs_partition` | `0x16c000` | `0x174000` | 32 KiB | Arduino LittleFS 전용 |
| `storage_partition` | `0x174000` | `0x17d000` | 36 KiB | Settings/ZMS와 EEPROM record |

기본 구성은 CPUAPP RRAM 1,524 KiB 가운데 영구 저장소 68 KiB만 끝에 남기고, 나머지
1,490,944 byte(1,456 KiB)를 하나의 application에 제공한다. Loader와 MCUboot를 포함하지 않는
현재 실행 구조에서는 사용하지 않는 boot reservation이나 대체 image slot을 기본값으로 미리
확보하지 않는다.

Arduino upload의 최대 Sketch image 크기는 `1490944` byte다. Partition 단일 원본은
`dts/nucode/nu54dk-arduino-storage.dtsi`, Arduino size 표시는 `boards.txt`다. Devicetree의
`zephyr,code-partition`, Zephyr linker의 FLASH origin/length와 Arduino 최대 크기가 같은 경계를
가리켜야 하며, package gate는 application section이 `0x16c000`을 침범하지 않는지 검사한다.

### 2.1 RC2에서 바뀐 이유

공개 `v0.3.0-rc.1`과 `v0.3.0-rc.2`는 향후 MCUboot/DFU를 예상해 boot 62 KiB와 application
slot 두 개를 선언하고 최대 Sketch 크기를 712,704 byte로 표시했다. 그러나 두 RC에는 실제
MCUboot, update 또는 rollback 경로가 없었고, application linker도 그 논리 slot 경계를 사용하지
않았다. 따라서 RC3는 loaderless 실행 계약과 실제 link 경계를 일치시키고, 사용하지 않는 두 번째
slot을 기본 구성에서 제거한다. 공개된 RC1/RC2 문서와 자산은 당시 계약을 보존하며 수정하지 않는다.

LittleFS와 Settings/ZMS의 시작 주소는 RC2와 동일하게 유지한다. RC3로 이동해도 일반 Upload가
mass erase를 하지 않는 한 이 주소의 데이터는 그대로 남을 수 있지만, 중요한 데이터는 version
변경 전에 백업하고 application이 schema와 복구 정책을 확인해야 한다.

### 2.2 고급 메모리 layout 계획

RC3가 정식 제공하는 layout은 위 loaderless 단일 application 하나다. Sketch의 전문가용
`prj.conf`와 `app.overlay` 합성 경로가 있다는 사실만으로 임의 partition을 지원한다고 선언하지
않는다. 메모리 경계를 바꾸려면 다음 항목이 하나의 선택 단위로 움직여야 한다.

1. Fixed partition의 주소와 크기
2. `zephyr,code-partition`과 linker가 실제 사용하는 FLASH 범위
3. Arduino IDE/CLI의 maximum Sketch size
4. LittleFS, Settings/ZMS와 update image의 겹침 검사
5. Upgrade/downgrade, 복구와 package 시험 matrix

`v0.6.0` M36에서 검증된 **고급 Memory layout 선택**을 설계한다. 기본 loaderless layout은 계속
유지하고, MCUboot/DFU와 signed update·rollback이 실제로 포함된 profile에서만 boot 영역과
dual-slot layout을 노출한다. Arduino Tools에는 임의 숫자 입력 대신 검증된 preset을 제공하고,
전문가 overlay는 같은 정적 검사와 linker assertion을 통과할 때만 지원 대상으로 인정한다.

## 3. EEPROM 계약

```cpp
#include <EEPROM.h>

if (EEPROM.begin(EEPROMClass::maximum_size)) {
  EEPROM.update(0, 42);
  if (!EEPROM.commit()) {
    // EEPROM.lastError()와 lastDriverError()를 확인한다.
  }
}
```

| 항목 | 계약 |
| --- | --- |
| 최대 크기 | 1024 byte |
| 초기값 | 저장 record가 없으면 요청 범위를 `0xFF`로 채움 |
| 쓰기 의미 | `write()`, `update()`, `put()`은 RAM mirror만 변경 |
| 영구 저장 | dirty mirror에 `commit()`이 성공해야 저장됨 |
| record | magic, schema version, 길이, CRC-32와 payload |
| 손상 처리 | 자동 초기화하지 않고 `EEPROMError::corrupt`로 거부 |
| 명시적 복구 | 사용자가 승인한 뒤 `reset()`으로 `0xFF` mirror를 새 record로 저장 |
| 범위 오류 | 음수 또는 열린 길이 이상의 주소는 `out_of_bounds` |
| 호출 문맥 | ISR에서 blocking 작업을 거부하고 `invalid_context` 반환 |

`commit()` 전 reset·전원 차단이 발생하면 RAM mirror 변경은 영구 저장되지 않는다. `update()`는
같은 byte를 RAM에서 다시 쓰지 않게 하지만, 실제 저장 장치 write 단위는 `commit()`의 전체
record다. EEPROM은 물리 EEPROM이나 byte 단위 전원 차단 원자성을 가장하지 않는다.

## 4. LittleFS 계약

```cpp
#include <LittleFS.h>

if (!LittleFS.begin(false)) {
  // 자동 포맷하지 않는다. 데이터 삭제를 승인한 경우에만 format()을 호출한다.
}

File file = LittleFS.open("/counter.bin", FILE_WRITE);
if (file) {
  file.write(7);
  file.flush();
  file.close();
}
```

| 항목 | 계약 |
| --- | --- |
| 저장 영역 | `arduino_fs_partition`, 32 KiB |
| 기본 mount | `LittleFS.begin(false)`, format 금지 |
| 자동 복구 선택 | `LittleFS.begin(true)`는 mount 실패 때만 명시적 format 후 재시도 |
| 명시적 복구 | `LittleFS.format()`은 기존 filesystem 데이터를 삭제 |
| 열린 파일 | 고정 slot 최대 4개, `File` 복사는 같은 handle 참조를 공유 |
| 경로 | mount 기준 절대/상대 경로, 최대 255 byte; `..` traversal 거부 |
| mode | `FILE_READ`, `FILE_WRITE`(truncate), `FILE_APPEND` |
| 제공 작업 | open/read/write/seek/flush/close, exists/remove/rename/mkdir/rmdir |
| 진단 | `FSError`와 원래 Zephyr 오류인 `lastDriverError()` |

기본 정책은 **비파괴 mount**다. Mount 실패를 곧바로 format으로 바꾸면 현장 데이터가 사라질 수
있으므로 `format()` 또는 `begin(true)`는 응용이 데이터 삭제를 승인한 뒤에만 사용한다. 열린
파일이 있으면 unmount를 거부할 수 있다.

## 5. Feature와 Arduino IDE 노출

Sketch에서 `<EEPROM.h>` 또는 `<LittleFS.h>`를 include하면 Build Adapter가 각각
`nucode.eeprom`, `nucode.littlefs` feature를 선언적으로 추가한다. 사용자는 일반적인 사용에서
`prj.conf`나 Devicetree overlay를 직접 편집하지 않는다.

| Library | Arduino 예제 | 권장 Feature set |
| --- | --- | --- |
| EEPROM | `EEPROMPersistence` | `Standard peripherals` |
| LittleFS | `LittleFSPersistence` | `Standard peripherals` |

두 예제는 `v0.3.0` stable의 29개 설치 예제에 포함된다. BLE profile에서도 build 입력은
호환되지만, 예제 메뉴의 기본 사용 안내는 storage 동작만 분리해 보는 `Standard peripherals`다.

## 6. 실패 진단

| 공개 오류 | 의미 | 기본 조치 |
| --- | --- | --- |
| `invalid_argument` | 잘못된 크기, mode 또는 경로 | 호출 인수와 path 확인 |
| `invalid_context` | ISR 등 blocking 불가 문맥 | work queue 또는 `loop()`로 이동 |
| `not_started` / `not_mounted` | begin/mount 전 사용 | 성공한 `begin()` 뒤 호출 |
| `out_of_bounds` | EEPROM 범위 밖 | `length()` 기준으로 주소 검증 |
| `corrupt` | CRC/schema 또는 filesystem 손상 | 데이터를 보존한 채 진단; 승인 후 명시적 reset/format |
| `no_space` | Settings 또는 filesystem 공간 부족 | 쓰기 빈도·파일 크기 정리 |
| `busy` | 열린 handle 또는 사용 중 자원 | 파일 close 뒤 unmount/format 재시도 |
| `driver_error` | 위 분류 밖 Zephyr 오류 | `lastDriverError()`와 전체 로그 보존 |

## 7. 검증 계약

AC-03은 다음 결과를 서로 구분한다.

1. Host contract: 고정 partition, feature resolver, API·오류·예제 metadata 검사
2. Target contract: 실제 NU54DK target용 EEPROM/LittleFS build와 negative semantic
3. Arduino package: `standard`와 `ble` profile에서 두 예제 compile
4. 두 보드 HIL: 각 보드에서 seed → reset 영속성 → EEPROM 손상 거부 → 명시적 복구 → 최종 정리
5. M22 clean-room: stable index로 설치한 package의 29개 예제 compile과 실제 upload

1~4는 exact commit `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`에서 완료됐다. 두 보드 모두
reset 3회와 최종 cleanup을 통과했으며 5는 M22 stable gate에서 완료됐다.

HIL은 EEPROM mirror와 AC-03 전용 LittleFS 시험 파일을 변경하는 파괴적 시험이다. 명시적 승인과
exact image·commit·board identity가 없으면 실행하지 않는다. 실제 PASS revision과 evidence는
[AC-03 검증 기록](<../04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>)에만 확정한다.

## 8. 명시적 범위 밖

- SD/SD_MMC, 외부 QSPI NOR와 USB mass storage
- 암호화 filesystem, secure storage와 PSA protected storage
- directory iterator와 모든 ESP/Adafruit FS 확장 함수의 완전 호환
- 파일 system 전체의 transaction/power-fail 원자성 보증
- RC3에서 임의 partition 크기를 입력하거나 사용자 overlay만으로 저장 layout을 교체하는 구성
- MCUboot/DFU dual-slot과 update/rollback — `v0.6.0` M36의 검증된 고급 layout 범위
- 제품 수명 기준의 wear/endurance 보증
