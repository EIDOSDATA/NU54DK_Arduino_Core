"""! @brief 최종 결과와 실제 종료 상태, 다음 Fixture 203 결선을 전달합니다. """
from pathlib import Path
import json
import shutil

work = Path(__file__).resolve().parent
out = work.parents[1] / 'outputs'
checks = json.loads((work / 'final-checks.json').read_text(encoding='utf-8-sig'))
audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
post = json.loads((work / 'postflight.json').read_text(encoding='utf-8'))
wiring = json.loads((work / 'next-wiring-audit.json').read_text(encoding='utf-8'))
assert checks['head'] == checks['origin_main'] and checks['working_tree_clean']
assert checks['own_running_process_count'] == 0 and audit['functional_pass'] == 9084
assert audit['initial_flash_failure_preserved'] and audit['successful_attempt'] == 2
assert wiring['status'] == 'passed' and wiring['next_fixture'] == 203
states = '·'.join(f"{label} {row['state']}" for label, row in zip(('A', 'B'), post['devices']))
report = f'''# Fixture 202 SPI 완료와 다음 결선

**최종 실행에서 9,084개 기능 PASS, 기능 실패 0개.** SWD는 flash·mailbox·종료 확인 모두 **10 MHz**였습니다.

- Exact firmware: `1349e208073d0fd7d3b020a5e9facf771b371237`.
- 실제 최종 연속 시험: {audit['continuous_elapsed_seconds']}초.
- 일반 전송 9,072개, cancel·STOP 6개, cancel 후 정상 복구 6개.
- 양쪽 controller 역할, P0↔P1 SPIM/SPIS30·20·21·22, 2/4/8 MHz, Mode 0~3, MSB/LSB, sync/async·단일/이중 buffer.
- Cleanup 2개·campaign 2개는 기능 PASS와 별도이며 총 journal 9,088개입니다.
- 독립 계획 ID와 실제 ID 완전 일치, 최종 JSON/journal 일치, 누락·범위 이탈·중복 0개.
- 첫 실행은 peer flash 중 CMSIS-DAP timeout으로 SPI 시작 전에 실패했습니다. 원본을 보존하고 두 보드의 10 MHz CPUID 응답 회복을 확인한 뒤 한 번의 새 실행으로 위 결과를 얻었습니다. 근본 원인은 미확정입니다.
- Pair build 2/2, 종료 CPUID·full commit·role 2/2 PASS. CPU snapshot은 {states}입니다.
- 문서 180개, 계약 45개, inventory 75·Serial 23·System 16 PASS.
- 문서·증거 커밋과 main 푸시 완료: `{checks['head']}`.
- 원격 main과 일치, checkout·board·SDK 깨끗함, 남은 시험·빌드 프로세스 0개.
- 최종 GitHub Actions 상태는 미확인입니다.

현재 Fixture 202 결선과 1349e20 DUT/peer image를 유지합니다. 이전 실패·재개용 image·raw evidence를
보존했고 추가 삭제 대상은 확인되지 않았습니다. UART 101~103 기능 4,932 PASS와 SPI 201 기능
18,169 PASS는 각각의 exact source로 유지합니다. SPI 203·TWI 301과 T12~T15·RC/공개는 남아 있습니다.

## 다음: Fixture 203 SPI

**두 USB를 모두 분리한 뒤 A/DUT 쪽 신호선 네 개만 옮기세요. B/peer와 공통 GND는 그대로입니다.**
A는 이번 D:/COM5·COM6, B는 E:/COM7·COM8 보드입니다. 재연결 때 드라이브 문자가 달라질 수
있으므로 현재 A/B 구분을 유지하세요.

| A 쪽 현재 핀 | A 쪽 옮길 핀 | 그대로 둘 B 핀 | 신호 |
| --- | --- | --- | --- |
| P2-25 | **P2-12 / P1.04** | P2-12 / P1.04 | SCK |
| P2-26 | **P2-11 / P1.05** | P2-11 / P1.05 | MOSI |
| P4-4 | **P2-10 / P1.06** | P2-10 / P1.06 | MISO |
| P4-5 | **P2-9 / P1.07** | P2-9 / P1.07 | CSN |
| P2-30 GND | **그대로 유지** | P2-30 GND | GND |

양쪽 DAP UART 분리, SWD 연결, 동일 I/O 전압을 유지하세요. 각 보드는 자기 USB 전원을 쓰며
보드 사이 전원선이나 외부 저항은 추가하지 않습니다. 결선 뒤 USB를 다시 연결하고 완료를
알려주면 새 exact image·확인서로 시작합니다. Fixture 203은 아직 실행하지 않았습니다.

[영구 검증 기록](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/04_검증 기록/71_T11_Fixture_202_current_source_SPI_회귀.md>) ·
[활성 TODO](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/TODO_v0.4.0.md>)
'''
out.mkdir(exist_ok=True)
target = out / 't11-fixture202-completion-report.md'
assert not target.exists()
target.write_text(report, encoding='utf-8', newline='\n')
for source, suffix in [('final-checks.json', 'final-checks.json'), ('results-audit.json', 'results.json'), ('staged-evidence-audit.json', 'evidence-audit.json'), ('changed-files.txt', 'changed-files.txt')]:
    destination = out / ('t11-fixture202-' + suffix)
    assert not destination.exists()
    shutil.copyfile(work / source, destination)
print(json.dumps({'report': str(target), 'commit': checks['head'], 'origin_main_matches': True, 'working_tree_clean': True, 'functional_pass': 9084, 'next_fixture_catalog_checked': 203}, ensure_ascii=False))
