# AC-03 Storage와 Library 호환성 기준선

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-AC03-001 |
| 대상 | `v0.3.0` AC-03 |
| 판정 | **완료 — 구현·host/target/package와 exact 두 보드 physical HIL PASS** |
| 구현 기준 source | `a56dc9d9c5d19db166dd453265067a68080923e6` |
| 최종 검증 source | `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb` |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 기준 SDK | NCS v3.4.0 / Zephyr 4.4.0 |
| Evidence | `build/ac03/hil/ac03-0b7f89283cd8.evidence.json` |
| Evidence SHA-256 | `ECB45D87E1C5A765461D4413571473C34AE429297295D42467B0E429BE9E55B4` |
| 검증일 | 2026-09-01 |

## 1. 판정 경계

AC-03은 EEPROM과 내부 LittleFS facade, fixed partition, profile feature, Arduino 예제, host/target
contract와 두 보드 HIL runner를 구현했다. Exact build/HIL 안전성 교정과 실기 실행을 끝냈으며
다음 결과를 구분한다.

- Storage production source와 package metadata: **구현됨**
- Host contract, target contract/HIL image build와 profile smoke: **PASS**
- 두 NU54DK reset 영속성·손상 복구 HIL: **PASS — 각 보드 reset 3회와 cleanup 확인**
- AC-03 전체 완료: **완료**
- `v0.3.0` stable 지원 선언: **아님 — M22 RC/stable gate 대기**

Parser, build 또는 준비된 token만으로 reset persistence와 storage recovery PASS를 만들지 않는다.

## 2. 고정 storage layout

| 영역 | 시작 | 크기 | 계약 |
| --- | ---: | ---: | --- |
| slot 0 | `0x010000` | 696 KiB | Application image, maximum 712704 byte |
| slot 1 | `0x0be000` | 696 KiB | 대체 image 영역 |
| Arduino LittleFS | `0x16c000` | 32 KiB | `arduino_fs_partition` 전용 |
| Settings/ZMS | `0x174000` | 36 KiB | 기존 Settings와 `arduino/eeprom` record |

LittleFS 끝과 Settings 시작은 `0x174000`, Settings 끝은 CPUAPP RRAM 끝 `0x17d000`과 일치한다.
Host와 target contract는 주소·크기·overlap, slot 크기와 `boards.txt` maximum size를 함께 검사한다.

## 3. EEPROM 기준선

- 최대 1024-byte 고정 RAM mirror
- Size 1..1024의 `begin()`
- `read/write/update`, proxy/iterator, trivially-copyable `get/put`
- `write/update/put`은 RAM만 변경하고 `commit()`이 성공해야 영구 저장
- Magic/schema/길이/CRC-32가 있는 Settings/ZMS record
- 잘못된 주소, ISR 문맥, 공간 부족, driver 오류와 손상 record의 안정 오류 분류
- 손상 record는 자동 초기화하지 않고 명시적 `reset()`으로만 복구

`reset()`은 데이터를 삭제하는 파괴적 API다. CRC는 손상 검출이며 암호화나 power-fail 인증이 아니다.

## 4. LittleFS 기준선

- 전용 32 KiB mapped partition
- `begin(false)`의 비파괴 mount와 `FS_MOUNT_FLAG_NO_FORMAT`
- 사용자 승인 선택인 `begin(true)`와 명시적 `format()`
- 최대 4개 고정 File slot과 generation 보호
- Stream read/write/peek, seek/position/size, flush/close
- exists/remove/rename/mkdir/rmdir
- 255-byte 경로 제한과 `..` traversal 거부
- mount/handle/busy/no-space/corruption/driver 오류 분류

Filesystem facade는 SD, 외부 flash, secure storage 또는 모든 ESP FS 확장을 지원으로 합성하지 않는다.

## 5. Package와 예제

현재 RC 후보는 8개 bundled library와 Arduino 예제 29개를 가진다.

| 분류 | 수 | AC-03 추가 |
| --- | ---: | --- |
| Standard | 22 | EEPROMPersistence, LittleFSPersistence |
| BLE | 7 | 없음 |
| 합계 | 29 | 2 |

`EEPROM`과 `LittleFS`는 각각 `nucode.eeprom`, `nucode.littlefs` feature로 resolve되며
`standard`·`ble` profile에서 선언형 conf를 추가한다. 일반 사용자는 `prj.conf`나 overlay를
직접 작성하지 않는다.

## 6. 자동 검증 계약

| 계층 | 입력 | 완료 조건 |
| --- | --- | --- |
| Host | `test_ac03_storage_contract.py`, profile/package tests | Layout, API, 오류, feature, 29개 example 집합 PASS |
| HIL runner | `test_ac03_storage.py` 12/12 PASS | 완전 line, 순서·nonce·trailing token, exact source/build/evidence와 failure cleanup |
| Target | `ac03_storage_contract`, `ac03_hil` | Fixed partition contract와 HIL image pristine build PASS |
| Arduino CLI | AC-03 smoke | EEPROM standard, LittleFS standard/ble compile PASS |
| M22 package | 설치 archive | 8개 library·29개 예제 전체 compile PASS |

M12 host gate도 runner 보강 뒤 전체 PASS했다. 최종 physical HIL은 exact Core commit
`0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`에서 수행했으며 evidence hash는 이 문서 상단과
아래 결과 표에 고정한다.

## 7. 두 보드 HIL 계약

같은 exact `ac03_hil` image를 서로 다른 NU54DK 두 대에 순차 기록한다. 각 보드는 다음 상태를
모두 통과해야 한다.

1. 명시적 CLEAR와 reset 뒤 idle 확인
2. EEPROM commit, LittleFS non-format mount 실패와 명시적 format·seed
3. Reset 뒤 EEPROM/LittleFS 값 영속성
4. EEPROM record 손상 주입
5. 손상 자동 수용 거부, 명시적 EEPROM reset·commit 복구
6. LittleFS isolation과 path traversal 거부
7. Reset 뒤 복구 값·filesystem 유지
8. 시험 파일 제거와 EEPROM 최종 reset

Runner는 `--allow-destructive-storage`, 서로 다른 board UID 두 개, exact build record/source digest와
새 evidence path를 요구한다. 실제 UID는 공개 문서에서 redaction한다. 실패 때 사용자 data가
원상 복구된다고 보증하지 않으며 실패 evidence와 log를 먼저 보존한다.

## 8. 최종 물리 결과와 후속 gate

| 항목 | 결과 |
| --- | --- |
| Exact Core / board | `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb` / `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Board 1 | reset 3회, EEPROM/LittleFS 영속성·손상 거부·명시적 복구·최종 cleanup PASS |
| Board 2 | reset 3회, EEPROM/LittleFS 영속성·손상 거부·명시적 복구·최종 cleanup PASS |
| Evidence | `build/ac03/hil/ac03-0b7f89283cd8.evidence.json` |
| SHA-256 | `ECB45D87E1C5A765461D4413571473C34AE429297295D42467B0E429BE9E55B4` |

AC-03의 완료 gate는 닫혔다. 남은 통합 작업은 29개 설치 예제 package compile, 지정 UID Upload와
동일 PC public clean-room 결과를 M22에 연결하는 것이다.

## 9. 관련 문서

- [Arduino Storage API](<../03_펌웨어 설계/10_Arduino_Storage_API.md>)
- [v0.3.0 구현 마일스톤](<../01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)
- [테스트와 검증](<../03_펌웨어 설계/04_테스트와_검증.md>)
- [M22 RC1 기준선](29_M22_v0.3.0_rc1_통합_릴리스_기준선.md)
