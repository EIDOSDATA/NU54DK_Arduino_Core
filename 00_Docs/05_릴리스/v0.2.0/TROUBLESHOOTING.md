# NU54DK Arduino Core v0.2.0-rc.1 문제 해결

> **상태: GitHub Draft 준비 완료 / clean Windows staged ZIP 검증 대기.** Draft는 실제 Git
> tag가 없는 내부 상태일 수 있으며 일반 공개 Boards Manager channel이 아니다. 최신 정식
> package가 필요하면 `v0.1.0` stable을 사용한다.

| 항목 | 값 |
| --- | --- |
| 공식 OS | Windows 10/11 x64 |
| Board/FQBN | `NU54DK (nRF54L15, Zephyr)` / `nucode:zephyr:nu54dk` |
| 기본 Upload | 온보드 CMSIS-DAP V2 + pyOCD |
| 선택 Upload | 외장 SEGGER J-Link |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain | `dcbdc366a1` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

## 1. `v0.2.0-rc.1`이 Boards Manager에 보이지 않음

Release가 GitHub **Draft**라면 보이지 않는 것이 정상이다. Draft asset은 공개 download URL로
제공되지 않으며 아래 RC URL도 public Prerelease 전환 전에는 설치 URL로 사용할 수 없다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.2.0-rc.1/package_nucode_nu54dk_rc_index.json
```

Draft 단계에서는 인증된 exact ZIP을 새 Sketchbook의 격리된 `hardware/nucode/zephyr`
staging에 수동 추출해 board/예제 열거, compile와 upload만 확인한다. `%LOCALAPPDATA%\Arduino15`
아래에 직접 추출하지 않으며 이를 Boards Manager 설치나 `post_install` PASS라고 기록하지 않는다.

프로젝트 소유자가 staged 결과를 승인하고 public Prerelease 전환과 asset 검증 완료를 알린 뒤에도
보이지 않으면 URL이 한 줄로 등록됐는지, GitHub 접근, proxy, TLS inspection과 시스템 시간을
확인하고 index를 갱신한다. Public RC에서는 별도 clean Windows Boards Manager 설치·`post_install`
end-to-end를 수행하고, 이 결과가 승인되기 전에는 stable 공개로 진행하지 않는다.

```powershell
arduino-cli core update-index
arduino-cli core search nucode
```

정식 `v0.1.0`은 다음 stable index로 설치한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

## 2. 설치가 오래 걸리거나 prerequisite 검증에 실패함

첫 설치는 NCS v3.4.0과 Toolchain bundle `dcbdc366a1`을 공식 배포 경로에서 받기 때문에 오래
걸리고 많은 디스크 공간을 사용한다. 중단 뒤 재시도할 때 exact download와 완료 marker가
유효하면 재사용한다. NCS와 Toolchain 전체를 먼저 삭제하지 않는다.

| 진단 | 의미와 조치 |
| --- | --- |
| `E_PREREQUISITE_PINS` | package와 설치 pin 불일치; 같은 RC index에서 package 재설치 |
| `E_PREREQUISITE_READY` | 완료 marker 없음/불일치; prerequisite log 확인 후 설치 재개 |
| `E_PREREQUISITE_TOOLCHAIN` | 고정 Toolchain 누락 또는 손상 |
| `E_PREREQUISITE_NRFUTIL` | 고정 도구 byte 검증 실패; 임의 binary로 우회 금지 |
| `E_PREREQUISITE_NCS` | NCS revision 불일치; 다른 workspace와 섞지 않고 exact 설치 복구 |

설치 log는 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`에서 확인한다. Arduino IDE가
`invalid UTF-8` gRPC 오류를 표시하면 IDE/내장 Arduino CLI version, 해당 시각 log와 설치된
platform version을 보존한다. 임의 인코딩 변환이나 package ZIP 수정으로 우회하지 않는다.

## 3. Compile 오류 또는 지나치게 긴 build path

