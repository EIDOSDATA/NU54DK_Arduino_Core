# v0.5.0-rc.1 Migration

## v0.4.1에서 RC 시험으로 이동

1. 스케치, 선택한 Feature set, 보드별 역할과 `nucode-build.json`·`prj.conf`·`app.overlay`를 보존합니다.
2. [RC 설치 안내](README.md)에 따라 별도 index에서 `nucode:zephyr@0.5.0-rc.1`을 설치합니다.
3. 기존 스케치는 **기존 profile 그대로** 먼저 compile합니다. Standard 예제는 `standard`,
   BLE 예제는 `ble`, Fabric 예제는 `fabric` 구성을 유지합니다.
4. 기본 Blink로 upload 경로를 확인하고 새 기능은 각 예제의 역할·상대 보드·종료 절차를 따릅니다.

기본 `standard/full` 메모리 설정은 유지합니다. `adaptive`는 자동 migration이 아니라
명시적으로 선택하는 실험적 profile입니다. BLE 고급 예제의 sidecar 설정을 빼고
`.ino`만 복사하면 원래 기능·역할을 재현할 수 없습니다.

Secure BLE DFU는 일반 `ble` image와 다른 MCUboot layout을 사용하며 외부 signing key가 필요합니다.
[DFU 예제 안내](../../../libraries/NUCODE_BLE_DFU/examples/README.md)를 먼저 읽습니다.
Private key를 스케치·로그·저장소에 넣지 않습니다. Core 설치 전환만으로 보드 flash나 저장 데이터가
migration되는 것은 아니며, storage format·reset이나 다른 image layout의 영향은 별도로 확인합니다.

## Stable v0.4.1로 복귀

Arduino IDE에서는 RC core를 제거한 뒤 stable URL을 사용해 `0.4.1`을 명시적으로 설치합니다.
CLI에서는 다음과 같이 전환합니다.

```powershell
$StableIndex = "https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json"
arduino-cli core uninstall nucode:zephyr
arduino-cli core update-index --additional-urls $StableIndex
arduino-cli core install nucode:zephyr@0.4.1 --additional-urls $StableIndex --run-post-install
arduino-cli core list
```

`0.4.1` 표시와 prerequisite 최종 PASS를 확인하고 stable에서 지원하는 스케치로 다시 빌드합니다.
RC에만 있는 API·113개 예제가 stable에도 제공되는 것은 아닙니다. Stable은 30개 예제입니다.

RC index를 stable root index 대신 덮어쓰지 않습니다. 제거·재설치 시험은 SDK marker와 cache의
보존을 확인했으며, 문제 해결을 위해 SDK 전체·사용자 스케치·키를 임의로 삭제할 필요는 없습니다.
검증 근거는 [Testing](TESTING.md)을 확인합니다.
