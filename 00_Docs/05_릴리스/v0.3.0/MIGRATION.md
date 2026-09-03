# NU54DK Arduino Core v0.3.0 마이그레이션

## v0.2.0 또는 RC에서 이동

1. Sketch와 EEPROM, Settings/ZMS, LittleFS의 중요한 데이터를 백업합니다.
2. Additional Boards Manager URLs에는 stable URL만 남깁니다.
3. Boards Manager index를 갱신하고 `nucode:zephyr@0.3.0`을 설치합니다.
4. Arduino IDE를 다시 시작해 Board, Feature set과 Upload probe를 확인합니다.
5. Blink를 clean compile·upload합니다.
6. 사용하는 storage, 주변장치와 BLE 예제를 각각 확인합니다.

Stable URL:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

Arduino CLI 예시:

```powershell
$StableIndex = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json'
arduino-cli core update-index --additional-urls $StableIndex
arduino-cli core install nucode:zephyr@0.3.0 --run-post-install --additional-urls $StableIndex
arduino-cli core list
```

## 변경 시 확인할 항목

- Maximum Sketch size는 1,490,944 byte입니다.
- LittleFS 시작 `0x16c000`과 Settings/ZMS 시작 `0x174000`은 RC2/RC3와 같습니다.
- 일반 Upload는 storage migration이나 백업을 대신하지 않습니다.
- EEPROM 변경은 `commit()` 전에는 영구 저장되지 않습니다.
- LittleFS의 format 옵션은 기존 내용을 삭제할 수 있습니다.
- Runtime pin 변경은 capability 또는 소유권 충돌 때 실패할 수 있습니다.
- RC per-tag index는 자동 update channel이 아니므로 안정 버전 사용 뒤 제거하십시오.

## 예제와 library 변화

`v0.2.0`의 4개 library·14개 예제에서 8개 library·29개 예제로 늘었습니다. Servo, EEPROM,
LittleFS와 BLE Security가 추가됐고, NUCODE NU54DK 및 BLE 예제가 확장됐습니다. 정확한 목록은
[설치·시험 문서](./TESTING.md)를 확인하십시오.

## 이전 버전으로 복귀

1. 중요한 storage 데이터를 백업합니다.
2. Boards Manager에서 `0.2.0` 또는 `0.1.0`을 명시적으로 선택합니다.
3. 설치 뒤 IDE를 다시 시작하고 그 버전의 API·예제 범위로 Sketch를 되돌립니다.
4. Blink를 clean compile·upload합니다.

이전 stable은 재현과 downgrade를 위해 index에 남지만 신규 수정·지원 대상은 아닙니다.
RC1/RC2는 application size 계약이 다르므로 생산 데이터가 있는 보드에서 반복 전환하지 마십시오.
