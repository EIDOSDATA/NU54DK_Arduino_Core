# NU54DK HIL 시험

이 디렉터리는 NU54DK 실물 보드가 필요한 host-side 시험만 관리합니다. 일반 host unit test나
Arduino compile test와 분리하며, 장치가 없는 CI에서 PASS로 추정하지 않습니다.

| 파일 | 역할 | 주요 fixture |
| --- | --- | --- |
| `m6_serial_echo.py` | pyOCD flash 후 UART READY·echo 검증 | NU54DK, CMSIS-DAP V2 UART |
| `m7_i2c_pmic.py` | BQ25186 고정 ID register의 읽기 전용 I2C 검증 | 보드 내장 PMIC |
| `m7_peripheral_hil.py` | SPI loopback·ADC·PWM token 검증 | 명시된 점퍼와 핀 fixture |
| `m8_upload.py` | manifest를 검증한 pyOCD/J-Link upload 반복 시험 | NU54DK debug probe |
| `m8_debug.py` | debug server와 Sketch source breakpoint 검증 | pyOCD 또는 J-Link |
| `m14_pin_hil.py` | 신규 LED output/readback과 버튼 pull·edge 검증 | NU54DK, CMSIS-DAP V2 UART, 사용자 버튼 동작 |
| `test_m7_*.py` | 실제 장치 없이 HIL protocol/parser를 검증 | 없음 |
| `test_m14_pin_hil.py` | M14 수동 동작 protocol·증적의 fail-closed 경계를 검증 | 없음 |

## 실행 원칙

- 보드 target과 build manifest가 기대값과 일치해야 합니다.
- 일반 upload 경로에서는 mass erase나 recover를 사용하지 않습니다.
- PMIC 시험은 허용한 address/register의 읽기만 수행합니다.
- probe UID, COM port와 물리 fixture는 실행 인자로 명시하거나 안전한 자동 탐색 결과가 하나일
  때만 사용합니다.
- 실기 PASS는 해당 commit, artifact hash와 fixture 조건을 검증 기록에 연결합니다.

## M14 신규 핀 HIL

`PIN_LED2`, `PIN_LED3`은 LOW/HIGH를 실제 GPIO에 기록한 뒤 raw readback이 같은지 자동
확인합니다. `PIN_BUTTON1`, `PIN_BUTTON2`, `PIN_BUTTON3`은 `INPUT_PULLUP`에서 뗀 상태
HIGH와 누른 상태 LOW를 확인하고 FALLING, RISING, CHANGE ISR을 순서대로 검증합니다.

화면의 Arduino 논리명과 보드의 사용자 버튼 표기는 다음과 같이 대응합니다. 회로도 내부의
부품 참조번호가 아니라 보드의 `SW0..3` 사용자 표기를 기준으로 조작합니다.

| Arduino 논리명 | DTS alias | 사용자 버튼 | nRF54L15 GPIO |
| --- | --- | --- | --- |
| `PIN_BUTTON0` | `sw0` | SW0 | P1.13 — M6에서 검증했으므로 M14 대상 제외 |
| `PIN_BUTTON1` | `sw1` | SW1 | P1.09 |
| `PIN_BUTTON2` | `sw2` | SW2 | P1.08 |
| `PIN_BUTTON3` | `sw3` | SW3 | P0.04 |

`PIN_LED1`은 `PIN_PWM0`과 동일한 물리 자원을 PWM이 소유하므로 이 digital HIL에서는
제외합니다. 해당 자원의 회귀 근거는 M7 `PIN_PWM0` 0/128/255 driver 시험입니다. 또한
`PIN_LED2`를 시험하는 동안에는 외부 debug session을 종료해 SWO와의 동시 소유를 피합니다.

보드 연결 전에는 **NCS v3.4.0 Toolchain terminal**에서 다음 production target
build-only를 실행합니다. 일반 PowerShell이라면 먼저 nRF Connect extension의 `Open terminal`로
고정 Toolchain 환경을 적용해야 합니다.

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$Build = "$env:TEMP\nu54dk-m14-pin-hil"

Push-Location $NcsRoot
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $Build `
  "$CoreRoot\tests\zephyr\m14_pin_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"
Pop-Location
```

실기는 CMSIS-DAP V2 target UART를 사용하는 다른 프로그램과 debug session을 모두 닫고
실행합니다. `--acknowledge-manual-actions`는 세 버튼을 화면 안내대로 직접 누르고 뗄 준비가
되었다는 명시적 승인입니다. 각 ACTION은 30초, 전체 transcript는 기본 520초 제한을 가지며,
기존 증적은 `--overwrite-evidence` 없이는 덮어쓰지 않습니다. Core HIL 관련 source와 보드
submodule이 clean하지 않거나, 현재 보드 checkout이 부모 commit의 gitlink와 다르거나, HEX 옆
build record가 기대 Core·보드 commit, NCS/Zephyr revision, NU54DK target과 다르면 flash 전에
실패합니다. build record의 Core 범위·M14 application·board tree SHA-256도 현재 source에서
CMake와 같은 방식으로 다시 계산하여 세 값이 모두 정확히 같아야 합니다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m14_pin_hil.py" `
  --hex "$Build\m14_pin_hil\zephyr\zephyr.hex" `
  --expected-core-revision $Commit `
  --acknowledge-manual-actions `
  --evidence "$CoreRoot\build\m14\hil\m14-pin-hil.evidence.json"
```

화면에 `ACTION`이 출력될 때 지정된 버튼 하나만 누르거나 뗍니다. 모든 핀과 edge가
통과해야 `status: passed` JSON과 SHA-256으로 결합된 companion transcript가 생성됩니다.
timeout, target FAIL, 핀 ID·순서 불일치 또는 중복 token은 PASS 증적을 만들지 않습니다.

구체적인 실행 명령과 이미 검증한 결과는
[M6 기준선](<../../../00_Docs/04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>),
[M7 기준선](<../../../00_Docs/04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>) 및
[M8 기준선](<../../../00_Docs/04_검증 기록/08_M8_업로드와_디버그_기준선.md>),
[M14 기준선](<../../../00_Docs/04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)을 따릅니다.
