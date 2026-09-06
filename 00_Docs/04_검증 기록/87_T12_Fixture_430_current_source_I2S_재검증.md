# T12 Fixture 430 — DMA 자원 처리 지연 교정과 I2S 전체 PASS

**Exact 36ba819bbe03280fa82c62ef76b00c87a92c2aff에서 Fixture 430 전체 192개 기능과 192회 양쪽 cleanup을 통과했다. 이전 짧은 buffer 실패를 포함한 전체 계획을 같은 source로 다시 실행했으며, 수신 payload 82,944 word를 독립 대조했다.**

기록일은 2026-09-07 Asia/Seoul이며 원본 시각은 UTC다. [86번](86_T12_Fixture_430_current_source_I2S_검증.md)의 세 source 실패·교정·부분 통과 기록은 그대로 보존한다. 이번 결과는 I2S 합성 신호 기능 범위이며 T12/M25 전체 완료를 뜻하지 않는다.

## 실행 조건과 확인

| 항목 | 내용 |
| --- | --- |
| 사용자 재확인 | “뭐가 문제였니? 결선 유지중이야.”, 2026-09-06T18:35:58Z 기록 |
| Fixture | 430, catalog revision 5, I2S20 양방향, master role 1/2 교대 |
| SWD | flash·mailbox·RAM 읽기·postflight 모두 10,000,000 Hz |
| SDK | NCS v3.4.0 / 99553055607b2e9885fbc80ccd11fa9da81c2df0, bundle dcbdc366a1 |
| Zephyr | bf801e4e3d19e1ffa76164346480cb7734dd2800 |
| Board gitlink | fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3 |
| 최종 업로드 | 양쪽 exact 36ba819, C:/u3z pair 2/2 build-only PASS |
| 기능 campaign | 1회 연속 전체 계획, 47.609초, 192 PASS·0 FAIL·0 미실행 |
| 종료 상태 | 양쪽 SLEEPING, I2S ENABLE=0, P1.04/05/06/07 PIN_CNF=2 |

| 430 신호 | A / role 1 | B / role 2 |
| --- | --- | --- |
| SCK | P1.04 (P2-12) | P1.04 (P2-12) |
| LRCK | P1.05 (P2-11) | P1.05 (P2-11) |
| A SDOUT → B SDIN | P1.06 (P2-10) | P1.07 (P2-9) |
| B SDOUT → A SDIN | P1.07 (P2-9) | P1.06 (P2-10) |
| 공통 GND | P2-30 | P2-30 |

사용자가 USB 분리 후 연결했던 430 결선 유지 확인을 적용했다. DAP UART 분리·SWD 연결·SB/PMIC 설정 유지, MCK 미연결 조건이다. [Confirmation](evidence/t12-fixture430-36ba819/confirmation.json)은 재확인 시각, source·catalog·두 image hash·probe digest를 연결한다. 30분 유효기간인 19:05:58Z 전에 두 실행을 마쳤으며 시각을 임의 갱신하지 않았다. 원래 430 요청 문구와 이번 결선 유지 답변은 [checkpoint](evidence/t12-fixture430-36ba819/checkpoint.json)에 함께 보존한다. Sector flash·제어 시작만 사용했으며 mass erase·recover·auto-unlock·속도 하향은 없었다.

## 원인과 교정

| Source | 실제 결과 |
| --- | --- |
| 70971f41aa1e0485d3e974fc8a4cd4f123ae2f33 / C:/u3y | HIL RAM trace 추가 후 이전과 같은 첫 72개 PASS, 73번째 48 kHz·24-bit·stereo·32-word·단일 buffer에서 underrun. [실패 원본](evidence/t12-fixture430-70971f4/fixture430-attempt1.json), [부분 감사](evidence/t12-fixture430-70971f4/partial-results-audit.json), [시간 추적](evidence/t12-fixture430-70971f4/timing-trace.json). Cleanup 73회·postflight 양쪽 PASS |
| 36ba819bbe03280fa82c62ef76b00c87a92c2aff / C:/u3z | 공용 compact DMA token 처리 교정 후 [전체 192개 PASS](evidence/t12-fixture430-36ba819/fixture430-attempt1.json). 같은 HIL trace·32-word 조건·payload oracle을 유지 |

