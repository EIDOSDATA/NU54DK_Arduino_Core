# NU54DK Arduino Core — 구성 프로필과 Arduino 예제 배포

| 항목 | 내용 |
| --- | --- |
| 문서 ID | BUILD-PROFILE-001 |
| 문서 개정 | 1.1 |
| 문서 상태 | 구현 기준선 — M13 완료 |
| 적용 제품 버전 | `v0.2.0` 이후 |
| 작성자 | Quantum / NUCODE |
| 관련 결정 | [ADR-0002](../00_사전%20리서치/02_Arduino_구성_프로필과_예제_노출_결정.md) |

---

## 1. 목적

이 문서는 Arduino IDE 사용자가 Zephyr Kconfig와 Devicetree를 직접 편집하지 않고 기능을
선택하는 build 계약과, package 설치 후 예제가 `파일 → 예제`에 나타나는 구조를 정의한다.

고급 사용자의 `prj.conf`/`app.overlay` 입력은 유지하되 기본 사용법과 분리한다. 최종 image는
계속 Loader 없는 Full Zephyr 정적 image이며 profile은 사전 빌드 firmware가 아니다.

---

## 2. 현재 구현 상태

현재 main의 예제 단일 원본은 표준 platform library 경로로 이동했다.

```text
libraries/NUCODE_NU54DK/examples/{Blink,InterruptButton,AnalogReadA0,PWMFade,SerialEcho}
libraries/SPI/examples/SPITransaction
libraries/Wire/examples/WirePmicId
```

공개 예제 7개에는 `prj.conf`와 `app.overlay`가 없다. 기본 `standard` profile이 GPIO,
Serial, Wire, SPI, ADC와 PWM의 검증된 설정을 제공하므로 일반 사용자는 `.ino`만 열어
compile/upload한다. Sketch sidecar는 공개 예제가 아닌 전문가용 마지막 override로만 남는다.

공개된 `v0.1.0` archive는 변경하지 않는다. 예제 경로 교정은 다음 배포 버전에 적용한다.

---

## 3. 디렉터리 계약

```text
variants/nu54dk/profiles/
├─ standard/
│  ├─ profile.json
│  ├─ prj.conf
│  └─ app.overlay
└─ <향후 검증된-profile>/

libraries/<NUCODE-library>/
├─ library.properties
├─ src/
├─ examples/
└─ zephyr/
   ├─ feature.yml
   ├─ Kconfig.conf
   └─ app.overlay
```

실제 구현 전에는 빈 profile 디렉터리를 만들지 않는다. 존재하는 profile은 build와 시험에서
사용되는 제품 입력이어야 한다.

---

## 4. Profile schema v1

`profile.json` schema v1은 다음 필드를 정확히 가진다.

```json
{
  "schema_version": 1,
  "id": "standard",
  "display_name": "Standard peripherals",
  "board": "nucode:zephyr:nu54dk",
  "zephyr_board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
  "ncs_version": "v3.4.0",
  "conf": "prj.conf",
  "overlay": "app.overlay",
  "features": ["gpio", "serial", "wire", "spi", "adc", "pwm"],
  "conflicts": [],
  "requires_hil": ["wire", "spi", "adc", "pwm"]
}
```

규칙은 다음과 같다.

- `schema_version`을 모르면 build를 중단한다.
- 상대 경로는 profile 디렉터리 밖으로 나갈 수 없다.
- profile ID, 모든 파일 내용과 builder schema version을 cache key에 넣는다.
- JSON 중복 key와 알 수 없는 필드는 기본적으로 거부한다.
- board/FQBN과 NCS version이 맞지 않으면 자동 보정하지 않는다.

---

## 5. Feature manifest schema v1

```json
{
  "schema_version": 1,
  "id": "nucode.ble",
  "requires": ["bluetooth"],
  "conf": ["Kconfig.conf"],
  "overlays": ["app.overlay"],
  "conflicts": ["radio.ieee802154.only"],
  "compatible_profiles": ["ble"]
}
```

`feature.yml`이라는 파일명을 사용하지만 schema v1 문법은 중복 key를 검출할 수 있는 UTF-8
JSON으로 고정한다. 일반 YAML 문법은 허용하지 않는다. manifest는 선언 데이터이며 command,
script, environment mutation 또는 임의 CMake 코드를 포함할 수 없다. 외부 library가 manifest를
설치했다고 자동 신뢰하지 않으며 초기 버전은 package에 포함된 NUCODE library만 허용한다.

---

## 6. Build Adapter 처리 순서

1. FQBN과 `boards.txt`의 profile option을 정규화한다.
2. Arduino library 탐색 전에 board/profile identity를 검증하고 provisional cache를 구성한다.
3. Arduino CLI가 생성한 source/include record에서 실제 선택된 bundled library를 수집한다.
4. 허용목록의 `zephyr/feature.yml`만 읽고 profile 요구 기능과 충돌을 검사한다.
5. platform → profile → 선택 feature → expert override 순서로 최종 app에 병합한다.
6. profile 및 선택 feature manifest/fragment hash로 최종 M9 cache key를 계산한다.
7. key가 바뀌면 context와 source record를 최종 workspace로 이관하고 pristine configure한다.
8. 최종 입력 목록과 hash를 `context.json`과 build manifest에 기록한다.

