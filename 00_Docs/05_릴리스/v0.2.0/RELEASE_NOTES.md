# NU54DK Arduino Core v0.2.0-rc.1 릴리스 노트

> **상태: GitHub Draft 준비 완료 / clean Windows staged ZIP 검증 대기.** Draft는 실제 Git
> tag가 없는 내부 Release object일 수 있다. 이 candidate는 아직 public RC Boards Manager
> 설치·`post_install` end-to-end를 완료하지 않았으며 정식 `v0.2.0`이 아니다. 단계별 검증과
> 프로젝트 소유자 승인이 끝날 때까지 최신 정식 버전은 `v0.1.0`이다.

`v0.2.0-rc.1`은 Loader나 LLEXT 없이 Arduino Sketch, Core와 Zephyr application을 하나의
정적 ELF/HEX로 만드는 NU54DK 전용 Native Full Zephyr Core의 두 번째 기능 묶음이다. 공식
사용자 환경은 Windows 10/11 x64이며 보드 FQBN은 `nucode:zephyr:nu54dk`다.

## Exact 구성

| 구성 | 고정 값 |
| --- | --- |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Core repository | `https://github.com/EIDOSDATA/NU54DK_Arduino_Core` |

최종 Draft plan은 candidate의 exact Core commit, package archive, RC index, checksum, SPDX SBOM,
license inventory, third-party notice와 이 문서의 byte를 별도로 고정한다. Remote 검증은 GitHub가
반환한 Draft ID와 asset allowlist/byte를 확인하며 Draft 이름을 실제 Git tag로 해석하지 않는다.

## M12~M17 주요 변경

### M12 — CI/CD와 재현 빌드

- 고정 NCS/Zephyr/board revision을 사용한 host, Zephyr build, package와 문서 gate를 구성했다.
- cache 입력과 source identity를 확인하고, 실패 log와 evidence를 분리해 보존한다.
- GitHub Actions와 로컬 runner가 같은 계약을 실행하도록 진입점을 통일했다.
- Windows에서 NCS와 Builder cache가 서로 다른 drive에 있어도 `west build`가 application
  volume에서 실행되도록 고정하고, Nordic container의 Git 조회는 대상 저장소별
  `safe.directory`만 사용한다.
- 공개 stable index는 Windows checkout에서도 승인된 LF byte와 SHA-256을 유지한다.

### M13 — Profile과 Arduino 예제 UX

- 일반 사용자가 `prj.conf`나 overlay를 직접 편집하지 않도록 strict feature/profile resolver를 추가했다.
- 기본 `Standard peripherals`와 `BLE NUS` Feature set을 Arduino Tools 메뉴에 노출한다.
- Arduino library의 표준 `examples` 구조를 package 사용자 예제의 단일 원본으로 사용한다.

### M14 — Core API와 NU54DK Variant

- Arduino Core API 호환 범위와 NU54DK DTS 기반 논리 pin/capability를 정리했다.
- GPIO, Serial, interrupt, Wire, SPI, ADC와 PWM의 기존 기능을 새 profile 구조에서 회귀 검증했다.
- 물리 pin 정의는 bundled NU54DK board package를 단일 원본으로 유지한다.

### M15 — NUCODE NU54DK Board/System API

`<NUCODE_NU54DK.h>`와 전역 `NU54DK` 객체로 다음 범위를 제공한다.

- board identity, device ID, reset report와 uptime
- watchdog 시작·feed·정지
- GRTC counter/alarm과 work-queue callback
- Settings/ZMS 기반 내부 storage
- SW0~SW3 또는 GRTC를 사용한 System OFF wake
- BQ25186 상태 읽기와 명시적 RAM-only 승인 뒤의 제한된 PMIC 설정 API

비-System-OFF HIL과 GRTC timed wake, 사용자 SW0/P1.13 wake는 실제 NU54DK에서 통과했다.
반면 배터리 충전 전압·전류, 충전 완료·재충전, SYS regulation, ship/shutdown과 실제 배터리
온도 보호의 전기 HIL은 수행하지 않았다. PMIC API의 존재를 배터리 안전성 인증으로 해석하면
안 된다.

### M16 — BLE Nordic UART Service

`<NUCODE_BLE.h>`의 전역 `BLESerial`은 Arduino `Stream` 형태의 NUS Peripheral 또는 Central
역할을 제공한다. advertising, exact local-name scan, 연결, RX write, TX notification과
재연결 경로를 두 NU54DK에서 HIL 검증했다.

지원 범위는 NUS Peripheral/Central 한정이다. 임의 GATT service/characteristic builder,
GATT read, indication, bonding, SMP, HID와 multiprotocol은 이 RC가 지원하지 않는다.

### M17 — NCS 기능·예제 coverage

9개 machine-readable record에서 기능을 `supported`, `build-only`, `deferred`로 구분했다.

