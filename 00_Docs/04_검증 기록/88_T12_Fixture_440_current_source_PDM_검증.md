# T12 Fixture 440 — PDM DMA 교정과 스테레오 미해결

**Fixture 440은 미완료다. 최신 exact ea4e25a에서 모노 DMA 4개를 통과한 뒤 첫 스테레오에서 두 채널이 같아 실패했다. 나머지 187개와 밀도 비교는 미실행이며, 양쪽 cleanup 5회·읽기 전용 자원 해제 확인은 통과했다.**

기록일은 2026-09-07 Asia/Seoul, 원본 시각은 UTC다. [87번 I2S 결과](87_T12_Fixture_430_current_source_I2S_재검증.md)는 다른 source의 완료 기록으로 보존한다. 이번에는 HIL 시험 프로그램의 PDM buffer 공급·신호원·핀 metadata를 수정했으며 공개 코어·API·SDK·board gitlink는 변경하지 않았다.

## 실행 조건

| 항목 | 내용 |
| --- | --- |
| 사용자 확인 | “좋아 그럼 이제 PDM 검증을 시작하자. 결선 다 했어.”, 2026-09-06T19:45:39Z 기록 |
| SWD | flash·mailbox·RAM/postflight 읽기 모두 **10,000,000 Hz** |
| Fixture | 440, catalog revision 5, PDM20/21, generator role 1/2 교대 계획 |
| SDK | NCS v3.4.0, 99553055607b2e9885fbc80ccd11fa9da81c2df0, bundle dcbdc366a1 |
| Zephyr | bf801e4e3d19e1ffa76164346480cb7734dd2800 |
| Board gitlink | fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3 |
| 마지막 업로드 | 양쪽 ea4e25a035dbc9219e417bf2a2056ce6f9a2e09c, C:/u4e exact pair |
| 최신 실행 종료 | 2026-09-06T20:13:56Z, 실패 뒤 cleanup 수행 |

| 440 신호 | A GPIO / role 1 | B GPIO / role 2 |
| --- | --- | --- |
| Clock | P1.04 | P1.05 |
| Gate | P1.05 | P1.04 |
| Data | P1.06 | P1.07 |
| 공통 GND | P2-30 | P2-30 |

**A P1.07과 B P1.06은 미연결**이다. 두 USB를 분리하여 위 결선으로 바꾼 뒤 재연결한 사용자 확인을 적용했다. DAP UART 분리·SWD 연결·SB/PMIC 유지, 같은 I/O 전압·전원 rail 미접속 조건이다. 고정 역할 배치는 [catalog](../../tests/hil/nu54dk/v04_fixtures.json)와 [HIL](../../tests/zephyr/v04_pair_hil/src/signal_hil.cpp)에 있다.

[Checkpoint](evidence/t12-fixture440-ea4e25a/checkpoint.json)와 [confirmation](evidence/t12-fixture440-ea4e25a/confirmation.json)은 사용자 문구·확인 시각·source·catalog hash·두 probe digest·HEX hash를 결합한다. Catalog의 전기적 배치는 그대로이고 stereo 신호원 설명만 갱신하여 revision 5를 유지했다. 확인 시각을 임의 갱신하지 않았고 네 실행은 원래 유효시간 안에 수행했다. Sector flash·제어 시작만 사용했으며 recover·mass erase·auto-unlock·SWD 속도 하향은 없었다. 다른 fixture는 실행하지 않았다.

## source별 실행과 수정

| Source / build | 실제 결과와 증거 |
| --- | --- |
| 8685cd8b361b0a8178b1c77227ede7c5e980aaa6 / C:/u4b | 첫 모노 vector에서 overflow. **0 PASS·1 FAIL·191 미실행**, cleanup 1회. [결과](evidence/t12-fixture440-8685cd8/fixture440-attempt1.json), [감사](evidence/t12-fixture440-8685cd8/results-audit.json) |
| 017f3a55c02e2cd9d2859c7002747d3904ca41ba / C:/u4c | buffer 공급 교정 후 **모노 DMA 4 PASS·첫 stereo FAIL·187 미실행**, cleanup 5회. [결과](evidence/t12-fixture440-017f3a5/fixture440-attempt1.json), [감사](evidence/t12-fixture440-017f3a5/results-audit.json) |
| f6ad2998c47e676f2e84af7fb877d20738ed3aeb / C:/u4d | stereo GPIOTE/DPPI 신호원 추가. **모노 DMA 4 PASS**, 첫 stereo generator prepare가 status 731로 실패. Cleanup **4회 PASS·1회 미확인**, 이후 읽기 전용 postflight에서 양쪽 자원 off 확인. [결과](evidence/t12-fixture440-f6ad299/fixture440-attempt1.json), [미확인 cleanup 감사](evidence/t12-fixture440-f6ad299/results-audit.json) |
| ea4e25a035dbc9219e417bf2a2056ce6f9a2e09c / C:/u4e | HIL overlay의 격리된 DAP 핀 metadata 교정. Prepare는 성공했지만 **모노 DMA 4 PASS·첫 stereo 동일 채널 FAIL·187 미실행**. Cleanup 5회·postflight 양쪽 PASS. [최신 결과](evidence/t12-fixture440-ea4e25a/fixture440-attempt1.json), [감사](evidence/t12-fixture440-ea4e25a/results-audit.json) |

