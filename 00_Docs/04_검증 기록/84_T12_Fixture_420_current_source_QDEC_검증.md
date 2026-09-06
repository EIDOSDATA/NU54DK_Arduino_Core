# T12 Fixture 420 — QDEC 기능 검증과 준비 취소 교정

**fc9f153의 기능 48개는 통과했다. 이후 START 전 취소에서 STOP 실패를 발견했고, 마지막 수정 a3d0ab5의 실기 재검증은 결선 유지 답변 대기다. 420 최종 완료로 처리하지 않는다.**

| Source / build | 관측 결과 | 상태 |
| --- | --- | --- |
| beebef829de94f92a3a0b6b8b0a6ed2447d3b560 / C:/u3r | 첫 QDEC report `[0,0,1]`, 기능 0·cleanup 1 | 실패 원본 보존 |
| fc9f1536e2caf4efee387c1a69b3a4c9e24adf3b / C:/u3s | 기능 48·cleanup 48·22.172초 PASS, 이후 별도 준비 취소에서 B STOP 실패 | 기능 PASS와 취소 FAIL 구분 |
| a3d0ab59bcee7a7940177fd768ad0f4a7c40c65c / C:/u3t | 전체 Host 656 PASS·1 조건부 SKIP, pair build 2/2 | 마지막 교정본 실기 미실행 |

