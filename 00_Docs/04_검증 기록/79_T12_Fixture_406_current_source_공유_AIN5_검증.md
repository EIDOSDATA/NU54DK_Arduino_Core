# T12 Fixture 406 — current-source 공유 AIN5 검증

| 항목 | 내용 |
| --- | --- |
| 문서 ID / 개정 | NU54-T12-F406-001 / 1.0 |
| 실행일 | 2026-09-06 UTC |
| 판정 | **첫 실행 12/12 PASS·2,592 samples·cleanup 12/12 PASS** |
| 연결 작업 | T05/T10/T12, R00~R13 완료 유지 |
| 실제 시험 source | `96f38e9486c69cda2c76b48029bc0dc9404d9709` |
| 보드 gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Fixture catalog | revision 4, ID 406 |
| 실제 신호 시험 구간 | 7.094초; build/flash 시간 제외 |
| 다음 작업 | **407 AIN6/P1.13 → 408 AIN7/P1.14 필수 후속** |

## 결선과 신호원

사용자 “어. 그리 했어.” 답변을 2026-09-06T13:25:22Z에 기록한 뒤 유효 시간 안에 실행했다.
A DUT P1.12/AIN5(P4-10) ↔ B peer P1.14(P4-12), 공통 GND(P2-30)다. 이전 A P1.11 신호선은
제거하고 양쪽 USB를 분리해 변경한 뒤 재연결했다. DAP UART 분리·SWD 연결·SB4/PMIC 설정 유지 조건을
[checkpoint](evidence/t12-fixture406-96f38e9/checkpoint.json)와 [confirmation](evidence/t12-fixture406-96f38e9/confirmation.json)에 보존했다.
전원 rail은 연결하지 않았다. A는 D/COM5·6, B는 E/COM7·8이며 실제 probe UID는 SHA-256으로 보존한다.

[보드 원본 회로도](<../../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>) 1·3쪽에서
P1.12 → SB4 → VBAT_MON, R8 470kΩ/VBAT·R11 1MΩ/GND·C12 100nF 공유 회로를 대조했다.
B P1.14는 **시험 내내 INPUT**을 유지하고 내부 pull-down → pull-up → pull-down으로 입력을 바꾼다.
각 단계 25ms 정착 후 2ms 간격의 manual SAADC SAMPLE을 사용한다. 강한 출력은 활성화하지 않으며
SB4와 PMIC를 변경하지 않았다. 실제 SB4 연결 상태·배터리 전압·PMIC 동작은 측정하지 않았다.

## 구현과 software 검증

shared analog helper에 406 입력 바이어스 모드와 GPIO readback 판정을 추가했다. 405 오픈드레인 동작은
Host 회귀로 보존했다. Fixture gate·runner allowlist·catalog·시험 계획과 생성 목록을 함께 갱신했다.
407은 아직 실행 gate에서 거부하며 별도 준비·결선 확인 뒤 활성화한다.

제품 core/library/variant·build 도구·board·SDK 변경은 없다. 실제 컴파일 입력 구성은 405와 같고,
컴파일 translation unit 중 바뀐 파일은 signal_hil.cpp 하나다. Header 변경과 시험 코드 확장은 Git source로
고정했다. [입력 비교](evidence/t12-fixture406-96f38e9/build-input-comparison.json)는 이 변경 경계를 기록하며 이전 HIL을 새 image의 PASS로 복사하지 않는다.

| 검사 | 결과 |
| --- | --- |
| 전체 Host | **649 tests / 80 groups PASS** |
| 집중 회귀 | signal 13·fixture 12·lifecycle 3 PASS |
| 계약 | 45 tests PASS |
| 생성 목록 / Inventory | 75 identities·19 families / 75·23·16 PASS |
| C/C++ 정렬 | 358 files PASS; 한국어 Doxygen·BSD/Allman·4칸·중괄호 필수 |
| exact pair target | DUT/peer **2/2 PASS**, C:/u3m, 117.09초, build warning 없음 |
| readiness | 필수 16개 중 blocker 8개 유지 |

