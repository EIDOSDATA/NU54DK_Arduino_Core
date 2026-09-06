# T10/T12 Fixture 440 — clock·gate 네 핀의 전기적 연결 관측

**PDM 전체 검증은 미완료이며 결선 확인이 필요하다. A/B의 P1.04·P1.05 중 한 핀만 HIGH로 구동했을 때, 나머지 세 핀을 입력 pull-down으로 두어도 모두 HIGH로 읽혔다. Fixture 440이 요구하는 독립된 clock·gate 두 net과 맞지 않아 추가 PDM 구동을 중단했다.**

기록일은 2026-09-07 Asia/Seoul, 원본 시각은 UTC다. [88번](88_T12_Fixture_440_current_source_PDM_검증.md)의 네 source 실패·HIL 수정·부분 DMA 결과는 그대로 보존한다. 이번 진단은 연결된 위치를 외부 점퍼나 특정 보드로 확정한 것은 아니다.

## 확인과 exact 실행

| 항목 | 내용 |
| --- | --- |
| 사용자 유지 확인 | “ㅇㅇ 그대로야. 언제쯤 PDM 검증 끝나?”, 2026-09-06T20:28:12Z 기록 |
| Source | b929b14f37d7d086c9accad748aab83b58a0e7be, clean main |
| Exact pair | C:/u4f, 두 역할 build-only 2/2 PASS, 122.39초 |
| SWD | 모든 flash·GPIO/mailbox/register 읽기·쓰기·postflight **10,000,000 Hz** |
| SDK / board | NCS 99553055607b2e9885fbc80ccd11fa9da81c2df0, Zephyr bf801e4e3d19e1ffa76164346480cb7734dd2800, board gitlink fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3 |
| 프로파일 | DAP UART 분리·SWD 연결, 같은 I/O 전압·공통 GND, SB/PMIC 유지 |
| 마지막 업로드 | 양쪽 b929b14, 이후 읽기 전용 identity·peripheral off·핀 입력 확인 |

[Checkpoint](evidence/t12-fixture440-b929b14/checkpoint.json)와 [confirmation](evidence/t12-fixture440-b929b14/confirmation.json)은 사용자 문구·시각·fixture 440 revision 5·catalog·source·probe/image hash를 연결한다. Sector flash·controlled start, auto_unlock=false를 유지했고 recover·mass erase·SWD 속도 하향은 없었다. 외부 결선 확인을 장치 열거로 대신하지 않았다. 뒤에 확인된 전기적 연결 문제는 이 사용자 확인과 별개의 관측이다.

## 실행과 판정

| 단계 | 관측과 한계 |
| --- | --- |
| 정적 data LOW/HIGH | [원본](evidence/t12-fixture440-b929b14/static-probe.json). PDM 시작 없이 GPIOTE source를 준비했다. 첫 script는 clock LOW를 가정해 초기 극성을 예상하여 4개 모두 assertion 실패했지만, 실제 OUTINIT과 peer 입력은 4회 모두 일치했다. 원래 실패를 보존하며 이를 PDM 기능 PASS로 세지 않는다 |
| Full canonical + 설정 trace | [결과](evidence/t12-fixture440-b929b14/fixture440-attempt1.json), [설정 trace](evidence/t12-fixture440-b929b14/setup-trace.jsonl). 이전과 같이 모노 DMA 4개 후 첫 stereo 동일 채널 실패·187개 미실행·cleanup 5회. Receiver PDM20 ENABLE=1, MODE=2(stereo/left-falling), CLK=37(P1.05), DIN=39(P1.07)를 읽었다. 같은 채널 결과를 mono mode 오설정이라고 단정할 근거는 없었다 |
| 정적 clock 전달 | [원본](evidence/t12-fixture440-b929b14/clock-path-probe.json). PDM/SPIS를 켜지 않고 receiver clock GPIO를 LOW/HIGH로 바꿨다. 예상 source clock뿐 아니라 gate pin도 함께 움직였다. Source GPIOTE event와 peer data 반응도 관측했지만 MHz timing 증거는 아니다 |
| Pull-down net 분리 검사 | [원본](evidence/t12-fixture440-b929b14/net-isolation-probe.json). 네 clock/gate GPIO 중 하나씩만 출력, 나머지는 입력 pull-down. 모든 구동 위치에서 네 핀이 함께 LOW/HIGH를 따랐다. **두 net의 분리 요구 FAIL** |
| 종료 | [Postflight](evidence/t12-fixture440-b929b14/postflight.json). 두 runtime identity·CPUID 확인, PDM20/PDM21/SPIS21/GPIOTE20 채널·DPPI20 channel 0 off, P1.04~07 입력. 실행 중 시험 없음 |

원래 정적 검사에서 예상과 반대였던 값은 준비 시 clock input이 HIGH로 읽혀 OUTINIT도 반대가 된 것과 일치한다. 이것을 데이터 선의 반전이나 public core 결함으로 해석하지 않는다. Pull-down 검사 이후에는 추가 PDM 구동을 하지 않았다. 원래 88번 및 이번 실행에 기록된 네 모노 DMA 완료를 **적법한 440 입력/밀도 검증 PASS로 확대하지 않는다**.

## 네 핀 분리 검사

| HIGH로 구동한 한 핀 | 정상 440에서 HIGH여야 하는 핀 | 실제 HIGH로 읽힌 핀 |
| --- | --- | --- |
| A P1.04 | A P1.04, B P1.05 | A P1.04·P1.05, B P1.04·P1.05 전부 |
| A P1.05 | A P1.05, B P1.04 | 네 핀 전부 |
| B P1.04 | B P1.04, A P1.05 | 네 핀 전부 |
| B P1.05 | B P1.05, A P1.04 | 네 핀 전부 |

