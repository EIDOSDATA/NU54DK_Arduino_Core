# 232 — M31 메모리 최적화 P1 GATT Inline Value

## 1. 판정

2026-09-23 adaptive build declaration에 `ble.gatt-inline-value-payload` capacity를 추가하고,
`CONFIG_NUCODE_BLE_GATT_INLINE_VALUE_SIZE`가 caller-owned buffer를 지정하지 않은
`BLECharacteristic`·`BLEDescriptor`의 실제 cached value 배열 크기를 결정하도록 연결했다.
범위는 1~512 B, aggregation은 `maximum`이다. 선언이 없으면 기존 512 B를 유지한다.

공개 `maximum_value_length`와 caller-owned buffer overload의 상한은 512 B 그대로다. inline 생성자가
요청한 capacity가 선언값보다 크면 내부 pointer와 capacity를 활성화하지 않아 이후 `setValue()`와
schema 등록이 fail-closed된다. 64 B보다 큰 값을 실제로 보존할 application은 image 수명의 고정
caller-owned buffer를 전달하면 된다.

## 2. 동일 1×1/1-link GATT fixture 비교

| 항목 | 512 B inline value | 64 B inline value | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 59,786 B | 59,338 B | 448 B |
| `fixtureValue` 객체 | 584 B | 136 B | 448 B |
| RAM headroom | 202,358 B | 202,806 B | +448 B |
| FLASH | 192,248 B | 192,228 B | 20 B |

GATT role RAM 상한은 61,000 B에서 60,000 B로 낮췄다. 객체 하나당 `(512-64)=448 B`가 감소하며,
descriptor를 inline으로 선언하는 schema도 객체마다 같은 절감을 얻는다. client-only Central 예제는
server value 객체를 만들지 않으므로 RAM 수치가 변하지 않는 것이 정상이다.

## 3. 호환과 실패 경계

- `maximum_value_length`는 512 B로 유지해 공개 long read/write 계약을 줄이지 않는다.
- 선언 없는 `standard`/`ble`과 기본 Host build의 inline 배열은 512 B를 유지한다.
- 64 B bounded Host build에서 inline object는 64 B set을 허용하고 65 B set을 거부한다.
- 같은 bounded image에서도 caller-owned 512 B buffer 생성자는 capacity 512 B와 65 B set을 허용한다.
- public header와 구현은 같은 generated Kconfig를 사용하므로 객체 layout과 constructor 경계가 같다.

## 4. 회귀

| 검증 | 결과 |
| --- | --- |
| capacity resolver·공개/구현 정적 계약·GATT Host 대상 | 57 PASS |
| R12 기본 512 B GATT lifecycle | 24 scenario PASS |
| R12 64 B inline·caller-owned 512 B 경계 | PASS |
| 전체 Host gate | 1,479 PASS, 2 skip |
| Markdown UTF-8·저장소 내부 link gate | 387 PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS |
| adaptive GATT final Kconfig·60,000 B ceiling | PASS |
| 실제 `CustomGattPeripheral` adaptive clean compile | PASS, FLASH 198,628 B, RAM 59,519 B |
| 실제 `CustomGattCentral` adaptive clean compile | PASS, FLASH 199,100 B, RAM 59,214 B |
| 물리 HIL | NOT RUN — compile-time object layout과 Host cached value 경계 범위 |

## 5. 남은 P1 경계

inline value는 객체별 실제 요청 capacity가 아니라 image 전체 선언 최대값을 사용한다. C++ object layout은
runtime constructor 인자로 달라질 수 없기 때문이다. 더 작은 schema별 pool로 옮기려면 Bluetooth 시작 전
값 설정과 static constructor 순서, 미등록 객체, descriptor ownership, caller-owned buffer 호환을 함께
재설계해야 한다. 현재 P1은 server-only/client-only source/state 분리와 shared TX pool 수명을 계속 조사한다.