[software 검증](evidence/t12-fixture406-96f38e9/software-verification.json), [target build](evidence/t12-fixture406-96f38e9/target-build-evidence.json),
[artifact index](evidence/t12-fixture406-96f38e9/target-artifact-index.json)에 log·도구·SDK와 산출물 hash를 연결했다.
이번 변경은 시험 harness 확장으로 pair 2개 target을 빌드했다. R13 전체 target·package·예제 검사는
64번의 당시 source 근거로 유지한다. 준비 중 실패나 실기 재시도는 없었다.

## 실제 결과와 독립 판정

32/256 samples × single/double buffer × LOW/HIGH/LOW의 12 vector를 실행했다.
SAADC 12-bit·gain 1/4·oversample 1, INT16_MIN sentinel, 정확한 DMA count·pointer·완료 mask를 검사했다.
LOW 전 sample은 -256~512, HIGH 전 sample은 1024 초과~4095여야 PASS다.
각 세 단계의 HIGH 중앙값이 양쪽 LOW보다 512 초과하여 높은지도 독립 대조했다.

| sample 길이 | phase당 실제 sample | LOW 전 중앙값 | HIGH 중앙값 | LOW 후 중앙값 |
| --- | --- | --- | --- | --- |
| 32 | 32 | 138 | 3728 | 136 |
| 32 | 64 | 140 | 3728 | 136 |
| 256 | 256 | 136 | 3728 | 136 |
| 256 | 512 | 136 | 3728 | 136 |

LOW 전체 raw 범위 120~148, HIGH 3,716~3,740이다. 총 **2,592 samples**의 raw array와 SHA-256을
별도 계산해 재검산했다. 이는 공유 입력의 LOW/HIGH 기능이며 교정된 ADC 전압·정확도 결과가 아니다.

실제 GPIO 설정을 시작/종료 사이 24회 읽었다. B P1.14의 raw PIN_CNF mask 0xF0F는 LOW 0x4,
HIGH 0xC로 모두 INPUT이다. 각 vector 뒤 B 먼저, A 다음 순서로 disarm [0]을 확인했고,
B no-pull INPUT 복귀(raw mask 0)를 12회 확인했다. JSON과 journal은 기능 12·cleanup 12·campaign 2,
총 26 record가 순서까지 일치한다. [독립 감사](evidence/t12-fixture406-96f38e9/results-audit.json)에 검사 결과를 보존했다.

| 원본 | SHA-256 |
| --- | --- |
| [최종 JSON](evidence/t12-fixture406-96f38e9/fixture406-attempt1.json) | `e2184a0146d55a834183bb37ab9235a3fda74213db6a2a056152941ad2e4c953` |
| [append journal](evidence/t12-fixture406-96f38e9/fixture406-attempt1.json.jsonl) | `88a910fc54f413aea4ff6050332658dbe6fce4af52fa1858ad6fa3b6f220a67e` |
| [실행 log](evidence/t12-fixture406-96f38e9/fixture406-attempt1.log) | raw-files.json에 원본/정규화 hash 별도 기록 |

SWD는 양쪽 **10,000,000 Hz**, exact UID·sector erase·auto_unlock=false를 유지했다.
Mass erase/recover·unlock·속도 하향은 수행하지 않았다. pyOCD의 Board ID 5415 미등록 및
non-secure 상태 안내는 원본 log에 남겼고, target/CPUID/full source/역할과 실제 명령 결과를 별도로 검증했다.

## 종료 identity와 원본 보존

2026-09-06T13:40:06.129763+00:00의 [읽기 전용 postflight](evidence/t12-fixture406-96f38e9/postflight.json)에서 flash/reset/fixture 명령 없이
양쪽 CPUID 0x411FD210, full source와 DUT/peer role을 다시 확인했다.
순간 CPU 상태는 A **RUNNING**, B **SLEEPING**였다. GPIO 해제 판정은 앞선 cleanup readback이 소유한다.

