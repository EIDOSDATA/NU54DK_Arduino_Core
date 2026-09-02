# ADR-0002 — Arduino 구성 프로필과 예제 노출 정책

| 항목 | 내용 |
| --- | --- |
| 문서 ID | ADR-0002 |
| 문서 개정 | 2.1 |
| 문서 상태 | **Accepted** |
| 결정일 | 2026-08-28 |
| 적용 범위 | `v0.2.0` 이후 구성 UX와 Arduino 예제 소유권 |
| 작성자 | Quantum / NUCODE |
| 관련 결정 | [ADR-0001 — Loader 없는 Native Full Zephyr 정적 빌드](01_개발_방식_비교_및_아키텍처_결정.md) |

> 이 ADR은 구성 UX를 선택한 이유와 안정된 정책만 소유한다. 실제 schema, fragment, profile,
> 예제 목록과 검증 결과는 구현·검증 문서에서 관리한다.

---

## 1. 결정

NU54DK Arduino Core는 Full Zephyr build의 자유도를 유지하되 일반 사용자가 `prj.conf`나
Devicetree overlay를 직접 작성하지 않아도 되게 한다.

표준 사용자 경로는 다음 두 입력으로 구성한다.

1. Arduino IDE의 보드·Tools 메뉴에서 검증된 feature set을 선택한다.
2. Arduino library를 include하면 승인된 Zephyr 요구사항을 Build Adapter가 반영한다.

Sketch의 `prj.conf`와 `app.overlay`는 Zephyr/NCS를 이해하는 사용자의 **전문가용 override**로
유지하되, 기본 예제나 일반 설치 절차의 필수 입력으로 사용하지 않는다.

Arduino 사용자 예제는 다음 platform library 경로를 단일 원본으로 사용한다.

```text
libraries/<library>/examples/<Sketch>/<Sketch>.ino
```

루트 `examples/`에 같은 Sketch의 복사본을 두지 않는다.

---

## 2. 결정 이유

Full Zephyr 구조에서는 기능에 따라 Kconfig, Devicetree, module과 partition 입력이 달라진다.
이를 일반 사용자에게 그대로 노출하면 다음 문제가 생긴다.

- Arduino 사용자가 Zephyr symbol과 DTS 문법을 먼저 알아야 한다.
- 예제를 복사하거나 `Save As`할 때 sidecar 설정이 누락될 수 있다.
- Resource와 pin 충돌이 늦은 configure 단계에서 드러날 수 있다.
- 비슷한 설정의 복사본이 시간이 지나면서 서로 달라질 수 있다.
- Library는 발견됐지만 필요한 subsystem이 꺼져 build 또는 runtime에서 실패할 수 있다.

반대로 모든 subsystem을 하나의 기본 image에서 항상 켜면 flash/RAM, boot 시간, resource 충돌과
시험 matrix가 불필요하게 커진다. 따라서 **검증된 profile + library feature + 전문가 override**
세 계층을 채택한다.

---

## 3. 사용자와 구성 경계

| 수준 | 사용자가 다루는 것 | 구성 방식 |
| --- | --- | --- |
| 기본 | `.ino`, library와 보드 선택 | 기본 profile 자동 적용 |
| 기능 선택 | Arduino IDE Tools 메뉴 | 검증된 curated feature set 선택 |
| 고급 | Zephyr/NCS 공개 API | Profile과 승인된 library feature 사용 |
| 전문가 | Kconfig/DTS project | Sketch의 명시적 override 사용 |

기본·기능 선택 사용자는 생성된 `.config`, `zephyr.dts`와 CMake 파일을 수정하지 않는다. 고급
사용자의 Zephyr/NCS 직접 사용은 유지하지만 portable Arduino API와 같은 호환성 등급으로
표시하지 않는다.

구성은 다음 순서로 결정적으로 병합한다.

```text
보드 DTS와 platform 최소 설정
  → curated profile
  → NUCODE library feature
  → 전문가용 Sketch override
  → 충돌·금지 조합 검사
  → 최종 Zephyr 구성
```

같은 입력은 같은 resolved manifest와 cache key를 만들어야 한다. Build Adapter는 승인된
declarative field만 읽고 임의 shell command를 실행하지 않으며, profile·feature·override의
출처와 hash를 build manifest에 기록한다.

검증하지 않은 독립 checkbox 조합을 무제한 공개하지 않는다. 실제로 함께 build·시험한 조합만
Tools 메뉴에 제공한다. 일반 third-party library에 NUCODE metadata가 없으면 표준 Arduino
library로 취급하고 header 이름만 보고 Zephyr 기능을 추측하지 않는다.

### 메모리 layout 선택

Loaderless 제품선의 기본값은 **단일 application이 영구 저장소를 제외한 RRAM 전체를 사용하는
layout**이다. 향후 boot/update 기능을 사용하지 않는 사용자에게 MCUboot 예약과 두 번째 image
slot 비용을 기본으로 부과하지 않는다.

