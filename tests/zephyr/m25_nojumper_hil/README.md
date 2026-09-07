# 점퍼 없이 수행하는 M25 실기

T14 PWM 지연 시작 취소와 관련 T12 준비용 SWD mailbox 프로그램이다. 보드 간 결선 없이
각 NU54DK의 P1.14 한 핀만 PWM 출력으로 사용한다. UART 콘솔·외부 입력은 사용하지 않는다.
부팅 후에는 mailbox 요청을 기다리며 스스로 시험을 시작하지 않는다.

Canonical build scenario는 `nucode.m25.nojumper_hil`이다. Host의
`tests/hil/nu54dk/v04_nojumper.py`는 clean source·board·build record·ELF SRAM symbol을
대조하고, nonce·요청 sequence·원본 응답을 검증한다. 실제 실행은 지정 probe의 배타 lock,
SWD 10 MHz, `auto_unlock=false`, sector flash와 controlled reset/start로 수행한다.
실패 응답은 판정 전에 기록하며 이후 명령은 차단한다. 자동 recover/mass erase는 하지 않는다.

PWM20/21/22 × decoder 4개 × TOP 1000/4000 × 단일/이중 sequence × auto/triggered step ×
finite/loop × 즉시 시작/미시작 취소/CPU START/DPPI START/DPPI 준비 취소로 **보드당 960개**다.
16-byte guard, DMA READY·SEQSTARTED·PWMPERIODEND, 정지 결과, ENABLE=0, pin/DMA/block
lease 해제와 GPIO 복원을 독립적으로 대조한다. DPPI START 구독을 유지한 stop은
ownership_conflict여야 하며, 연결 소유자가 구독을 해제한 다음 실제 stop/cancel을 수행한다.

미시작 취소는 하드웨어 STOPPED 없이 logical stopped 이벤트를 전달한다. 실제 시작이나
DMA 준비 흔적이 있으면 기존 STOP 확인·timeout 시 lease 유지 계약을 따른다. 반환받은
START 주소는 해당 active 실행 동안만 유효하며 CPU/ISR START와 stop을 동시에 호출하지 않는다.

이 결과는 출력 파형의 peer 측정, 주기·듀티 오차, 외부 회로와의 동작을 증명하지 않는다.
해당 T12 실기는 별도 GPIO 결선과 capture 판정이 필요하다.
