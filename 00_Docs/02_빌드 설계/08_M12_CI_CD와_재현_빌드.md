# CI/CD와 재현 빌드 — M12~M17 현재 계약

| 계층 | 실행 환경 | 목적 |
| --- | --- | --- |
| Software gates | GitHub-hosted Ubuntu/Windows | 계약, unit, 문서, package, 예제 discovery |
| Reproducible builds | 고정 Nordic container + Windows | Zephyr/Arduino/M14/M17 build gate |
| NU54DK HIL | 승인된 self-hosted Windows runner | pyOCD upload와 UART 실기 |

CI는 지원 범위를 증명하는 gate이지 Release를 자동 승인하는 시스템이 아니다. 정확한 run ID,
artifact hash와 당시 판정은 [M12 기준선](<../04_검증 기록/14_M12_CI_CD_기준선.md>)과
[M17 기준선](<../04_검증 기록/19_M17_NCS_기능과_예제_Coverage_기준선.md>)에 보존한다.

---

## 1. Software gates

[`m12-software-gates.yml`](../../.github/workflows/m12-software-gates.yml)은 pull request,
`main` push와 수동 실행에서 다음 job을 수행한다.

| Job | 현재 검사 |
| --- | --- |
| `contract` | lock file, workflow trigger/권한, pin과 board submodule 경계 |
| `host` | Python host unit와 Windows PowerShell 계약 |
| `core-semantic` | M14 Core C++ native semantic runtime |
| `documents` | tracked Markdown UTF-8과 local link |
| `package` | Boards Manager package 2회 재현성과 strict validation |
| `example-discovery` | Arduino CLI `1.5.1`에서 현재 소스 트리를 임시 platform으로 설치해 예제 19개 열거 |

Checkout은 submodule을 recursive로 받고 full history를 사용한다. Workflow permission은
`contents: read`이며 같은 ref의 중복 실행은 취소한다.

M12와 정식 `v0.2.0`의 역사적 기준은 public library 4개·예제 14개다. 현재 `v0.3.0` 개발 트리는
`NUCODE_BLE_Security`를 포함한 library 5개·예제 19개이며, 별도 Arduino CLI 개발 검증에서
19/19 compile을 통과했다. 현재 discovery gate의 19개 기대값을 과거 `v0.2.0` artifact 기록에
소급 적용하지 않는다.

로컬 진입점은 다음과 같다.

~~~text
python tools/ci/run_m12_gate.py contract
python tools/ci/run_m12_gate.py host
python tools/ci/run_m12_gate.py docs
python tools/ci/run_m12_gate.py package
python tools/ci/run_m12_gate.py examples --arduino-cli <exact-path>
~~~

---

## 2. 재현 Build workflow

[`m12-reproducible-build.yml`](../../.github/workflows/m12-reproducible-build.yml)은 `main` push와
수동 실행에서 Linux와 Windows build를 분리한다.

### 2.1 Linux / pinned Nordic container

1. `ncs-3.4.0.lock.json`과 workflow pin을 검증한다.
2. exact west workspace를 준비하고 cache key를 lock에서 계산한다.
3. `run_zephyr_build.py`로 대표 Zephyr/Twister build-only suite를 실행한다.
4. `run_m17_feasibility.py`로 NCS 기능의 official control과 NU54DK 적용 가능성을 기록한다.
5. `run_m14_qemu.py`로 Core C++ policy를 QEMU에서 실행한다.
6. 결과를 14일 보존 artifact로 게시한다.

M17의 Thread/Matter/IEEE 802.15.4 feasibility PASS는 build 적용 가능성 기록이며 v0.2.0의
Arduino runtime 정식 지원을 뜻하지 않는다.

### 2.2 Windows / pinned prerequisites

1. Python `3.12.10`, Arduino CLI `1.5.1`과 고정 Nordic prerequisite를 준비한다.
2. 설치된 NCS/Zephyr/board revision을 lock과 대조한다.
3. `tests/arduino-cli/run_smoke.py`의 `blink`, `m6`, `m7`, `examples` suite를 실행한다.
4. `run_m17_external_arduino.py`로 고정한 외부 Arduino library를 격리 설치·compile한다.
5. Wire/SPI feature provenance를 확인하고 결과를 14일 보존 artifact로 게시한다.

