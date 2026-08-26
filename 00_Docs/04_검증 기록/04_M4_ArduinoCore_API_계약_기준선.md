# M4 ArduinoCore-API 계약 기준선

| 항목 | 값 |
| --- | --- |
| 상태 | 완료 |
| 검증일 | 2026-08-27 |
| 작성자 | Quantum / NUCODE |
| Core 기준 commit | `1c5b9d07dbf2` + 본 M4 변경 |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 읽기 전용 |
| NCS / Zephyr | NCS v3.4.0 / Zephyr 4.4.0 |
| target compiler | GNU Arm C++ 14.3.0, C++17 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| ArduinoCore-API | 1.5.2 / `cd91833d90b4fe50e428021ba5051e2b7ceafc84` |

---

## 1. 목적과 판정

M4는 Arduino API를 대량 구현하는 단계가 아니다. 재사용할 upstream API의 불변 revision,
source 배치, include 경계, ABI 확인 항목과 라이선스 보존 방식을 먼저 고정한다. 다음을
실제 완료 조건으로 사용했다.

- branch가 아닌 ArduinoCore-API 1.5.2의 정확한 commit을 고정한다.
- 공개 package에 포함할 원본 source와 라이선스를 저장소 안에 보존한다.
- upstream source와 NUCODE MIT source의 소유권을 구분한다.
- NCS v3.4.0의 NU54DK C++17 target에서 핵심 header 계약을 compile·link한다.
- upstream host suite를 실행할 수 없으면 제품 source를 임의 수정하지 않고 실패 위치와
  제외 사유를 기록한다.

이 기준을 모두 충족했으므로 M4 상태를 `완료`로 판정한다. `String`, `Print`, `Stream`,
`Serial` 또는 interrupt backend가 지원 완료됐다는 뜻은 아니다.

---

## 2. 고정 source와 무결성

### 2.1 포함 범위

`third_party/ArduinoCore-API`에는 고정 commit에서 다음 48개 파일만 가져왔다.

- `LICENSE`
- `README.md`
- `api/**`

upstream의 `.github`, 개발 설정과 `test/**`는 firmware package의 build 입력이 아니므로
vendor snapshot에 넣지 않았다. 시험할 때는 같은 commit의 임시 detached checkout을
사용했다. vendor 파일은 `.gitattributes`로 LF를 강제하며 local modification은 없다.

### 2.2 식별값

| 항목 | 값 |
| --- | --- |
| upstream repository tree | `e3ee9af96182bc45187a579f8b4c5050e59ccc2d` |
| upstream `api` tree | `e1223bd76ddcb72801f3a6509e4bcb5ca311294c` |
| `LICENSE` SHA-256 | `5749785c8bdefafcb5d798270ed0a967036fe2ca63dcedade1627565dfef81d2` |
| `README.md` SHA-256 | `2d9812d0e1ee222c73ba39ff959bb5e933b60c7b7b5b85b0ccc5d1ada97fd7a5` |
| `api/ArduinoAPI.h` SHA-256 | `421b66ccbbf038cef50df9860f7da13a6b4e92358b0550e52202b0aaabfc84ec` |
| 48개 파일 manifest SHA-256 | `2536845d333cbd9fb84cbb16cb5d80c8cd9cf2eaa4918f95902f9e34050d4e1e` |

manifest 값은 forward-slash relative path를 UTF-8 byte 순서로 정렬한
`path:파일-SHA-256` record를 UTF-8 LF와 마지막 LF로 연결해 계산했다. 전체 기계 판독 정보는
[`ArduinoCore-API.provenance.yml`](../../third_party/ArduinoCore-API.provenance.yml)에
보관한다.

---

## 3. 라이선스 경계

NUCODE가 작성한 Core와 시험 source는 저장소 최상위 MIT License를 적용한다. vendored
ArduinoCore-API는 MIT로 재표시하지 않는다.

| 범위 | 라이선스 |
| --- | --- |
| ArduinoCore-API 대부분의 `api/**` | `LGPL-2.1-or-later` |
| `api/Udp.h` | MIT |
| `api/deprecated-avr-comp/avr/pgmspace.h` | MIT |

component 표현은 `LGPL-2.1-or-later AND MIT`로 기록했다. 원본 license 전문, copyright와
각 파일 header를 유지하고 [`THIRD_PARTY_NOTICES.md`](../../third_party/THIRD_PARTY_NOTICES.md)에
MIT Core와 분리해 고지했다. 이 작업은 source 식별과 고지 기준선이며 법률 자문을
대신하지 않는다. binary/package 공개 전에는 실제 정적 링크 및 source 제공·재링크 의무를
배포 형태에 맞춰 다시 검토한다.

---

## 4. Zephyr include 계약

Core module이 활성화되면 `third_party/ArduinoCore-API` **root만** system include 경로에
추가한다.

~~~text
-isystem <CoreRoot>/third_party/ArduinoCore-API
~~~