MCUboot/DFU, signed update와 rollback이 필요한 사용자는 `v0.4.0` M24에서 제공할 검증된 고급
Memory layout을 명시적으로 선택한다. 이 선택은 단순 Devicetree 조각이 아니라 code partition,
linker 최대 범위, Arduino maximum size, storage 주소와 migration 정책을 묶은 profile 계약이다.
Tools 메뉴에는 임의 byte 입력보다 시험한 preset만 제공한다. 전문가 `app.overlay`도 같은 충돌
검사와 linker assertion을 통과할 때만 지원 조합으로 인정한다.

---

## 4. 충돌과 신뢰 경계

다음 상황에서 조용한 fallback이나 임의 기능 비활성화를 하지 않는다.

- 같은 hardware instance를 둘 이상의 peripheral이 요구함
- 서로 양립하지 않는 radio/controller profile을 함께 선택함
- 같은 `chosen` 역할이나 pin을 상충하는 소비자가 요구함
- application, update slot, LittleFS와 Settings partition이 겹치거나 RRAM 끝을 벗어남
- Devicetree code partition, linker FLASH 범위와 Arduino maximum size가 서로 다름
- 고정 NCS/Zephyr에 없는 module, symbol 또는 binding을 요구함

가능하면 Zephyr configure 전에 실패하고 요청한 profile·feature, 충돌 resource, 구성 출처와
해결 가능한 검증 profile을 표시한다. 전문가 override도 보드 안전 규칙과 resource ownership을
우회하지 못하며, 검증하지 않은 조합을 정식 지원으로 자동 승격하지 않는다.

---

## 5. 예제 소유권

공개 예제는 API나 기능을 소유한 library 아래에 둔다.

- 보드·GPIO·Serial·board/system 기능은 보드 library가 소유한다.
- Wire와 SPI 예제는 각 Arduino API library가 소유한다.
- BLE처럼 독립 subsystem인 기능은 해당 기능 library가 소유한다.
- Zephyr driver 자체 검증은 native sample 또는 test가 소유한다.

예제 폴더와 주 `.ino` 이름은 같아야 한다. Package allowlist, discovery test와 release gate는
같은 경로를 사용한다. 실제 예제 목록과 개수는 ADR에 고정하지 않고
[저장소 구조와 소유권](../01_아두이노%20코어%20설계/01_저장소_폴더_구조.md)과 각 library의
`examples` 디렉터리를 따른다.

---

## 6. 결과와 검증 원칙

이 결정으로 일반 사용자는 `.ino`, library와 검증된 Tools 선택에 집중하면서 Full Zephyr build와
공개 Zephyr/NCS API 사용 자유를 유지한다. 대신 profile·feature schema, resolver, resource
diagnostic과 검증 조합별 build/HIL matrix를 유지해야 한다.

Profile, feature 또는 공개 예제를 바꿀 때 다음을 확인한다.

1. Arduino CLI와 IDE가 의도한 예제를 열거하고 모든 package 예제가 compile된다.
2. Package에 library 예제만 포함되며 중복 루트 예제가 없다.
3. 선택 결과가 최종 `.config`와 `zephyr.dts`에 나타난다.
4. 동일 입력이 같은 manifest와 cache key를 만든다.
5. 충돌·금지 조합은 명시적 오류로 실패한다.
6. Hardware 의존 기능은 target build와 필요한 HIL을 구분해 연결한다.

예제 compile PASS를 hardware 동작 PASS로 확대하지 않는다.

---

## 7. 기각한 대안

| 대안 | 기각 이유 |
| --- | --- |
| 모든 사용자에게 raw Zephyr 설정 요구 | Arduino 사용성 목표와 맞지 않음 |
| 모든 기능을 기본 profile에서 활성화 | Resource 낭비, 충돌과 검증 matrix 증가 |
| Header 이름으로 기능 자동 추측 | Alias와 간접 include 때문에 비결정적 |
| 기능 조합별 prebuilt firmware | Full Zephyr 자유도와 단일 build graph 원칙 훼손 |
| 루트와 library 예제를 함께 유지 | Arduino 예제 열거와 단일 원본 원칙 훼손 |

---

## 8. 구현과 증거

구체 schema, 파일명, 현재 profile과 예제 목록은 다음 문서를 따른다.

- [구성 프로필과 Arduino 예제 배포](<../02_빌드 설계/07_구성_프로필과_Arduino_예제_배포.md>)
- [M13 구성 profile 검증](<../04_검증 기록/15_M13_구성_프로필_검증.md>)
- [저장소 구조와 소유권](../01_아두이노%20코어%20설계/01_저장소_폴더_구조.md)
- [v0.2.0 구현 마일스톤](../01_아두이노%20코어%20설계/05_v0.2.0_구현_마일스톤.md)

병합 우선순위, 신뢰 경계나 예제 소유권을 바꿀 때는 이 ADR을 개정하거나 후속 ADR을 추가한다.

---

## 9. 결정 이력

| 일자 | 상태 | 내용 |
| --- | --- | --- |
| 2026-08-28 | Accepted | Curated profile, library feature와 전문가 override 계층 채택 |
| 2026-08-28 | Accepted | Arduino 예제를 platform library 경로의 단일 원본으로 결정 |
| 2026-08-31 | Refined | 구현 목록과 미래형 설명을 제거하고 결정 중심으로 축약 |
| 2026-09-02 | Refined | Loaderless 단일 application을 기본값으로, MCUboot/DFU dual-slot을 검증된 고급 layout으로 분리 |
