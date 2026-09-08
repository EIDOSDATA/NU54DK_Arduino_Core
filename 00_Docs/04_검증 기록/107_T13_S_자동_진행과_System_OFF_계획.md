# T13 S 자동 진행과 peer 제어 System OFF 검증 계획

2026-09-08T10:59Z: C01~04 각각900초와 C05 3600초·양쪽 STOP 완료로 동시5/7(71%)이며 C06을 실행 중이다.
고정 serial17/21·stream3/4·PWM6/6·역할 전환2/5는 source별 근거로 유지한다.
CTS d44cef2의 exact 두 역할 target·Host58·원격 Host104묶음788시험 준비를 완료했다.
UART parity/break는93e38ff exact target2/2·T13 Host63시험·원격 전체 Host105묶음793시험을 통과했다.
SPI boundary4f573f0도 exact target2/2·새 Host4시험·원격 전체 Host106묶음797시험을 확인했다.
현재 자동 배치→TWIM 계측→System OFF→충돌/CTS→UART parity/break→SPI boundary 순서를 유지한다.
그 뒤 e9afcc9의 C01/C05 동시 CTS 예행4조건을 예약했다. exact target2/2·변경 관련 Host6+5시험과
원격 전체 Host106묶음800시험을 확인했다. 준비 기록은 아래 e9afcc9 보존 목록을 따른다.
f77e1cb RX 지연도 exact target2/2·새 Host4시험·원격 전체 Host107묶음804시험을 확인해 그 다음
예행8조건을 예약했다. 모든 후속은 원래21:26:14KST 확인 종료 전에 남은 시간만 사용한다.

2026-09-08 후속 구현 범위: T13의 기존 자원 충돌 요구 중 S UART21/22/30에서 같은 block의
SPI 활성화, 다른 UART의 동일 GPIO 점유, 내부 DMA workspace 겹침을 의도하여 거부의 원자성과
기존 송수신·STOP·새 seed 재획득을 확인한다. 후보 출력은 원래 UART TX/RTS가 연결된 peer 입력만
사용하며 현재 peer 출력에 새 출력을 배치하지 않는다. Host/target 뒤 양쪽 역할의 각 조건을 예행하고
시간 안에 가능한 각100회만 수행한다. UART30은 실제 P0 경로이므로 같은 block SPI 조건만 적용한다.
UART21/22의 세 조건과 UART30의 한 조건을 양쪽 역할에서 검사하는14조건이다.
UART00/20·event/PWM 충돌까지 완료한 것으로 확대하지 않는다.

2026-09-08 소유자 지시를 반영한다. T13 S와 T14의 영향 분석·재시험, T17 증거/문서 유지 범위다.
U UART00은 현재 결선에서 실행하지 않으며 S 완료 또는 가능한 작업 소진 후 GPIO 재배치를 안내한다.
T12와 QDEC 문제 보고 후 검증 작업 완료 결정은 유지한다. QDEC 재진단은 새로 예약하지 않는다.

UART CTS 후속 구현 범위: S 단독20/21/22/30의 한쪽은4선 DUT로 유지하고, peer는 활성화 전
TX/RX 두 선과 별도 GPIO RTS 소유권으로 구성한다. peer가 기존 RTS→DUT CTS net을100ms HIGH로
유지한 뒤 LOW로 돌린다. 실행 중 UARTE PSEL을 변경하지 않는다. 양쪽 device 시각·실제 CTS 수준·
대기 TX·완료량·정상 payload 재개·STOP·새 seed 재획득을 요구한다. 이 fixture 변경은 원본에 표시하며
peer 하드웨어 RTS 자체 검증이나 RX 지연/parity/break의 완료로 확대하지 않는다.
근거: [Nordic UARTE 핀 설정](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/uarte.html-concept_wmv_f2m_wr).

UART line 오류 후속 범위: S UART20/21/22/30에서 DUT even parity·peer parity 없음의 오류와,
peer UART를 완전히 반환한 뒤 원래 TX GPIO에1ms LOW를 주는 break를 준비한다. 대상 DUT는
의도적 오류 구간에서 TX를 시작하지 않고 실제 UARTE error event·mask와 양쪽 guard·정지 및
새 seed 정상 재획득을 요구한다. 정상 연속 시험과 구분하며 예행을 예약했으나 실기 결과는 아직0이다.