기록일은 2026-09-07 Asia/Seoul이며 원본 시각은 UTC다. 모든 flash·mailbox·진단·리셋·postflight는 **SWD 10,000,000 Hz**다.
Board gitlink `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0·bundle dcbdc366a1을 유지했다.

## 확인된 결선과 범위

| 기능 | A DUT / role 1 | B peer / role 2 |
| --- | --- | --- |
| QDEC phase A | P1.04 (P2-12) | P1.14 (P4-12) |
| QDEC phase B | P1.06 (P2-10) | P1.10 (P4-8) |
| 공통 GND | P2-30 | P2-30 |

사용자 “연결 했어. 시작하자.”를 2026-09-06T16:05:26Z에 기록했다. 양쪽 USB를 분리하여 위 결선으로 변경 후 재연결,
DAP UART 분리·SWD 연결·기존 SB/PMIC 유지 조건이다. B만 송신하며 B P1.14/P1.10의 LED buffer 공유는 그대로다.
Fixture revision 5, controller role 2. [원래 확인](evidence/t12-fixture420-beebef8/checkpoint.json)과 각 image에 연결된 [실행 확인](evidence/t12-fixture420-fc9f153/confirmation.json)을 보존했다.
원래 확인 시각은 재사용 시에도 바꾸지 않았다. runner의 1,800초 확인 기간이 16:35:26Z에 만료되어 같은 결선 유지 질문을 보냈다.
이 기록 시점에는 답변을 받지 못해 a3d0ab5에 대한 새 확인서·flash·실기 결과를 만들지 않았다.

## 첫 실패와 파형 교정

[beebef8 실행](evidence/t12-fixture420-beebef8/fixture420-attempt1.json)은 첫 항목에서 누산 0·double transition 1로 실패했다. 두 disarm은 `[0]`이다.
[같은 결선 진단](evidence/t12-fixture420-beebef8/qdec-diagnostic1.json)은 reset/flash 없이 기존 유효 nonce와 마지막 disarm sequence를 검증해 이어서 수행했다.
PWM20→QDEC20, 100 cycles·10 ms 상태 간격의 유한 파형에서 A 두 핀의 네 상태를 모두 읽었다. 최종 누산은 -400·double 2였다.
시작 전에도 -2·double 1이 관측돼 이 진단을 정확한 400-edge PASS로 세지 않는다. SWD GPIO trace는 전기적 파형 계측이나 모든 edge 포착을 보증하지 않는다.

Nordic 전이 표에서 AB의 A는 상위 비트이며 정방향은 00→01→11→10→00이다.
또한 PWM 값의 bit 15를 1로 둔 FallingEdge 극성에서 compare 0/TOP이 LOW/HIGH가 된다.
[QDEC 표](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/qdec.html-concept_gfd_jzd_4r),
[PWM 규칙](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/pwm.html-concept_l3d_smw_nr).
기존 시험 generator는 A/B bit 배치를 거꾸로 사용했고 PWM 극성을 생략했다. QDEC가 켜진 뒤 송신 GPIO를 초기화하던 순서도 교정했다.
`qdec_waveform.h`를 실제 native compile/run하고 출력값을 독립 AB decoder에 넣어 방향·4/400 count·종료 LOW를 검증했다.
QDEC의 기대값이나 double-transition 오류 기준은 완화하지 않았다. 제품 core·SDK·board는 수정하지 않았다.

## fc9f153 기능 PASS와 별도 취소 FAIL

[정식 48-vector 실행](evidence/t12-fixture420-fc9f153/fixture420-attempt1.json)은 PWM20/21/22 × QDEC20/21 × 1/100 cycle × 정·역방향 × debounce off/on을 검사했다.
상태 간격 2,000 us·QDEC sampling 256 us, expected ±4/±400이 모두 일치했다. 절대 누산 합계 **9,696**, signed 합계 0, double 0이다.
48 cleanup과 campaign 관리 2개를 더한 **98개 journal**을 [독립 감사](evidence/t12-fixture420-fc9f153/results-audit.json)에서 최종 JSON과 순서·image/confirmation hash까지 대조했다.
Debounce on/off는 설정·정상 신호 수신 범위이며 실제 bounce 주입이나 필터 효과 검증은 아니다.

[추가 prepared-cancel](evidence/t12-fixture420-fc9f153/prepared-cancel.json)은 START 전에 두 출력 LOW·QDEC `[0,0,0]`를 확인했다.
하지만 첫 PWM20/QDEC20 조합의 B disarm이 `status=730, result=[1]`로 실패하여 전체 진단은 FAIL이며 나머지 5개는 실행하지 않았다.
원인은 미시작 `start_via_task=true` PWM에서 STOP 완료를 확인하지 못한 것이다. 기능 48 PASS와 합쳐 전체 PASS라고 하지 않는다.
[읽기 전용 snapshot](evidence/t12-fixture420-fc9f153/postflight-stored.json)은 두 runtime identity와 B의 잔여 설정을 보존했다.
처음 postflight wrapper가 dirty checkout 검사로 probe 접근 전 실패한 [로그](evidence/t12-fixture420-fc9f153/postflight-after-cancel.log)도 삭제하지 않았다.
그 뒤 [B 제어 리셋](evidence/t12-fixture420-fc9f153/cleanup-reset.json)으로 파형 재시험·flash 없이 자원을 회수했다. full source/role 재확인,
PWM20/21/22 ENABLE=0, P1.14/P1.10 PIN_CNF=2를 읽어 reset cleanup을 확인했다. 이를 원래 STOP 성공으로 바꾸지 않는다.

## 마지막 교정본과 남은 검증

a3d0ab5에서는 START 전 DMA 활성화 대신 두 송신 GPIO의 OUT/PIN_CNF를 저장하고 LOW로 준비한다.
START에서 기존 PWM play를 호출하며, STOP 확인 후 또는 시작 전 취소 시 원래 GPIO 상태를 복원한다.
STOP timeout 상태는 다음 stopAll에서 다시 STOP을 확인하며 해제 증거 없이 복원하지 않는다.
고정 pin allowlist·fixture gate·기존 HIL 단독 점유 경계 안의 변경이다. public PwmSequenceFabric의 미시작 deferred START 취소 동작 자체는 **T14 미해결 이슈**로 추적한다.

| 검사 | 결과와 source |
| --- | --- |
| 최종 전체 Host | a3d0ab5 총 **657**, 656 PASS·1 조건부 Arduino CLI package-discovery SKIP, 81개 그룹; native compiler SKIP 0 |
| C/C++ 정렬 | 마지막 HIL 코드 359개 PASS, clang-format 22.1.8 |
| QDEC native/Host | 7 PASS, 실제 생성값을 독립 전이 표로 검증 |
| Signal Host | GPIO idle 교정 단계 14 PASS, 이후 전체 final Host에도 포함 |
| 계약 / package | 계약 45 PASS, fc9f153 package 20 PASS |
| Inventory / 예제 | fc9f153 generated·75 identities/19 families·75 inventory·23 serial·16 system·예제 발견 PASS |
| Target | 각 source의 pair 2/2 build PASS. 마지막 a3d0ab5 실기 미실행 |

[최종 Host 원본](evidence/t12-fixture420-a3d0ab5/gate-host-final.log), [software 요약](evidence/t12-fixture420-a3d0ab5/software-summary.json),
[build index](evidence/t12-fixture420-a3d0ab5/target-artifact-index.json), [build 입력 비교](evidence/t12-fixture420-a3d0ab5/build-input-comparison.json)을 보존했다.
앞선 dirty 단계 Host는 655 PASS·2 SKIP였으며 clean m27 9개 재검사와 마지막 clean 전체 Host를 별도 원본으로 남겼다.
fc9f153→a3d0ab5 차이는 TODO와 HIL signal_hil.cpp뿐이다. 최종 42개 translation unit 중 변경은 HIL signal_hil.cpp,
정규화 설정·source membership·제품 core·SDK·board는 동일하다. package/Inventory를 a3d0ab5에서 새로 실행했다고 세지 않는다.

다음에는 결선 유지 답변을 받고 **실제 clean HEAD exact pair**를 확인하여 기존 48개와
[준비 취소 6개 계획](evidence/t12-fixture420-a3d0ab5/prepared_cancel.py)을 실행한다. 취소 계획은 각 PWM/QDEC 조합에서 START 없음·LOW·누산 0,
양쪽 disarm 및 B OUT/PIN_CNF의 원래 값 복원을 검사한다. 성공 후 postflight와 문서를 갱신한다.
현재 보드의 업로드 source는 fc9f153이며 C:/u3t의 a3d0ab5와 다르다. 문서 commit 이후 HEAD도 별도다.
430 I2S·440 PDM·남은 T12 요구·T13 soak/동시성·최종 통합·R14/공개와 readiness 미해결 8개는 유지한다.
401~408의 역사 근거 276 기능·59,616 samples·276 cleanup은 [83번](83_T12_Fixture_408_current_source_PWM_ADC_검증.md)에 유지한다.

## 원본 보존과 재개

[beebef8 manifest](evidence/t12-fixture420-beebef8/raw-files.json), [fc9f153 manifest](evidence/t12-fixture420-fc9f153/raw-files.json), [a3d0ab5 manifest](evidence/t12-fixture420-a3d0ab5/raw-files.json)은
각 stage의 UTF-8 LF 사본과 원본 byte gzip·SHA-256을 제공한다. 준비만 한 script를 실행 결과로 세지 않는다.
UID 원문 부재, gzip 복원, 실제 workspace 원본·Git stage byte를 검사한다. 과거 기록·SDK·board·공개 자산은 보존했고,
새 C++ header는 현재 HIL에서 사용한다. 불필요한 저장소 임시 파일은 추가하지 않았다.
[최종 문서 검사](evidence/t12-fixture420-a3d0ab5/docs-verification.json)와 [재개 상태](evidence/t12-fixture420-a3d0ab5/completion-status.json)를 함께 읽는다.
