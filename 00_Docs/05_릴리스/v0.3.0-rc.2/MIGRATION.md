# NU54DK Arduino Core v0.3.0-rc.2 마이그레이션

> `v0.3.0-rc.2`는 공개 검증을 완료한 Public Prerelease입니다. 시험용으로만 아래 RC2 URL을
> 추가하십시오. 현재 정식 설치 channel은 계속 stable `v0.2.0`입니다.

## 1. 이동 전 원칙

- RC2는 production stable이 아닌 시험 후보입니다.
- Stable index와 RC2 per-tag index는 별도 URL입니다.
- RC1 per-tag index는 RC2를 자동으로 제공하지 않으므로 RC2 URL로 교체해야 합니다.
- Core 제거 또는 version 변경을 이유로 공유 NCS와 Toolchain directory를 수동 삭제하지 않습니다.
- EEPROM, Settings/ZMS와 LittleFS의 중요한 데이터는 먼저 별도로 백업합니다.

## 2. RC2 index 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 다음 URL을
추가합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json
```

Stable URL은 그대로 유지할 수 있습니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

동일한 `nucode:zephyr` package에 대해 여러 과거 RC per-tag URL을 동시에 둘 필요는 없습니다.
RC1을 시험했다면 RC1 URL을 제거하고 RC2 URL만 남깁니다.

## 3. Stable v0.2.0에서 RC2로 이동

1. 중요한 Sketch와 storage 데이터를 백업합니다.
2. [RC2 Public Prerelease](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0-rc.2)와 정확히 7개 자산이 공개됐는지 확인합니다.
3. RC2 index를 Additional Boards Manager URLs에 추가합니다.
4. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 찾습니다.
5. Version `0.3.0-rc.2`를 명시적으로 선택해 설치합니다.
6. Post-install 실행을 승인하고 prerequisite 검증이 끝날 때까지 기다립니다.
7. Arduino IDE를 다시 시작하고 Board, Feature set과 Upload probe를 다시 확인합니다.
8. 먼저 Blink를 compile·upload한 뒤 필요한 Storage 또는 BLE 시험으로 진행합니다.

RC2의 RRAM application/storage layout은 stable `v0.2.0`과 다를 수 있습니다. 기존 firmware가
사용한 데이터를 자동 migration한다고 가정하지 마십시오.

## 4. RC1에서 RC2로 이동

RC1의 package 설치가 정상이어도 RC1 public clean-room final evidence는 완성되지 않았습니다.
다음 순서로 이동합니다.

1. Additional Boards Manager URLs에서 RC1 per-tag index URL을 제거합니다.
2. RC2 per-tag index URL을 추가합니다.
3. Boards Manager index를 갱신합니다.
4. Version `0.3.0-rc.2`를 명시적으로 선택해 upgrade합니다.
5. 설치 뒤 표시된 version과 `BoardInfo` 출력을 확인합니다.
6. Blink와 사용 중인 profile의 대표 예제를 다시 compile·upload합니다.

RC1 tag, archive와 설치 기록을 RC2 파일로 덮어쓰지 않습니다. 문제 보고서에는 실제로 시험한
version을 구분해 적습니다.

## 5. Sketch 변경점

### EEPROM

- 변경은 RAM mirror에 먼저 적용되며 `commit()` 전에는 reset이나 전원 차단으로 사라질 수
  있습니다.
- `commit()` 결과와 `lastError()`를 확인합니다.
- 손상 record는 자동 초기화하지 않습니다. `reset()`은 데이터 삭제를 승인한 경우에만
  호출합니다.

### LittleFS

- 기본 mount는 `begin(false)`이며 자동 format하지 않습니다.
- `format()`과 `begin(true)`는 기존 filesystem 데이터를 삭제할 수 있습니다.
- 열린 file 수, path 길이와 지원 API 경계를 [Known issues](./KNOWN_ISSUES.md)에서 확인합니다.

### BLE와 주변장치

- Standard와 BLE 예제는 서로 다른 Feature set을 요구할 수 있습니다.
- Runtime pin 변경은 capability와 소유권 충돌을 fail-closed로 거부할 수 있습니다.
- Windows SecureKeyboard는 기존 bond가 시험을 방해하면 OS와 보드 양쪽의 삭제 절차를 확인한 뒤
  다시 pairing합니다.

## 6. Stable v0.2.0으로 복귀

1. 중요한 RC storage 데이터를 백업합니다.
2. Boards Manager에서 version `0.2.0`을 명시적으로 선택합니다.
3. Stable index가 Additional Boards Manager URLs에 남아 있는지 확인합니다.
4. 설치 뒤 Arduino IDE를 다시 시작합니다.
5. `v0.2.0`에서 제공하는 Feature set과 예제 범위로 Sketch를 되돌립니다.
6. Blink를 compile·upload해 기본 경로를 확인합니다.
7. RC2 index가 더 필요 없으면 Additional Boards Manager URLs에서 제거합니다.

Core downgrade는 board flash와 package version을 바꾸지만 RC2 storage 내용을 자동 변환하거나
정리하지 않습니다. Storage layout이 다른 firmware 사이를 오갈 때는 시험 보드를 사용하십시오.
