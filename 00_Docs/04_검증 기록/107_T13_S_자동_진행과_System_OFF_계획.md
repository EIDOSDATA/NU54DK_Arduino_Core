# T13 S 자동 진행과 peer 제어 System OFF 검증 계획

2026-09-08 소유자 지시를 반영한다. T13 S와 T14의 영향 분석·재시험, T17 증거/문서 유지 범위다.
U UART00은 현재 결선에서 실행하지 않으며 S 완료 또는 가능한 작업 소진 후 GPIO 재배치를 안내한다.
T12와 QDEC 문제 보고 후 검증 작업 완료 결정은 유지한다. QDEC 재진단은 새로 예약하지 않는다.

## 마일스톤과 현재 상태

| T13 하위 묶음 | 상태 | 현재 S에서 자동 진행 범위 |
| --- | --- | --- |
| PWM STOP/미시작 취소 | original506680f 6/6·600회 완료 | 원본 감사·문서 반영 |
| 고정 serial 복구 | 17/21 완료, TWIM 취소4개 미완료 | RX 시작/END·이전 AMOUNT 구분 보완 후 재검증 |
| stream 복구 | 3/4 완료, I2S B97번째 실패 | 원본 분석·원인 분리·재검증 |
| 역할 전환 | 예행5/5, 정식 첫 block47회에서 Host 중단 | 새 campaign으로 각100회, 이전47회 합산 금지 |
| 동시 안정성 | 0/7 완료 | C01~06·C08; 일반900초, C05는3600초 |
| 추가 오류·충돌 | 일부 runner 미구현 | UART flow/지연/parity/break, SPI slave/short/CS, TWI 지연/stuck-low, 자원 충돌의 구현·Host/target·실기 |
| peer 제어 System OFF | 새로 추가, 실기0 | 아래 단계의 구현·검증; 무인 성립 실패 시 원본·한계를 남기고 독립 작업 계속 |
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
serial30과 독립 동시 조합은 같은 고정 source의 별도 프로세스로 계속 진행 중이다.

TWIM 취소의 opcode123 원본 계측을 추가했다. 이전 AMOUNT, 이번 RXREADY/RXEND,
수신 RAM과 취소 cycle을 분리해 보존하며 기존 통과 기준은 유지한다. 실기 전 Host/target 및
exact source 검사를 요구한다. 로컬 T13 Host43시험 중42개는 통과했고 한 C++ 실행 시험은
Windows 응용 프로그램 제어 WinError4551로 실행이 차단됐다. 정책을 해제하지 않으며 원격
전체 Host 결과를 별도로 확인한다. 이는 해당 C++ 시험 PASS가 아니다.

원본: [중단 정지 감사](evidence/t13-handover-interruption-cleanup-506680f/manifest.json),
[새 serial00 100회](evidence/t13-serial0-handover-sauto-01-506680f/manifest.json),
[serial20 실패](evidence/t13-serial20-handover-sauto-01-506680f/manifest.json),
[serial21 실패](evidence/t13-serial21-handover-sauto-01-506680f/manifest.json),
[serial22 실패](evidence/t13-serial22-handover-sauto-01-506680f/manifest.json).