Arduino의 library 탐색은 Zephyr configure보다 늦게 끝나므로 feature library를 사용하는 최초
build는 provisional profile configure와 최종 feature configure의 두 단계가 될 수 있다. 각 cache
identity에서는 pristine configure를 한 번만 수행하며, 같은 최종 identity는 재사용한다.

include 문자열만 보고 기능을 추측하지 않는다. source record에 실제로 선택된 library와
manifest가 연결되어야 한다.

---

## 7. Arduino Tools 메뉴

Tools 메뉴는 사용자가 이해할 수 있는 결과 중심 이름을 사용한다.

```text
Tools → Feature set → Standard peripherals
```

Bluetooth LE나 저전력 profile은 해당 마일스톤의 기능·충돌·HIL 검증이 끝난 뒤에만 메뉴에
추가한다. 존재하지 않는 선택지를 먼저 노출하지 않는다.

각 항목은 독립 boolean 모음이 아니라 검증된 profile ID 하나를 선택한다. 선택하지 않은
세부 기능은 library manifest가 additive하게 요청할 수 있지만 profile이 금지한 충돌은
override하지 못한다.

`Advanced/custom`은 raw 설정을 자동으로 활성화하는 옵션이 아니다. Sketch sidecar가 있을 때
전문가 지원 범위와 diagnostic을 명확하게 표시하는 선택이다.

---

## 8. 예제 소유권

| 예제 | 소유 library | 이유 |
| --- | --- | --- |
| Blink | `NUCODE_NU54DK` | 보드 기본 GPIO |
| InterruptButton | `NUCODE_NU54DK` | 보드 버튼·LED 역할 |
| AnalogReadA0 | `NUCODE_NU54DK` | NU54DK A0 역할 |
| PWMFade | `NUCODE_NU54DK` | NU54DK PWM 역할 |
| SerialEcho | `NUCODE_NU54DK` | 보드 console Serial |
| WirePmicId | `Wire` | Wire transaction과 NU54DK PMIC 예시 |
| SPITransaction | `SPI` | SPI transaction 예시 |

새 기능 library는 자신의 예제, profile 요구사항과 검증을 함께 소유한다. 같은 `.ino`를 루트
예제나 문서 asset에 복사하지 않는다.

예제 폴더와 주 `.ino` 파일 이름은 정확히 같아야 한다. 한 예제는 독립적으로 열고 compile할
수 있어야 하며 개인 probe UID, COM 번호 또는 절대 경로를 포함하지 않는다.

---

## 9. Package 계약

Boards Manager archive에는 다음을 포함한다.

- `libraries/*/library.properties`
- `libraries/*/src/**`
- `libraries/*/examples/**`
- 구현된 경우 `libraries/*/zephyr/**`
- 구현된 경우 `variants/nu54dk/profiles/**`

루트 `examples/`는 package allowlist에 포함하지 않는다. source repository와 release archive가
같은 library example 구조를 사용한다.

공개된 stable version은 exact source commit뿐 아니라 해당 package builder commit에서도만
재생성한다. main의 후속 변경으로 같은 stable 파일 이름을 다시 만들지 않는다.

---

## 10. 자동 검증

### 예제 열거

```powershell
arduino-cli lib examples `
  --fqbn nucode:zephyr:nu54dk `
  --json
```

예상 library/Sketch 목록을 JSON으로 검사한다. 단순히 ZIP 안에 파일이 있는지만 확인하지 않는다.

### Compile matrix

- 모든 `NUCODE_NU54DK` 예제
- `WirePmicId`
- `SPITransaction`
- profile을 요구하는 각 feature library의 최소 예제
- 예제 두 개의 병렬 build
- profile 변경 후 cache invalidation
- sidecar가 없는 기본 사용자 경로
- 전문가 override positive/negative

### Package matrix

- ZIP에 library example 필수 경로 존재
- 루트 `examples/` 부재
- `library.properties` architecture 호환
- 설치 후 CLI example listing
- Arduino CLI 1.5.1의 IDE backend와 동일한 example listing 검증
- clean Windows Arduino IDE 시각적 메뉴 smoke는 M18 release gate에서 재확인

---

## 11. 오류 정책

| 오류 | 처리 |
| --- | --- |
| 알 수 없는 profile/schema | build 중단과 지원 version 표시 |
| library feature 충돌 | 두 요청자와 충돌 자원을 표시하고 중단 |
| 요구 module 없음 | 고정 NCS version과 필요한 module 표시 |
| expert override syntax 오류 | 원본 파일·행과 함께 실패 |
| 예제 sidecar 의존 잔존 | M13 release gate 실패 |
| IDE/CLI 예제 목록 누락 | package gate 실패 |

기능을 조용히 끄거나 다른 peripheral/profile로 자동 fallback하지 않는다.

---

## 12. M13 완료 체크리스트

- [x] profile schema와 resolver 구현
- [x] `boards.txt` curated menu 구현
- [x] library feature manifest resolver 구현
- [x] profile/feature/override hash를 cache와 evidence에 연결
- [x] M7 예제의 sidecar를 내부 설정으로 이전
- [x] 7개 예제 CLI 열거와 compile 자동화
- [x] Arduino IDE가 사용하는 CLI example listing에서 library별 정확한 예제 집합 검증
- [x] conflict/unknown schema/path traversal negative test
- [x] 사용자 가이드에서 raw Zephyr 설정을 기본 절차에서 제거

Arduino IDE의 실제 메뉴 렌더링을 사람이 다시 보는 항목은 기능 구현 판정과 분리해 M18 clean
Windows release gate에서 수행한다.