| 역할 | HEX SHA-256 | ELF SHA-256 |
| --- | --- | --- |
| 1 | `bc450586da8a2307138c71216e62f5da28db37f4b93d5ff87a54ff863228a967` | `c588bf4fcf2a9adc3cede3a28e77603a5deebe6ad0506d8e180944615a69e754` |
| 2 | `7d4e9ee8c86895cd41636f56dadc9c71f32570b275eccb9f658b504d94af8b2c` | `8136abc4ddaf627e6483ccaded98a1bba644b6db02da4c3358859665bb7149a1` |

[실행 wrapper](evidence/t12-fixture406-96f38e9/run.py)와 [runtime](evidence/t12-fixture406-96f38e9/runtime.py)는 exact source·image·두 UID hash를 고정한다.
[원본 manifest](evidence/t12-fixture406-96f38e9/raw-files.json)의 **42개 입력**은 UTF-8 LF 사본 및 원본 byte gzip으로 보존했고,
gzip roundtrip·원본/정규화 SHA-256·평문 UID 없음 검사를 통과했다. 원본 log의 줄바꿈도 gzip으로 복원된다.
이 문서 이후 commit은 문서·증거 등록이며 실기 image source와 구분한다.

## 다음 작업과 남은 범위

401~404의 PWM 192개·41,472 samples, 405의 오픈드레인 12개·2,592 samples,
406의 입력 바이어스 12개·2,592 samples를 합쳐 **216개 기능·46,656 samples·216개 cleanup**이다.
AIN0~5의 해당 기능 경로까지 완료했으며 각 실행의 exact source는 구분한다.
**407·408 모두 필수**다. 이후 420 PDM·430 I2S·440 QDEC와 PWM period/duty capture,
ADC calibration/채널 순서 등 전체 T12 요구가 남아 있다. T13~T15·통합·RC·공개도 미완료다.

다음 407 결선 안내: 양쪽 USB를 분리하고 A 쪽 신호선만 **P1.12에서 P1.13/AIN6(P4-11)**로 옮긴다.
B **P1.14**와 공통 GND는 유지한다. DAP UART 분리·SWD 연결·기존 SB/PMIC 설정을 유지하고,
두 USB를 다시 연결한다. P1.13은 회로도 1·8쪽의 SW1 신호(버튼 부품 SW2)와 공유하므로 **버튼을 누르지 않는다**.
새 사용자 완료 확인 뒤 407 신호원·Host·exact build를 준비해 실행한다. 아직 407에 대한 확인·flash/HIL은 없다.

이번 추가 helper와 evidence는 실제 사용 중이다. 과거 실기·공개 자산·SDK·재사용할 exact image는 유지한다.
불필요하다고 확인된 새 tracked 파일은 없어 삭제하지 않았다. 최종 Git/프로세스 상태는 저장소 밖 완료 보고서에 남긴다.
GitHub Actions의 이번 source 상태는 별도로 확인하지 않았다.

## 최종 문서 검증

활성 문서와 새 79번 기록 9개를 갱신했다. Markdown UTF-8·내부 링크 **188 files**, 계약 45개,
Inventory 75/23/16 및 readiness blocker 8개 유지 검사를 통과했다.
[문서 검증 기록](evidence/t12-fixture406-96f38e9/documentation-verification.json)에 공개한 log의
정규화 byte hash를 보존했다. 사전 software 검증의 hash는 raw-files manifest와 gzip 원본 byte를 기준으로 한다.
문서 등록 뒤 링크 검사를 한 번 더 수행하고 staged 원본 gzip·hash·변경 경계를 대조한 뒤 commit·main push한다.
공개 release/tag는 생성하지 않는다. 최종 commit과 origin 일치·깨끗한 checkout·보드/SDK 불변·작업 프로세스 종료
결과는 저장소 밖 완료 보고서에 남겨 자기 commit hash를 소급 삽입하지 않는다.
