# NU54DK Arduino Core v0.3.0-rc.2 문제 해결

> **현재 RC2는 공개 전입니다.** Public Prerelease 발표 전의 URL 404 또는 Boards Manager
> 미노출은 결함이 아닙니다. 현재 정식 사용자는 stable `v0.2.0` 문서를 따르십시오.

| 항목 | 값 |
| --- | --- |
| Package | `nucode:zephyr` |
| Board FQBN | `nucode:zephyr:nu54dk` |
| RC version | `0.3.0-rc.2` |
| 기본 Upload | CMSIS-DAP V2 + pyOCD |

## 1. RC2가 Boards Manager에 보이지 않음

RC2 공개 뒤 다음 per-tag URL이 정확히 등록됐는지 확인합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json
```

- GitHub Release가 `Pre-release`로 공개됐는지 확인합니다.
- RC1 URL만 등록돼 있다면 제거하고 RC2 URL로 교체합니다.
- Boards Manager index를 새로 고친 뒤 Arduino IDE를 다시 시작합니다.
- Stable URL만 등록하면 공개 전 RC version이 보이지 않는 것이 정상입니다.

## 2. 설치가 오래 걸리거나 실패함

첫 설치는 Nordic NCS v3.4.0과 Toolchain `dcbdc366a1`을 내려받으므로 오래 걸릴 수 있습니다.

- Arduino IDE와 post-install 확인 창을 닫지 말고 완료를 기다립니다.
- 충분한 디스크 공간과 안정적인 네트워크를 확인합니다.
- 설치 version이 `0.3.0-rc.2`인지 확인합니다.
- 중단됐다면 설치된 platform의 `post_install.bat`을 일반 사용자 권한으로 다시 실행합니다.
- 관리자 권한, 시스템 PATH 변경 또는 NCS/Toolchain의 수동 삭제를 먼저 시도하지 않습니다.

RC1의 M22 내부 clean-room 실패는 검증 harness가 설치 대상 leaf를 선생성한 문제였습니다.
일반 사용자가 Toolchain directory를 임의로 만들거나 지우라는 의미가 아닙니다. RC2에서 같은
오류가 재현되면 처음 실패한 post-install 단계와 log를 보존해 보고하십시오.

## 3. Compile 실패 또는 예제가 보이지 않음

1. Board가 `NU54DK (nRF54L15, Zephyr)`인지 확인합니다.
2. 설치된 Core가 `0.3.0-rc.2`인지 확인합니다.
3. 예제에 맞는 Feature set을 선택합니다.
4. Arduino IDE를 다시 시작해 library/example index를 갱신합니다.
5. `File → Examples`에 library 8개와 예제 29개가 있는지 확인합니다.

Standard 예제를 BLE profile에서, 또는 BLE 예제를 Standard profile에서 빌드하면 필요한 feature가
빠지거나 의도한 resource 구성이 달라질 수 있습니다.

## 4. CMSIS-DAP Upload 실패

- Probe가 한 대면 `CMSIS-DAP (pyOCD)`를 사용합니다.
- Probe가 둘 이상이면 `CMSIS-DAP with UID (pyOCD)`를 선택하고 정확한 UID를 입력합니다.
- UID는 COM 번호나 DAPLink drive 문자와 다릅니다.
- Compile과 Upload에 같은 Board, Feature set, Upload probe 설정을 사용합니다.
- 다른 프로그램이 CMSIS-DAP 또는 VCOM을 점유하지 않는지 확인합니다.
- 일반 실패 뒤 mass erase 또는 recover를 자동 복구 절차로 사용하지 않습니다.

## 5. Serial 출력이 없음

- CMSIS-DAP VCOM을 115200 8N1로 엽니다.
- Upload에 사용한 보드의 COM port가 맞는지 확인합니다.
- 다른 serial monitor를 닫고 다시 연결합니다.
- `SerialEcho`로 기본 송수신을 먼저 확인합니다.

## 6. EEPROM 데이터가 저장되지 않음

- 값을 바꾼 뒤 `EEPROM.commit()`을 호출했는지 확인합니다.
- `commit()` 결과와 `EEPROM.lastError()`를 기록합니다.
- `reset()`은 데이터를 삭제하므로 진단 목적으로 자동 호출하지 않습니다.
- 다른 partition layout의 firmware로 이동했다면 기존 record를 그대로 사용할 수 있다고 가정하지
  않습니다.

## 7. LittleFS mount 실패

- 기본 `LittleFS.begin(false)`는 손상 또는 미초기화 filesystem을 자동 format하지 않습니다.
- 중요한 데이터가 있으면 format 전에 image와 출력부터 보존합니다.
- 시험 보드에서 데이터 삭제를 승인한 경우에만 `format()` 또는 `begin(true)`를 사용합니다.
- 경로 길이, 열린 file 수와 미지원 API를 [Known issues](./KNOWN_ISSUES.md)에서 확인합니다.

## 8. BLE 연결 또는 pairing 실패

- Peripheral과 Central 역할, Feature set과 예제가 올바른지 확인합니다.
- 두 보드의 reset 순서와 advertising timeout을 기록합니다.
- Windows SecureKeyboard는 OS에 남은 bond와 보드 저장 bond가 서로 다르지 않은지 확인합니다.
- Bond 삭제는 보안 상태를 바꾸는 작업이므로 시험 대상과 삭제 범위를 확인한 뒤 수행합니다.
- BLE Mesh, OpenThread, Matter 또는 USB HID 동작을 BLE 예제에서 기대하지 않습니다.

## 9. Stable로 되돌리기

RC2 시험을 중단하려면 [Migration](./MIGRATION.md)에 따라 stable `v0.2.0`을 명시적으로
설치합니다. RC2 index URL은 제거할 수 있지만 stable index와 공유 prerequisite는 유지합니다.

## 10. Issue에 포함할 정보

- Core version, Arduino IDE/CLI와 Windows version
- Board FQBN과 Feature set
- 예제 또는 최소 Sketch
- 첫 실패 단계와 오류 전문
- Compile 또는 post-install log
- Upload runner 종류와 장치 수 — 전체 probe UID는 제거
- Storage 시험의 reset/format 여부
- BLE 시험의 peer, 역할과 pairing 상태

비밀, 사용자 계정 경로와 전체 probe UID는 공개 Issue에 올리지 마십시오.
