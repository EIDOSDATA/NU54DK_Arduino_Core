# NU54DK Arduino Core v0.3.0-rc.3 마이그레이션

> `v0.3.0-rc.3`는 시험용 Release Candidate입니다. 현재 정식 설치 channel은 stable
> `v0.2.0`입니다.

## 1. 이동 전 원칙

- Stable index와 RC3 per-tag index는 별도 URL입니다.
- 과거 RC per-tag URL은 RC3를 자동 제공하지 않으므로 RC3 URL로 교체합니다.
- Core 제거 또는 version 변경 때문에 공유 NCS와 Toolchain directory를 삭제하지 않습니다.
- EEPROM, Settings/ZMS와 LittleFS의 중요한 데이터는 먼저 별도로 백업합니다.
- RC3는 application linker 경계를 바꾸므로 최소한 Blink clean compile·upload를 다시 수행합니다.

## 2. RC3 index 추가

RC3가 Public Prerelease로 공개된 뒤 Arduino IDE의
`File → Preferences → Additional Boards Manager URLs`에 다음 URL을 추가합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.3/package_nucode_nu54dk_rc_index.json
```

Stable URL은 그대로 유지할 수 있습니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

동일한 `nucode:zephyr` package의 RC1/RC2/RC3 per-tag URL을 동시에 둘 필요는 없습니다. 이전
RC URL을 제거하고 현재 시험할 RC3 URL만 남깁니다.

## 3. Stable v0.2.0 또는 RC2에서 RC3로 이동

1. 중요한 Sketch와 storage 데이터를 백업합니다.
2. RC3 Release 페이지가 Public Prerelease인지 확인합니다.
3. RC3 index를 Additional Boards Manager URLs에 추가합니다.
4. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 찾습니다.
5. Version `0.3.0-rc.3`를 명시적으로 선택해 설치합니다.
6. Post-install 실행을 승인하고 prerequisite 검증이 끝날 때까지 기다립니다.
7. Arduino IDE를 다시 시작하고 Board, Feature set과 Upload probe를 다시 확인합니다.
8. Blink를 clean compile·upload하고 출력의 maximum program storage가 `1490944` byte인지
   확인합니다.
9. 사용 중인 Storage, 주변장치 또는 BLE 예제를 순서대로 확인합니다.

RC3는 loaderless application의 `0x000000..0x16c000` 범위를 linker에 동일하게 적용합니다. RC2의 논리
696 KiB slot 두 개는 제거되지만 LittleFS `0x16c000`과 Settings/ZMS `0x174000` 시작 주소는
같습니다. 일반 Upload가 storage 보존을 보장하는 migration 도구는 아니므로 중요한 데이터는
반드시 백업합니다.

## 4. Sketch와 사용법 변경점

일반 Sketch API와 29개 예제 목록은 RC2에서 바뀌지 않습니다. 주요 변경은 build·memory
contract입니다.

- Standard와 BLE profile 모두 같은 1,490,944-byte application 범위를 사용합니다.
- 기존 Sketch가 712,704 byte를 넘더라도 새 한도 안이면 build할 수 있습니다.
- 큰 image는 compile 성공만 확인하지 말고 실제 Upload와 boot를 확인합니다.
- RC3에는 Memory layout 선택 메뉴가 없습니다. 임의 partition override는 정식 지원하지 않습니다.
- EEPROM 변경은 `commit()` 전에는 영구 저장되지 않습니다.
- LittleFS는 `begin(false)`로 비파괴 mount하고, format은 데이터 삭제를 승인한 뒤에만 수행합니다.
- Runtime pin 변경은 capability와 소유권 충돌을 fail-closed로 거부할 수 있습니다.

## 5. Stable v0.2.0 또는 RC2로 복귀

1. 중요한 RC3 storage 데이터를 백업합니다.
2. Boards Manager에서 되돌릴 version을 명시적으로 선택합니다.
3. 해당 stable 또는 per-tag index URL이 등록돼 있는지 확인합니다.
4. 설치 뒤 Arduino IDE를 다시 시작합니다.
5. 해당 version에서 제공한 Feature set과 예제 범위로 Sketch를 되돌립니다.
6. Blink를 clean compile·upload해 기본 경로를 확인합니다.
7. RC3 index가 더 필요 없으면 Additional Boards Manager URLs에서 제거합니다.

과거 RC로 복귀하면 Arduino가 다시 712,704-byte maximum을 표시합니다. 이는 해당 역사
artifact의 계약이며 RC3 파일로 고쳐 쓰지 않습니다. Version 사이의 partition 차이를 반복 시험할
때는 중요 데이터가 없는 시험 보드를 사용하십시오.
