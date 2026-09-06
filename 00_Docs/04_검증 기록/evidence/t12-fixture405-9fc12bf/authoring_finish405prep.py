"""! @brief 준비 상태와 재현 가능한 검사·실행 wrapper를 기록합니다. """
from pathlib import Path
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
work = Path(__file__).resolve().parent
for name in ('README.md', '05_리팩토링_진행_체크리스트.md'):
    path = repo / '00_Docs/01_아두이노 코어 설계/14_리팩토링' / name
    text = path.read_text(encoding='utf-8')
    text = text.replace('Fixture 408 PWM→AIN7: A P1.07→P1.14 전원 OFF 결선 변경 및 사용자 확인', 'Fixture 405 AIN4/P1.11 오픈드레인 기능 시험 구현·검증·실행; 사용자 결선 확인 완료. 후속 406→407→408 필수')
    text = text.replace('다음에는 전원 OFF·A P1.07→P1.14/AIN7 변경과 새 confirmation이 필요하다.', '사용자 추가 요청으로 405→406→407→408을 모두 수행한다. 현재 405 A P1.11↔B P1.14 결선 확인을 받았으며 전용 오픈드레인 시험 코드를 검증 중이다. 제품 core와 R00~R13 완료는 유지하며 T05/T10/T12 준비·실기 근거를 구분한다.')
    text = text.replace('408부터 후속 요구를 이어간다.', '405→406→407→408부터 후속 요구를 이어간다. 공유 회로만으로 생략하지 않는다.')
    path.write_text(text, encoding='utf-8', newline='\n')

host = (work / 't09-connected/run_host.ps1').read_text(encoding='utf-8')
host = host.replace('t09-connected\\host-373d98d-powershell-path.log', 't12-fixture405\\gate-host.log')
(work / 't12-fixture405/run_host.ps1').write_text(host, encoding='utf-8', newline='\n')
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py'):
    text = (work / 't12-fixture404' / name).read_text(encoding='utf-8')
    text = text.replace('404', '405').replace('C:\\u3k', 'C:\\u3l')
    if name == 'runtime.py':
        text = text.replace("SOURCE = 'e080bbc8f07a0ad751d83dacdb259d395b69be5b'", "SOURCE = (WORK / 'source.txt').read_text(encoding='ascii').strip()")
    (work / 't12-fixture405' / name).write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE405_WRAPPERS_PREPARED')
