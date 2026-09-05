# R03 — Analog/Stream ISR·정지 동기화

2026-09-06, 시작 source `7e9270d`. 종료 commit은 이 문서의 최초 commit으로 식별한다.
파일 이동 없이 정확성을 교정했다. 다음은 R04 LittleFS 공유 File 참조 관리다.

## 공유 상태와 정지 계약

| 공유 항목 | writer / reader | 동기화·소유권 |
| --- | --- | --- |
| lifecycle·설정·lease | thread API / thread API | 기존 fabric mutex, stopping 예약 |
| 진단 결과·native 오류 | ISR와 API / 조회 | 짧은 spinlock의 내부 snapshot |
| event queue·손실 flag | ISR / takeEvent | queue spinlock, 기존 고정 용량 유지 |
| STOP generation·알림 | 실행 시작·stop·ISR / stop waiter | 별도 spinlock, queue와 독립 |
| PDM buffer 주소·길이·active, 초기 callback flag | reserve/release thread / IRQ | metadata spinlock, 자원 manager 호출은 lock 밖 |

공개 result/driverError getter는 각각 내부 snapshot을 읽는다. 두 번의 별도 getter 호출 사이에
새 진단이 발생할 수 있으므로 두 호출이 같은 사건을 뜻한다는 보증은 추가하지 않는다.
queue가 가득 차면 기존 순서와 entries를 보존하고 다음 takeEvent에서 `error/-ENOBUFS`를 먼저
반환한다. STOP 알림은 queue 손실에 영향받지 않는다.

SAADC/PWM/PDM/I2S는 stop 요청 전에 stopping 상태와 waiter를 예약하고 fabric mutex를 놓은
상태에서 기다린다. 같은 handle의 재시작은 거부되며 다른 block은 진행할 수 있다. 대기는 남은
예산을 최대 10 us씩 차감하고 마지막 경계를 확인해 0·1·UINT32_MAX의 overflow를 방지한다.
이는 busy-wait 예산이며 scheduler 선점 시간을 포함하는 정밀 wall-clock 보증은 아니다.

STOP 미확인 timeout에서는 driver/DMA/lease를 보존하고 stopping 상태에서 명시적 stop 재시도를
허용한다. 늦은 STOP을 같은 실행에 보존하며 새 실행은 generation과 알림을 초기화한다. 알림은
hardware request ID가 아니며 새 실행 전 pinned nrfx의 uninit/init·IRQ 정지 경계가 필요하다.
확인 뒤에만 uninit과 lease 반환을 수행한다. 반환 실패는 faulted 및 잔여 lease로 보존한다.

DMA 시작 뒤 commit 실패와 PDM 초기 buffer 설정 실패도 STOP 요청만 수행하고 자원을 유지한다.
후속 stop은 예약 단계 lease에는 rollback, committed lease에는 release를 적용한다. SAADC 추가
buffer commit 실패도 같은 경로를 따른다. faulted를 재configure해 잔여 lease를 덮어쓰지 않는다.

## 실패 회귀와 검증

production AnalogFabric.cpp/StreamFabric.cpp 전체를 fake nrfx 및 실제 mutex/spinlock/thread와
컴파일한다. 수정 전 최초 12개 scenario 중 10개 실패, commit 실패 경로를 추가한 4개 실패를
[원본 log](evidence/r03-7e9270d/before.txt)와 [추가 log](evidence/r03-7e9270d/before-commit-failure.txt)에
보존했다. 수정 후 26개 scenario는 모두 통과했다.

STOP 누락·지연·이전 신호, overflow 중 정지, timeout 경계, 반복 start/stop, 다른 block 진행,
진단 concurrent writer 20,000회, PDM metadata 교차 50회, release/commit/초기 buffer 실패를
검사한다. 동일 실행에서 동시 stop waiter는 wrong_state로 거부한다.

| 검사 | 결과 |
| --- | --- |
| production driver 회귀 | Analog 12 + Stream 14 = 26 PASS |
| Host 전체 | 604개 중 602 PASS·2 조건부 SKIP |
| contract / inventory | 45/45 PASS / identity 75·serial 23·system 16·readiness blocker 8 유지 |
| target | Analog·Stream·onboard 및 DUT/Peer 5/5 build-only PASS |
| C/C++/ino 정렬 | clang-format 22.1.8, 254개 dry-run PASS |
| package·설치 예제·전체 target | 최종 R13에서 전체 재실행 |
| flash / physical HIL | NOT RUN |

최종 source hash와 gate는 [software 증거](evidence/r03-7e9270d/software-and-source.json),
resolved config·artifact는 [target 증거](evidence/r03-7e9270d/target-build.json), R02와 동일 config의
메모리 차이는 [DUT/Peer 비교](evidence/r03-7e9270d/pair-comparison.json)에 기록했다.
R00 공개 header 25개는 동일하며 API·ABI·CLI·schema·저장 형식·partition migration은 없다.

- dut: flash 183,704 byte (+1,576), RAM 161,502 byte (+160).
- peer: flash 183,716 byte (+1,576), RAM 161,502 byte (+160).

초기 20개 회귀 기준 target `C:/r03`도 통과했으나 추가 교정 후 `C:/r03a`의 5개를 최종 근거로
사용한다. 중간 Host 실패 log는 추가 commit-failure 회귀가 기존 경로를 거부한 기록으로 보존한다.
SDK·board·공개 asset·역사 evidence는 변경하지 않았다. runtime byte가 달라졌으므로 R11에서
이 계약을 유지하고 최종 T12에서 Fixture 401 이후 데이터·STOP·DMA 반환·정상 재시작을 확인한다.
실기 PASS는 현재 기록에 포함하지 않는다. 되돌림 단위는 내부 동기화 helper, 두 Fabric 교정과
production driver 회귀다.
