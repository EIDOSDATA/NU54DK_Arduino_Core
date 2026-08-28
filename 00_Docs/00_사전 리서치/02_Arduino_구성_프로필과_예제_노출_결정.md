# ADR-0002 — Arduino 구성 프로필과 예제 노출 정책

| 항목 | 내용 |
| --- | --- |
| 문서 ID | ADR-0002 |
| 문서 개정 | 1.0 |
| 문서 상태 | **Accepted** |
| 결정일 | 2026-08-28 |
| 적용 제품 버전 | `v0.2.0` 이후 |
| 작성자 | Quantum / NUCODE |
| 관련 결정 | [ADR-0001 — Loader 없는 Native Full Zephyr 정적 빌드](01_개발_방식_비교_및_아키텍처_결정.md) |

---

## 1. 결정 요약

NU54DK Arduino Core는 Full Zephyr 빌드의 자유도를 유지하되 일반 Arduino 사용자가
`prj.conf`나 Devicetree overlay를 직접 편집하지 않아도 되게 한다.

표준 사용자 경로는 다음 두 입력으로 제한한다.

1. Arduino IDE의 보드·Tools 메뉴에서 검증된 기능 세트를 선택한다.
2. 필요한 Arduino library를 include하면 해당 library가 선언한 Zephyr 요구사항을 Build
   Adapter가 자동으로 반영한다.

Sketch 옆의 `prj.conf`와 `app.overlay`는 제거하지 않는다. 다만 이는 Zephyr를 이해하는
사용자를 위한 **전문가용 override**이며, 기본 예제나 일반 사용 절차의 필수 단계가 아니다.

Arduino 예제는 루트 `examples/`가 아니라 다음 표준 platform library 경로를 단일 원본으로
사용한다.

```text
libraries/<library>/examples/<Sketch>/<Sketch>.ino
```

---

## 2. 배경

Loader 없는 Full Zephyr 방식에서는 기능마다 Kconfig와 Devicetree 입력이 필요하다. 이 입력을
사용자에게 그대로 노출하면 다음 문제가 생긴다.

- Arduino 입문자가 Zephyr symbol과 DTS 문법을 알아야 한다.
- 예제를 복사하거나 Arduino IDE에서 `Save As`할 때 sidecar 설정이 누락될 수 있다.
- BLE, Thread, SPI/UART 충돌과 같은 조합 오류가 늦은 CMake 단계에서 드러난다.
- 여러 예제가 비슷한 설정을 복사해 시간이 지나면서 서로 달라진다.
- 라이브러리를 설치했지만 필요한 subsystem이 꺼져 있어 link 또는 runtime에서 실패한다.

반대로 모든 기능을 하나의 거대한 기본 이미지에서 항상 켜면 Flash/RAM 사용량, boot 시간,
충돌 가능성과 시험 행렬이 불필요하게 커진다. 따라서 **검증된 프로필 + library 기능 선언 +
전문가 override**의 3단계 구조를 채택한다.

---

## 3. 사용자 수준

| 수준 | 사용자가 다루는 것 | 설정 방식 |
| --- | --- | --- |
| 기본 | `.ino`, Arduino library, 보드 선택 | 기본 프로필 자동 적용 |
| 기능 선택 | Arduino IDE Tools 메뉴 | 검증된 curated profile 선택 |
| 고급 | Zephyr/NCS 공개 API | 선택 profile 위에 승인된 library feature 적용 |
| 전문가 | Kconfig/DTS를 직접 제어하는 프로젝트 | Sketch의 `prj.conf`·`app.overlay` override |

기본 및 기능 선택 사용자는 생성된 `.config`, `zephyr.dts` 또는 CMake 파일을 직접 수정하지
않는다. Build Adapter가 선택 결과와 출처를 build manifest에 기록한다.

---

## 4. 구성 입력과 병합 순서

구성은 다음 순서로 결정적으로 병합한다.

```text
보드 DTS와 platform 최소 설정
  → 선택한 NU54DK curated profile
  → 발견된 NUCODE library의 feature manifest
  → 전문가용 Sketch prj.conf/app.overlay
  → 충돌·금지 조합 검사
  → 최종 prj.conf/app.overlay 생성
```

### 4.1 Platform 최소 설정

- Arduino runtime과 필수 C++ 설정만 포함한다.
- Wire, SPI, BLE, Thread 같은 선택 subsystem을 모두 무조건 활성화하지 않는다.
- source template은 사용자가 수정하는 파일이 아니다.

### 4.2 Curated profile

전역 자원 또는 무선 stack처럼 조합 영향이 큰 선택을 관리한다. 목표 경로는 다음과 같다.

```text
variants/nu54dk/profiles/<profile-id>/
├─ profile.json
├─ prj.conf
└─ app.overlay
```

독립 체크박스를 무제한 추가하지 않는다. 실제로 함께 검증한 조합만 하나의 profile ID로
공개한다. profile ID와 모든 입력 hash는 cache key에 포함한다.

### 4.3 Library feature manifest

NUCODE가 제공하는 기능 library는 필요한 Zephyr 기능을 선언할 수 있다.

```text
libraries/<library>/
├─ library.properties
├─ src/
├─ examples/
└─ zephyr/
   ├─ feature.yml
   ├─ Kconfig.conf
   └─ app.overlay
```

