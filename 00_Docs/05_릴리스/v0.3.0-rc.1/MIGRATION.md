# NU54DK Arduino Core v0.3.0-rc.1 마이그레이션

> 이 절차는 `v0.2.0` stable에서 RC를 **시험**하는 방법입니다. RC 검증이 끝나면 stable로
> 되돌릴 수 있으며 stable index는 계속 유지됩니다.

## 1. RC index 추가

Arduino IDE의 `File → Preferences → Additional Boards Manager URLs`에 다음 URL을 추가합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.1/package_nucode_nu54dk_rc_index.json
```

기존 stable URL을 삭제할 필요는 없습니다. Boards Manager에서 설치할 version을 반드시
`0.3.0-rc.1`로 확인하십시오.

## 2. 설치 전 보존

1. EEPROM, Settings와 filesystem에 중요한 데이터가 있으면 응용의 export 기능으로 백업합니다.
2. Arduino IDE, Serial Monitor, debugger와 다른 pyOCD/J-Link process를 닫습니다.
3. 현재 설치 version, Feature set과 Upload probe를 기록합니다.
4. 여러 NU54DK가 연결됐다면 시험 대상 CMSIS-DAP UID를 로컬에만 기록합니다.

RC Upload는 전체 Zephyr image를 기록합니다. EEPROM은 Settings/ZMS의 `arduino/eeprom`, LittleFS는
새 전용 partition을 사용하므로 과거 application의 임의 storage layout과 호환된다고 가정하면 안 됩니다.

## 3. RC 설치와 기본 확인

1. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 검색합니다.
2. `0.3.0-rc.1`을 명시적으로 선택해 설치합니다.
3. 첫 설치의 Nordic prerequisite 다운로드와 `post_install`이 끝날 때까지 기다립니다.
4. Arduino IDE를 재시작합니다.
5. `NU54DK (nRF54L15, Zephyr)`와 `Standard peripherals`를 선택합니다.
6. Blink를 clean compile·upload해 stable build cache가 섞이지 않았는지 확인합니다.
7. Storage 예제를 실행하기 전에 [Known issues](./KNOWN_ISSUES.md)를 읽습니다.

전체 RC 확인 순서는 [Testing](./TESTING.md)을 따릅니다.

## 4. Sketch 변경점

### EEPROM

```cpp
#include <EEPROM.h>

EEPROM.begin(1024);
EEPROM.put(0, value);
EEPROM.commit();  // 영구 저장은 이 호출이 성공해야 완료됩니다.
```

`write()`나 `put()`만 호출하고 reset하면 변경은 사라집니다. 손상된 record는 자동 초기화하지
않으며 사용자가 데이터 삭제를 승인한 뒤 `EEPROM.reset()`을 호출해야 합니다.

### LittleFS

```cpp
#include <LittleFS.h>

if (!LittleFS.begin(false)) {
  // 진단 후 데이터 삭제를 승인한 경우에만 LittleFS.format()을 호출합니다.
}
```

자동 format 의존 코드는 비파괴 기본 정책과 다릅니다. `begin(true)` 또는 `format()`은 기존
filesystem 내용을 삭제할 수 있습니다.

### BLE와 주변장치

- BLE 예제는 해당 BLE Feature set을 선택합니다.
- Runtime pin 변경은 peripheral이 종료된 상태에서만 수행합니다.
- 기본 `Serial`은 계속 CMSIS-DAP VCOM 기반 Zephyr console이며 `Serial1`과 다른 객체입니다.

## 5. Stable v0.2.0으로 복귀

1. Boards Manager에서 version `0.2.0`을 선택해 다시 설치합니다.
2. IDE를 재시작하고 `Standard peripherals`에서 Blink를 clean compile합니다.
3. Stable image를 Upload합니다.
4. RC 전용 EEPROM/LittleFS 데이터가 stable API에서 보이지 않는 것은 정상입니다.
5. RC 시험을 끝냈다면 Additional URLs에서 RC URL만 제거할 수 있습니다. Stable URL은 유지합니다.

RC를 제거해도 공유 NCS/Toolchain prerequisite를 임의로 삭제하지 마십시오.