- Board가 `nucode:zephyr:nu54dk`인지 확인한다.
- 기존 v0.1/RC build output을 재사용하지 말고 한 번 clean compile한다.
- build/cache 경로를 OneDrive, network share나 더 긴 사용자 경로로 옮기지 않는다.
- package에 포함되지 않은 AVR register, native USB 또는 특정 vendor HAL library는 그대로
  호환되지 않을 수 있다.
- Zephyr API를 직접 사용할 때 필요한 header와 feature를 Sketch가 명시해야 한다.
- bundled board DTS를 별도 checkout으로 덮어쓰지 않는다.

`NUCODE_BLE.h` 또는 `BLESerial` symbol에서 오류가 나면 Tools의 Feature set이 `BLE NUS`인지
확인한다. 일반 GPIO/Wire/SPI 예제는 `Standard peripherals`가 기본값이다.

## 4. 예상한 Arduino 예제가 보이지 않음

이 RC가 배포하는 사용자 예제는 NUCODE NU54DK 10개, Wire/SPI 2개와 NUCODE BLE 2개로 총
14개다. Arduino IDE를 재시작하고 `파일 → 예제`의 platform bundled library를 확인한다.

Adafruit LSM6DS3TR-C compatibility Sketch와 Zephyr/NCS sensor·crypto·radio fixture는 내부
compile/build 검증 입력이며 package 사용자 예제가 아니다. IDE 메뉴에 나타나지 않는 것이
정상이다. 외부 Adafruit library를 별도로 설치해 compile하더라도 실제 sensor runtime/HIL과
NUCODE wrapper 지원을 뜻하지 않는다.

## 5. CMSIS-DAP/pyOCD Upload 실패

1. data 통신 가능한 USB cable, board 전원과 다른 USB port를 확인한다.
2. Tools의 Upload probe가 `CMSIS-DAP (pyOCD)`인지 확인한다.
3. Arduino Serial Monitor, nRF VS Code debug, 다른 pyOCD/GDB process를 닫는다.
4. CMSIS-DAP가 두 개 이상 연결돼 있으면 대상 외 probe를 분리하거나 명시적 probe ID를 사용한다.
5. build와 upload가 같은 `nucode:zephyr:nu54dk` target을 사용했는지 확인한다.

| 오류 | 조치 |
| --- | --- |
| `E_RUNNER_UNAVAILABLE` | package prerequisite와 pyOCD 실행 파일 검증 |
| `E_PROBE_NOT_FOUND` | USB cable, 전원, CMSIS-DAP driver와 장치 열거 확인 |
| `E_PROBE_AMBIGUOUS` | 여러 probe 중 정확한 ID 지정 또는 나머지 분리 |
| `E_PROBE_BUSY` | debugger, Serial/debug server와 다른 upload process 종료 |
| `E_PYOCD_TARGET` | 고정 pyOCD가 `nrf54l` target을 제공하는지 prerequisite 복구 |

`The operation ... is not available for the selected device`와 함께 `nrfutil` runner가 표시되면
Nordic DK용 runner를 NU54DK CMSIS-DAP에 사용한 것이다. NU54DK Arduino board와 pyOCD Upload
probe를 선택해 clean compile/upload한다. 일반 Upload 문제를 해결하려고 `--erase`, mass erase
또는 recover를 먼저 실행하지 않는다.

## 6. 외장 J-Link Upload 실패

- SEGGER J-Link Software가 설치돼 있고 package가 유효 설치 경로를 찾는지 확인한다.
- SWDIO, SWDCLK, GND, VTref와 필요 시 RESET 연결을 확인한다.
- onboard CMSIS-DAP와 외장 J-Link가 동시에 target SWD를 구동하지 않게 한다.
- Tools에서 `SEGGER J-Link`를 선택하고 정확한 J-Link serial number를 입력한다.
- target device는 `nRF54L15_M33`, 기준 SWD speed는 4000 kHz다.

J-Link runner 또는 tool이 없으면 pyOCD로 자동 fallback하지 않는다. J-Link 오류를 해결하거나
사용자가 명시적으로 CMSIS-DAP/pyOCD로 다시 선택한다. Debug와 Upload에 사용하는 probe serial은
COM port 번호와 다른 식별자다.

