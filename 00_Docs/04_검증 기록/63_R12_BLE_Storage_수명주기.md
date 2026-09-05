# R12 BLE·Storage 수명주기 구조 확대

상태: 착수. R11 `86b53f8` 뒤의 T14/T15 software 회귀다. current-source T11 이후의 물리 시험은 미실행이다.

| 단계 | 책임 | 보존·검증할 계약 |
| --- | --- | --- |
| R12-A GAP | UUID/address 값, Device session·event, advertising, scanning, connection callback/reference | 단일 facade·once stack, generation, stale callback, fixed queue, callback 재진입 |
| R12-B GATT | database/schema, server value/notification, client operation/subscription lifecycle | 고정 슬롯과 connection 참조, pending operation token, disconnect 뒤 늦은 callback 거부 |
| R12-C Security/profile | pairing·사용자 인증 응답, bond lifecycle, BAS/DIS/HIDS profile | 제한된 pending reference·event, pairing/저장 실패, 재연결, callback 재진입 |
| R12-D Storage | EEPROM record codec·Settings 저장, LittleFS path/slot·mount | R04 retain/release, 기존 on-disk 형식과 partition, 실패/손상/재부팅 유지 |

각 단계에서 실제 production 구현을 Host의 fake Bluetooth/Settings/filesystem driver와 함께
검증하고, 해당 target와 기존 계약 검사를 수행한다. 파일 분리와 발견한 동작 수정은 별도
commit으로 구분한다. 공개 header·singletons·feature schema와 Arduino installed-example
호환성은 유지한다. 새 private 경계는 상태의 단일 소유를 명시하며 mutable extern을 늘리지 않는다.
메모리 절감이 증명되지 않은 feature 세분화를 도입하지 않고 동일 구성의 flash/RAM을 비교한다.

Host fake는 reference 수명·queue·오류 전파를 검증하는 도구다. BLE 무선 연결, bond의 실제
flash 내구성, LittleFS 실제 전원 차단 복구 결과로 승격하지 않는다. 전체 설치 예제·패키지는
R13 마지막 software gate에 묶고 최종 소스 current-source T11 직전에서 멈춘다.

## R12-A GAP 결과

Device facade와 session/event 소유를 원본 cpp에 남기고 UUID/address 값, advertising,
scanning, connection/reference callback을 명시적 4개 cpp로 분리했다. 광고·스캔 설정은
각 모듈이 private 소유하며 기존 공유 configuration spinlock은 유지했다.
85개 함수 본문은 상태/accessor 이름을 정규화하면 동일하고 공개 header·NUS·Stack 등
6개 파일은 byte 동일하다. 공개 singleton·feature schema·queue 크기는 유지했다.

실제 GAP/Stack을 별도 TU로 링크한 Host는 reference 회수, 늦은 MTU/연결 callback,
재연결, event 40회 중 queue 24개·drop 16개, callback 안 end/begin, pending end,
scan payload 복사, driver 실패 후 재시도, once settings 실패 보존, 광고 option과 payload
한도 등 10개 시나리오를 통과했다. 분리 전 9개 시나리오도 통과했으며 광고 시나리오는
추가 회귀다. Host fake는 실제 Bluetooth 무선·bond flash 시험이 아니다.

| 검사 | 결과 |
| --- | --- |
| 전체 Host | 624개 중 622 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / 322개 PASS |
| target | M19 contract·peripheral/central 및 M20 contract 4/4 build-only PASS; 162.81초 |
| 명시적 source 소속 | GAP 5개 + Stack 1개가 각 target에서 정확히 1회 |

| 동일 구성의 flash / RAM | 이전 | 이후 |
| --- | --- | --- |
| M19 GAP | 183,380 / 47,920 B | 183,608 / 47,968 B |
| M20 GATT | 179,016 / 50,392 B | 179,236 / 50,472 B |