사용자는 `<api/ArduinoAPI.h>`처럼 include한다. `third_party/ArduinoCore-API/api`를 include
root로 넣지 않는 이유는 upstream `api/String.h`가 C library의 소문자 `string.h`와
Windows의 case-insensitive 경로에서 충돌할 수 있기 때문이다. system include 지정은 원본
upstream warning을 제품 source warning과 분리한다.

`api/ArduinoAPI.h`가 없으면 module configure 단계에서 즉시 `FATAL_ERROR`를 발생시켜
불완전한 source archive를 명확히 진단한다.

---

## 5. Target 계약 시험

### 5.1 시험 범위

`tests/zephyr/m4_api_contract`는 build-only 시험이며 다음을 compile-time에 확인한다.

- `ARDUINO_API_VERSION == 10502`
- 기본 `pin_size_t`가 8-bit인 ABI
- `String` 공개 기본 생성자 계약
- `HardwareSerial`이 `Stream`을 상속하는 추상 interface임
- 기본 `attachInterrupt(pin_size_t, voidFuncPtr, PinStatus)` signature
- 기존 M3 runtime source와 upstream header 계약을 한 firmware image에서 link할 수 있음

upstream `Common.h`는 Sketch 함수를 C linkage 안에서 선언하지만 현재 M3 최소
`Arduino.h`는 `setup()`/`loop()`를 C++ linkage로 선언한다. 두 header를 같은 translation
unit에 섞어 생산 API를 조기에 변경하지 않았다. 계약 확인 TU와 기존 Sketch TU를 분리해
M4 build를 통과시켰으며, 생산 `Arduino.h` 통합과 최종 linkage 정리는 M6 backend 작업과
함께 수행한다.

### 5.2 Pristine 재현 명령

~~~powershell
$CoreRoot = "C:/Users/eidos/GitHub/NU54DK_Arduino_Core"
$BoardRoot = "$CoreRoot/board_package/NU54DK_Zephyr_DTS"

west -z "C:/ncs/v3.4.0/zephyr" build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  "$CoreRoot/tests/zephyr/m4_api_contract" `
  -d "$CoreRoot/build/m4-api-contract" `
  -- `
  -DBOARD_ROOT="$BoardRoot" `
  -DEXTRA_ZEPHYR_MODULES="$CoreRoot"
~~~

### 5.3 결과

| 항목 | 결과 |
| --- | --- |
| CMake configure | PASS |
| ArduinoCore-API system include root | PASS |
| Twister test discovery | PASS — `nucode.m4.api_contract` 1개 |
| 핵심 header/ABI static contract | PASS |
| 기존 Core runtime와 final link | PASS |
| FLASH | 29,904 B / 1,524 KB — 1.92% |
| RAM | 6,832 B / 256 KB — 2.61% |

보드 package는 build 전후 동일한 `fe65f2f0880b`로 깨끗하게 유지했다. 이 시험은 hardware
backend 동작 시험이 아니므로 flash나 HIL을 수행하지 않는다.

---

## 6. Upstream host suite 결과

고정 commit의 원본 `test/CMakeLists.txt`는 Catch2 v3.4.0을 FetchContent로 가져온다. 현재
Windows PC에서 CMake 4.2.1 호환 정책을 지정하고 MinGW GCC/G++ 6.3.0으로 원본 suite를
구성했다.

~~~powershell
cmake -S <upstream>/test -B <temp-build> -G Ninja `
  "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" `
  "-DCMAKE_C_COMPILER=C:/MinGW/bin/gcc.exe" `
  "-DCMAKE_CXX_COMPILER=C:/MinGW/bin/g++.exe"
cmake --build <temp-build> --parallel
~~~

- configure: PASS
- Catch2 build: FAIL
- 중단 위치: Catch2 `catch_reporter_junit.cpp`
- 진단: MinGW.org GCC 6.3.0 환경에 `gmtime_s` 선언이 없음
- ArduinoCore-API test executable: 생성 전
- 실제 upstream test case: 실행되지 않음

이 결과는 ArduinoCore-API DUT compile/test 실패가 아니라 현재 host compiler와 upstream이
고정한 Catch2 harness 조합의 실패다. upstream 또는 vendored 제품 source를 수정해 통과로
위장하지 않았다. M4의 target 계약은 실제 NCS GCC 14.3.0에서 별도로 통과했으며, 공통
source를 link하는 M6에서는 최신 host compiler CI와 target semantic test를 추가해야 한다.

---

## 7. 후속 경계

M4 완료가 다음 기능을 의미하지 않는다.

- `String.cpp`, `Print.cpp`, `Stream.cpp`, `Common.cpp`의 제품 link
- `Serial`, GPIO interrupt, Wire 또는 SPI hardware backend
- upstream 전체 API의 NU54DK 지원 선언
- 일반 Arduino library corpus 호환
- LGPL binary 배포 의무의 최종 법률 판단

M5는 이 고정 snapshot을 build input으로 사용해 Arduino CLI 수직 경로를 검증할 수 있다.
M6는 공통 source와 생산 `Arduino.h`의 type/linkage를 한 번만 정의하도록 통합하고 실제
semantic test를 추가해야 한다.
