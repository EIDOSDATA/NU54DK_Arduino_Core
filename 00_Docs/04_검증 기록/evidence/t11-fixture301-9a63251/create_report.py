"""! @brief 최종 Git 상태와 T11 완료, 다음 401 결선을 전달합니다. """
from pathlib import Path
import json
import shutil

work = Path(__file__).resolve().parent
out = work.parents[1] / 'outputs'
checks = json.loads((work / 'final-checks.json').read_text(encoding='utf-8-sig'))
audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
coverage = json.loads((work / 't11-coverage-audit.json').read_text(encoding='utf-8'))
wiring = json.loads((work / 'next-wiring-audit.json').read_text(encoding='utf-8'))
assert checks['head'] == checks['origin_main'] and checks['working_tree_clean'] and checks['own_running_process_count'] == 0
assert audit['functional_pass'] == 1986 and audit['successful_attempt'] == 1
assert coverage['current_source_t11_complete'] and wiring['next_fixture'] == 401
report = f'''# Fixture 301 완료와 current-source T11 단독 통신 회귀 완료

**Fixture 301은 첫 실행에서 1,986개 기능 PASS, 실패 0개입니다. SWD는 모든 단계에서 10 MHz였습니다.**

- Exact firmware: `9a63251ed6f8b9916d8e49d8210414b21c5c7267`.
- 연속 시험 {audit['continuous_elapsed_seconds']}초. 일반 전송 1,944개, NACK/cancel 12개, stuck-SDA bus recovery 6개, 각 오류 후 정상 전송 18개, clock stretch 6개.
- 두 controller 역할의 6개 조합, 100/400/1,000 kHz, sync/async·단일/이중 buffer 검사.
- 고유 ID 1,986개와 전체 실행 순서가 독립 계획에 일치. Cleanup 2개·campaign 2개 별도, 총 journal 1,990개.
- Pair build 2/2, 종료 CPUID·full commit·role 2/2 PASS.
- 문서 182개·계약 45개·inventory 75·Serial 23·System 16 PASS. Readiness blocker 8개 유지.
- UART·SPI·TWI 일곱 묶음의 **61,423개 기능 결과**와 원본 hash·동일 컴파일 입력을 대조해 current-source T11 단독 회귀 완료.
- 각 실행의 embedded commit identity와 과거 실패는 구분 보존. T12~T15·최종 통합·RC/공개는 남아 있습니다.
- 문서·증거 commit 및 main push 완료: `{checks['head']}`. 원격과 일치, checkout·board·SDK 깨끗함, 남은 시험/빌드 프로세스 0개.
- 최종 GitHub Actions 상태는 미확인입니다. 추가 제거할 불용 파일은 확인되지 않았습니다.

## 다음: T12 Fixture 401 PWM→AIN0

**두 USB 전원을 모두 분리한 뒤 아래 신호 한 선과 GND만 남기세요.**

| 신호 | A/DUT | B/peer |
| --- | --- | --- |
| B PWM → A AIN0 | **P2-12 / P1.04 유지** | 현재 P2-25 끝을 **P4-12 / P1.14**로 이동 |
| GND | P2-30 유지 | P2-30 유지 |

기존 SCL A P2-11↔B P2-26 점퍼는 양쪽에서 제거하세요. B만 PWM을 출력하고 A는 ADC 입력입니다.
A는 이번 D:/COM5·COM6, B는 E:/COM7·COM8 보드이며 현재 A/B 구분을 유지하세요.
DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·각자 USB 전원을 유지합니다. 외부 저항이나 보드 간
전원선은 추가하지 않습니다. USB 재연결 후 결선 완료를 알려주면 새 exact image·확인서로 시작합니다.

[영구 검증 기록](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/04_검증 기록/73_T11_Fixture_301_current_source_TWI_회귀.md>) ·
[활성 TODO](<C:/Users/eidos/GitHub/NU54DK_Arduino_Core/00_Docs/TODO_v0.4.0.md>)
'''
out.mkdir(exist_ok=True)
target = out / 't11-fixture301-completion-report.md'
assert not target.exists()
target.write_text(report, encoding='utf-8', newline='\n')
for name, suffix in [('final-checks.json', 'final-checks.json'), ('results-audit.json', 'results.json'), ('t11-coverage-audit.json', 't11-coverage.json'), ('staged-evidence-audit.json', 'evidence-audit.json'), ('changed-files.txt', 'changed-files.txt')]:
    destination = out / ('t11-fixture301-' + suffix)
    assert not destination.exists()
    shutil.copyfile(work / name, destination)
print(json.dumps({'report': str(target), 'commit': checks['head'], 'current_source_t11_complete': True, 'next_fixture': 401}))