초기 공통 context에 두 설정을 포함한 분리는 M20 RAM을 312 B 증가시켰다. 설정을
각 모듈에 두어 미사용 설정의 보존을 줄인 최종 결과는 +80 B다. accessor·공통 상태의
실체화와 정렬로 남은 증가를 그대로 기록하며 footprint 개선이라고 주장하지 않는다.
첫 target은 minimal C++ 환경에 없는 cstring/cstdio header로 실패했다. 원본과 같은
C header로 수정했으며 SDK는 수정하지 않았다. C:/r12a 실패와 r12a2 중간 결과는 로컬 보존한다.

[gate](evidence/r12a-86b53f8/software-and-source.json),
[본문·header](evidence/r12a-86b53f8/comparison.json),
[target](evidence/r12a-86b53f8/target-build.json),
[기준선](evidence/r12a-86b53f8/target-before.json),
[메모리·symbol](evidence/r12a-86b53f8/target-comparison.json),
[실제 Host](evidence/r12a-86b53f8/gap-after.txt)를 보존한다.
다음은 R12-B GATT database/server/client 및 lifecycle 분리·fault injection이다.
R12 전체는 B/C/D 완료 전까지 진행 중이며 current-source T11은 NOT RUN이다.

## R12-B GATT 결과

원본 cpp는 GATT session·queue·poll을 소유한다. GattDatabase는 schema·등록 rollback,
GattServer는 cached value·CCC·notification/indication, GattClient는 discovery·operation·
subscription을 소유한다. 고정 server slot 배열과 client 요청 buffer/params는 해당 cpp에서
별도 private 소유하여 사용하지 않는 경로의 큰 저장소가 공통 상태를 통해 남지 않게 했다.
mutable extern 없이 기존 mutex/spinlock 경계, 공개 singleton, 고정 한도를 보존했다.

함수 본문 112개(두 characteristic constructor 초기화 목록 포함)가 accessor 이름을
정규화하면 동일하다. 나머지 BLE source/header 12개도 byte 동일하다. 실제 GAP/GATT/Stack
별도 TU를 링크한 Host 11개 시나리오는 분리 전후 모두 통과했다. 등록 두 번째 실패 시
첫 service를 rollback하고 stack enable 전에 실패하며 재시도하는 경로, cached read/write
복사와 잘못된 길이/prepare 거부, queue overflow·callback 안 end/begin, notification busy,
indication destroy 이전 재사용 거부와 데이터 보존, disconnect 뒤 늦은 callback, client
discovery/read/write/subscribe/unsubscribe driver·ATT 실패와 재연결을 검증했다.

GATT token의 connection pointer는 기존처럼 비소유 snapshot이다. API와 현재 연결 검사에서
일시 reference를 얻고 반환한다. pending 전송에 새 refcount 소유를 추가하지 않았다.

| 검사 | 결과 |
| --- | --- |
| 전체 Host | 625개 중 623 PASS·2 조건부 SKIP |
| 마지막 상태 배치 조정 뒤 회귀 | 실제 GATT 11개 / M20 계약 6개 PASS |
| contract / inventory / style | 45/45 / PASS / 330개 PASS |
| target | M20 contract·peripheral/central 및 M19 contract 4/4 build-only PASS |
| source 소속 | GATT 선택 3개 target에 공통 1개+database/server/client 3개 각 1회 |

첫 분리는 최소 M20 contract에서도 server slot과 client 요청 저장소가 한 context에 묶여
RAM 14,160 B가 증가했다. 이를 private 별도 객체로 되돌린 최종 측정은 아래와 같다.
전체 Host는 첫 분리에서 실행했고 마지막 상태 배치 변경 뒤 해당 production Host와 계약,
target 4개를 다시 확인했다. C:/r12b 중간 결과도 로컬 보존한다.

| 동일 구성의 flash / RAM | 이전 | 이후 |
| --- | --- | --- |
| M20 GATT | 179,236 / 50,472 B | 179,336 / 50,472 B |
| M19 GAP | 183,608 / 47,968 B | 183,608 / 47,968 B |

