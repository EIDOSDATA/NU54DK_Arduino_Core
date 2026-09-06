# T09 UART 유휴 bias 교정과 BLE 무배선 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | T09/T14 추가 USB·온보드·BLE; 외부 current-source T11 직전 정지 |
| 최초 exact source | `18a7cbec9cceed38d6c866131afdac9e6ffbc4b8` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 최신 사용자 확인 | 전원 OFF 후 DAP UART 연결 전환·USB 재연결 완료, SWD 연결 유지, 보드 간 선 없음 |
| 최종 결과 | BLE 3개 pair gate PASS; 수정 source 373d98d의 온보드 8개 runner·18개 결과 PASS; 외부 T11 NOT RUN |

## 최초 결과와 교정 근거

`C:/u2a` exact 18a7cbe의 17개 target은 build-only 17/17, failed/error/warning 0이다.
두 보드는 D/COM5·COM6과 E/COM7·COM8로 식별했고 UID 원문은 기록하지 않았다.
앞선 65번의 UART 분리 상태는 역사적 사실이며 이번 사용자 확인으로 연결 상태가 바뀌었다.

TWIM20/21은 두 보드 모두 PMIC `0x41`을 반환했으나 TWIM22 READY는 A 34바이트,
B 33바이트로 실패했다. B에서는 정확한 32바이트 앞의 `f8`을 포착했다.
A의 같은 TWIM22 image를 flash 없이 한 번 reset한 진단에서는 정확한 READY·PMIC 결과가
통과했다. 이 진단을 최초 suite PASS로 대체하지 않는다. M25 A도 READY prefix 6바이트로 실패했다.
UART20은 양쪽 보드 모두 선택 P1 VCOM에서 정확한 32바이트 역순 응답을 받았으나
비선택 P0 VCOM에 각각 11/12바이트가 들어와 strict oracle이 실패했다.

B UART20의 동일 firmware에서 비선택 P0.00 PIN_CNF는 `0x2`(입력, pull 없음)였다.
한 번의 비교 진단에서 원래 설정은 비선택 COM8 9바이트로 실패했고, PULL 필드만 임시
pull-up `0xe`로 바꾸면 선택 COM7의 정확한 응답과 COM8 무응답이 함께 통과했다.
진단 뒤 PIN_CNF `0x2` 복원을 readback으로 확인했다. 흐름제어·CTS 시험은 하지 않았다.
이 근거는 온보드 fixture의 유휴 bias 누락을 가리키며 납땜 위치나 모든 USB 잡음 원인을
확정하는 전기적 측정은 아니다.

`onboard_start.py`는 exact CPUID와 HALTED 상태 확인 뒤 P0.00·P1.04가 입력인지 먼저
검사하고 PULL만 변경한다. 두 pin 모두 검사한 뒤 쓰며 readback 실패 시 resume하지 않는다.
그 뒤 초기 VCOM buffer를 비우고 앱을 시작한다. READY·응답의 추가 byte, 중복 응답과
비선택 포트의 데이터 거부는 그대로다. 제품 runtime·공개 API·저장 형식·board·SDK는 변경하지 않는다.
신규 Host 3개는 수정 전 3 FAIL, 수정 후 3 PASS이며 온보드 전체 관련 Host 28개 PASS다.
교정 commit `373d98da055b83e86b039448965d630e8d546497`을 고정한 뒤 아래 실제 보드 회귀를 완료했다.

## BLE actual pair 결과

모두 clean exact 18a7cbe에서 canonical runner·DAPLink MSD flash·COM5/COM7·128-bit nonce를
사용했다. 두 보드 사이 전선 없이 RF로 실행했고 raw transcript와 원본 JSON을 작업 폴더
`work/t09-connected`와 아래 evidence 경로에 원본 byte·hash를 함께 보존했다. UID만 출력·JSON 직렬화 전에 SHA-256 표기로 대체했으며 판정은 canonical runner 그대로다.

| Gate | 실제 결과 |
| --- | --- |
| M19 GAP | scan filter·advertising·link request·connect/disconnect·재광고·재연결·callback 문맥 PASS |
| M20 generic GATT | discovery·read/write·notify/indicate·unsubscribe·disconnect 뒤 handle 무효화·재발견 PASS |
| M21 security/profile | pairing·bond warm-reboot 복원·삭제 뒤 재부팅 zero·old-key 거부·repair·BAS/DIS/HID protocol PASS |

M21은 시험 bond를 clear/erase/re-pair하며 factory reset이나 mass erase를 하지 않았다.
Windows/스마트폰 HID 입력 수동 확인, AC-03 EEPROM/LittleFS 파괴 시험과 최종 RC lifecycle은
이번 BLE PASS에 포함하지 않는다. 기존 peer P0 CTS 납땜 이슈의 중단 지시도 유지한다.

