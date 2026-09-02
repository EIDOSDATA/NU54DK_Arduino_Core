# NU54DK Arduino Core v0.3.0-rc.1 문제 해결

| 항목 | 값 |
| --- | --- |
| Board/FQBN | NU54DK / `nucode:zephyr:nu54dk` |
| 공식 OS | Windows 10/11 x64 |
| 기본 Upload | CMSIS-DAP V2 + pyOCD |
| RC version | `0.3.0-rc.1` |

## 1. RC가 Boards Manager에 보이지 않음

Additional Boards Manager URLs에 stable URL이 아니라 다음 **RC 전용** URL도 등록했는지 확인합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.1/package_nucode_nu54dk_rc_index.json
```

Release가 public prerelease로 전환되기 전에는 URL이 열리지 않습니다. GitHub Release 페이지에서
`v0.3.0-rc.1`과 `package_nucode_nu54dk_rc_index.json` 자산을 먼저 확인한 뒤 index를 갱신합니다.

## 2. 설치가 오래 걸리거나 실패함

첫 설치는 NCS v3.4.0과 Toolchain bundle을 Nordic 공식 배포에서 받기 때문에 오래 걸리고 디스크를
많이 사용합니다. IDE와 PC를 임의로 종료하지 말고 설치 로그를 보존합니다.

- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs` 확인
- proxy, TLS inspection, GitHub/Nordic 다운로드와 시스템 시간 확인
- package를 수동으로 수정하거나 다른 NCS revision과 섞지 않음
- 실패 원인이 확인되기 전에 NCS/Toolchain 전체를 삭제하지 않음

## 3. Compile 실패 또는 예제가 보이지 않음

- Board가 `NU54DK (nRF54L15, Zephyr)`인지 확인합니다.
- 설치 version이 `0.3.0-rc.1`인지 확인합니다.
- 기본 예제는 `Standard peripherals`, BLE 예제는 해당 BLE Feature set을 선택합니다.
- 이전 `v0.2.0` build directory를 재사용하지 말고 clean compile합니다.
- Arduino IDE를 재시작하고 `File → Examples`에서 8개 bundled library를 확인합니다.

RC 후보는 예제 29개를 제공합니다. Storage 예제 두 개가 보이지 않으면 RC가 아니라 stable
`0.2.0`을 설치했을 가능성이 큽니다.

## 4. CMSIS-DAP Upload 실패

1. 데이터 통신 USB cable, 보드 전원과 연결 상태를 확인합니다.
2. Serial Monitor, nRF debugger와 다른 pyOCD process를 닫습니다.
3. Probe가 한 대면 `CMSIS-DAP (pyOCD)`를 선택합니다.
4. 둘 이상이면 `CMSIS-DAP with UID (pyOCD)`와 정확한 UID를 사용합니다.
5. COM 번호와 DAPLink drive 문자를 UID로 입력하지 않습니다.

일반 오류를 해결하려고 mass erase 또는 recover를 먼저 실행하지 마십시오. 외장 J-Link를 선택한
경우 pyOCD로 자동 fallback하지 않습니다.

## 5. Serial 출력이 없음

기본 `Serial`은 native USB CDC가 아니라 CMSIS-DAP VCOM을 사용하는 115200 8N1 Zephyr console입니다.
대응 COM port를 열고 다른 프로그램이 점유하지 않는지 확인합니다. `Serial1`은 uart30 runtime
instance이므로 console COM과 같은 객체가 아닙니다.

## 6. EEPROM 데이터가 저장되지 않음

- `EEPROM.begin(size)`의 반환을 확인합니다. Size는 1..1024입니다.
- `write()`/`update()`/`put()` 뒤 `EEPROM.commit()` 성공을 확인합니다.
- `lastError()`와 `lastDriverError()`를 기록합니다.
- ISR callback 안에서 EEPROM API를 호출하지 않습니다.
- `corrupt`면 자동 초기화하지 말고 데이터 삭제 승인을 받은 뒤에만 `EEPROM.reset()`을 실행합니다.

## 7. LittleFS mount 실패

- 기본 `LittleFS.begin(false)`는 데이터를 보호하기 위해 자동 format하지 않습니다.
- 열린 파일을 모두 `close()`한 뒤 unmount/format을 재시도합니다.
- 경로의 `..`, 과도한 길이와 지원하지 않는 mode를 제거합니다.
- `lastError()`와 `lastDriverError()`를 기록합니다.
- 기존 데이터 삭제를 승인한 경우에만 `LittleFS.format()` 또는 `begin(true)`를 실행합니다.

## 8. BLE 연결·pairing 실패

- 두 image가 같은 서비스/이름 계약과 올바른 BLE Feature set으로 clean build됐는지 확인합니다.
- Windows에 남은 이전 pairing이 시험을 방해하면 장치를 제거한 뒤 다시 시작합니다.
- SecureKeyboard의 숫자 비교 화면에서는 보드 예제가 요구하는 버튼 확인 순서를 따릅니다.
- BLE HID 연결 성공과 실제 key 입력을 별도로 확인합니다.

## 9. Issue에 포함할 정보

비밀과 전체 probe UID를 제거한 뒤 다음을 남깁니다.

- Arduino IDE/CLI, Windows와 Core version
- FQBN, Feature set과 Upload probe
- 예제 이름과 처음 실패한 단계
- 전체 compile/upload error와 해당 시각 설치 로그
- Storage 오류 enum/driver code 또는 BLE 상태 token
- 실제 hardware 결과를 주장할 때 wiring·전원·보드 수와 재현 순서