처음 HIL은 `buffer_needed`를 처리하지 않아 첫 buffer 반환 전에 다음 DMA를 공급하지 못했다. Payload 0/1과 guard 2/3을 분리하고 요청 event에 맞춰 queue하도록 수정했다. 마지막 payload가 반환되면 guard가 활성인 동안 STOP을 확인한다. 반환 pointer·길이·중복·순서도 검사한다. Mono SPIS는 DMA source 소진 뒤에도 같은 density byte를 출력하도록 overrun character를 맞췄다. 이 수정 후 관측된 네 모노 vector의 overflow는 사라졌으나 전체 buffer/mode 회귀가 완료된 것은 아니다.

기존 SPIS 신호만으로 두 stereo 채널을 구분할 수 없어, stereo에는 GPIOTE20 입력 event를 DPPI20으로 출력 toggle task에 연결하는 시험 신호원을 추가했다. 수신 clock의 양 에지를 사용하고 source 극성과 `left_on_rising_edge`가 채널 순서에 반영되는지를 엄격하게 판정한다. Density 인자 25/50은 기본 stereo 극성, 75는 반전 극성으로 사용하며 stereo의 실제 25/50/75% 독립 밀도를 주장하지 않는다. **이 신호원의 물리 동작은 아직 입증되지 않았다.**

f6ad299의 prepare 실패에서는 해당 핀의 metadata가 UART 전용·analog capability로 남아 EventFabric이 경로를 거부했다. UART를 끈 [pair HIL overlay](../../tests/zephyr/v04_pair_hil/app.overlay)에서만 P1.04~07을 DAP GPIO Kconfig 조건부 input/output/analog로 지정했다. [해석된 DTS](evidence/t12-fixture440-ea4e25a/role1-zephyr.dts)와 [두 역할 요약](evidence/t12-fixture440-ea4e25a/software-summary.json)은 capability 19, policy 4, ownership 9를 확인한다. 일반 board pin 정책을 변경하지 않았다. 이 수정으로 prepare는 통과했지만 스테레오 오류는 남았다.

## 최신 부분 결과의 범위

전체 계획은 PDM20/21 × 256/1024 sample × density 인자 25/50/75 × mono/stereo × left edge 2종 × 단일/이중 buffer × generator role 2종 = **192개**다. 이전 source의 부분 PASS를 합산하지 않는다.

현재 통과한 네 vector는 **A 신호원 → B PDM20, 256 sample, density 인자 25, mono, 두 edge·단일/이중 buffer**뿐이다. 요청 길이·완료량·반환 순서와 sample 수신을 통과했고, [원본](evidence/t12-fixture440-ea4e25a/pdm-samples.jsonl)의 성공 capture 네 개는 총 **1,536 sample**이다. Density 25/50/75 비교 record는 **0개**이므로 이 부분 결과로 입력 밀도 응답까지 검증했다고 하지 않는다. PDM21·반대 board 역할·1024 sample은 아직 실행하지 않았다.

다섯 번째 vector `(20, 256, 25, 1, 0, 1)`의 stereo 수신은 두 채널 평균이 모두 **-14895.46875**, 좌우 **128쌍 전부 동일**했다. [Sample 분석](evidence/t12-fixture440-ea4e25a/sample-analysis.json)은 저장된 원본만 비교한 것이며 추가 실기 측정이 아니다. 신호원 경로·물리 전달·수신 설정 중 어디가 원인인지 아직 확정하지 않았다. 결선 오류나 공개 코어 결함으로 단정하지 않는다.

엄격한 oracle은 동일 채널, 뒤바뀐 채널/edge, 잘못된 극성, 짧은 DMA를 거부한다. 이 기준을 낮춰 PASS를 만들지 않았다. 다음 진단용 [register hook](evidence/t12-fixture440-ea4e25a/diagnostic_template.py)은 준비 파일이며 **미실행**이다. 다음 확인 후 신호원 prepare·수신 시작 직후 설정을 읽고, clock 정지 상태에서 source LOW/HIGH와 peer 입력을 대조하여 원인을 좁힌 뒤 전체 계획을 재실행해야 한다.

## 종료 상태와 증거 한계

[최신 postflight](evidence/t12-fixture440-ea4e25a/postflight.json)는 reset·flash·fixture 명령 없이 두 runtime identity, CPUID 0x411fd210과 PDM20/PDM21/SPIS21/GPIOTE20 사용 채널·DPPI20 channel 0의 해제를 확인했다. P1.04~07은 모두 입력이다. PDM/SPIS 기본 입력 설정 2, GPIOTE 해제의 입력 설정 0, 시작 시 원래 P1.04 pull-up 설정 12를 구분한다. 출력 DIR가 남아 있거나 peripheral 활성 상태이면 통과시키지 않는다. 실행 중 시험은 없다.