10:15Z 준비 검사: break의 UART→GPIO 전환 동안 DUT RX를 시작하지 않도록 순서를 보강하고
초안 두 역할 target2/2와 T13 Host63시험·정렬·계약·문서 검사를 통과했다. 전체 Host는
R03 analog production의12개 하위 실행에서 Windows 응용 프로그램 제어 WinError4551로
차단됐다. 다른 R03 PWM/stream은 통과했으며 보안 정책을 변경하지 않는다. 이 로컬 전체 검사를
PASS로 세지 않고 실패 원본을 보존하며 고정 source의 원격 전체 Host를 별도 요구한다.

## 마일스톤과 현재 상태

다음 구현 범위: S TWIM20/21/22/30의 SDA LOW100ms 복구를 독립 시험한다. A TWIM은 staged
상태에서만 recoverBus를 호출하고 B는 TWIS를 활성화하지 않은 채 기존 SDA만 별도 소유한
open-drain GPIO로 LOW/해제한다. 실제 유지 시간·라인 수준·첫 driver_error/-ECANCELED·해제 뒤
success와 GPIO/DMA/state 복원을 확인하고 양쪽 STOP 뒤0x42 새 seed 정상 통신을 요구한다.
20/21/22는 P1.10/14,30은 P0.00/01을 사용하며 P1.02/03·PMIC에는 주입하지 않는다. 활성 TWIM을 clock stretching 중 disable하는
시험이 아니며, TWIS 버퍼 공급 지연과 다른 controller 역할은 별도 항목으로 남긴다.

다음 구현 범위: S 단독 UART20/21/22/30의 양쪽을 활성화 전에2선으로 구성하고 한쪽 RX 버퍼
공급을 정확히 한 번2ms 늦춘다. 두 DMA 버퍼가 반환되고 실제 rx_buffer_needed가 추가로 관측된
시점부터 지연하며20ms frame 주기·1Mbaud·1024byte는 유지한다. 실제 지연 시간·guard·연속 pattern과
양쪽 STOP·새 seed의 원래4선 복구를 요구한다. 임의의 무제한 RX 미공급이나 손실 없는 최대 속도
지원으로 확대하지 않는다. 현재 실기/예약 source는 그대로 유지한다.

후속 구현 범위: 기존 C01/C05의 UART30 CTS100ms 정지·재개를 전용 flow fixture에 추가한다.
동시에 실행되는 다른 UART/TWI/SPI의 GPIO·DMA 설정은 유지하며 같은 측정 구간의 양방향
완료량 증가와 전체 payload·guard·STOP·새 seed 복구를 함께 요구한다. 원래900/3600초 정상
안정성 결과와 분리하며 단독 CTS나 짧은 오류 주입을 장시간 동시 시험의 대체로 삼지 않는다.

다음 도구 구현 범위: 기존 S SPIS00/20/21/22/30의 짧은 DMA와 미준비 조건을 우선 분리한다.
A controller는1024byte를 요청하고 B target만512byte DMA 또는 미등록 상태로 둔다.
기존 GPIO/8MHz와 정상 회귀 기준은 유지하며 master RX 전체, target의 실제 AMOUNT/STATUS/
semaphore·DMA 경계·양쪽 STOP 및 새 seed의 정상 frame을 요구한다. CS 조기 해제는 기존 cancel의
실제 CS HIGH와 peer 부분량 증거가 충족되는지 별도로 대조하며 이 두 mode의 완료로 합치지 않는다.
현재 실행/예약 checkout은 수정하지 않는다. 이 단락은 구현 착수 범위이며 실기 PASS가 아니다.