## 교정 후 실제 온보드 결과

제품 실행 source·테스트 앱은 바꾸지 않고 HIL의 시작 준비만 교정했다. 그래도 clean exact
revision 계약에 맞춰 `C:/u2b`에 373d98d의 온보드 9개와 pair 역할 2개를 새로 build했다.
11/11 build-only, failed/error/warning 0이며 최초 17개 중 대응하는 11개와 컴파일 입력 파일 hash·
resolved config·source membership·FLASH/RAM 사용량이 같다. Runtime commit identity byte는 새
revision을 반영하므로 HEX 자체를 이전 이미지와 같다고 주장하지 않는다.

| 실제 검사 | A/DUT | B/peer |
| --- | --- | --- |
| UARTE20/21/22/30 | 4/4 PASS | 4/4 PASS |
| TWIM20/21/22 PMIC read-only | 3/3 PASS, 모두 0x41 | 3/3 PASS, 모두 0x41 |
| M25 event·내부 VDD·stream handle | PASS, 2004 ticks / raw 4092 | PASS, 2004 ticks / raw 4092 |
| M26 TEMP·WDT30 reset | PASS, 3450 centi-°C / cause 0x10 | PASS, 3575 centi-°C / cause 0x10 |

8개 canonical runner에서 **18개 결과 PASS, 수정 후 실패 0개**다. 최초 18a7cbe의 실패 5개는
별도로 보존한다. 모든 초기 READY와 측정 응답은 선택 VCOM에서 정확한 32바이트였고 비선택
포트는 조용했다. UART는 115200 baud·32바이트, RTS/CTS off다. 기존 peer P0 CTS 실패 경로의
흐름제어·정지/재개 시험은 재실행하지 않았으며 이번 무흐름제어 PASS로 그 실패를 지우지 않는다.

M26의 의도한 watchdog reset 경계에서만 기존 protocol v2가 허용하는 prefix를 A 27바이트,
B 3바이트로 기록했다. RESET_READY 대기는 각각 1.937/1.938초다. 초기 READY·AR26·NU26
판정은 완화하지 않았다. 내부 VDD raw 4092는 교정 전압·ADC 정확도 보증이 아니다.

## Software 회귀와 실행 환경 오류

| 검사 | 결과 |
| --- | --- |
| 전체 Host | 643개 중 642 PASS / 조건부 M13 설치 discovery 1 SKIP |
| 실제 설치본 M13 discovery 별도 실행 | 11/11 PASS, 조건부 경로 실제 확인 |
| 교정 관련 온보드 Host | 28/28 PASS, 전체 Host에도 포함 |
| CI contract | 45/45 PASS |
| Inventory·생성 drift | instance 75 / Serial 23 / System capability 16 PASS |
| C/C++ style | clang-format 22.1.8, 직접 관리 356개 dry-run PASS |
| 문서 | Markdown 175개 UTF-8·내부 링크 PASS |
| Readiness | 필수 16개·미해결 8개 유지 |

Host 첫 실행은 작업 wrapper PATH의 Windows PowerShell 누락으로 M10 prerequisite 2 FAIL/
2 ERROR가 났다. PATH를 수정한 전체 재실행을 위 결과로 사용한다. 별도 M13 첫 실행은
`PYTHONUTF8` 누락으로 CLI JSON을 cp949로 읽다 실패했고, 고정 UTF-8 환경에서 11개를
다시 통과했다. 이 환경 오류 로그도 보존하며 제품 firmware 결함과 구분한다.
Build 비교 script는 Git의 한글 경로 quoting을 NUL 구분 UTF-8 읽기로 바로잡아 11개를 대조했다.

제품 코드 불변이므로 [64번](64_R13_도구_정책_build_구조.md)의 full 60 target·package 20·
실제 설치 예제 29·QEMU 3 등의 exact source 결과는 그 범위 그대로 유지한다. 이번 17개+
11개 build를 새로운 full 60 gate로 표기하지 않는다. 새로운 RC·Release·공개 asset은 만들지 않았다.
GitHub Actions의 이번 HEAD 상태는 별도로 확인하지 않았으며 로컬 결과로 CI 성공을 추정하지 않는다.

## 원본 증거

