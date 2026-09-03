# NU54DK Arduino Core v0.3.0 문제 해결

| 항목 | 값 |
| --- | --- |
| Package | `nucode:zephyr@0.3.0` |
| Board/FQBN | `NU54DK (nRF54L15, Zephyr)` / `nucode:zephyr:nu54dk` |
| 기본 Upload | CMSIS-DAP V2 + pyOCD |
| NCS / Zephyr | v3.4.0 / 4.4.0 |
| Toolchain | `dcbdc366a1` |

## Boards Manager에 0.3.0이 보이지 않음

다음 stable URL이 한 줄로 등록됐는지 확인하고 index를 갱신합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

```powershell
arduino-cli core update-index
arduino-cli core search nucode
```

과거 RC per-tag URL은 stable 자동 update를 제공하지 않습니다. RC 시험이 끝났다면 제거하십시오.

## 설치가 오래 걸리거나 실패함

첫 설치는 Nordic NCS v3.4.0과 고정 Toolchain을 받으므로 오래 걸리고 디스크 공간을 사용합니다.
중단 뒤에는 설치된 platform의 `post_install.bat`을 다시 실행하십시오. 공유 NCS/Toolchain 전체를
먼저 삭제하지 마십시오.

로그는 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`에 있습니다. `ready.json`, NCS,
Zephyr 또는 Toolchain identity가 고정 값과 다르면 Build Adapter는 build 전에 실패합니다.

## Compile 실패

- Board가 `nucode:zephyr:nu54dk`인지 확인합니다.
- 오래된 version/RC build output 대신 짧은 로컬 경로에서 clean compile합니다.
- OneDrive, network share와 긴 build path를 피합니다.
- BLE library는 `BLE NUS` Feature set, 일반 예제는 `Standard peripherals`를 선택합니다.
- package의 bundled board DTS를 다른 checkout으로 덮어쓰지 않습니다.
- 임의 AVR register, native USB 또는 vendor HAL 의존 library는 호환되지 않을 수 있습니다.

## CMSIS-DAP/pyOCD Upload 실패

1. 데이터 통신 가능한 USB cable, board 전원과 다른 USB port를 확인합니다.
2. Serial Monitor, debug server와 다른 pyOCD/GDB process를 닫습니다.
3. `CMSIS-DAP (pyOCD)`가 선택됐는지 확인합니다.
4. probe가 여러 대면 `CMSIS-DAP with UID (pyOCD)`와 정확한 UID를 사용합니다.
5. compile과 upload에 같은 FQBN, board option과 build path를 사용합니다.

`No ACK`, `Timeout reading from probe` 또는 Windows의 `장치 설명자 요청 실패`가 함께 보이면
software 재설치보다 먼저 보드 전원과 USB cable을 완전히 분리했다가 다시 연결하고 열거를
확인하십시오. COM 번호는 pyOCD probe UID가 아닙니다. 일반 upload 진단에서 mass erase나
recover를 먼저 실행하지 마십시오.

## 외장 J-Link Upload 실패

SEGGER Software, target VTref, SWDIO/SWDCLK/GND와 필요 시 RESET 연결을 확인합니다. 대상은
`nRF54L15_M33`, 기준 SWD speed는 4,000 kHz입니다. J-Link 실패 시 pyOCD로 자동 전환하지 않습니다.

## Upload는 됐지만 Serial 출력이 없음

`Serial`은 native USB CDC가 아니라 온보드 CMSIS-DAP의 DAP UART입니다. 해당 COM port를
115200 8N1로 열고 다른 Serial Monitor가 점유하지 않는지 확인합니다.

## Memory 또는 storage 문제

- Maximum Sketch size가 1,490,944 byte인지 확인합니다.
- 다른 partition을 가진 RC build directory를 재사용하지 않습니다.
- EEPROM은 변경 후 `commit()`을 호출해야 합니다.
- LittleFS는 먼저 `begin(false)`로 비파괴 mount합니다.
- `format()` 또는 `begin(true)`는 데이터 삭제를 승인한 경우에만 사용합니다.
- version 이동 전 중요한 데이터를 백업합니다.

## Wire, SPI, ADC, PWM 또는 Servo가 거부됨

Variant capability, 승인된 peripheral route와 현재 pin ownership을 확인합니다. `Wire.end()` 또는
`SPI.end()` 뒤에만 runtime pin을 바꾸고 다시 `begin()`합니다. PWM/tone/Servo의 pin·period
충돌은 의도적으로 fail-closed 처리합니다.

## BLE 또는 HID 문제

- BLE 예제는 `BLE NUS` Feature set으로 clean compile합니다.
- Central/Peripheral local name과 service UUID가 일치하는지 확인합니다.
- `poll()`이 필요한 예제는 loop에서 계속 호출합니다.
- Windows HID는 Bluetooth 설정에서 기존 bond를 정리하고 다시 pairing할 수 있습니다.
- BLE Mesh, Thread, Matter와 multiprotocol 문제는 `v0.3.0` 지원 범위가 아닙니다.

## Issue에 포함할 정보

비밀번호, token, 전체 probe UID와 개인 경로를 제거한 뒤 다음을 첨부하십시오.

- Windows, Arduino IDE/CLI와 Core version
- FQBN, Feature set과 Upload probe
- NCS/Zephyr/Toolchain 검증 결과
- 처음 실패한 단계와 전체 오류
- probe 개수, pyOCD/J-Link version
- hardware 동작 문제라면 wiring, 전원 조건과 재현 절차