각 LOW 구간은 네 핀 모두 0이었다. 4개 출력 위치 × LOW/HIGH × 4개 핀 = **32개 관측** 중 분리되어야 할 net의 HIGH 관측 8개가 예상과 다르다. 각 register의 PIN_CNF도 함께 보존했다. 한 핀만 DIR=output·INPUT=connected 값 1이고, 나머지 세 핀은 DIR=input·INPUT=connected·PULL=down 값 4였다. 따라서 단순 floating 입력만을 원인으로 보기 어렵다. 저항값·연결 위치·실제 PDM 파형의 정밀 계측은 하지 않았다.

직접 GPIO 진단은 승인된 P1.04/05와 data 입력만 사용했다. PDM/SPIS/GPIOTE 활성 상태가 아님을 먼저 확인했고, 동시에 서로 반대인 두 GPIO 출력을 만들지 않았다. `finally`에서 입력으로 복귀한 뒤 원래 OUT·PIN_CNF를 복원하고 cleanup을 확인했다. 마지막 P1.04의 원래 input pull-up 값 12와 나머지 기본 입력값 2도 보존했다.

[독립 감사](evidence/t12-fixture440-b929b14/diagnostic-audit.json)는 raw 32개·8개 분리 위반, 정적 source OUTINIT/peer 입력 일치, cleanup·postflight를 대조한다. `net-isolation-probe.json`의 top-level `status=passed`는 **진단 절차와 복원의 완료**만 의미한다. 기능 PASS는 명시적으로 false이며, 실제 결선 판정은 감사의 `wiring_matches_fixture440=false`다. 같은 파일의 진단 완료 상태를 결선 PASS로 해석하지 않는다.

## Software와 원본 보존

이번에는 repository code를 수정하지 않았다. [입력 비교](evidence/t12-fixture440-b929b14/software-summary.json)는 이전 ea4e25a와 두 역할의 **42개 translation unit 파일 hash·정규화 Kconfig·source membership·해석된 DTS byte가 모두 동일**함을 확인한다. Canonical runner·catalog도 같다. Runtime source identity만 새 commit에 맞게 달라지므로 이전 이미지의 SHA나 HIL 결과를 복사하지 않고 C:/u4f pair를 다시 빌드·업로드했다.

이전 ea4e25a의 Host **660 PASS·1 조건부 SKIP**, native compiler SKIP 0, 정렬 **361 PASS**는 해당 source 결과로 참조하며 이번 source의 새 실행이라고 표시하지 않는다. 전체 Host·제품 target·예제·계약·Inventory·package는 코드 변경이 없어 이번에 반복하지 않았다. 새 pair 2/2는 [artifact index](evidence/t12-fixture440-b929b14/target-artifact-index.json)와 [build 로그](evidence/t12-fixture440-b929b14/build.log)에 있다.

새 원본 55개는 [manifest](evidence/t12-fixture440-b929b14/raw-files.json)에 UTF-8 LF 사본·원래 byte gzip·SHA-256으로 보존한다. 원래 실패 log와 후속 감사는 함께 남긴다. [문서 검증](evidence/t12-fixture440-b929b14/docs-verification.json)은 Markdown 198개·원본 복원·변경 범위·stage byte를 확인한다. 88번 이하의 역사 기록·evidence·SDK·board·공개 자산은 변경하지 않았다. 사용하지 않는 저장소 임시 파일을 새로 만들지 않았다.

## 필요한 사용자 확인과 재개

현재 장애는 확인 시각의 단순 만료가 아니라 **clock·gate의 전기적 분리 조건 미충족**이다. 두 USB를 분리한 상태에서 아래 세 신호선을 확인한다.

| 신호 | A GPIO | B GPIO |
| --- | --- | --- |
| Clock | P1.04 | P1.05 |
| Gate | P1.05 | P1.04 |
| Data | P1.06 | P1.07 |

Clock·gate는 서로 독립된 두 선이어야 한다. 이전 I2S의 A P1.04↔B P1.04 또는 A P1.05↔B P1.05 선이 남아 있으면 제거한다. 공통 GND와 data는 유지하며 **A P1.07·B P1.06은 미연결**이다. 브레드보드의 같은 접점 등에서 두 신호가 합쳐지지 않았는지도 확인한다. 이것은 관측된 연결 위치의 단정이 아니라 점검 순서다. DAP UART 분리·SWD 연결을 유지해 USB를 재연결하고 실제 확인/수정 내용을 받아야 한다.

재개하면 **먼저 같은 pull-down net 검사로 두 신호의 분리를 확인**한다. 통과한 뒤 exact source의 전체 192개와 mono density 32개를 재시험하고, PDM의 settling 4·연속 measured 100 buffer 요구도 별도로 완료해야 한다. 분리 실패 상태로 PDM을 다시 켜지 않는다. GPIO가 이미 정확하게 연결되었다는 답변만으로 관측을 지우거나 임의 핀 변경·보드 회로 수정을 하지 않는다.

처음 안내한 20~40분은 진단·재시험 계획치였으며, 결선 점검과 새로운 실패 때문에 완료 시간을 확정할 수 없다. PDM/T12 전체 완료는 아직 아니고, T12 PWM capture·ADC calibration/다중 채널·timer/event, T13 이후·T14 공용 PWM·readiness 미해결 8개는 유지한다.