93e38ff UART line source의 exact 두 역할 target·T13 Host63시험과 원격 전체 Host105묶음793시험을
확인했다. 기존 충돌/CTS 배치 종료 뒤에 UART parity/break16조건 예행을 예약했으며 원래 확인서
잔여시간이 부족하면 미시작으로 기록한다. 실행된 예행이 성공한 조건만100회 후속을 허용한다.
SPI boundary 초안 Host는67시험 중 새4개를 포함64개 통과·기존 C++ 실행3개가 WinError4551로
차단됐다. 최초 target의 SDK accessor const/이름 차이는 읽기 전용 DMA 레지스터 접근으로 수정하고
초안 두 역할 target2/2·새 Host4시험·정렬·계약·문서 재검사를 통과했다. 고정 source의 exact target과
원격 전체 Host를 확인해 UART line 배치 다음 순서에 등록했다. 두 준비 단계의 실제 HIL 결과는 아직0이다.
UART line 준비 원본은 [93e38ff 보존 목록](evidence/t13-uart-line-preparation-93e38ff/manifest.json)에
실패한 로컬 전체 Host까지 포함했다. 준비 검사와 실기 완료를 구분한다.
SPI 준비 원본도 [4f573f0 보존 목록](evidence/t13-spi-boundary-preparation-4f573f0/manifest.json)에
초안 target 실패·Host Windows4551 차단과 수정 후 exact 검사를 구분해 보존했다.

C01/C05 동시 CTS 초안은 두 역할 target2/2와 flow Host6시험을 통과했다. T13 전체 회귀에서
공유 선택 함수 변경이 단독 parity/break의 입력 범위를 넓히는 문제가 검출되어 단독 조건을 명시했다.
수정 후70시험 중69개가 통과했고 기존 stream C++ 실행1개는 Windows4551로 차단됐다.
고정 source의 변경 관련 flow/UART line Host와 원격 전체 Host를 별도로 요구하며 미실행을 PASS로 세지 않는다.
동시 CTS [e9afcc9 준비 원본](evidence/t13-concurrent-flow-preparation-e9afcc9/manifest.json)에
초안 문제 검출·수정과 Windows 차단, exact 검사와 원격 Host를 구분해 보존했다.
RX 공급 지연 초안도 두 역할 target2/2·새 Host4시험·정렬/계약/문서 검사에 통과했다. 전체 T13 Host는
74개 중73개 통과·기존 production route C++ 실행1개가 Windows4551로 차단됐다. 고정 source의
관련 Host·target과 원격 전체 Host를 확인한 뒤 동시 CTS 다음에 예행을 등록한다. 현재 RX 지연 실기는0이다.
f77e1cb의 exact gate와 원격 전체 Host 확인 뒤 등록을 완료했으며 [RX 지연 준비 원본](evidence/t13-rx-delay-preparation-f77e1cb/manifest.json)에
초안 Windows 차단까지 보존했다. C05의3600초·양쪽 STOP 원본은 [506680f 실기 보존 목록](evidence/t13-c05-soak-sauto-01-506680f/manifest.json)에 있다.
새 SDA LOW 도구의 Host78시험을 통과했다. 첫 초안 target에서 지원되지 않는 C++ cerrno 헤더를
발견해 SDK의 errno.h로 정정한 뒤 두 역할 target2/2 재검사를 통과했다. UART30과 같이 TWIM30도 실제 P0 경로임을 Host에서
검출해 원래 P0.00/01을 사용하도록 수정했다. 이 준비 검사나 과거 정상 TWI를 새 SDA LOW 실기 PASS로 세지 않는다.

| T13 하위 묶음 | 상태 | 현재 S에서 자동 진행 범위 |
| --- | --- | --- |
| PWM STOP/미시작 취소 | original506680f 6/6·600회 완료 | 원본 감사·문서 반영 |
| 고정 serial 복구 | 17/21 완료, TWIM 취소4개 미완료 | RX 시작/END·이전 AMOUNT 구분 보완 후 재검증 |
| stream 복구 | 3/4 완료, I2S B97번째 실패 | 원본 분석·원인 분리·재검증 |
| 역할 전환 | 예행5/5, 정식2/5 완료(serial00·30 각100회), SPI20/21/22 실패 보존 | 최초 RX 오류 계측을 보강하여 원인 분리; 이전 중단47회 합산 금지 |
| 동시 안정성 | 5/7 완료(C01~05), C06 진행 중(2026-09-08T10:59Z) | C01~06·C08; 일반900초, C05는3600초 |
| 추가 오류·충돌 | 일부 runner 미구현 | UART flow/지연/parity/break, SPI slave/short/CS, TWI 지연/stuck-low, 자원 충돌의 구현·Host/target·실기 |
| peer 제어 System OFF | 구현·exact Host/target 준비 완료, 실기0 | S 현재 배치와 TWIM 계측 뒤 bridge 예행부터 실행; 무인 성립 실패 시 원본·한계를 남기고 독립 작업 계속 |
| U UART00 | 대기 | S→U 현재 재배치 확인 전 실행 금지 |
| S 증거 마감 | 진행 중 | 원본·지원 제한·문서·commit/push·CI; 전체 T13 완료로 확대하지 않음 |

