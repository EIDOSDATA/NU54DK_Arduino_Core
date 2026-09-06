# T12 Fixture 407 준비와 Host 실행 차단

| 항목 | 내용 |
| --- | --- |
| 문서 ID / 개정 | NU54-T12-F407-PREP-001 / 1.0 |
| 작성일 | 2026-09-06 UTC |
| 판정 | **준비 부분 완료·Host BLOCKED·407 flash/HIL NOT RUN** |
| 준비 source | `076685aa78247ec18e4fd95be50b2123a1f043fa` |
| 보드 gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 연결 작업 | T05/T10/T12; R00~R13 완료 유지 |
| 마지막 실제 HIL | Fixture 406, exact `96f38e9486c69cda2c76b48029bc0dc9404d9709` |
| 다음 | 승인된 Host 환경에서 필수 회귀 완료 후 407 실기; 408도 필수 후속 |

## 확인된 결선과 시험 준비

사용자는 직전 407 안내에 대해 “USB 제거 후 407 결선을 한 다음, 다시 연결을 했어.
이제 진행하도록 해.”라고 확인했다. 첫 기록 시각은 **2026-09-06T13:47:49Z**다.
A **P1.13/AIN6(P4-11)** ↔ B **P1.14(P4-12)**와 공통 GND(P2-30), 이전 A P1.12 제거,
양쪽 USB 분리 후 변경·재연결, DAP UART 분리·SWD 연결·버튼 미누름 안내 조건이다.
[사용자 확인 기록](evidence/t12-fixture407-preparation-076685a/checkpoint.json)에 당시 안내와 답변을 함께 보존했다.

[보드 회로도](<../../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>) 1·8쪽에서 P1.13은
SW1 신호(버튼 부품 SW2)와 공유하며 누르면 GND로 연결됨을 대조했다. 외부 pull-up은 없고
회로도는 내부 pull-up 사용을 지시한다. B P1.14는 R34 330Ω를 거쳐 LED4용 U9B buffer 입력에도 연결된다.
407은 B를 **INPUT 상태로 유지**하고 내부 pull-down/up/down으로만 신호를 만든다.
버튼을 누르지 않고 단계마다 25ms 정착 후 32/256 samples·single/double buffer를 검사하는 **12 vector**를 준비했다.
LOW는 전 sample -256~512, HIGH는 전 sample 1024 초과~4095, GPIO raw INPUT·DMA sentinel/count·양쪽 cleanup을 요구한다.
버튼 자체·debounce·wake·교정 전압 시험은 아니다. 기존 SB/PMIC 설정과 강한 출력 구동은 변경하지 않았다.

Fixture catalog revision 5에 407을 등록하고 gate·runner·shared helper·Host 테스트·생성 목록을 갱신했다.
405/406의 기존 판정을 보존하고 407 stuck-LOW·출력 모드·누락 sample·sentinel·경계 위반 회귀를 추가했다.
제품 core/library/variant·build tool·board·SDK는 변경하지 않았다.

## 실제 실행한 검사

| 검사 | 결과 |
| --- | --- |
| Signal Host 14개 | Python 판정 **13 PASS**, C++ helper 실행 **1 BLOCKED** |
| Lifecycle Host 3개 | 컴파일러 실행 **3 BLOCKED** |
| Fixture Host | **12 PASS** |
| 계약 | **45 PASS** |
| C/C++ 정렬 | **358 files PASS**; 한국어 Doxygen·BSD/Allman·4칸·중괄호 필수 |
| 생성 목록 / Inventory | 75 identities·19 families / 75·23·16 PASS |
| 준비 시점 문서 | Markdown **188 files PASS** |
| exact pair target | **DUT/peer 2/2 build-only PASS**, C:/u3n, 114.63초, warning 없음 |
| USB 열거 | 두 지정 UID hash·D/COM5·6 및 E/COM7·8 정상 |
| 전체 Host / 407 flash·reset·HIL | **미완료 / 미실행** |
| readiness | 필수 16개 중 blocker 8개 유지 |

[차단 상태](evidence/t12-fixture407-preparation-076685a/blocked-status.json), [target build](evidence/t12-fixture407-preparation-076685a/target-build-evidence.json),
[artifact index](evidence/t12-fixture407-preparation-076685a/target-artifact-index.json), [prepared images](evidence/t12-fixture407-preparation-076685a/prepared-images.json),
[USB 열거](evidence/t12-fixture407-preparation-076685a/usb-only-inventory.json)에 각 결과를 구분했다.
전체 Host 650 PASS나 407 실기 PASS로 집계하지 않는다. Target build는 C++ Host 실행과 실제 보드 검증을 대체하지 않는다.

