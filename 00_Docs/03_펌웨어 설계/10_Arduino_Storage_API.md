# NU54DK Arduino Storage API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-STORAGE-001 |
| 적용 후보 | `v0.3.0-rc.2` |
| 현재 정식 버전 | `v0.2.0` — 아래 API를 정식 지원으로 소급하지 않음 |
| 구현 | `EEPROM`, `LittleFS` bundled library |
| 검증 상태 | AC-03 host/target/package와 exact 두 보드 영속성·복구 HIL PASS |
| 최종 갱신일 | 2026-09-01 |

## 1. 목적과 지원 경계

AC-03은 NU54DK의 내부 RRAM을 Arduino 사용자가 익숙한 `EEPROM`과 `LittleFS` API로 사용하게
한다. Loader나 별도 저장 daemon은 없으며 Sketch와 facade가 하나의 Zephyr image에 정적으로
링크된다.

- EEPROM은 Zephyr Settings/ZMS의 독립 key `arduino/eeprom`을 사용한다.
- LittleFS는 Settings와 겹치지 않는 전용 32 KiB partition을 사용한다.
- 두 facade는 thread 문맥에서만 blocking storage 작업을 허용한다.
- 외부 QSPI flash, SD, secure storage, 암호화와 power-fail 보증은 이 계약에 포함하지 않는다.
- API 이름이나 compile 성공을 임의 제3자 library 전체 호환으로 확대하지 않는다.

## 2. 고정 RRAM layout

| 영역 | 시작 | 끝(미포함) | 크기 | 역할 |
| --- | ---: | ---: | ---: | --- |
| MCUboot 예약 | `0x000000` | `0x00f800` | 62 KiB | 향후 boot 기반과 정렬 여유 |
| `slot0_partition` | `0x010000` | `0x0be000` | 696 KiB | 현재 application image |
| `slot1_partition` | `0x0be000` | `0x16c000` | 696 KiB | 대체 image 영역 |
| `arduino_fs_partition` | `0x16c000` | `0x174000` | 32 KiB | Arduino LittleFS 전용 |
| `storage_partition` | `0x174000` | `0x17d000` | 36 KiB | Settings/ZMS와 EEPROM record |

Arduino upload의 최대 Sketch image 크기는 `712704` byte(696 KiB)다. Partition 단일 원본은
`dts/nucode/nu54dk-arduino-storage.dtsi`, Arduino size 표시는 `boards.txt`다. 이 경계를
바꾸면 EEPROM/LittleFS, Settings, 향후 boot/DFU migration과 package validation을 함께
재검증해야 한다.

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

두 예제는 `v0.3.0-rc.2` 후보의 29개 설치 예제에 포함된다. BLE profile에서도 build 입력은
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
5. M22 clean-room: 공개 RC index로 설치한 package의 29개 예제 compile과 실제 upload

1~4는 exact commit `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`에서 완료됐다. 두 보드 모두
reset 3회와 최종 cleanup을 통과했으며 5는 M22 public RC gate다.

HIL은 EEPROM mirror와 AC-03 전용 LittleFS 시험 파일을 변경하는 파괴적 시험이다. 명시적 승인과
exact image·commit·board identity가 없으면 실행하지 않는다. 실제 PASS revision과 evidence는
[AC-03 검증 기록](<../04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>)에만 확정한다.

## 8. 명시적 범위 밖

- SD/SD_MMC, 외부 QSPI NOR와 USB mass storage
- 암호화 filesystem, secure storage와 PSA protected storage
- directory iterator와 모든 ESP/Adafruit FS 확장 함수의 완전 호환
- 파일 system 전체의 transaction/power-fail 원자성 보증
- 임의 partition 변경 또는 사용자 overlay를 통한 저장 layout 교체
- 제품 수명 기준의 wear/endurance 보증