## System OFF 자동화 설계와 판정

기존 M15의 timed GRTC와 사용자 SW0/P1.13 wake PASS는 유지한다. 이번 추가는 A를 제어 보드,
B를 System OFF 시험 보드로 사용하며 DAP UART를 계속 분리하는 별도 T13 경로다.

1. 양쪽 exact image·UID·SWD10MHz·controlled flash와 현재 S 전체 전기 검사를 선행한다.
2. 기존 S의 UART 교차선으로 A↔B 명령/결과를 중계한다. A의 SWD만 Host 제어·관측에 사용한다.
3. B의 debug power request 해제·정상 모드 복귀/reset을 Host에서 수행한다. B가 정상 모드임을
   peer 경로로 확인한 뒤 시험 중 B SWD 접근을 금지한다. 실제 해제 실패를 System OFF PASS로 세지 않는다.
4. B는 통신/DMA 종료·buffer/clock 반환 후 System OFF에 들어간다. 예행은 타이머 wake부터 시행한다.
5. GPIO wake는 이미 연결된 P1.14 등을 검토하여 A의 단일 open-drain 신호로 발생시킨다.
   최종 핀·pull·동작 순서·제한 시간을 Host/target 전에 고정한다. 현재 미연결 P1.13을 연결됐다고
   가정하지 않는다. 다른 GPIO의 wake를 실제 SW0/P1.13 버튼 경로 재검증으로 기록하지 않는다.
6. 준비 nonce·회차·부팅 시각·진입/무응답 구간·RESETREAS·retention 상태와 새 pattern의 통신 복구를
   대조한다. RESET_DEBUG·일반 reset·즉시 복귀·로그 단절만으로 성공을 판정하지 않는다.
7. 첫 예행이 성립하면 타이머/GPIO 각100회 복구를 목표로 한다. 장치/확인서 제한 전에 유한 종료하고
   양쪽 출력/자원을 반환한다. 새 image를 적용한 부분의 기존 영향 회귀도 별도 판정한다.

구현 사양은 [T13_POWER.md](../../tests/hil/nu54dk/T13_POWER.md)에 고정한다. UART21 P1.06/07의
128byte 양방향 DMA와 P1.14 open-drain wake를 사용한다. de5ad42의 별도 power 두 역할과 일반 S
두 역할 target, 원격 Host101묶음778시험이 통과했다. 아직 debug 해제나 System OFF 실기는0이다.

SWD 하드웨어 스위치의 제어선은 현재 S GPIO에 직접 연결돼 있지 않다. 이를 GPIO로 제어한다고
가정하지 않으며 SDK pyOCD의 debug power-down과 Nordic 정상 모드 복귀 절차를 우선 검증한다.
이 과정에서 수동 스위치나 추가 배선이 실제로 필요해지면 그 항목을 중단하고 다른 S 작업을 계속한다.
기존 수동 runner의 확인 prompt를 허위 답변으로 통과시키거나 손으로 누른 버튼 결과를 만들지 않는다.

근거: [Nordic Debug Interface mode](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/debug.html-debuginterfacemode),
[System OFF](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/pmu.html-unique_1139880052),
[기존 M15](17_M15_NU54DK_Board_System_기준선.md), [현재 S 계획](../../tests/hil/nu54dk/T13_PLAN.md).

## 실행 유지와 실패 처리

Host 배치를 독립 숨김 프로세스로 실행하고 각 항목의 시작/종료·오류·원본 위치를 즉시 저장한다.
프로세스가 살아 있는 동안 동일 보드에 다른 flash/runner를 실행하지 않는다. 코드 준비는 main,
실행 checkout은 C:/tr13dev로 분리한다. 실패·중단의 미완료 반복이나 끊긴 연속 시간을 합산하지 않는다.
원래 S 확인 종료 2026-09-08T12:26:14Z(한국21:26:14)를 연장하지 않는다. 남은 유효시간 안에
완료하기 어려운 긴 시험은 시작하지 않으며 만료 후에는 Host/target·분석·문서 작업을 진행한다.
U 재배선·사용자 승인·정식 공개는 자동으로 수행한 것으로 처리하지 않는다.

