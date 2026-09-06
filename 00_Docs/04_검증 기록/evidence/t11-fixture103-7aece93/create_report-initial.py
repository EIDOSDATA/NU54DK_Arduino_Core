"""! @brief 최종 UART 증거와 catalog로 확인한 다음 SPI 결선을 사용자에게 전달합니다. """
from pathlib import Path
import json
import shutil

work = Path(__file__).resolve().parent
out = work.parents[1] / 'outputs'
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
checks = json.loads((work / 'final-checks.json').read_text(encoding='utf-8-sig'))
audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
aggregate = json.loads((work / 'uart-route-aggregate.json').read_text(encoding='utf-8'))
assert checks['head'] == checks['origin_main'] and checks['working_tree_clean']
assert checks['own_running_process_count'] == 0 and audit['functional_pass'] == 2466
assert aggregate['totals']['functional_pass'] == 4932
catalog = json.loads((repo / 'tests/hil/nu54dk/v04_fixtures.json').read_text(encoding='utf-8'))
current = next(row for row in catalog['fixtures'] if row['id'] == 103)
following = next(row for row in catalog['fixtures'] if row['id'] == 201)
old_by_peer = {tuple(row['peer'][:2]): row for row in current['links']}
new_by_peer = {tuple(row['peer'][:2]): row for row in following['links']}
expected = [(('P2', 11), ('P4', 20), ('P2', 12)), (('P2', 12), ('P4', 21), ('P2', 11)), (('P2', 9), ('P2', 17), ('P2', 10)), (('P2', 10), ('P2', 19), ('P2', 9)), (('P2', 30), ('P2', 30), ('P2', 30))]
assert len(current['links']) == len(following['links']) == 5
for old_pin, new_pin, peer_pin in expected:
    assert tuple(old_by_peer[peer_pin]['dut'][:2]) == old_pin
    assert tuple(new_by_peer[peer_pin]['dut'][:2]) == new_pin
report = f'''# Fixture 103 완료와 다음 SPI 결선

SWD는 flash·mailbox·종료 확인 모두 **10 MHz**로 유지했습니다.

- Exact firmware: `7aece93395f0d74272816894a18c2c5e3f1a2abe`.
- Fixture 103 최종 실행: **2,466개 기능 PASS, 기능 실패 0개**, 연속 {audit['continuous_elapsed_seconds']}초.
- 정상 전송 2,376개, CTS 정지·재개 18개, parity/break 검출 36개, 오류 직후 정상 복구 36개.
- cleanup 2개·campaign 2개는 기능 PASS와 별도입니다.
- 최초 peer flash에서 CMSIS-DAP timeout 1개가 발생했습니다. UART 시작 전 실패 원본을 보존하고,
  두 보드의 10 MHz CPUID 응답 회복을 확인한 뒤 한 번의 새 실행으로 위 결과를 얻었습니다.
  근본 원인은 미확정이며 속도 하향·mass erase/recover는 하지 않았습니다.
- DUT/peer build 2/2, 종료 CPUID·full commit·role 2/2 PASS. 두 CPU는 SLEEPING입니다.
- 문서 178개, 계약 45개, inventory 75·Serial 23·System 16 PASS.
- 문서·증거 커밋과 main 푸시 완료: `{checks['head']}`.
- 원격 main과 일치, checkout·board·SDK 깨끗함, 남은 시험·빌드 프로세스 0개.
- 최종 GitHub Actions 상태는 미확인입니다.

현재 Fixture 103 결선과 7aece93 DUT/peer image를 유지합니다. Current-source T11의 UART
Fixture 101·102·103은 source별 원본을 보존한 **총 4,932개 기능 PASS**로 완료했습니다.
SPI 201~203·TWI 301 및 T12~T15·RC/공개는 아직 남아 있습니다.

## 다음: Fixture 201 SPI

**두 USB를 모두 분리한 뒤 A/DUT 쪽 신호선 네 개만 옮기세요. B/peer와 공통 GND는 그대로입니다.**
아래 표는 SCK부터 나열했으므로 A의 현재 핀과 그대로 둘 B 핀을 함께 확인하세요.
A는 이번 D:/COM5·COM6, B는 E:/COM7·COM8 보드입니다. 재연결 시 드라이브 문자가 바뀔 수
있으므로 지금의 A/B 구분을 유지하세요.

| A 쪽 현재 핀 | A 쪽 옮길 핀 | 그대로 둘 B 핀 | SPI 신호 |
| --- | --- | --- | --- |
| P2-11 | **P4-20 / P2.01** | P2-12 / P1.04 | SCK |
| P2-12 | **P4-21 / P2.02** | P2-11 / P1.05 | A MOSI / A SPIS MISO |
| P2-9 | **P2-17 / P2.04** | P2-10 / P1.06 | A MISO / A SPIS MOSI |
| P2-10 | **P2-19 / P2.05** | P2-9 / P1.07 | CSN |
| P2-30 GND | **그대로 유지** | P2-30 GND | GND |

양쪽 DAP UART 분리, SWD 연결, 동일 I/O 전압을 유지하세요. 각 보드는 자기 USB 전원을 쓰며
보드 사이 전원선이나 외부 저항은 추가하지 않습니다. 역할 교대 시 MOSI/MISO 처리는 firmware가
담당합니다. 결선 뒤 USB를 다시 연결하고 완료를 알려주면 새 exact image·확인서로 시작합니다.

[영구 검증 기록](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/04_검증 기록/69_T11_Fixture_103_current_source_UART_회귀.md>) ·
[활성 TODO](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/TODO_v0.4.0.md>)
'''
out.mkdir(exist_ok=True)
target = out / 't11-fixture103-completion-report.md'
assert not target.exists()
target.write_text(report, encoding='utf-8', newline='\n')
for source, suffix in [('final-checks.json', 'final-checks.json'), ('results-audit.json', 'results.json'), ('staged-evidence-audit.json', 'evidence-audit.json'), ('changed-files.txt', 'changed-files.txt'), ('uart-route-aggregate.json', 'uart-route-aggregate.json')]:
    destination = out / ('t11-fixture103-' + suffix)
    assert not destination.exists()
    shutil.copyfile(work / source, destination)
print(json.dumps({'report': str(target), 'commit': checks['head'], 'origin_main_matches': True, 'working_tree_clean': True, 'functional_pass': 2466, 'uart_functional_pass_total': 4932, 'next_fixture_catalog_checked': 201}, ensure_ascii=False))
