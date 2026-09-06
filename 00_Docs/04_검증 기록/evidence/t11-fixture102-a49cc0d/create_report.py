"""! @brief 종료 증거와 catalog 대조를 거친 다음 결선을 사용자 보고서로 정리합니다. """
from pathlib import Path
import json
import shutil

work = Path(__file__).resolve().parent
out = work.parents[1] / 'outputs'
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
checks = json.loads((work / 'final-checks.json').read_text(encoding='utf-8-sig'))
audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
assert checks['head'] == checks['origin_main'] and checks['working_tree_clean']
assert checks['own_running_process_count'] == 0 and audit['functional_pass'] == 822
catalog = json.loads((repo / 'tests/hil/nu54dk/v04_fixtures.json').read_text(encoding='utf-8'))
current = next(row for row in catalog['fixtures'] if row['id'] == 102)
following = next(row for row in catalog['fixtures'] if row['id'] == 103)
expected = [(('P2', 25), ('P2', 12), ('P2', 11)), (('P2', 26), ('P2', 11), ('P2', 12)), (('P4', 4), ('P2', 10), ('P2', 9)), (('P4', 5), ('P2', 9), ('P2', 10)), (('P2', 30), ('P2', 30), ('P2', 30))]
for old, new, (old_pin, new_pin, peer_pin) in zip(current['links'], following['links'], expected):
    assert tuple(old['dut'][:2]) == old_pin and tuple(new['dut'][:2]) == new_pin
    assert tuple(old['peer'][:2]) == peer_pin and old['peer'] == new['peer']
report = f'''# Fixture 102 완료와 다음 결선

SWD는 flash·mailbox·종료 확인 모두 **10 MHz**로 유지했습니다. 속도 하향과 재시험은 없었습니다.

- Exact firmware: `a49cc0dbc1ef8bf5f697106d873bdce55f5911df`.
- Fixture 102: **822개 기능 PASS, 실패 0개**, 연속 {audit['continuous_elapsed_seconds']}초.
- 정상 전송 792개, CTS 100ms 정지·재개 6개, parity/break 검출 12개, 오류 직후 정상 복구 12개.
- cleanup 2개·campaign 2개는 기능 PASS와 별도로 보존했습니다.
- DUT/peer build 2/2, 종료 CPUID·full commit·role 2/2 PASS. 두 CPU는 SLEEPING입니다.
- 문서 177개, 계약 45개, inventory 75·Serial 23·System 16 PASS.
- 문서·증거 커밋과 main 푸시 완료: `{checks['head']}`.
- 원격 main과 일치, checkout·board·SDK 깨끗함, 남은 시험·빌드 프로세스 0개.
- 최종 GitHub Actions 상태는 미확인입니다.

현재 두 보드에는 exact a49cc0d DUT/peer image와 Fixture 102 결선이 남아 있습니다.
앞선 Fixture 101(154324c)의 1,644 PASS는 별도 exact 원본으로 보존했습니다.
Current-source T11은 Fixture 101·102까지 부분 완료이며 Fixture 103·201~203·301 및
T12~T15·RC/공개는 아직 남아 있습니다.

## 다음: Fixture 103

**두 USB를 모두 분리한 뒤 A/DUT 쪽 신호선 네 개만 옮기세요. B/peer와 공통 GND는 그대로입니다.**

A는 이번에 D:/COM5·COM6, B는 E:/COM7·COM8로 확인한 보드입니다. 재연결 때 드라이브 문자가
바뀔 수 있으므로 지금의 A/B 구분을 유지하세요.

| A 쪽 현재 핀 | A 쪽 옮길 핀 | 그대로 둘 B 쪽 핀 |
| --- | --- | --- |
| P2-25 | **P2-12 / P1.04 TX** | P2-11 / P1.05 RX |
| P2-26 | **P2-11 / P1.05 RX** | P2-12 / P1.04 TX |
| P4-4 | **P2-10 / P1.06 RTS** | P2-9 / P1.07 CTS |
| P4-5 | **P2-9 / P1.07 CTS** | P2-10 / P1.06 RTS |
| P2-30 GND | **그대로 유지** | P2-30 GND |

양쪽 DAP UART 분리, SWD 연결, 동일 I/O 전압을 유지하세요. 각 보드는 자기 USB 전원을
사용하며 보드 사이 전원선이나 외부 저항은 추가하지 않습니다. 결선 뒤 USB를 다시 연결하고
완료를 알려주면 새 exact image·확인서로 Fixture 103을 이어갑니다.

[영구 검증 기록](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/04_검증 기록/68_T11_Fixture_102_current_source_UART_회귀.md>) ·
[활성 TODO](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/TODO_v0.4.0.md>)
'''
out.mkdir(exist_ok=True)
target = out / 't11-fixture102-completion-report.md'
assert not target.exists()
target.write_text(report, encoding='utf-8', newline='\n')
for source, suffix in [('final-checks.json', 'final-checks.json'), ('results-audit.json', 'results.json'), ('staged-evidence-audit.json', 'evidence-audit.json'), ('changed-files.txt', 'changed-files.txt')]:
    destination = out / ('t11-fixture102-' + suffix)
    assert not destination.exists()
    shutil.copyfile(work / source, destination)
print(json.dumps({'report': str(target), 'commit': checks['head'], 'origin_main_matches': True, 'working_tree_clean': True, 'functional_pass': 822, 'next_fixture_catalog_checked': 103}, ensure_ascii=False))