## 2026-09-08 자동 진행 중간 기록

새 serial00 전환은 original506680f에서100/100회 완료했다. 이전47회와 합산하지 않는다.
serial20은1회 step09, serial21은5회 step02, serial22는1회 step02의 SPI 단계에서
engine/renew 오류로 끝났으며 세 실행 모두 양쪽 정지를 증명했다. `lease renewal failed`라는
문구만으로 확인서 만료나 통신 단절로 단정하지 않는다. lane 최초 오류를 계속 분석한다.
serial30도 새100/100회 완료했다. C01·C02는 각각900초 연속 실행·양쪽 STOP까지 완료했고 C03을 진행 중이다.

2026-09-08T09:42Z: C03도900초·양쪽 STOP을 통과했고 C04를 시작했다.

이후 raw 분석에서 세 SPI 단계의 최초 RX payload 불일치(code6)를 확인했다. byte 위치는
568/749/499이며 firmware lease_expired는0이다. 따라서 공통 오류 문구가 확인서 만료를 뜻하는
것은 아니다. 전기 파형·peer buffer 원인을 아직 확정하지 않았고 재결선을 요구하지 않는다.

TWIM 취소의 opcode123 원본 계측을 추가했다. 이전 AMOUNT, 이번 RXREADY/RXEND,
수신 RAM과 취소 cycle을 분리해 보존하며 기존 통과 기준은 유지한다. 실기 전 Host/target 및
exact source 검사를 요구한다. 로컬 T13 Host43시험 중42개는 통과했고 한 C++ 실행 시험은
Windows 응용 프로그램 제어 WinError4551로 실행이 차단됐다. 정책을 해제하지 않으며 원격
전체 Host 결과를 별도로 확인한다. 이는 해당 C++ 시험 PASS가 아니다.

2114187 계측 source의 로컬 두 역할 target과 원격 Software gate가 통과했다. System OFF 별도
image 초안은 두 역할 빌드, 정상/오류 판정 Host5시험, 계약·문서 검사까지 통과했다. 초안 build의
`cstring` 헤더 실패는 최소 C++ 환경의 C 헤더로 고쳤다. 아직 보드에 이 image를 적용하지 않았으며
source 고정 후 exact build/원격 Host를 다시 확인한다.

원본: [중단 정지 감사](evidence/t13-handover-interruption-cleanup-506680f/manifest.json),
[새 serial00 100회](evidence/t13-serial0-handover-sauto-01-506680f/manifest.json),
[serial20 실패](evidence/t13-serial20-handover-sauto-01-506680f/manifest.json),
[serial21 실패](evidence/t13-serial21-handover-sauto-01-506680f/manifest.json),
[serial22 실패](evidence/t13-serial22-handover-sauto-01-506680f/manifest.json).

추가 원본: [serial30 100회](evidence/t13-serial30-handover-sauto-01-506680f/manifest.json),
[C01 900초](evidence/t13-c01-soak-sauto-01-506680f/manifest.json),
[C02 900초](evidence/t13-c02-soak-sauto-01-506680f/manifest.json).

[C03 900초 원본](evidence/t13-c03-soak-sauto-01-506680f/manifest.json)도 별도로 보존했다.
[C04 900초 원본](evidence/t13-c04-soak-sauto-01-506680f/manifest.json)은 별도의 연속 측정과 양쪽 STOP을 보존한다.

자원 충돌14조건의 b5d614e는 exact 두 역할 target·T13 Host55시험·원격 Host103묶음785시험을
확인했다. b5d614e 이전884c642의 UART30 bank 선택 오류는 실기 적용 전에 수정했고 원본을 유지한다.
CTS GPIO 주입 도구는 초안 두 역할 target과 T13 전체 Host58시험·형식·계약 검사를 통과했다.
둘 다 아직 실기 PASS가 아니며 고정 source와 개별 예행을 요구한다.

