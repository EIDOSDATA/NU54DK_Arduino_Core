# NU54DK Arduino Core v0.2.0 릴리스 노트

> **상태: 정식 릴리스.** RC2 Boards Manager 설치·`post_install`, 설치본 예제 14/14
> compile, 명시 UID upload, UART READY와 BLE NUS 양방향 transparent bridge 검증을
> 통과한 동일 runtime payload를 별도 stable package·tag·Release로 승격한다.

`v0.2.0`은 Loader나 LLEXT 없이 Arduino Sketch, Core와 Zephyr application을 하나의
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

아래 값은 승격 근거인 공개 RC2의 불변 이력이다. RC2는 tag commit
`1c5dcecfc0dba2ef25e06963dcba61c63f454db9`와 12개 asset을 가진다.
RC index SHA-256은 `fa73f3ba34ecfc84984aa836f423cb0d31a2ce56518fac6c56b99ec8dd70f89b`,
ZIP SHA-256은 `753712094ff2500d8ab4b6184a27b2a0ad44bfece0236bd3788d01cd9c1ad7af`다.

## RC2 교정 사항

공개 `v0.2.0-rc.1`을 실제 Boards Manager로 설치한 뒤 package 사용자 예제 14개를 전부
Arduino CLI로 compile하고, NU54DK에서 Blink upload, SerialEcho 왕복 및 두 보드 NUS 양방향
전송을 실행했다. 이 과정에서 확인한 두 문제를 RC2에서 다음과 같이 교정했다.

- 기본 `CMSIS-DAP (pyOCD)`는 field 없이 단일 probe를 자동 선택한다. 별도
  `CMSIS-DAP with UID (pyOCD)` 경로는 필수 `CMSIS-DAP unique ID`를 Builder의 `--probe-id`로
  전달해, 둘 이상 연결된 상태에서도 나머지 보드를 분리하지 않고 안전하게 upload한다.
- `NUSPeripheral` 예제는 `received` event를 같은 `Serial`에 기록하지 않는다. BLE에서 받은
  byte는 Stream 경로로만 출력하고, 광고·연결·ready·해제·오류 상태만 사람이 읽는 로그로 남긴다.

RC1의 tag와 자산은 불변 기록으로 유지하지만 새 설치·검증에는 RC2를 사용한다.

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

| 항목 | 실제 결과 | v0.2.0 판정 |
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

RC2 공개 설치본은 격리 Boards Manager 설치와 `post_install`, package 사용자 예제 14/14
compile, `CMSIS-DAP with UID (pyOCD)` Blink upload와 대응 UART의
`NUCODE_M8_UPLOAD_READY`를 통과했다. 실제 UID는 공개 기록에 남기지 않았다.

RC2 설치본 NUS Peripheral/Central은 startup `BLE NUS ready`와 양방향 고유 payload 원문 연속
수신을 통과했고 RC1의 수신 상태 로그 삽입은 재현되지 않았다. 이 공개 예제 transparent bridge
HIL은 위 M16의 frame boundary·disconnect/reconnect 전문 HIL을 재실행한 것이 아니다.

## 설치·공개 상태

정식 `v0.2.0`은 다음 stable index와 GitHub Release를 사용한다. stable index는 최신순으로
`0.2.0`, `0.1.0`을 함께 제공하며 RC1·RC2 index와 자산은 검증 이력으로 보존한다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.2.0
```

정식 공개 산출물의 source commit, 크기와 SHA-256, 공개 시각 및 lifecycle 결과는
[v0.2.0 정식 릴리스 공개 기록](../../04_검증%20기록/21_v0.2.0_정식_릴리스_공개_기록.md)에
고정한다. RC2의 exact HIL을 stable exact HIL로 이름만 바꾸지 않으며, stable은 RC2와의
version-independent runtime payload 동등성과 공개 package 수명주기 검증을 함께 근거로 삼는다.

## 라이선스

NUCODE 자체 작성 코드는 MIT License다. ArduinoCore-API, NU54DK board package, Zephyr/NCS와
외부 prerequisite에는 각 원본 license와 notice가 적용된다. NCS, Nordic Toolchain, nRF Util,
pyOCD와 SEGGER J-Link Software를 Core ZIP 안에 임의 재배포하지 않는다. SPDX SBOM과 license
inventory는 구성요소 식별 자료이며 법률 자문을 대신하지 않는다.