Windows의 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core` cache는 prerequisite 상태와 도구 경로를
재사용하는 CI 속도 최적화일 뿐 gate의 source가 아니다. Build Adapter의
`%LOCALAPPDATA%\NU54\c` cache를 보존하는 계약도 아니다. 이 cache가 없어도 exact prerequisite와
source에서 같은 검사를 다시 수행할 수 있어야 한다.

---

## 3. M17 gate 경계

현재 CI에 연결된 M17 검사는 두 종류다.

| Gate | 확인하는 것 | 확인하지 않는 것 |
| --- | --- | --- |
| NCS feasibility | 고정 NCS sample의 official control과 NU54DK build 적용 가능성 | v0.2.0 runtime 지원 선언 |
| External Arduino | 고정 revision 외부 library compile과 Wire/SPI feature 선택 | 임의 최신 library 전체 호환성 |

[`m17_coverage.py`](../../tools/coverage/m17_coverage.py)는
[`coverage/ncs-v3.4.0`](../../coverage/ncs-v3.4.0)의 manifest, record와 pin을 검증한다. Dataset은
NCS `v3.4.0`에 고정한다. upstream 최신 branch를 CI에서 암묵적으로 따라가지 않는다.

---

## 4. Exact dependency lock

단일 원본은
[`ncs-3.4.0.lock.json`](../../tools/ci/ncs-3.4.0.lock.json)과
[`m17-external-libraries.lock.json`](../../tools/ci/m17-external-libraries.lock.json)이다.

| 항목 | 현재 고정 값 |
| --- | --- |
| NCS | tag `v3.4.0`, revision `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0`, revision `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Linux container | `ghcr.io/nrfconnect/sdk-nrf-toolchain` digest `sha256:f1dca44678dae83e37404e33f369786f5b2ffe2ed497eec1815f66c3a868bace` |
| Windows toolchain bundle | `dcbdc366a1` |
| Arduino CLI | `1.5.1` |

GitHub Actions도 tag가 아니라 workflow에 적힌 commit SHA로 고정한다. Lock 또는 action pin을
바꾸는 변경은 build 결과와 함께 검토해야 하며, 문서의 복사본만 수정해서는 안 된다.

Nordic container, NCS와 Toolchain은 프로젝트 artifact에 재배포하지 않는다. CI는 upstream
공식 배포물을 exact identity로 사용하며 license/provenance 경계는 lock과 package inventory에
기록한다.

---

## 5. Physical NU54DK HIL

[`m12-nu54dk-hil.yml`](../../.github/workflows/m12-nu54dk-hil.yml)은 자동 PR gate가 아니라
`workflow_dispatch` 전용이다. 다음 label을 가진 승인된 runner에서만 실행한다.

~~~text
self-hosted, Windows, X64, nu54dk-hil
~~~

Repository secret으로 명시적 HIL 승인을 확인한 뒤 exact source/NCS를 검증하고 M8 pyOCD
upload와 UART READY를 실행한다. Hardware evidence는 30일 보존한다. Probe 연결, 전원, UART
배선과 runner 보안은 운영자가 관리한다.

HIL workflow가 존재하거나 queue에 들어갔다는 사실은 PASS가 아니다. 완료 artifact와 검증
기록이 있어야 실기 판정에 사용할 수 있다. `v0.3.0` 개발 검증은 AC-01 exact commit
`ac10ba3b253bd6bf76bcf73aa2c79278304908a4`, M19/M20 exact commit
`0103a8434ac205a953c981385ae26a2a64aeeccc`, M21 exact commit
`065d4f573618aca5da1e715915622e987208b775`의 HIL PASS를 각각 검증 기록에 고정한다. M21 host
38/38도 PASS했다. M21 진행 중 — 자동 검증 완료, Windows/스마트폰 OS HID pairing·실제 키 입력 수동 확인 대기 상태다.

---

## 6. Evidence와 Release 경계

- software/reproducible build artifact: 14일
- physical HIL artifact: 30일
- 정식 기준선: `00_Docs/04_검증 기록`의 append-only 기록
- 공개 Release hash/SBOM/license: 버전별 릴리스 문서와 GitHub Release

CI artifact는 임시 진단 자료이므로 정식 기준선에 필요한 결과는 commit, workflow, lock,
artifact identity와 함께 검증 기록으로 승격한다. 과거 run ID나 로그 전체를 이 설계 문서에
복사하지 않는다.

Workflow는 package를 검증하지만 tag 생성, stable index 변경, GitHub Release 공개 또는
latest 지정은 자동으로 수행하지 않는다. 공개에는 별도 사람 승인과 릴리스 절차가 필요하다.

---

## 7. 관련 구현과 기록

- [`verify_ci_lock.py`](../../tools/ci/verify_ci_lock.py)
- [`prepare_ncs_workspace.py`](../../tools/ci/prepare_ncs_workspace.py)
- [`run_zephyr_build.py`](../../tools/ci/run_zephyr_build.py)
- [`run_m14_qemu.py`](../../tools/ci/run_m14_qemu.py)
- [`run_m17_feasibility.py`](../../tools/ci/run_m17_feasibility.py)
- [`run_m17_external_arduino.py`](../../tools/ci/run_m17_external_arduino.py)
- [M12 CI/CD 기준선](<../04_검증 기록/14_M12_CI_CD_기준선.md>)
- [M17 NCS 기능과 예제 coverage 기준선](<../04_검증 기록/19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [M18 공개 검증과 RC2 교정](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
- [AC-01 GPIO 호환성 검증](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)
- [M19 BLE Core/GAP 검증](<../04_검증 기록/23_M19_BLE_Core_GAP_검증.md>)
- [M20 범용 GATT 검증](<../04_검증 기록/24_M20_범용_GATT_검증.md>)
- [M21 BLE 보안과 표준 Profile 검증](<../04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)