d44cef2 CTS image는 exact 두 역할 target·Host58시험·원격 Host104묶음788시험을 통과했다.
이전 source의 build가 있던 C:/t4f04에는 덮어쓰지 않았고, 새 C:/t4l04에 별도 빌드했다.
원본: [b5d614e 충돌 준비](evidence/t13-conflict-preparation-b5d614e/manifest.json),
[d44cef2 CTS 준비](evidence/t13-flow-preparation-d44cef2/manifest.json).

## TWIM 취소 AMOUNT 대조 근거

[Nordic nRF54L15 TWIM register 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/twim.html-topic?contentId=ZCNrRd3TXd2U_Zlq48Iw7Q)은
DMA.RX.AMOUNT를 최근 DMA transaction의 END/MATCH에서 갱신하는 값으로 정의한다.
현재 SDK nrfx_twim.c의 TXRX는 TX buffer와 RX buffer를 설정하고 LASTTX→STARTRX shortcut으로
수신을 시작한다. TX 도중 취소했을 때 RX AMOUNT가 이전 정상 전송의256으로 남을 수 있다는
가설과 맞지만, 아직 이번 원본으로 확정하지 않는다. opcode123의 시작 전 값·RXREADY/END·
수신 RAM·실제 TX 부분량을 함께 수집한다. 시작/완료 event0만으로 이번 RX가 없었다고 단정하지
않고 driver의 event clear 경로도 대조한다. 기존 실패의 판정이나 원본을 미리 바꾸지 않는다.

## Nordic errata와 현재 실패의 대조

- [SPIM8](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_8.html?contentId=kxYSRXGTZ75bNAvYNrfIlg)은
  CPHA0·PRESCALER>2·첫 송신 bit1 조건의 MOSI 문제다. 현재 SDK nrfx_spim.c는 해당 조건에
  CSNDUR와 START 전/STARTED 후 offset0xc84 workaround를 적용하는 경로를 포함한다.
  core SpimFabric.cpp는 nrfx_spim_init/xfer를 사용하며 CS duration255를 설정한다.
  최초 오류 byte568/749/499만으로 이 errata가 원인이라고 확정하지 않는다. 특히 normal master의
  RX는 MISO 방향이므로 MOSI errata와 구분한다. 첫 실제 byte 원본을 추가한 이유다.
- [SPIM21](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_21.html?contentId=e9uUoQU3VuanCppXyAz5CA)은
  clock 종료 뒤 MOSI의 추가 전이를 설명하며 문서상 consequence는 없다. 전송 중 RX 불일치의
  직접 근거로 사용하지 않는다.
- [SPIS54](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_54.html?contentId=ksFfAvV4L1vT0n4CwKBeIg)은
  CS inactive에서 SDO가 floating일 때의 추가 전류 문제다. 통신 오류의 확정 원인이나 현재
  확인된 결선의 변경 사유로 확대하지 않는다.
- [TWIM105](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_105.html?contentId=eH3BnjumOZsG8A~kiCmQlw)은
  clock stretching 중 disable 이후의 무응답과 reset 복구를 설명한다. 아직 미구현인 stuck-low/
  공급 지연 시험은 LOW 해제와 STOP을 먼저 증명해야 하며, 실패 시 reset으로 복구한 결과를
  무reset 정상 복구로 바꾸어 기록하지 않는다.

이 대조는 source 검토이며 실제 silicon revision별 workaround 동작이나 새 실기 PASS가 아니다.

다음 source에는 첫 RX payload 불일치의 actual/expected byte·주변4byte·DMA 주소·AMOUNT·guard를
STOP 전 고정하는 opcode124를 추가한다. 예전 실패에 없던 actual byte를 추정으로 채우지 않는다.
기존 통과 기준을 유지하며 자원 충돌 opcode125와 함께 Host/target·exact source를 확인한 뒤 실기한다.

준비 검사 원본: [2114187 TWIM exact build·Host·CI](evidence/t13-twi-proof-preparation-2114187/manifest.json),
[de5ad42 power exact build·Host·CI와 유한 후속 배치](evidence/t13-power-preparation-de5ad42/manifest.json).
de5ad42는 기록 시점 원격15검사 중14성공·1진행 중이며 전체 성공으로 기록하지 않는다.