| 항목 | 실제 결과 | v0.2.0-rc.1 판정 |
| --- | --- | --- |
| 외부 Adafruit LSM6DS3TR-C compatibility Sketch | Arduino compile/link PASS | build-only; package 미포함, sensor runtime/HIL 미실행 |
| Zephyr sensor direct-build fixture | NU54DK compile/link PASS | build-only; NUCODE sensor wrapper 없음 |
| NCS Crypto RNG | 공식 보드와 NU54DK build PASS | direct/build-only; Arduino crypto API와 semantic/HIL 없음 |
| IEEE 802.15.4 PHY test | 공식 보드 PASS, NU54DK NVMC symbol 오류 | deferred, 미지원 |
| OpenThread CLI | 공식 보드와 NU54DK build PASS | deferred, 미지원; network join/radio HIL 없음 |
| Matter template | 공식 보드 PASS, NU54DK `factory_data_partition` 누락 | deferred, 미지원 |

Compile 성공은 센서 실기 동작, radio 통신, Thread network join 또는 Matter commissioning을
뜻하지 않는다. 외부 sensor source와 세 direct-build fixture는 Core ZIP의 Arduino 사용자
예제로 배포하지 않는다.

## Package 사용자 예제

Arduino IDE의 `파일 → 예제`에서 배포하는 예제는 다음 14개다.

- NUCODE NU54DK: `Blink`, `SerialEcho`, `InterruptButton`, `AnalogReadA0`, `PWMFade`,
  `BoardInfo`, `WatchdogBasic`, `CounterAlarm`, `SettingsStorage`, `SystemOffWake`
- Wire: `WirePmicId`
- SPI: `SPITransaction`
- NUCODE BLE: `NUSPeripheral`, `NUSCentral`

`NUSPeripheral`과 `NUSCentral`을 빌드할 때는 Tools 메뉴의 Feature set을 `BLE NUS`로 선택한다.
나머지 기본 예제는 `Standard peripherals`가 기본값이다.

## 검증 상태

M12~M17의 host, target build와 필요한 HIL은 각 마일스톤 기준선에 완료 상태로 보존했다.
M17은 coverage host 21/21, 전체 M17 host 47/47, generic Zephyr regression 14/14를 통과했다.
M16 NUS는 서로 다른 두 NU54DK에서 양방향 payload와 재연결 HIL을 통과했다.

아직 완료되지 않은 M18 수동 gate는 두 단계다.

1. Draft exact ZIP을 별도 clean Windows의 새 Sketchbook `hardware/nucode/zephyr` staging에
   수동 추출하고 package 사용자 예제 열거, 대표 `standard`/`ble` compile, 온보드
   CMSIS-DAP V2/pyOCD 실제 NU54DK upload와 실행을 확인한다. 이 결과는 Boards Manager 설치나
   `post_install` PASS가 아니다.
2. 프로젝트 소유자가 staged 결과를 승인해 Draft를 public RC로 전환한 뒤, 다시 clean
   Windows에서 공개 RC index를 통한 Boards Manager 설치·`post_install`, 예제/compile/upload와
   upgrade/downgrade/uninstall lifecycle을 검증한다. 이 결과를 다시 승인한 뒤에만 stable을
   검토한다.

Draft ID와 asset SHA-256 재검증만으로 위 두 수동 gate를 PASS로 표시하지 않는다.

## 설치·공개 상태

Draft asset은 일반 공개 URL에서 받을 수 없으므로 현재 일반 사용자가 Boards Manager에 등록할
RC URL은 없다. 공개 검증 담당자는 인증된 계정으로 exact ZIP과 sidecar를 받아 새 Sketchbook의
격리된 hardware staging에 수동 추출해 시험한다. `%LOCALAPPDATA%\Arduino15`를 직접 수정하지
않으며 이 staged 시험을 Boards Manager 설치 완료로 기록하지 않는다. 일반 사용자는 다음
stable index와 `0.1.0`을 계속 사용한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

프로젝트 소유자가 이후 RC를 public Prerelease로 전환하면 RC 전용 index는 다음 고정 경로를
사용한다. **Draft인 동안에는 이 URL을 설치 절차로 사용하지 않는다.**

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.2.0-rc.1/package_nucode_nu54dk_rc_index.json
```

Public RC 전환 시점에 실제 Git tag와 공개 asset URL이 생긴다. 공개 RC의 Boards Manager
end-to-end가 별도 clean Windows에서 통과하고 프로젝트 소유자가 승인하기 전에는
`v0.2.0` stable을 공개하지 않는다.

## 라이선스

NUCODE 자체 작성 코드는 MIT License다. ArduinoCore-API, NU54DK board package, Zephyr/NCS와
외부 prerequisite에는 각 원본 license와 notice가 적용된다. NCS, Nordic Toolchain, nRF Util,
pyOCD와 SEGGER J-Link Software를 Core ZIP 안에 임의 재배포하지 않는다. SPDX SBOM과 license
inventory는 구성요소 식별 자료이며 법률 자문을 대신하지 않는다.
