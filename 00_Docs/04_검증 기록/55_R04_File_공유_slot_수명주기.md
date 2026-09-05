# R04 — LittleFS File 공유 slot 수명주기

2026-09-06, 시작 source `6b79480`. 종료 commit은 이 문서의 최초 commit으로 식별한다.
다음은 R05 제품 identity 원본 정리다.

## 변경 계약

copy와 copy assignment의 generation 검사·참조 증가, move assignment의 기존 참조 해제와
close의 감소·마지막 backend close를 같은 filesystem mutex로 직렬화했다. 내부
`retainSlotLocked`/`releaseSlotLocked`는 caller가 mutex를 보유해야 하며 직접 lock하지 않는다.
`name()`/bool의 공유 slot 조회도 같은 mutex로 보호한다. name 포인터는 해당 File의
close·대입·소멸 전까지만 빌려준다.

서로 다른 File 객체는 같은 파일 위치와 handle을 공유하며 동시 작업이 직렬화된다. 동일 File
객체의 변경·소멸과 다른 접근이 겹치면 호출자가 동기화한다. ISR의 복사·이동·대입은 차단하며
기존 source/destination 참조를 변경하지 않는다. 소멸·close도 thread 문맥에서 수행해야 한다.
참조 수 최댓값에서는 새 복사가 invalid로 끝나고 busy 오류를 기록한다.

기존 fs_close 오류의 의미는 유지한다. backend close를 한 번 시도한 뒤 slot은 회수하고
native 오류를 기록한다. 이 결과를 저장 성공으로 해석하지 않는다. File header의 잘못된
‘이동 전용’ 설명을 수정했으며 실행 token·signature·layout은 동일하다. slot 4개·generation
32 bit·참조 16 bit·path 255, EEPROM 기록과 partition·저장 형식에는 변화가 없다.

## 검증

production FS.cpp를 실제 recursive mutex와 메모리 Zephyr FS fake에 연결했다. 수정 전
mutex 진입 누락, 8 thread retain/release 교차, ISR 대입의 3개 실패를
[원본 log](evidence/r04-6b79480/before.txt)에 보존했다. 수정 후 8 scenario 모두 통과했다.

- copy/assignment/self assignment/move/self move/close 및 기존 목적지 close.
- 공유 파일 위치와 byte 내용 유지, 마지막 close 한 번과 중복 close.
- 실제 mutex 보유 중 copy 대기, 8 thread × 4,000회의 서로 다른 handle 교차.
- 마지막 두 참조의 동시 close, stale generation 거부·slot 재사용·0을 건너뛰는 wrap.
- 참조 포화, backend close 오류, ISR copy/move/assignment 차단과 원래 참조 보존.

| 검사 | 결과 |
| --- | --- |
| production File 동작 회귀 | 8/8 PASS |
| Host 전체 | 605개 중 603 PASS·2 조건부 SKIP |
| CI contract | 45/45 PASS |
| AC-03 target | storage contract·storage HIL image 2/2 build-only PASS |
| C/C++/ino 정렬 | clang-format 22.1.8, 259개 dry-run PASS |
| 저장 장치·재부팅 실기 | NOT RUN, 최종 current-source 시험으로 유지 |

[source·gate 증거](evidence/r04-6b79480/software-and-source.json)와
[target 설정·artifact 증거](evidence/r04-6b79480/target-build.json)를 보존한다.
SDK·board·기존 공개 asset·역사 evidence는 변경하지 않았다. API·ABI·CLI·schema·저장 형식의
migration은 없다. software fake는 실제 LittleFS flash persistence를 대신하지 않으며 R12의
저장 오류/손상 및 최종 실기 회귀에 연결한다. 되돌림 단위는 File 내부 참조 helper·API guard,
관련 설명과 production File Host 회귀다.
