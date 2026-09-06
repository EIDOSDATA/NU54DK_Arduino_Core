"""! @brief 실제 종료 결과를 활성 문서에 반영하고 Git 동기화 전 검토 자료를 만듭니다. """
from pathlib import Path
import json
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
work = Path(__file__).resolve().parent
summary = json.loads((work / 'result-summary.json').read_text(encoding='utf-8'))
handoff = json.loads((work / 'pair-handoff-373d98d.json').read_text(encoding='utf-8'))
assert handoff['status'] == 'passed' and len(handoff['devices']) == 2
assert summary['onboard_case_passes'] == 18 and summary['host']['passed'] == 642
record = repo / '00_Docs/04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md'
text = record.read_text(encoding='utf-8')
text = text.replace('| 진행 상태 | BLE M19/M20/M21 PASS; idle bias 수정 뒤 온보드 실제 회귀 대기 |', '| 최종 결과 | BLE 3개 pair gate PASS; 수정 source 373d98d의 온보드 8개 runner·18개 결과 PASS; 외부 T11 NOT RUN |')
text = text.replace('현재 이 단계의 교정은 실제 보드 재검증 전이므로 완료 PASS로 선언하지 않는다.', '교정 commit `373d98da055b83e86b039448965d630e8d546497`을 고정한 뒤 아래 실제 보드 회귀를 완료했다.')
text = text.replace('`work/t09-connected`에 보존했다. 후속 evidence 등록 시 원본 byte와 hash를 함께 남긴다.', '`work/t09-connected`와 아래 evidence 경로에 원본 byte·hash를 함께 보존했다. UID만 출력·JSON 직렬화 전에 SHA-256 표기로 대체했으며 판정은 canonical runner 그대로다.')
text = text[:text.index('## 다음 재개')] + '''## 교정 후 실제 온보드 결과

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
'''
record.write_text(text, encoding='utf-8')
todo = repo / '00_Docs/TODO_v0.4.0.md'
text = todo.read_text(encoding='utf-8').replace('TODO-V04-001 / 2.3', 'TODO-V04-001 / 2.4')
rows = {
'작성 직전 기준 commit': '`373d98da055b83e86b039448965d630e8d546497` — idle bias 수정·온보드 검증 source; BLE source는 18a7cbe',
'다음 착수 항목': '**외부 current-source T11 직전 정지** — 다음은 전원 OFF·Fixture 101 결선·DAP UART 분리 확인',
'이번에 끝낸 일': 'T09 추가 검증 완료. 373d98d 온보드 8개 runner/18개 결과 PASS, 18a7cbe BLE M19/M20/M21 pair PASS, idle bias 교정과 최초 실패 보존. [66번 기록](<./04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>) 참조',
'진행 중인 T 항목': '현재 실행 없음. R00~R13 및 T09 후속 완료. 외부 current-source T11·T12/T13·후속 RC/공개 대기',
'다음 구체적 행동': '사용자가 다음 외부 실기를 시작할 때 두 보드의 모든 전원을 끄고 Fixture 101 UART 4선+GND를 연결하며 DAP UART를 분리한다. SWD 연결을 유지하고 결선 완료 확인 뒤 exact source image로 preflight한다',
'다음 작업에 필요한 사용자 행동': '지금 요청한 T11 직전 작업은 완료. 다음 착수에는 전원 OFF·Fixture 101 결선·DAP UART 분리·USB 재연결 완료 확인이 필요',
'이 TODO 작성 작업의 실행 중 시험': '실행 중 HIL/build 없음. 두 보드에는 exact 373d98d DUT/peer image가 남아 있으며 종료 CPUID·runtime role/commit·독립 ping 2/2 PASS. 외부 fixture 명령 미실행',
'문서 작업 검증': '전체 Host 642 PASS/조건부 1 SKIP, 별도 설치 M13 11 PASS, contract 45, inventory/생성 drift, style 356, Markdown 175 PASS. 최초 target 17개와 교정 source target 11개 PASS. R13 full 60/package/설치 예제/QEMU 근거는 64번에 유지. readiness blocker 8개',
'최종 HIL 입력 찾기': 'C:/u2b DUT/peer는 exact 373d98d이며 종료 identity/ping 근거가 66번에 있다. BLE는 C:/u2a exact 18a7cbe. 마지막 문서 HEAD와 다음 HIL source가 다르면 제품 입력 불변성과 build/runtime identity를 대조하고 exact HEAD image를 새로 준비',
}
lines = text.splitlines()
for index, line in enumerate(lines):
    for name, value in rows.items():
        if line.startswith('| ' + name + ' |'):
            lines[index] = '| ' + name + ' | ' + value + ' |'
