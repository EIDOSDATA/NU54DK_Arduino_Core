# T10/T12 Fixture 440 — 재결선과 PDM 위상 진단

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 진행 상태는 [v0.5.0 TODO](../TODO_v0.5.0.md)를 따릅니다.

현재 문제 상태: PDM 위상·준비 순서 문제는 **해결 완료**입니다. [91번](91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md)의 기본·밀도 시험과 [92번](92_T12_Fixture_440_PDM_연속_전체_검증.md)의 연속 96/96에서 재검증했습니다. 아래 중간 실패·미실행은 보존합니다.

**당시 결과:** 재결선 후 clock/gate 분리는 통과했다. PDM은 76개 조합을 통과한 뒤 stereo 좌우 부호 실패가 발생했다. 후속 CONSTLAT 보완은 빌드를 통과했지만 이 기록 시점에는 결선 유지 확인 만료로 실기를 실행하지 않았다.

기록일 2026-09-07 Asia/Seoul, 아래 시각은 UTC다. [89번](89_T12_Fixture_440_clock_gate_분리_진단.md)의 이전 결선 관측과 [88번](88_T12_Fixture_440_current_source_PDM_검증.md)의 실패 원본은 그대로 보존한다.

## 확인과 결선

사용자 “재연결 완료. 다시해.”를 2026-09-06T21:02:10Z에 기록했다. A P1.04↔B P1.05(clock), A P1.05↔B P1.04(gate), A P1.06↔B P1.07(data), 공통 GND다. A P1.07·B P1.06은 미연결, DAP UART 분리·SWD 연결, SB/PMIC 유지 조건이다. 모든 실기·flash·진단·postflight는 **SWD 10 MHz**, exact 두 probe, auto_unlock=false, sector flash·controlled start를 사용했다.

[확인 원본](evidence/t12-fixture440-79e4bdd/checkpoint.json)에 시각·조건을 보존한다. NCS 99553055607b2e9885fbc80ccd11fa9da81c2df0, Zephyr bf801e4e3d19e1ffa76164346480cb7734dd2800, board gitlink fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3은 유지했다.

## Source별 실행

| Source / build | 실제 결과 |
| --- | --- |
| 79e4bdd509bc5b12209364399fe9a115cf3946a7 / C:/u4g | 수정한 분리 진단 96 개 PASS. PDM 모노 DMA 4 PASS 후 첫 stereo 부호 FAIL·187 미실행·cleanup 5 PASS |
| 7641229dca8c37be7a0d07241d407cb14cbf76ca / C:/u4h | Clock pull-down 설정 뒤 10 us 안정화 추가. 기능 76 PASS·61,440 samples 후 stereo 부호 FAIL·115 미실행·cleanup 77 PASS. Mono density 비교는 아직 미도달 |
| 5273b30c05e1cdf2b7043f39c1f2536f1699bb59 / C:/u4i | Stereo 생성 중 reference-counted CONSTLAT 요청/해제 추가. SDK C header의 C++ linkage로 두 역할 link FAIL. Flash·실기 NOT RUN |
| e9d264c502488754fbda2eabcf174764f703e37d / C:/u4j | C linkage 교정. 두 역할 build 2/2 PASS·관련 Host 17 PASS·정렬 361 PASS. Confirmation 만료 preflight 거부, flash·실기 NOT RUN |

79e4bdd의 [결과](evidence/t12-fixture440-79e4bdd/fixture440-attempt2.json)·[감사](evidence/t12-fixture440-79e4bdd/results-audit.json), 7641229의 [결과](evidence/t12-fixture440-7641229/fixture440-attempt1.json)·[감사](evidence/t12-fixture440-7641229/results-audit.json)는 계획 순서·source/role·원래 sample·cleanup을 대조한다. 76 개 뒤 실패한 vector는 generator role 1, `(21, 1024, 25, 1, 0, 1)`이다. 좌우 평균은 -17985.287109375, +17998.0625로 분리되지만 기대 부호 순서와 반대였다. 판정 기준을 완화하거나 채널 순서를 사후 교환하지 않았다.

## 분리 진단의 교정

재결선 첫 [32 개 관측](evidence/t12-fixture440-79e4bdd/net-isolation-probe.json)은 첫 A P1.05 한 값만 예상과 달랐다. [10 ms 간격 반복](evidence/t12-fixture440-79e4bdd/net-isolation-settled-retry.json)에서도 첫 한 값만 남았다. 진단 스크립트가 다른 보드의 PIN_CNF 쓰기를 flush하기 전에 첫 보드를 읽는 순서 문제가 있었다. 이 두 원래 실패를 결선 PASS로 변경하지 않았다.

각 보드의 입력 설정·출력 해제 쓰기를 flush하고 register를 확인하도록 고친 [최종 진단](evidence/t12-fixture440-79e4bdd/net-isolation-flushed-retry.json)은 출력 위치 4 개 × LOW/HIGH × 반복 3 회 × 관측 핀 4 개 = **96 개 전부 PASS**였다. [독립 감사](evidence/t12-fixture440-79e4bdd/net-flushed-audit.json)의 `wiring_matches_fixture440=true`가 이 판정이다. 원본 top-level 진단 완료 상태와 PDM 기능 PASS는 구분한다. 이전 네 핀의 동시 HIGH 관측은 이번 96 개 결과에서 재현되지 않았다.

