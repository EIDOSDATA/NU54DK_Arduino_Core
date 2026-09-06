# T12 Fixture 430 — I2S 부분 통과와 짧은 버퍼 실패

**Exact 7c44abffb30402c56cb5e2fd7a1c21829b3b3a16에서 192개 계획 중 72개가 통과했으며, 73번째 조건에서 실패했다. 나머지 119개는 미실행이고 430 전체는 FAIL이다. 양쪽 disarm과 I2S 정지·핀 복원은 확인했다.**

기록일은 2026-09-07 Asia/Seoul이며 원본 시각은 UTC다. [85번](85_T12_Fixture_420_current_source_QDEC_재검증.md)의 420 전체 PASS는 별도 source의 과거 결과로 유지한다.

## 실행 조건과 source별 경과

| 항목 | 내용 |
| --- | --- |
| 사용자 지시 | “결선 완료. 430을 테스트 해.”, 기록 시각 2026-09-06T17:43:49Z |
| Fixture | 430, catalog revision 5, I2S20 양방향, master role 1/2 교대 계획 |
| SWD | flash·mailbox·읽기 진단·postflight 모두 10,000,000 Hz |
| SDK | NCS v3.4.0, bundle dcbdc366a1, Zephyr bf801e4e3d19e1ffa76164346480cb7734dd2800 |
| Board gitlink | fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3 |
| 최종 업로드 | 양쪽 exact 7c44abf, C:/u3x pair 2/2 build-only PASS, 120.55초 |
| 현재 상태 | 양쪽 SLEEPING, I2S ENABLE=0, P1.04/05/06/07 PIN_CNF=2 |

USB 분리 후 이전 420 신호선을 제거하고 아래 430 결선을 한 사용자 확인을 반영했다. DAP UART 분리·SWD 연결·SB/PMIC 설정 유지, MCK 미연결 조건이다.

| 신호 | A / role 1 | B / role 2 |
| --- | --- | --- |
| SCK | P1.04 (P2-12) | P1.04 (P2-12) |
| LRCK | P1.05 (P2-11) | P1.05 (P2-11) |
| A SDOUT → B SDIN | P1.06 (P2-10) | P1.07 (P2-9) |
| B SDOUT → A SDIN | P1.07 (P2-9) | P1.06 (P2-10) |
| 공통 GND | P2-30 | P2-30 |

각 [confirmation](evidence/t12-fixture430-7c44abf/confirmation.json)은 원래 확인 시각과 해당 source·두 image hash·probe digest·catalog hash에 연결했다. 원문 probe UID는 공개하지 않았다. Sector flash와 제어 시작만 사용했고 mass erase·recover·auto-unlock·SWD 속도 하향은 없었다.

| 실제 source | 결과와 원본 |
| --- | --- |
| 56a88a5c9b9c68055fccfa9b185a7f1cb6aa4a73 / C:/u3v | 첫 16 kHz·8-bit·stereo·32-word·단일 buffer에서 underrun, 기능 PASS 0. [정식 실패](evidence/t12-fixture430-56a88a5/fixture430-attempt1.json), 양쪽 cleanup 및 [postflight](evidence/t12-fixture430-56a88a5/postflight.json) 정상 |
| c4611822d5a1180741989a351112b8784d610d5d / C:/u3w | buffers_needed 처리·10 us polling·별도 tail 추가 후 첫 조건의 DMA 완료는 확인했으나 시작 빈 frame으로 payload 비교 실패, 기능 PASS 0. [정식 실패](evidence/t12-fixture430-c461182/fixture430-attempt1.json), [postflight](evidence/t12-fixture430-c461182/postflight.json) 정상 |
| 같은 c461182의 별도 진단 | 양쪽 master 역할·폭 4종·채널 3종의 24개 startup 진단. [원본](evidence/t12-fixture430-c461182/startup-diagnostic.json)은 기능 PASS가 아니며 모든 양쪽 cleanup [0]. 앞 행 postflight는 이 진단보다 앞선 시각이다 |
| 7c44abffb30402c56cb5e2fd7a1c21829b3b3a16 / C:/u3x | tail 전체 반환·별도 guard·packed sample 전체 비교 교정 후 72 PASS, 1 FAIL, 119 NOT RUN. [정식 결과](evidence/t12-fixture430-7c44abf/fixture430-attempt1.json)와 [읽기 전용 postflight](evidence/t12-fixture430-7c44abf/postflight.json) |

## 교정한 범위와 남은 오류

공용 core·SDK·board는 수정하지 않았다. HIL이 연속 I2S의 다음 buffer 요청을 처리하지 않던 부분을 수정하고, payload slot 0/1 뒤 tail slot 2와 정지용 guard slot 3을 제출한다. Tail 전체가 실제 반환된 뒤 STOP하여 시작 지연만큼 뒤로 밀린 마지막 sample까지 수집한다. 시작 시 빈 frame이 있을 수 있고 반환된 STOP buffer는 부분 전송일 수 있다는 구분은 [Nordic 송수신 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/i2s.html-concept_wvj_ssy_vr)과 고정 SDK의 nrfx_i2s.h callback 계약을 참조했다.

8/16-bit sample은 mono에서도 한 word 안의 모든 sample을 비교하도록 마스크를 고쳤다. 24-bit는 유효 하위 24-bit를, 32-bit는 전체를 검사한다. [Nordic EasyDMA 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/i2s.html-concept_gq4_jly_vr)의 sample packing을 따른다. 수신은 요청 payload word 수보다 16 word 더 보존한다. 시작부 최대 8개 zero frame과 채널 정렬만 허용하고, 이후 요청한 payload 전체를 순서대로 정확히 비교한다. 중간 누락·손상·마지막 sample 부족을 허용하지 않는다. Host 실패 주입 검사에서 packed 상위 sample 손상, 중간/마지막 누락, 초과 startup, 짧은 capture를 거부했다. 이는 정착 후 데이터 전송 검사이며 startup latency의 정밀 보증은 아니다.

