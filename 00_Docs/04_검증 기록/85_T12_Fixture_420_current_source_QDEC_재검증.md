# T12 Fixture 420 — QDEC 수정본 재검증 완료

**Exact 6bd8d3f15ad29fc21f7a58c736cd86e917a3d314에서 기능 48개와 cleanup 48개, 별도 START 전 취소 6개가 모두 통과했다. 두 보드의 runtime identity·핀 복원·PWM/QDEC 해제까지 확인했다.**

[84번](84_T12_Fixture_420_current_source_QDEC_검증.md)의 첫 파형 실패와 fc9f153 취소 실패는 당시 결과로 보존한다.
이번에는 a3d0ab5의 마지막 GPIO LOW 준비·복원 교정과 같은 코드를 실제 clean main에서 다시 빌드하여 검증했다.
공용 PwmSequenceFabric의 미시작 deferred START 취소 결함은 T14 미해결 항목이며, 이 HIL 결과로 수정 완료 처리하지 않는다.

## Source와 새 확인

| 항목 | 값 |
| --- | --- |
| 실기 source | `6bd8d3f15ad29fc21f7a58c736cd86e917a3d314` |
| Target build | C:/u3u, DUT·peer **2/2 PASS**, 119.40초, build-only |
| 도구 | NCS v3.4.0, bundle dcbdc366a1, pyOCD nrf54l |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| SWD | flash·mailbox·postflight 모두 **10,000,000 Hz** |
| Fixture | 420, catalog revision 5, controller role 2 |
| 결선 재확인 | 사용자 “ㅇㅇ 그대로야.”, 2026-09-06T16:48:47Z |
| 실행 경계 | 이번 source 첫 실행 PASS, 실패·재시도 없음, 430 미실행 |

기록일은 2026-09-07 Asia/Seoul, 원본 시각은 UTC다. 기존 420 결선·DAP UART 분리·SWD 연결·SB/PMIC 유지 답변을
[새 checkpoint](evidence/t12-fixture420-6bd8d3f/checkpoint.json)에 남겼다. [confirmation](evidence/t12-fixture420-6bd8d3f/confirmation.json)은 현재 두 HEX와 full source,
probe digest·catalog hash에 연결되며 1,800초 기간 안에 모든 신호 시험을 마쳤다. 원래 만료된 시각을 덮어쓰지 않았다.

| 신호 | A DUT / role 1 | B peer / role 2 |
| --- | --- | --- |
| QDEC phase A | P1.04 (P2-12) | P1.14 (P4-12) |
| QDEC phase B | P1.06 (P2-10) | P1.10 (P4-8) |
| 공통 GND | P2-30 | P2-30 |

B만 송신하며 LED4/LED2 buffer 입력 공유는 그대로다. 정확한 두 probe와 full role/source를 검증하고 sector flash·제어 시작을 수행했다.
Mass erase·recover·auto-unlock·SWD 속도 하향은 사용하지 않았다. 원문 UID 대신 SHA-256 digest를 보존한다.

## 기능 48개와 별도 취소 6개

[정식 실행](evidence/t12-fixture420-6bd8d3f/fixture420-attempt1.json)은 PWM20/21/22 × QDEC20/21 × 1/100 cycles × 정·역방향 × debounce off/on,
상태 간격 2,000 us의 **48개**를 검사했다. 예상 누산 **±4/±400**과 전부 일치했으며 double transition은 0,
절대 누산 합계 **9,696**, signed 합계 0이었다. 기능 campaign 연속 시간은 **22.063초**다.
[독립 결과 감사](evidence/t12-fixture420-6bd8d3f/results-audit.json)에서 고유 ID·순서·48 cleanup·campaign 관리 2개를 합친 98개 journal을 최종 JSON과 대조했다.
48 cleanup 모두 양쪽 disarm `[0]`이며 각 image·confirmation hash와 10 MHz flash도 확인했다.

[준비 취소 실행](evidence/t12-fixture420-6bd8d3f/prepared-cancel.json)은 정식 시험의 마지막 유효 disarm 응답 CRC·nonce·sequence를 검사한 뒤
같은 firmware에서 reset/flash 없이 이어갔다. PWM20/21/22 × QDEC20/21의 **6개 조합**을 별도로 검사했다.
START 명령은 보내지 않았으며, 20 ms 뒤 다음을 모두 확인했다.

