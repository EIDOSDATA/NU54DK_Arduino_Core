# v0.5.0 Migration

## v0.4.1에서 이동

Stable Boards Manager URL은 그대로 사용합니다. Boards Manager에서 `0.5.0`을 선택해 업데이트한 뒤
기존 Sketch를 다시 Verify합니다. v0.4.1은 catalog 공급과 지원이 종료되지만 tag·Release 자산은
역사 재현용으로 보존됩니다.

- 기본 `standard`, `ble`, `fabric` 구성을 계속 사용할 수 있습니다.
- 새 예제의 `.ino` 상단에서 권장 Feature set과 필수 sidecar를 확인합니다.
- 확장 BLE 예제는 `BLE NUS`, 특수 기능은 예제가 지정한 전용 구성을 선택합니다.
- 다중 보드 예제는 각 역할의 probe UID와 COM 포트를 기록해 혼동하지 않습니다.

## v0.5.0-rc.1/rc.2에서 이동

RC 전용 URL을 Preferences에서 제거하고 stable URL만 남긴 뒤 `0.5.0`을 설치합니다. RC와 stable을
같은 data directory에서 오갈 때는 Boards Manager에 표시된 버전을 명시적으로 확인합니다.
RC2 공개 archive에는 연속 Upload 제한이 남아 있으므로 정식 0.5.0으로 업데이트해야 교정이 적용됩니다.

## 되돌리기와 데이터

현재 stable catalog는 0.5.0 하나만 공급합니다. 구버전으로 되돌려야 하면 해당 GitHub Release의
고정 자산을 명시적으로 사용해야 하며 일반 지원 대상이 아닙니다. LittleFS format, EEPROM reset,
DFU slot 초기화는 저장 데이터를 지울 수 있으므로 먼저 필요한 데이터를 백업합니다.