## Host 차단의 근거와 대응

Windows가 기존 고정 Host 컴파일러
`C:\NU54DEV\tools\WinLibs-16.1.0-UCRT\mingw64\bin\g++.exe` 실행을
**WinError 4551 — 애플리케이션 제어 정책에서 이 파일을 차단했습니다**로 거부했다.
Windows 경로로 통일한 직전 406의 고정 Host 환경에서도 동일하게 거부됐다. 최초 혼합 구분자 PATH가
원인이었다고 단정하지 않는다. [Code Integrity 이벤트](evidence/t12-fixture407-preparation-076685a/host-code-integrity-events.json)의
3033/3077과 Smart App Control 차단 기록에서 해당 executable을 확인했다.
[컴파일러 hash](evidence/t12-fixture407-preparation-076685a/host-compiler-hash.json)는
`82b7669f84077cfd283ee165b53c75180251ea665fe1440cf5e7b4d160dc37cd`다.

최초 [signal log](evidence/t12-fixture407-preparation-076685a/signal-host-initial.log)와 [lifecycle log](evidence/t12-fixture407-preparation-076685a/lifecycle-host-initial.log),
고정 환경의 [signal 재확인](evidence/t12-fixture407-preparation-076685a/signal-host.log)을 보존했다. 이는 Host 환경 차단이며
실기 실패나 보드 결함이 아니다. 보안 정책·allowlist·파일 차단 속성을 변경하거나 컴파일러를 위장하지 않았다.
승인된 별도 Host 환경이 있는지 사용자에게 질문했고 답변 대기 중이다.

## 원본 보존과 재개

[원본 manifest](evidence/t12-fixture407-preparation-076685a/raw-files.json)의 **36개 입력**을 UTF-8 LF 사본과 원본 byte gzip으로 보존했다.
원본/정규화 hash, gzip roundtrip 및 평문 UID 없음 검사를 수행했다. 과거 401~406 실기·공개 자산은 유지했다.
현재 두 보드는 406 image를 마지막으로 올린 상태이며 이번 USB 재연결 후 firmware runtime identity를
다시 읽은 것은 아니다. 이번에는 USB 열거와 빌드 image 파일 검사만 했다.

1. 기존 차단 기록을 보존하고, 실행이 승인된 Host 개발 환경을 확인한다. 보안 정책을 우회하지 않는다.
2. 해당 환경과 실제 source를 기록하고 signal/lifecycle 및 canonical 전체 Host gate를 통과한다.
3. 소스가 바뀌면 새 clean source와 exact pair image를 다시 결합한다. 문서 commit으로 HEAD가 달라졌다고
   기존 build source 문자열만 바꿔 사용하지 않는다.
4. 결선 확인의 30분 유효 시간이 지나면 현재 407 결선·스위치·버튼 미누름을 재확인한다.
   원래 확인 시각을 현재 시각으로 덮어쓰지 않는다. 두 UID와 exact HEX hash로 새 확인서를 만든다.
5. **SWD 10,000,000 Hz**, sector erase·auto_unlock=false를 유지해 407 한 번 실행하고 실제 원본으로 판정한다.
6. 결과·문서·최종 검사 후 commit·main push한다. 이어 408 결선 확인과 실기를 반드시 수행한다.

현재 407의 필수 Host gate가 미완료이므로 이번 준비·차단 기록은 로컬 checkpoint commit으로 보존하고
원격 main에는 푸시하지 않는다. TODO의 최종 회귀 후 push 조건을 유지한다. 새 release/tag는 없다.
401~406 누계 **216개 기능·46,656 samples**와 T12 부분 완료 상태는 그대로이며 407 결과를 더하지 않는다.
추가 helper는 실제 참조 중이고 과거 증거·exact image는 재개에 필요하므로 삭제하지 않았다.

## 문서·증거 저장 검증

활성 문서와 새 기록 9개를 갱신했고 Markdown UTF-8·내부 링크 **189 files PASS**를 확인했다.
[문서 검사](evidence/t12-fixture407-preparation-076685a/documentation-verification.json)에 log hash를 보존한다.
문서 등록 뒤 최종 링크 검사와 staged 원본 36개 gzip/hash 대조를 수행한 후 로컬 checkpoint로 commit한다.
필수 Host 검증은 계속 BLOCKED이며 문서 검사를 Host 또는 물리 PASS로 사용하지 않는다.
최종 Git 상태·실행 프로세스 종료·board/SDK 불변은 저장소 밖 인계 보고서에 남긴다.