text = '\n'.join(lines) + '\n'
needle = '- [x] **T09 — Host 검사·시험 펌웨어 빌드·무배선 추가 시험**\n'
text = text.replace(needle, needle + '  - DAP UART 연결 후 추가 회귀: 373d98d 온보드 18 PASS와 18a7cbe BLE M19/M20/M21 pair PASS. idle bias 교정·처음 실패·새 exact 결과는 [66번 기록](<./04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에 분리 보존. 외부 current-source T11 NOT RUN.\n')
todo.write_text(text, encoding='utf-8')
footers = {
    'README.md': './00_Docs/04_검증 기록/',
    '00_Docs/README.md': './04_검증 기록/',
    '00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md': '../04_검증 기록/',
    '00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md': '../../04_검증 기록/',
}
for name, relative in footers.items():
    path = repo / name
    lines = path.read_text(encoding='utf-8').splitlines()
    for index, line in enumerate(lines):
        if line.startswith('2026-09-06 후속: USB로만 연결된 두 보드'):
            lines[index] = f'2026-09-06 후속: [65번 기록](<{relative}65_R13_후속_USB_무배선_실기와_정리.md>)의 904 PASS·파일 정리를 보존한다. 이후 DAP UART 연결 전환 뒤 [66번 기록](<{relative}66_T09_UART_유휴_bias와_BLE_회귀.md>)에서 UART idle bias를 교정하고 온보드 18개 결과·BLE 3개 pair gate를 통과했다. 현재 두 보드는 USB만 연결되어 있고 보드 간 선은 없다. 외부 current-source T11 직전에서 정지했으며 다음은 전원 OFF·Fixture 101 결선·DAP UART 분리 확인이다.'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
checklist = repo / '00_Docs/01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md'
text = checklist.read_text(encoding='utf-8')
begin = text.index('2026-09-06 후속 사용자 확인:')
end = text.index('\n## 2.', begin)
text = text[:begin] + '2026-09-06 최신 상태: 두 보드 각각 USB 연결, 보드 간 선 없음, 사용자 확인으로 DAP UART 연결 전환 완료, SWD 연결 유지다. R00~R13 완료 뒤 [66번 기록](<../../04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)의 온보드 18개 결과와 BLE 3개 pair gate를 통과했다. 외부 current-source T11 직전에서 정지했으며 다음에는 전원 OFF·Fixture 101 결선·DAP UART 분리와 새 confirmation이 필요하다.\n' + text[end:]
text += '\nT09 추가 UART idle bias 교정과 BLE 실기는 [66번 기록](<../../04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>)에 연결한다. 기존 peer P0 CTS 흐름제어 실패는 이번 무흐름제어 PASS로 해소 처리하지 않는다.\n'
checklist.write_text(text, encoding='utf-8')
history = repo / '00_Docs/04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md'
history.write_text(history.read_text(encoding='utf-8') + '\n후속 연결 전환 완료 뒤의 최신 UART/BLE 실제 결과와 종료 스위치 상태는 [66번 기록](66_T09_UART_유휴_bias와_BLE_회귀.md)에 보존한다. 이 문서의 앞선 분리 상태와 904 PASS는 당시 사실로 유지한다.\n', encoding='utf-8')
final_checks = (work.parent / 'usb-followup/end_checks.ps1').read_text(encoding='utf-8-sig')
final_checks = final_checks.replace("$workers = @(Get-CimInstance", "$taskPath += '|C:[\\\\/]u2[a-z](?=[\\\\/\\s\"'']|$)'\n$workers = @(Get-CimInstance")
final_checks = final_checks.replace("'usb-followup\\final-checks.json'", "'t09-connected\\final-checks.json'")
(work / 'end_checks.ps1').write_text(final_checks, encoding='utf-8')
print('FINAL_DOCS_UPDATED;HIL_ALREADY_STOPPED')
