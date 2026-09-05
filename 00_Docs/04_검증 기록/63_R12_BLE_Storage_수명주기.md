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