공개 method symbol 누락은 없다. 실제 무선·재부팅 bond 시험은 수행하지 않았다.
[gate](evidence/r12b-ee17789/software-and-source.json),
[본문·header](evidence/r12b-ee17789/comparison.json),
[target](evidence/r12b-ee17789/target-build.json),
[메모리·symbol](evidence/r12b-ee17789/target-comparison.json),
[Host 전](evidence/r12b-ee17789/gatt-before.txt)·[후](evidence/r12b-ee17789/gatt-after.txt)를 보존한다.
다음은 R12-C Security/profile의 pairing·bond·HIDS/BAS/DIS 수명주기 분리다.

## R12-C0 M21 baseline compile 보정 착수

추가 M21 기준선 3개가 미사용 PHY helper와 NCS HIDS C header의 deprecated enum 위치 경고로
실패했다. 파일 분리 전에 PHY helper를 해당 feature 조건 안에 두고, HIDS SDK 호출과 init
구조체를 기존 C backend로 옮긴다. SDK 수정·경고 억제 없이 공개 API와 report 값을 보존한다.
이 보정 commit 뒤 Security/profile 파일 분리를 수행한다. C:/r12cp 원본 실패를 보존한다.

### R12-C0 결과

M21 기준선 실패를 SDK 수정·경고 억제 없이 보정했다. `publicPhy`는 실제 호출부와 같은
CONFIG_BT_USER_PHY_UPDATE 조건 안에 둔다. HIDS init parameter 구성, protocol mode 변환,
연결 등록/회수와 report 송신은 기존 C backend에서 실행한다. C++에는 bool mode와 고정
buffer를 받는 private C 선언만 노출한다. callback은 C의 단일 정적 포인터로 소유한다.
공개 Security header·feature/conf와 keyboard report map은 그대로다.

| 검사 | 결과 |
| --- | --- |
| 실제 Security Host | 이전·이후 12개 시나리오 PASS; 이후 HIDS backend는 gcc C11로 별도 compile |
| 전체 Host | 626개 중 624 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / 336개 PASS |
| 추가 M21 target | contract·HIL peripheral/central 3/3 build-only PASS |

Host는 pending 응답의 reference, timeout, 중복/잘못된 응답, callback 안 승인, pairing 실패,
늦은 이전 연결 callback, event queue overflow, BAS/DIS 실패, HID encryption/CCC 거부,
boot/report protocol과 reconnect reference 회수를 검증한다. 새 pairing 완료에도 저장
snapshot이 없으면 persistence_pending에 머물고, boot snapshot 후보가 새 pairing 없이
L2에 도달할 때만 verified가 된다. bond 삭제 실패는 기존 상태로 rollback한다.
저장 실패 모델은 저장된 bond가 없는 상태를 주입한다. 실제 Bluetooth key 저장 완료·
재부팅 복원·flash 내구성을 Host PASS라고 주장하지 않는다.

Host의 atomic_set fake는 실제 Zephyr처럼 이전 값을 반환하도록 exchange로 수정했다.
첫 harness의 verified 상태를 candidate로 오인한 assertion은 재연결 후 candidate를
만들도록 수정했으며 해당 이유로 production bond 동작을 변경하지 않았다.
기존 source 계약은 SDK 호출 위치가 C backend로 옮겨진 사실까지 함께 검사한다.

[gate·source](evidence/r12c0-b7f79fd/software-and-source.json),
[target](evidence/r12c0-b7f79fd/target-build.json),
[원본 실패](evidence/r12c0-b7f79fd/baseline-failure.txt),
[Host 전](evidence/r12c0-b7f79fd/security-before.txt)·[후](evidence/r12c0-b7f79fd/security-after.txt)를 보존한다.
M21은 기존 canonical 목록에 빠져 있어 같은 runner에 명시적으로 세 suite를 추가한 로컬
wrapper를 썼다. 전체 software 목록 반영은 R13에서 수행한다. 다음은 이 보정본을 기준으로
Security/pairing/bond/BAS/DIS/HID 파일만 분리하는 R12-C1이다. 실기 NOT RUN.