근거는 [결과 요약](evidence/usb-connected-373d98d/result-summary.json),
[USB inventory](evidence/usb-connected-373d98d/usb-inventory.json),
[build 비교](evidence/usb-connected-373d98d/build-comparison.json),
[최초 17개 artifact](evidence/usb-connected-373d98d/u2a-artifact-index.json),
[수정 후 11개 artifact](evidence/usb-connected-373d98d/u2b-artifact-index.json),
[원본 hash 목록](evidence/usb-connected-373d98d/raw-files.json)에 연결한다.
각 text 사본은 UTF-8/LF이며 `.raw.gz`를 풀면 저장 당시 원본 byte를 얻는다.
부팅 경계의 비 UTF-8 byte가 포함된 BLE `.transcript.log`는 변환 없이 원본 byte로 보존하고
manifest의 `exact-binary-transcript`로 구분한다. 그런 byte를 삭제하거나 대체 문자로 바꾸지 않는다.

| 실제 HIL | A / peripheral | B / central |
| --- | --- | --- |
| UART | [A JSON](evidence/usb-connected-373d98d/uart-a-373d98d.json) | [B JSON](evidence/usb-connected-373d98d/uart-b-373d98d.json) |
| TWIM | [A JSON](evidence/usb-connected-373d98d/twim-a-373d98d.json) | [B JSON](evidence/usb-connected-373d98d/twim-b-373d98d.json) |
| M25 | [A JSON](evidence/usb-connected-373d98d/m25-a-373d98d.json) | [B JSON](evidence/usb-connected-373d98d/m25-b-373d98d.json) |
| M26 | [A JSON](evidence/usb-connected-373d98d/m26-a-373d98d.json) | [B JSON](evidence/usb-connected-373d98d/m26-b-373d98d.json) |
| M19 | [pair JSON](evidence/usb-connected-373d98d/m19-pair-18a7cbe.json) | 동일 nonce의 두 transcript 별도 보존 |
| M20 | [pair JSON](evidence/usb-connected-373d98d/m20-pair-18a7cbe.json) | 동일 nonce의 두 transcript 별도 보존 |
| M21 | [pair JSON](evidence/usb-connected-373d98d/m21-pair-18a7cbe.json) | 동일 nonce의 두 transcript 별도 보존 |

최초 실패 JSON·계측 비교 JSON·실행 wrapper·Host 원본 log도 같은 evidence 디렉터리에 있다.
Raw UID·원문 DETAILS.TXT는 저장하지 않았다. 앞선 65번의 중간 파일 정리·보존 manifest는 유지하며
새 HIL 입력과 오류 근거를 불필요 파일로 삭제하지 않는다. 계속 필요한 helper·호환 진입점·활성
TODO도 보존했다. 이번 변경의 C/C++·SDK·board·third-party 정렬/삭제는 없다.
검증 중 다시 생성된 Python cache 3개 디렉터리의 17개 파일, 217,893바이트만 추가 정리했다.
[삭제 전 경로·hash와 결과](evidence/usb-connected-373d98d/cache-cleanup.json)를 남겼다.

## 종료 상태와 다음 작업

마지막에는 `C:/u2b`의 exact 373d98d DUT/peer image를 sector flash하고 CPUID `0x411fd210`,
RAM의 full runtime commit·role 및 독립 nonce ping을 양쪽 모두 확인했다.
[종료 JSON](evidence/usb-connected-373d98d/pair-handoff-373d98d.json)과 append-only journal은
identity/ping 2개 결과다. 이를 전체 primitives 904건이나 외부 fixture 시험으로 확대하지 않는다.
실기 프로세스는 모두 종료했고 보드에는 위 pair image가 남아 있다.

현재 스위치는 DAP UART 연결, SWD 연결이며 보드 간 선은 없다. **외부 current-source T11은
NOT RUN**이다. 다음 작업은 전원을 모두 끄고 [Fixture 101 결선표](44_M24_Fixture_101_UART_실기_검증.md)에
따라 UART 4선+GND를 연결하고 DAP UART를 분리한 뒤 사용자의 완료 확인을 받는 것이다.
보드 사이 전원선은 연결하지 않는다. 결선·스위치 확인 전에는 외부 fixture 명령을 보내지 않는다.
최종 문서 commit은 제품 입력을 바꾸지 않지만, 다음 HIL은 당시 clean HEAD와 exact build/runtime
identity를 다시 대조하고 필요한 새 역할 image를 build한다.

AC-03 EEPROM/LittleFS 파괴 시험은 저장 영역 덮어쓰기의 별도 조건이 있고, System OFF·버튼·
OS HID 입력 확인과 T12/T13에는 사용자 동작/결선이 필요하다. T16~T18·R14·T19~T25는 기존
선행 gate를 유지한다. 이번 요청은 T11 직전까지이며 그 뒤 단계는 착수하지 않았다.