## 7. Upload는 됐지만 Serial 출력이 없음

`Serial`은 native USB CDC가 아니라 CMSIS-DAP의 VCOM/DAP UART를 사용하는 Zephyr console
wrapper다. 장치 관리자의 해당 COM port를 115200 8N1로 열고 다른 Serial Monitor가 점유하지
않는지 확인한다. SWD probe ID, J-Link serial과 COM port를 서로 바꾸어 입력하지 않는다.

## 8. BLE NUS가 연결되지 않음

- Peripheral과 Central image를 서로 다른 두 board 또는 호환 NUS peer에 각각 올린다.
- 두 예제의 exact local name 기본값이 `NU54-NUS`로 같은지 확인한다.
- 양쪽 모두 `BLE NUS` Feature set으로 clean compile했는지 확인한다.
- `BLESerial.poll()`을 loop에서 계속 호출한다.
- 연결 전에는 `ready()`가 false일 수 있으며 write를 강제하지 않는다.

이 RC는 임의 GATT builder, bonding/SMP, HID 또는 multiprotocol을 제공하지 않는다. 해당 기능을
요구하는 library 문제를 NUS 연결 오류로 처리하지 않는다.

## 9. System OFF wake가 debug 연결에서 다르게 동작함

Active SWD/debugger는 reset cause와 실제 저전력 진입을 방해할 수 있다. Firmware를 flash한 뒤
debug session을 끝내고 필요하면 SWD cable/probe 연결을 분리한다. `SystemOffWake` 예제는 Serial
명령 `BUTTON` 또는 `TIMER`를 받은 뒤에만 진입한다. 버튼 경로의 기본 wake source는
SW0/P1.13이다. debug reset cause를 GRTC 또는 버튼 wake PASS로 해석하지 않는다.

## 10. PMIC API가 거부되거나 예상 전원 상태가 되지 않음

PMIC write는 명시적 RAM-only 승인과 현재 승인에서의 register watchdog 정책 확인을 요구한다.
reset 뒤에는 다시 승인해야 한다. 무조건 raw register write로 우회하지 않는다.

배터리 충전 전압·전류, recharge, SYS regulation, ship/shutdown과 실제 NTC 보호는 software API
구현만 제공하며 전기 HIL이 완료되지 않았다. 실제 배터리 chemistry, 용량, 온도 감지와 전원
복구 경로를 사용자가 검증하지 않았다면 변경 API를 실행하지 않는다.

## 11. Sensor, Crypto, Thread 또는 Matter가 동작하지 않음

- NUCODE sensor wrapper와 Arduino crypto wrapper는 제공하지 않는다.
- LSM6DS3TR-C 결과는 외부 library compatibility compile-only이며 실제 장치 동작 보증이 아니다.
- IEEE 802.15.4, OpenThread와 Matter는 모두 v0.2.0에서 deferred·미지원이다.
- OpenThread CLI의 NU54DK build PASS는 network join이나 radio runtime 지원 선언이 아니다.
- 802.15.4 NU54DK build에는 NVMC symbol 문제가 있고 Matter에는 `factory_data_partition`이 없다.

이 문제를 해결하기 위해 임의 board DTS, partition 또는 radio register patch를 package에 섞지 않는다.

## 12. Issue에 포함할 정보

Password, GitHub token, 전체 probe UID와 개인 경로를 제거한 뒤 다음을 기록한다.

- Arduino IDE와 bundled Arduino CLI version, Windows version
- Core version `0.2.0-rc.1` 또는 `0.1.0`
- FQBN과 선택 Feature set/Upload probe
- NCS `v3.4.0`, Zephyr `4.4.0`, Toolchain `dcbdc366a1` 검증 결과
- 전체 compile/upload 오류와 처음 실패한 단계
- pyOCD 또는 J-Link version과 probe 개수
- 실제 board 동작을 주장하는 경우 wiring, 전원 조건과 재현 절차