`feature.yml`의 schema와 허용 key는 M13에서 고정한다. Build Adapter는 임의 shell command를
실행하지 않고 허용된 Kconfig fragment, overlay, module dependency와 conflict만 읽는다.
일반 third-party Arduino library에 manifest가 없으면 기본 Arduino library로 취급한다.

### 4.4 전문가 override

Sketch에 `prj.conf` 또는 `app.overlay`가 있으면 마지막 입력으로 반영한다. 다음 조건을
만족해야 한다.

- verbose log에 `expert override`라고 명시한다.
- 사용한 파일과 SHA-256을 build manifest에 기록한다.
- 보드 안전 규칙이나 소유권 충돌을 우회하지 못한다.
- 동일 peripheral을 두 driver가 소유하는 구성은 빌드 전에 실패한다.

---

## 5. 충돌 처리

다음 경우 자동 fallback이나 조용한 기능 비활성화를 하지 않는다.

- `spi00`과 `uart00`처럼 같은 하드웨어 instance를 동시에 요구함
- BLE/802.15.4 controller 또는 radio profile이 서로 양립하지 않음
- 같은 `chosen` 역할을 서로 다른 장치로 요구함
- 동일 pin을 상충하는 출력 peripheral이 소유함
- 요구한 NCS module이나 Kconfig symbol이 고정 NCS v3.4.0에 없음

오류는 feature 이름, 요청한 library/profile, 충돌 자원과 해결 가능한 profile을 함께 출력한다.

---

## 6. Arduino 예제 배포 결정

Arduino IDE 예제 메뉴는 platform bundled library의 `examples`를 기준으로 한다. 예제 소스의
현재 단일 원본은 다음과 같다.

```text
libraries/NUCODE_NU54DK/examples/
├─ Blink/
├─ InterruptButton/
├─ AnalogReadA0/
├─ PWMFade/
└─ SerialEcho/

libraries/Wire/examples/WirePmicId/
libraries/SPI/examples/SPITransaction/
```

루트 `examples/` 복사본은 두지 않는다. 기능별 library를 추가할 때 예제도 해당 library가
소유한다.

```text
libraries/NUCODE_BLE/examples/
libraries/NUCODE_Power/examples/
libraries/NUCODE_Watchdog/examples/
```

현재 M7 예제의 `prj.conf`와 `app.overlay`는 기존 Build Adapter 계약을 유지하기 위한 과도기
입력이다. M13에서 동일 설정을 profile/feature manifest로 이동하고 일반 예제 폴더에서는
제거한다.

---

## 7. 검증 계약

다음 검증을 모두 통과해야 예제 또는 profile 변경을 병합한다.

1. `arduino-cli lib examples -b nucode:zephyr:nu54dk --json`에 의도한 예제가 나타난다.
2. 배포 ZIP에 `libraries/*/examples`가 포함되고 루트 `examples/`는 없다.
3. 모든 공개 예제를 독립적으로 compile한다.
4. feature/profile 선택 결과가 최종 `.config`와 `zephyr.dts`에 나타난다.
5. 동일 입력은 같은 profile hash와 cache key를 만든다.
6. 충돌 profile은 명시한 오류 코드로 실패한다.
7. Arduino IDE의 `파일 → 예제`에서 수동 smoke test를 release gate에 포함한다.

---

## 8. 결과와 비용

### 장점

- Arduino 사용자는 `.ino`와 library 선택에 집중할 수 있다.
- Full Zephyr 전체 빌드와 NCS API 직접 사용 자유도를 유지한다.
- 지원 조합과 HIL 범위를 profile 단위로 관리할 수 있다.
- 예제와 기능 구현이 같은 library에 있어 변경 누락이 줄어든다.

### 비용

- feature manifest schema와 resolver를 유지해야 한다.
- profile 조합별 Flash/RAM 및 HIL 행렬이 필요하다.
- 전문가 override에는 일반 경로보다 제한된 지원 정책이 필요하다.

이 비용은 사용자에게 raw Zephyr 설정을 요구하거나 모든 기능을 항상 켜는 비용보다 낮다고
판단한다.

---

## 9. 기각한 대안

| 대안 | 기각 이유 |
| --- | --- |
| 모든 사용자에게 `prj.conf`/overlay 요구 | Arduino 사용성 목표와 맞지 않음 |
| 모든 기능을 기본 profile에서 활성화 | 자원 낭비, 충돌 및 검증 행렬 증가 |
| header 이름을 보고 기능 추측 | alias·간접 include 때문에 비결정적 |
| 기능 조합별 prebuilt firmware | Full Zephyr 자유도와 단일 build graph 원칙 훼손 |
| 루트 `examples/` 유지 | Arduino platform library 예제 열거 계약과 맞지 않음 |

---

## 10. 구현 연결

- 예제 경로 이동과 package/CLI 열거 검증: 이번 구조 개정에서 적용
- profile schema, Tools 메뉴와 feature resolver: M13
- 기존 M7 sidecar 설정의 내부 profile 이전: M13
- BLE 및 이후 기능 library의 manifest 적용: M16 이후

상세 순서는 [v0.2.0 구현 마일스톤](../01_아두이노%20코어%20설계/05_v0.2.0_구현_마일스톤.md)을
따른다.