진단과 canonical upload에서 SWD timeout 세 건(B 두 번·A 한 번)이 발생했다. 각각 읽기 전용 CPUID 응답을 확인한 뒤 한 번의 새 실행을 수행했으며, 실패 원본과 후속 성공을 분리 보존했다. Recover·mass erase·속도 하향·자동 무한 재시도는 없었다. 첫 SWD 쓰기 순서 문제를 다른 SWD timeout의 원인으로 확정하지 않는다.

## 당시 위상 보완 — 후속 해결 완료

초기 입력 안정화는 처음 실패하던 stereo를 통과시켰지만 76 개 뒤 같은 부호 반전이 재발했다. 초기값만으로 문제 전체가 해결됐다고 보지 않는다. [7641229 설정 trace](evidence/t12-fixture440-7641229/setup-trace.jsonl)는 실패 당시 initial output LOW와 PDM21 MODE=2·입력 pin 설정을 보존한다.

후속 HIL은 stereo generator 준비 때 `nrf_sys_event_request_global_constlat()`를 요청하고 GPIOTE/DPPI 해제 뒤 대응 release를 호출한다. Pair 설정에 NRF_SYS_EVENT·NRFX_POWER를 활성화하고 불필요한 IRQ latency 기능은 비활성화했다. SDK header가 C linkage guard를 제공하지 않아 발생한 [link 실패](evidence/t12-fixture440-5273b30/failed-build-summary.json)는 호출 측 `extern "C"`로 교정했다. SDK·공용 core·일반 보드 pin 정책은 수정하지 않았다.

[Nordic DPPI latency 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/ppi.html-concept_latencies)은 저전력 상태에 따른 지연과 CONSTLAT 사용을 설명한다. 이것은 수정 방향의 근거다. **이번 부호 실패의 원인이 그 지연인지, CONSTLAT 보완이 해결하는지는 아직 실기로 확인하지 않았다.** 새 runner trace와 postflight는 POWER_CONSTLATSTAT도 읽도록 준비했다.

## Software와 보존

7641229·5273b30 각각 전체 Host **660 PASS·1 조건부 SKIP**, 82 그룹, 정렬 **361 PASS**다. e9d264c는 그 뒤 C linkage만 바뀌었으며 관련 Host **17 PASS**, 정렬 **361 PASS**, pair **2/2 build PASS**를 확인했다. 이전 전체 Host를 e9d264c에서 새로 실행한 것처럼 세지 않는다. [최종 software 범위](evidence/t12-fixture440-e9d264c/software-summary.json), [artifact index](evidence/t12-fixture440-e9d264c/target-artifact-index.json), [입력 비교](evidence/t12-fixture440-e9d264c/build-input-comparison.json)를 참조한다. 비교 script의 최초 “전체 source 소속 동일” 가정은 실패했다. 실제 추가 항목이 SDK nrf_sys_event.c 하나임을 대조해 수정했고, 원래 assertion 실패도 보존했다. 공용 core와 DTS byte는 유지했다.

네 source의 원본 **196 개**를 UTF-8 LF 사본·원래 byte gzip·SHA-256으로 보존한다. Manifest는 각각 [79e4bdd](evidence/t12-fixture440-79e4bdd/raw-files.json), [7641229](evidence/t12-fixture440-7641229/raw-files.json), [5273b30](evidence/t12-fixture440-5273b30/raw-files.json), [e9d264c](evidence/t12-fixture440-e9d264c/raw-files.json)에 있다. 준비 script는 실행 사실을 뜻하지 않는다. [문서 검증](evidence/t12-fixture440-e9d264c/docs-verification.json)은 Markdown 199 개·원본 복원·stage byte 검사를 기록한다. 기존 역사 파일·SDK·board·공개 자산은 보존했다. 새 저장소 임시 파일은 없으며 재개용 build와 실패 원본은 사용 중이므로 제거하지 않았다.

## 당시 재개 대기 — 현재 재실행 지시 아님

21:02:10Z 결선 확인은 21:32:10Z 만료됐다. 최종 [preflight](evidence/t12-fixture440-e9d264c/preflight.log)는 이를 거부했으며 e9d264c는 업로드하지 않았다. 현재 양쪽 보드는 **7641229**, 관련 peripheral off·신호 입력이다. [마지막 postflight](evidence/t12-fixture440-7641229/postflight.json)를 참조한다. 실행 중 시험은 없다.

이때 440 결선 유지 답변과 전체 재검증을 기다렸다. 후속 91·92번에서 기본 192개·밀도 32개와 settling 4·measured 100-buffer 연속 96개를 완료했다. 공용 PWM STOP 결함도 **해결 완료([94번](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md))**이며 현재 잔여는 활성 TODO를 따른다. 이 기록 당시 원격 CI는 확인하지 않았다.