실패 trace는 queueBuffers가 278~309 us 걸린 뒤 underrun event(type 3)를 관측했다. 48 kHz·24/32-bit·stereo에서 32-word buffer의 명목 구간은 약 333 us다. 기존 공용 자원 경로는 작은 DMA token을 처리할 때마다 16-entry 임시 lease를 만들고 reserve→commit→token 변환, 반납 시 역변환을 수행했다. RX/TX 각각의 획득·반납과 service 처리가 짧은 buffer 교대 시간에 부담을 주었다.

[io_resource_manager.cpp](../../cores/arduino/internal/io_resource_manager.cpp)에서 compact token 획득·반납을 기존 mutex 아래 한 번의 직접 table 처리로 바꿨다. [IoResourceTable.cpp](../../cores/arduino/internal/resource/IoResourceTable.cpp)는 자원을 먼저 검증한 뒤 전체를 반영한다. 같은 owner의 기존 자원 차용, 겹치는 DMA 영역 충돌, pending reservation, manager epoch·generation에 따른 stale 판정과 실패 시 원상 유지를 보존했다. 큰 lease의 reserve/commit/rollback 경로와 공개 API·SDK·board는 변경하지 않았다.

[4,000단계 native 대조](../../tests/host/compact_tokens_main.cpp)는 실제 table 두 개에서 새 경로와 기존 reserve→commit→변환 알고리즘의 반환값·token·snapshot을 비교한다. 자원 중첩·용량 부족·owner 차용·잘못된 generation·reset 이후 stale token·보류 예약을 검증한다. 공용 경로 수정이므로 I2S 이외 영향 target도 빌드했고, 과거 T11 실기를 이 source의 새 PASS로 옮기지 않았다.

[전체 시간 감사](evidence/t12-fixture430-36ba819/timings-audit.json)에서 수신 측 384개 trace의 **queue 960회 모두 성공, 104~112 us**를 관측했다. 오류·underrun event는 0개이고 모든 trace가 32-entry 저장 한도보다 짧다. 시간은 고정 Zephyr GRTC의 1 MHz cycle counter 기준이며 외부 sample clock의 교정된 주파수·jitter 측정은 아니다. RAM 추적은 HIL 전용이며 비교 전후 동일하게 유지했다.

## 전체 결과와 독립 감사

계획은 master role 2종 × 16/48 kHz × 8/16/24/32-bit × stereo/left/right × 32/256 word × 단일/이중 buffer = **192개**다. 한 source의 전체 실행 결과만 완료로 인정했고 이전 source의 72개 부분 PASS를 합산하지 않았다.

[독립 감사](evidence/t12-fixture430-36ba819/results-audit.json)는 모든 고유 기능 ID와 계획 순서·양쪽 상태·confirmation/image hash를 대조했다. [수신 원본 384건](evidence/t12-fixture430-36ba819/i2s-payloads.jsonl)은 요청 payload **82,944 word**와 각 capture의 16-word 여유분을 포함한다. 8/16-bit packed sample 전체, 24-bit 유효 sample, 32-bit 전체를 비교했다. 시작부 최대 8개 zero frame·채널 정렬만 허용하고 이후 전체 payload의 누락·손상·마지막 sample 부족을 거부하는 기존 oracle을 유지했다.

Canonical payload read 결과는 변경 없이 저장했다. 완료된 각 payload를 읽은 뒤 [RAM 시간 기록](evidence/t12-fixture430-36ba819/i2s-timings.jsonl)을 추가로 읽었으며, 추가 mailbox/fixture 명령은 없었다. Journal **386개 = 기능 192 + cleanup 192 + campaign 2**가 최종 JSON과 일치한다. Cleanup 192회 모두 양쪽 `[0]`이다.

19:01:33Z [읽기 전용 postflight](evidence/t12-fixture430-36ba819/postflight.json)는 reset·flash·fixture 명령 없이 두 full runtime identity, CPUID 0x411fd210, SLEEPING, I2S off와 신호 핀 복원을 확인했다. 마지막 업로드는 양쪽 36ba819이며 문서 commit과 구분한다. 실행 중 시험은 없다.

## Software 검증과 원본 보존