8685cd8의 원래 postflight script는 모든 핀이 2라고 가정하여 P1.04=12에서 assertion 실패했다. 원본 실패를 보존하며, register 자료상 peripheral off·입력 방향 확인과 원래 assertion 성공 여부를 구분한다. f6ad299에서는 prepare 실패로 세션이 poisoned 상태가 되어 마지막 A cleanup 명령 성공을 입증하지 못했다. 이를 5회 PASS로 계산하지 않으며, 이후 [postflight](evidence/t12-fixture440-f6ad299/postflight.json)의 off 확인은 별도의 관측이다.

## Software 검증과 문서 보존

| Source | 전체 Host | 정렬 | Exact pair build |
| --- | --- | --- | --- |
| 8685cd8 | 82그룹, 659 PASS·1 조건부 SKIP | 361 PASS | C:/u4b 2/2 PASS |
| 017f3a5 | 82그룹, 659 PASS·1 조건부 SKIP | 361 PASS | C:/u4c 2/2 PASS |
| f6ad299 | 82그룹, 660 PASS·1 조건부 SKIP | 361 PASS | C:/u4d 2/2 PASS |
| ea4e25a | 82그룹, **660 PASS·1 조건부 SKIP** | **361 PASS** | **C:/u4e 2/2 PASS**, 124.53초 |

[최신 Host 원본](evidence/t12-fixture440-ea4e25a/gate-host-final.log)과 [source/환경](evidence/t12-fixture440-ea4e25a/gate-host-final.json)은 clean ea4e25a, LLVM 22.1.8·WinLibs sysroot를 기록한다. 유일한 SKIP은 설치된 Arduino CLI discovery 조건이고 native compiler SKIP은 0개다. 구현 중 dirty subset은 최종 Host와 구분한다. 형식은 한국어 Doxygen·BSD/Allman·4칸·중괄호 필수다.

[Artifact index](evidence/t12-fixture440-ea4e25a/target-artifact-index.json)는 각 HEX/ELF/.config hash와 실제 source를 기록한다. [입력 비교](evidence/t12-fixture440-ea4e25a/build-input-comparison.json)의 translation-unit file hash·membership·정규화 Kconfig 동일성은 **DTS까지 동일하다는 뜻이 아니다**. 이번 HIL overlay는 해석된 pin metadata와 생성 헤더를 바꾸므로 DTS를 각 source·역할별로 따로 보존했다. 공개 core 변경이 없는 HIL 수정이며 전체 제품 target·예제 행렬, 계약·Inventory·package·원격 CI는 이번에 재실행하지 않았다. 87번의 해당 검사는 그 source의 결과로 유지한다.

원본 **167개**는 source별 manifest에 UTF-8 LF 사본·원래 byte gzip·SHA-256으로 보존한다: [8685cd8 40개](evidence/t12-fixture440-8685cd8/raw-files.json), [017f3a5 41개](evidence/t12-fixture440-017f3a5/raw-files.json), [f6ad299 40개](evidence/t12-fixture440-f6ad299/raw-files.json), [ea4e25a 46개](evidence/t12-fixture440-ea4e25a/raw-files.json). 준비 script의 존재를 실기 실행 증거로 삼지 않는다. [문서 검증](evidence/t12-fixture440-ea4e25a/docs-verification.json)은 Markdown 197개·원본 gzip 복원·변경 범위·Git stage byte를 대조한다. 기존 87번 이하 기록·evidence·공개 자산은 보존했다. HIL 수정·회귀 검사·raw 증거는 모두 사용 중이며 제거할 저장소 임시 파일은 없었다.

## 재개 조건과 남은 일

440 결선은 마지막 사용자 확인 상태로 기록되어 있다. [실행기](../../tests/hil/nu54dk/v04_fixture.py)의 30분 확인 유효시간은 **2026-09-06T20:15:39Z에 만료**됐다. 새 flash/신호 실행 전에 현재 결선과 DAP UART 분리 상태가 그대로인지 새 사용자 답변을 받아야 한다. 이미 실행된 결과나 USB 장치 열거로 확인 시각을 갱신하지 않는다. 문서 commit은 업로드 source와 다르므로 재개할 때 실제 clean HEAD pair를 다시 빌드·식별한다.

다음 순서는 같은 440 결선 유지 확인 → source/receiver 설정과 정적 신호 전달 진단 → 오류 교정 → 해당 exact source의 전체 192개·32개 mono density 비교·cleanup 재검증이다. 이후 **PDM settling buffer 4개와 측정용 연속 buffer 100개** 요구도 별도로 수행해야 한다. 이번 단일/이중 buffer 결과는 그 요구를 대체하지 않는다.

남은 T12 PWM period/duty capture·ADC calibration/다중 채널 순서·timer/event 요구, T13 복구·동시성·soak, T14 공용 PWM의 START 전 STOP timeout, T15 이후 통합·R14·RC/공개와 readiness 미해결 8개는 유지한다. 외부 PDM microphone 호환·교정된 오디오 품질은 이번 합성 신호 범위가 아니다.