최종 실행은 role 1 master의 16 kHz 전체 48개와 48 kHz 8/16-bit 24개를 통과했다. **48 kHz·24-bit·stereo·32-word·단일 buffer**에서 role 1 상태 `[1,1,1,0,128,32,32,1]`이 발생했다. 기능 완료 플래그는 0이며 성공으로 인정하지 않았다. 128은 현재 HIL의 queue/underrun/stop 공통 오류 비트여서 정확한 발생 위치를 더 좁혀야 한다. 실패 후 [RAM 읽기 진단](evidence/t12-fixture430-7c44abf/i2s-buffer-diagnostic.json)에서는 role 1 첫 RX buffer가 끝부분 데이터로 덮인 상태를 관측했다. 짧은 DMA 구간의 buffer 재사용과 일치하지만 HIL service 지연과 공용 Fabric 내부 지연 중 근본 원인은 아직 확정하지 않았다.

다음 교정에서는 start 반환부터 첫 queue까지 시간, buffer 요청/반환 순서와 오류 발생 위치를 분리해 확인한다. 32-word 조건을 늘리거나 실패 조건을 제외해 통과시키지 않는다. 수정 뒤 새 clean source의 전체 192개를 다시 실행해야 하며 서로 다른 source의 부분 PASS를 합산하지 않는다.

## 부분 결과와 종료 감사

[독립 감사](evidence/t12-fixture430-7c44abf/partial-results-audit.json)는 예정 순서의 첫 72개 고유 기능 ID, 수신 원본 144개와 전체 요청 **31,104 word**, 상태·image·confirmation hash를 대조했다. [수신 원본](evidence/t12-fixture430-7c44abf/i2s-payloads.jsonl)은 canonical read 결과를 추가 장치 명령 없이 그대로 보존한다. Sample 단위의 전체 payload와 startup 길이·raw SHA-256을 독립 계산해 정식 결과와 비교했다.

성공 72개 뒤 실패한 조건의 cleanup까지 **73회 모두 양쪽 [0]**이다. Journal 총 145개는 최종 JSON과 같고 campaign 완료 record는 없다. 최종 postflight는 reset/flash/fixture 명령 없이 두 full identity·CPUID 0x411fd210·SLEEPING·I2S off·신호 핀 복원을 확인했다. 보드 간 결선은 430 상태로 남아 있다.

## Software와 문서 보존

[최종 software 요약](evidence/t12-fixture430-7c44abf/software-summary.json): exact 7c44abf 전체 Host 81개 그룹 **총 659개 = 658 PASS·1 조건부 Arduino CLI discovery SKIP**, native compiler SKIP 0. LLVM 22.1.8과 명시한 WinLibs sysroot를 사용했다. 앞선 c461182는 총 658개 = 657 PASS·1 조건부 SKIP로 별도 보존한다. 새 oracle·유한 buffer 순서를 포함한 subset 16개 PASS, 직접 관리 C/C++/ino 정렬 **360개 PASS**, 최종 pair target **2/2 PASS**다. [Host 원본](evidence/t12-fixture430-7c44abf/gate-host-final.log)과 [artifact index](evidence/t12-fixture430-7c44abf/target-artifact-index.json)에 연결한다. 전체 target 행렬·package gate·예제 compile 행렬·원격 Actions는 이번에 재실행하지 않았다. 이전 R13 software 결과를 이 source의 실기로 대체하지 않는다.

세 source 원본은 [56a88a5 manifest](evidence/t12-fixture430-56a88a5/raw-files.json), [c461182 manifest](evidence/t12-fixture430-c461182/raw-files.json), [7c44abf manifest](evidence/t12-fixture430-7c44abf/raw-files.json)에 UTF-8 LF 사본·원래 byte gzip·SHA-256으로 보존한다. 준비된 전체 PASS 감사 script의 존재는 실행 성공 근거가 아니며 이번에 실행한 감사는 partial-results-audit이다. [문서 검사](evidence/t12-fixture430-7c44abf/docs-verification.json)는 Markdown 195개, 원본 복원·scope·stage byte 대조를 기록한다. 사용 중인 I2S helper/native 검증은 유지했으며 제거할 저장소 임시 파일은 없었다. 기존 실패 기록·공개 자산·SDK·board는 보존한다.

## 재개 조건

원래 결선 확인은 **2026-09-06T18:13:49Z**에 만료했다. 최종 실패 실행은 18:13:17Z에 끝났고, 다음 실기 전에 현재 430 결선·스위치 유지 재확인을 요청했다. 만료 후 새 신호 시험은 실행하지 않았다. 재확인을 받은 새 시각만 기록하고 실제 clean HEAD의 exact pair를 빌드·검사해 재개한다. 문서 commit은 마지막 업로드 source와 다르다.

[완료 상태](evidence/t12-fixture430-7c44abf/completion-status.json)와 활성 TODO에 남은 430 오류를 유지한다. 440 PDM은 미실행이며 별도 USB 분리·재결선 확인이 필요하다. PWM period/duty capture·ADC calibration API/다중 채널 순서·남은 timer/event 요구, T13 복구·동시성·soak, T14 공용 PWM deferred START 취소 결함, T15 이후 통합·R14/공개 및 readiness 미해결 8개도 유지한다. 이번 부분 결과로 T12 전체나 M25를 완료 처리하지 않는다.
