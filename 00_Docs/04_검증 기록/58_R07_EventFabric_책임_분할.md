# R07 — EventFabric 책임 분할

시작 source `8b6cb97`. 상태: 완료. 종료 commit은 EventFabric 분할 구현 commit으로 식별한다. public header/API, 상태 전이, 기존 mutex와
metadata 초기화 순서를 보존하는 기계적 추출이다. R06와 분리해 구현하며 새 실기는 없다.

## 구현 전 대응표

| 기존 EventFabric.cpp 책임 | 변경 파일 | 상태·동기화·호출 경계 | 생성물과 검증 |
| --- | --- | --- | --- |
| handle factory·singleton | EventFabric.cpp | 기존 함수 static handle 배열과 singleton 유지 | public symbol/header 동일 |
| context type·용량 상수 | internal/event/EventFabricInternal.h | 내부 accessor 타입, writable extern 없음 | 내부 header만 추가 |
| context 배열·검색·공통 acquire/release·metadata 초기화 | internal/event/EventFabricRegistry.cpp | 한 저장소와 한 mutex, 기존 SYS_INIT 순서/우선순위 유지 | metadata/전체 instance lookup |
| TIMER 설정·비교·task/event | internal/event/TimerFabric.cpp | registry context와 같은 mutex, thread 상태 연산 | 기존 clock/endpoint 계약 |
| EGU channel·task/event | internal/event/EguFabric.cpp | registry context와 같은 mutex | acquire/release/trigger |
| GPIOTE pin/route·task/event | internal/event/GpioteFabric.cpp | registry context와 같은 mutex, pin 상태 보존 | pin lease·GPIO 순서 |
| DPPI endpoint 검증·연결·channel/group | internal/event/DppiFabric.cpp | registry context와 같은 mutex, 고정 4 subscriber | invalid/domain/중복/연결·해제·회수 |
| PPIB bridge channel·task/event | internal/event/PpibFabric.cpp | registry context와 같은 mutex | bridge domain/metadata |

변경 파일은 `CONFIG_NUCODE_ARDUINO_EVENT_FABRIC`의 기존 CMake 분기에 각각 한 번 등록한다.
선택하지 않은 구성은 어느 구현 파일도 포함하지 않는다. 새 HAL 계층은 도입하지 않는다.
현재 별도 사용자 ISR callback/queue는 없으며 thread 상태 변경은 기존 mutex가 보호한다.
조회/endpoint 함수의 기존 lock 유무와 초기화 뒤 register metadata read도 그대로 유지한다.
mutex 자체는 registry 파일의 private storage이고 내부 참조 accessor로만 공유한다.

## 검증 계획

분할 전 현재 Event target `nucode.m25.event` 1/1을 `C:/r7pre`에 build-only로 고정했다.
공개 header bytes·기존 함수 body token·symbol/메모리, production DPPI Host 회귀,
선택/비선택 target 및 pair image를 비교한다. 전체 Host/contract/inventory/docs/style도 검사한다.
예전 T11 PASS와 새 build/mock 결과를 current-source physical PASS로 사용하지 않는다.

## 결과

| 검사 | 결과 |
| --- | --- |
| 공개 header | 전체 bytes 동일 |
| 다섯 peripheral 본문 | whitespace·mutex 참조 accessor 치환 외 token 동일 |
| DPPI production Host | 전/후 7개 시나리오 PASS, 4 thread × 500회 연결·해제 포함 |
| 선택/비선택 target | Event·M3 runtime·DUT/peer 4/4 build-only PASS |
| CMake source 소속 | 선택 구성 7개 파일 각각 한 번, 비선택 구성 0개 |
| Host 전체 | 618개 중 616 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / C/C++/ino 275개 PASS |
| current-source T11·T12 실기 | NOT RUN |

같은 Event target의 flash는 97576 → 97264 bytes,
RAM은 58752 → 58752 bytes다. 유지된 context table·mutex object 크기가
동일하고 기존에 링크된 공개 함수 symbol의 누락은 없다. 파일 경계가 생겨 각 peripheral의
기존 `instance()` 함수 5개가 추가로 링크되며 public API가 새로 생긴 것은 아니다.
이 수치는 특정 Event contract image의 결과이며 전체 성능 개선 또는 실기 PASS를 뜻하지 않는다.

Host는 실제 DPPI/registry/factory 구현을 컴파일하고 endpoint register·resource allocator를
mock으로 교체했다. 비교 기준은 분할 전 EventFabric.cpp에서 같은 registry/DPPI 본문을
그대로 뽑은 TU이며, 사용하지 않는 다른 backend는 실행되면 abort한다. 잘못된 endpoint,
domain/role, 중복 channel, subscriber 한도와 재연결, disconnect, release, ISR 거부를 검사했다.
TIMER·EGU·GPIOTE·PPIB의 하드웨어 동작은 Host 결과로 승격하지 않는다.

분할 전 Event target은 R06-B 검증 중 선행 생성한 것이므로 당시 working tree의 build-only
기준선이다. 이때 EventFabric.cpp bytes는 R07 시작 source와 동일했다. 원시 identity를
그대로 보존하며 최종 clean source의 HIL 근거로 바꾸지 않는다.

[소스·gate](evidence/r07-8b6cb97/software-and-source.json),
[본문/Host 비교](evidence/r07-8b6cb97/comparison.json),
[symbol·메모리·source 소속](evidence/r07-8b6cb97/target-comparison.json),
[target 결과](evidence/r07-8b6cb97/target-build.json)에 연결한다.
초기 nrfx include 누락과 Host 링크 준비 실패는 [실패 기록](evidence/r07-8b6cb97/initial-failures.json)에
보존했다. 공개 API/ABI·enum·singleton·CLI·schema·partition·저장 format·SDK·board·공개 자산은
변경하지 않았다. package는 기존 cores 하위 포함 정책을 유지하며 최종 실제 설치 ZIP 전체
예제 검증은 R13의 exact source gate로 수행한다.

다음 R08은 기존 IoResourceManager의 identity/충돌 정책과 예약·commit·rollback 경계를
분리하고 RuntimePeripheralRoute의 phase와 실제 획득 자원 기록을 분리한다.
부분 pin handover·PM·pinctrl 실패에서 남은 lease와 fail-closed 상태를 먼저 Host로 고정한다.
