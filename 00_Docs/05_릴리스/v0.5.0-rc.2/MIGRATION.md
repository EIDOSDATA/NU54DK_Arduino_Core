# v0.5.0-rc.2 이동과 복귀

## RC1에서 RC2

1. Sketch와 sidecar를 별도로 보관한다. Boards Manager가 교체하는 설치 폴더에 개인 파일을 두지 않는다.
2. 환경설정의 RC1 index URL을 [RC2 index](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.2/package_nucode_nu54dk_rc_index.json)로 교체한다.
3. Boards Manager에서 `NUCODE NU54DK Zephyr Boards` **0.5.0-rc.2**를 선택한다.
4. 예제를 새 설치본에서 다시 열고 `.ino` 상단의 Feature set·보드 수·역할을 확인한다.
5. Upload probe 메뉴를 다시 선택한다. 폐지된 UID 자리표시자 메뉴 대신 실제 UID 환경 변수/CLI 선택을 사용한다.

기본 FQBN은 `nucode:zephyr:nu54dk`다. 기본 profile은 여전히 `standard`이며 자동으로
모든 BLE/Audio 기능을 켜지 않는다. 사용자 Sketch API를 일괄 변경할 필요는 없지만 sidecar는 보존한다.
오래된 build 산출물을 새 버전의 성공 근거로 사용하지 않는다.

## v0.4.1에서 이동

[RC1 Migration](../v0.5.0-rc.1/MIGRATION.md)의 기능·profile·secure DFU 경계를 그대로 따른다.
RC2 설치에는 RC1이 선행 설치되어 있을 필요가 없다. RC1→RC2 upgrade·제거·재설치는 별도로 검증했다.
Secure BLE DFU의 partition/key와 일반 image 전환은 별도 절차이며 자동 recover/mass erase로 해결하지 않는다.

## Stable 복귀

Stable index URL을 유지/추가하고 Boards Manager에서 **0.4.1**을 명시적으로 설치한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

RC 전용 ISO/Audio/CS 등의 Sketch는 stable 지원이 아니다. Stable 예제로 기능을 확인한다.
RC1로 돌아가려면 RC1 전용 index URL과 0.5.0-rc.1을 선택할 수 있으며 과거 자산은 변경하지 않았다.
설치 버전은 Boards Manager 또는 `arduino-cli core list`로 확인한다.