- 송신 준비 상태가 ready·미시작·미완료·오류 없음이고 B P1.14/P1.10은 LOW 출력(PIN_CNF=3)이었다.
- A P1.04/P1.06 입력은 LOW, QDEC 누산·double·오류 report는 `[0,0,0]`이었다.
- 양쪽 disarm 총 12회가 `[0]`였고, 각 조합마다 B OUT latch와 전체 PIN_CNF가 준비 전 값으로 복원됐다.

이 6개는 기능 48개와 구분한다. 이전 fc9f153의 실패를 성공으로 고치지 않으며 이번 교정 경로의 새 실기 증거다.
[읽기 전용 postflight](evidence/t12-fixture420-6bd8d3f/postflight.json)에서는 두 full identity와 CPUID `0x411fd210`, CPU SLEEPING,
양쪽 신호 핀 PIN_CNF=2, PWM20/21/22와 QDEC20/21 ENABLE=0을 확인했다. 후속 flash/reset/fixture 명령은 없었다.
실제 encoder·bounce 주입 효과·교정된 주기/jitter·overflow·invalid transition·T13 동시성/soak는 측정하지 않았다.

## Software 근거와 원본 보존

[software 변경 경로 비교](evidence/t12-fixture420-6bd8d3f/software-input-comparison.json)에서 a3d0ab5→6bd8d3f가 문서·증거만의 차이임을 확인했다.
[이번 build 입력 비교](evidence/t12-fixture420-6bd8d3f/build-input-comparison.json)와 [artifact index](evidence/t12-fixture420-6bd8d3f/target-artifact-index.json)는 이전 C:/u3t와
42개 저장소 translation unit의 hash·membership·정규화 설정이 같은 것을 확인하고 현재 source identity를 별도로 보존한다.
이전 a3d0ab5 전체 Host **총 657, 656 PASS·1 조건부 Arduino CLI discovery SKIP**, 81개 그룹·native compiler SKIP 0와
C/C++ 정렬 **359 PASS**는 [84번의 software 근거](evidence/t12-fixture420-a3d0ab5/software-summary.json)를 따른다.
이번 재개에서는 코드를 변경하지 않았으며 그 Host/정렬 실행을 새 source에서 재실행한 것으로 세지 않는다.
계약·package·Inventory·예제 발견의 이전 실행 source도 84번에 구분되어 있다.

[manifest](evidence/t12-fixture420-6bd8d3f/raw-files.json)에 이번 원본 37개의 UTF-8 LF 사본과 원래 byte gzip·SHA-256을 연결했다.
[문서 검사](evidence/t12-fixture420-6bd8d3f/docs-verification.json)는 Markdown 194개와 원본 복원·scope·Git stage byte 대조를 기록한다.
문서 commit은 업로드 source와 구분하며 다음 flash는 실제 clean HEAD의 pair를 검사한다.
저장소 임시 파일은 추가하지 않았다. 사용 중인 QDEC header와 native 검증은 유지하고 기존 실패 근거·SDK·board·공개 자산은 보존했다.

## 다음 430 I2S

아래 GPIO와 커넥터 대응은 [현재 catalog·pinmap 감사](evidence/t12-fixture420-6bd8d3f/next-wiring-audit.json)로 대조했다. **430은 아직 실행하지 않았다.**
양쪽 USB를 분리하고 기존 420 신호선을 제거한 뒤 다음과 같이 바꾸고 USB를 다시 연결한다.

| 신호 | A 보드 | B 보드 |
| --- | --- | --- |
| SCK | P1.04 (P2-12) | P1.04 (P2-12) |
| LRCK | P1.05 (P2-11) | P1.05 (P2-11) |
| A SDOUT → B SDIN | P1.06 (P2-10) | P1.07 (P2-9) |
| B SDOUT → A SDIN | P1.07 (P2-9) | P1.06 (P2-10) |
| 공통 GND | P2-30 | P2-30 |

MCK 연결은 없다. DAP UART 분리·SWD 연결·기존 SB/PMIC 유지 조건의 새 사용자 확인 후 430을 진행한다.
401~408의 276 기능·59,616 samples·276 cleanup 근거는 [83번](83_T12_Fixture_408_current_source_PWM_ADC_검증.md)에 유지한다.
440 PDM·남은 T12 요구·T13 복구/동시성/soak·T14 공용 PWM 결함·T15 이후 통합·R14/공개와 readiness 미해결 8개는 유지한다.
[완료 상태](evidence/t12-fixture420-6bd8d3f/completion-status.json)와 활성 TODO를 다음 작업의 출발점으로 사용한다.