[Software 요약](evidence/t12-fixture430-36ba819/software-summary.json)의 검사는 모두 exact clean 36ba819 결과다. 구현 중 subset 기록의 dirty source와 최종 Host 결과는 구분한다.

| 검사 | 결과 |
| --- | --- |
| 전체 Host | 82개 그룹, 총 660개 = **659 PASS·1 조건부 Arduino CLI discovery SKIP**, native compiler SKIP 0 |
| 계약 / Inventory | 계약 45 PASS, Inventory PASS, readiness 미해결 8개 유지 |
| Package | M10 package 20 PASS |
| 정렬 | LLVM clang-format 22.1.8, 직접 관리 C/C++/ino 361개 PASS |
| Exact pair | C:/u3z 2/2 build-only PASS, 285.60초; 이후 이 pair로 430 실기 수행 |
| 영향 target | C:/u4a 8/8 build-only PASS, 472.83초: M3 runtime, AC02 ownership, M24 fabric/SPI/TWI, M25 analog/event/stream |

[Host 로그](evidence/t12-fixture430-36ba819/gate-host-final.log), [pair artifact index](evidence/t12-fixture430-36ba819/target-artifact-index.json), [영향 target artifact index](evidence/t12-fixture430-36ba819/affected-target-artifact-index.json)에 연결한다. LLVM 22.1.8·명시한 WinLibs sysroot를 사용했고 전체 target 행렬·예제 compile 행렬·원격 Actions는 이번에 재실행하지 않았다. Host mock의 하드웨어 성공 문자열을 실제 보드 결과로 계산하지 않는다. 70971f4의 Host 658 PASS·1 조건부 SKIP·정렬 360·pair 2/2는 [별도 source 요약](evidence/t12-fixture430-70971f4/software-summary.json)으로 보존한다.

새 원본은 [70971f4 manifest](evidence/t12-fixture430-70971f4/raw-files.json) 41개와 [36ba819 manifest](evidence/t12-fixture430-36ba819/raw-files.json) 80개에 UTF-8 LF 사본·원래 byte gzip·SHA-256으로 보존한다. 70971f4의 전체 PASS 감사 script는 준비 파일이며 실제 결과는 부분 감사다. [문서 검사](evidence/t12-fixture430-36ba819/docs-verification.json)는 Markdown 196개·121개 원본 복원·변경 범위·Git stage byte 대조를 기록한다. 기존 86번·세 source 증거와 공개 자산은 변경하지 않았다. 이번에 추가한 trace·native 검증은 사용 중이며 제거할 저장소 임시 파일은 없었다.

## 다음 작업

430 결선은 유지되어 있고 **440 PDM은 미실행**이다. USB를 모두 분리한 뒤 아래 440 결선으로 바꾸고 새 사용자 확인을 받아야 다음 신호를 실행한다. DAP UART 분리·SWD 연결·SB/PMIC 설정 유지 조건이다.

| 440 신호 | A GPIO | B GPIO |
| --- | --- | --- |
| Clock | P1.04 | P1.05 |
| Gate | P1.05 | P1.04 |
| Data | P1.06 | P1.07 |
| 공통 GND | P2-30 | P2-30 |

440에서는 **A P1.07과 B P1.06을 연결하지 않는다**. Firmware의 고정 board-role별 clock/gate/data 배치에 따른 3개 신호선이며, 반대 방향 data 선을 추가하면 안 된다. [Fixture catalog](../../tests/hil/nu54dk/v04_fixtures.json)와 [signal HIL](../../tests/zephyr/v04_pair_hil/src/signal_hil.cpp)을 따라 재확인한다.

남은 T12는 440 PDM, PWM period/duty capture, ADC calibration API·다중 채널 순서, timer/event의 전체 요구다. T13 복구·동시성·soak, T14 공용 PWM의 실제 START 전 start_via_task STOP timeout, T15 이후 통합, R14·RC/공개와 readiness 미해결 8개를 유지한다. 공용 자원 경로 변경 이후 필요한 최종-source 통신 회귀도 후속 통합에서 확인한다. 이번 430 기능 PASS는 주파수/jitter 정밀 측정·외부 codec 호환·오디오 품질·주입한 underrun/overrun 복구 검증을 포함하지 않는다.
