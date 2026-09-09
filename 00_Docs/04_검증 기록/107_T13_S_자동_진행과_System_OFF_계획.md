# T13 S 자동 진행과 peer 제어 System OFF 검증 계획

이 문서는 2026-09-08 자동 실행과 준비의 이력이다. 현재 실행 순서·범위는
[110번](110_문서_정리와_T13_S_잔여_재개.md), 당시 최종 감사는
[108번](108_T13_S_자동_실행_종료와_재개_항목.md)을 따른다.

## 결과 요약

| 항목 | 2026-09-08 최종 관측 | 후속 판정 |
| --- | --- | --- |
| 정상 안정성 | 단독 29/29, 동시 7/7, 합계 36/36 | source별 완료. C01~04·C06·C08 각 900 초, C05 3600 초 |
| 고정 serial 복구 | 17/21 | TWIM 취소 4 조건의 이전 RX AMOUNT 판정 오류 확인; 정식 완료는 109번 |
| Stream / PWM 복구 | 3/4 / 6/6 | I2S B 97번째 재시작 오류 미해결, PWM 600 회 완료 |
| Serial 역할 전환 | 예행 5/5, 정식 2/5 | serial00·30 각 100 회; SPI20/21/22 실패 보존. 이후 사용자 제외 |
| 자원 충돌 | 예행 14/14, 정식 5/14 | 이후 9 조건 반복 면제·사용자 수용은 109번. 추가 실기 PASS가 아님 |
| CTS | 단독 예행 8 조건 실패 | 실제 정지/재개 뒤 정상 간격 상한을 잘못 적용한 판정 문제. 새 source 재검증 필요 |
| UART parity/break | 예행 9실패·7미시작 | RX 활성 전 ARM ENABLE 전제 수정, 당시 새 실기 0 |
| System OFF | bridge 실패, 실제 OFF 0 회 | debug 유지 진단·정상 bridge·timer/GPIO wake를 구분 |
| 실행 마감 | 12 대열 종료, 56완료 실행 감사 | 최초 실패·양쪽 STOP·clock 0·핀 반환 보존 |

이 표의 미완료는 당시 상태다. 최신 CTS 12/12·RX 지연 8/8·UART line 16/16과 U 준비는 110번에서 확인한다.
중간 진행률과 다음 실행 예약을 현재 지시처럼 반복하던 문단은 결과·준비 표로 통합했다.

## 원인 분석: TWIM 취소의 RX AMOUNT

2114187의 네 인스턴스 모두 repeat1은 이전/terminal RX AMOUNT0/0, 정상 재획득 이후 repeat2는
256/256이었다. TX는 모두 2 byte에서 취소됐고, 새 전송 전 초기화·취소 직전·terminal 관측에서
RXSTARTED/ENDRX는 모두 0이며 256 byte 수신 RAM 전체가 0xCC로 남았다. 같은 event의 시각·길이도
일치했다. [네 인스턴스 원본 대조](evidence/t13-twi-rx-provenance-analysis-2114187/manifest.json)를 보존했다.

SDK `nrfx/hal/nrf_twim.h`의 RX AMOUNT 설명은 마지막 transaction이며 END/MATCH에서 갱신된다고
명시한다. `nrfx_twim.c`의 취소 STOPPED 처리는 RXSTARTED/ENDRX를 지우지 않는다.
이번 TXRX가 TX 단계에서 취소돼 새 RX가 시작되지 않았는데 이전 256을 새 부분 RX로 해석한 것이
기존 판정 실패의 원인이다. 새 판정은 opcode123의 20 word·새 RX 미시작·전체 RAM 불변·이전 AMOUNT
일치·단일 terminal event를 매회 필수로 대조하며 raw256과 이번 RX0을 구분한다.
Core의 취소 구현은 변경하지 않는다. 기존 실패 판정은 그대로 보존하고 새 exact source100 회 재검증이
완료되기 전에는 serial17/21을 올리지 않는다. 관련 Host 9 시험 통과, T13 Host 84 중 83통과/기존
stream C++ 실행 1 개 Windows4551 차단을 보존했다.

원본: [TWIM20](evidence/t13-twi20-proof-sauto-01-2114187/manifest.json),
[TWIM21](evidence/t13-twi21-proof-sauto-01-2114187/manifest.json),
[TWIM22](evidence/t13-twi22-proof-sauto-01-2114187/manifest.json),
[TWIM30](evidence/t13-twi30-proof-sauto-01-2114187/manifest.json),
[System OFF bridge](evidence/t13-power-bridge-sauto-01-de5ad42/manifest.json),
[C08](evidence/t13-c08-soak-sauto-01-506680f/manifest.json).

### 레지스터 해석 근거

[Nordic nRF54L15 TWIM register 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/twim.html-topic?contentId=ZCNrRd3TXd2U_Zlq48Iw7Q)은
DMA.RX.AMOUNT를 최근 DMA transaction의 END/MATCH에서 갱신하는 값으로 정의한다.
현재 SDK nrfx_twim.c의 TXRX는 TX buffer와 RX buffer를 설정하고 LASTTX→STARTRX shortcut으로
수신을 시작한다. TX 도중 취소했을 때 RX AMOUNT가 이전 정상 전송의 256으로 남을 수 있다는
가설과 맞지만, 당시에는 원본 대조 전 가설이었다. 위의 후속 2114187 계측으로 이번 RX 미시작과 이전 AMOUNT 잔류를 구분했다. opcode123의 시작 전 값·RXREADY/END·
수신 RAM·실제 TX 부분량을 함께 수집한다. 시작/완료 event 0만으로 이번 RX가 없었다고 단정하지
않고 driver의 event clear 경로도 대조한다. 기존 실패의 판정이나 원본을 미리 바꾸지 않는다.

## 원인 분석: SPI 역할 전환 실패 — 보존, 재진단 제외

Original506680f의 serial00 첫 실행은 47/100에서 Host 프로세스가 종료됐다. 새 100/100과 합산하지 않았다.
serial20은 repeat1/step09, serial21은 repeat5/step02, serial22는 repeat1/step02에서 실패했다.
첫 RX 불일치 byte 위치는 각각 568/749/499이고 firmware lease_expired는 0이었다.
양쪽 STOP·clock 0·17 핀 입력 반환을 확인했다. serial30의 새 100/100도 별도 완료했다.
`lease renewal failed`를 사용자 확인 만료나 통신 단절의 원인으로 단정하지 않는다.

[고정 board 회로도](<../../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>)의 1·6쪽을
확인했다. P1.07은 SB12를 거쳐 U7의 UARTE_CTS에 연결되고, P1.06은 SB11/UARTE_RTS다.
LED1~4는 각각 P2.09/P1.10/P2.07/P1.14이므로 P1.07의 오류를 LED Schmitt 입력으로 바로
설명하지 않는다. DAP UART 분리 확인은 유지하되, OE 비활성과 실제 배선의 용량/반사/타이밍은
다른 관측이다. [회로도 대조 원본](evidence/t13-spi-route-review-b5d614e/manifest.json)을 보존했다.
I2S B RX의 별도 1 word 오류까지 같은 원인으로 합치지 않는다.

현재 SDK MDK는 SPIM20/21/22/30의 core16 MHz·RXDELAY reset1을 정의한다.
[47번](47_M24_Fixture_201_SPI_실기_검증.md)의 과거 수정은 공통값 2에 의한 한 bit 지연을 1로
교정했고 실제 TX/ORC100 회와 전체 기능을 통과했다. 그 과거 실패와 현재 간헐적 중간 byte 오류는
동일 현상으로 확정하지 않는다.

[Nordic RXDELAY](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spim.html-register.iftiming.rxdelay)는
SPIM core cycle 단위의 샘플 지연이고, [PRESCALER](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spim.html-register.prescaler)는
낮은 분주값에서 기본 RXDELAY 조정이 필요할 수 있다고 설명한다. 계산상 core16 MHz의 1cycle은
62.5ns이고 SCK8 MHz 반주기와 같다. 이는 수신 시점 비교가 필요한 이유이며 RXDELAY0이 정답이라는
증거가 아니다. SPIS가 수신한 오류까지 controller RXDELAY만으로 설명할 수도 없다.
후속은 동일 S net에서 별도 진단 소스로 8 MHz/RXDELAY0 또는 4 MHz/기존값을 각각 비교하되,
GPIO 구동·실제 레지스터·최초 오류·전체 payload·STOP을 함께 남겨야 한다.
낮춘 진단 속도의 통과를 원래 8 MHz 역할 전환 통과로 대체하지 않는다. 아직 이 비교 실기는 미실행이다.

### 최초 byte 보존 계측

b5d614e의 재현 결과는 다음과 같다. 세 입력은 모두 B P1.06 → A P1.07이며 직전 4 byte는 일치했다.
guard·lease 오류는 없었다. 공통 경로는 진단 단서이지 전기 원인 확정이 아니다.

| 인스턴스 | 최초 실패 위치 | expected / actual |
| --- | --- | --- |
| SPI20 | 역방향 step02, A SPIS20 RX frame 1 offset 339 | 0x90 / 0x9E |
| SPI21 | step09, A SPIM21 RX frame 30 offset 467 | 0xC4 / 0xC7 |
| SPI22 | step01, A SPIM22 RX frame 0 offset 286 | 0x31 / 0x11 |

Opcode124는 첫 byte·전후 4 byte·DMA 주소·AMOUNT·guard를 STOP 전에 보존했다.
이전 실패에 없던 actual byte를 추정하지 않았다. 당시 계획한 속도/RXDELAY 비교는 현재 handover 제외 범위다.

## 원인 분석: CTS 주입 구간의 판정 상한

d44cef2 단독 예행 8 조건은 실제 CTS HIGH와 TX 정지/재개를 통과했지만 정상 lane의 100 ms 상한에서 실패했다.
UART20 role1 원본은 DUT HIGH 100018 µs, peer 100019 µs, 해당 TX/peer RX 완료 간격 115 ms,
반대 방향 20 ms다. 실제 100 ms 주입을 정상 무주입 조건과 같은 상한으로 판정한 문제다.

2e5a2c5는 실제 HIGH를 검증한 동일 fixture/seed·영향받은 한 방향에만
HIGH + 20 ms + 11 ms + 1 ms 경계를 적용했다. 반대 방향·다른 lane·주입 전·새 seed 재획득은 100 ms,
전체 payload·guard·drained hash·양쪽 STOP은 그대로 요구한다.
기존 8 개 raw는 새 상한 안이지만 새 seed 재획득 증거가 없으므로 FAIL을 PASS로 바꾸지 않았다.

## 수정·준비 검사와 실제 실행의 구분

아래 값은 source별 준비 검사다. Windows Application Control의 WinError4551로 실행되지 못한
C++ 시험은 로컬 PASS로 세지 않았고 보안 정책을 변경하지 않았다. 원격 Host를 별도로 확인했다.

| source / 범위 | 로컬 검사·수정 | exact / 원격 확인 |
| --- | --- | --- |
| 2114187 TWIM 계측 | T13 Host 42/43; C++ 1 개 차단 | 두 역할 target·Software PASS |
| 772b47e TWIM 판정 | 새 Host 9; T13 83/84·stream C++ 1 개 차단 | target 2/2·원격 Host 814 시험 |
| de5ad42 power | Host 5; 초안 cstring→C 헤더 수정 | power/S 각 2/2, Host 101 묶음 778 시험; 기록 시 CI 14성공·1진행 중 |
| b5d614e 충돌 | T13 Host 55; 이전 884c642 UART30 bank 수정 | target 2/2·Host 103 묶음 785 시험 |
| d44cef2 CTS | T13 Host 58; 새 build C:/t4l04 (기존 C:/t4f04 보존) | target 2/2·Host 104 묶음 788 시험 |
| 93e38ff UART line | T13 Host 63; break 전환 중 DUT RX 시작 지연 | target 2/2·Host 105 묶음 793 시험 |
| 4f573f0 SPI 경계 | 초안 Host 64/67·C++ 3 개 차단; SDK accessor const/이름 수정·새 Host 4 | target 2/2·Host 106 묶음 797 시험 |
| e9afcc9 동시 CTS | flow 6·line 5; 공유 선택 함수 입력확장 수정; 초안 69/70·C++ 1 개 차단 | target 2/2·Host 106 묶음 800 시험 |
| f77e1cb RX 지연 | 새 Host 4; 초안 73/74·C++ 1 개 차단 | target 2/2·Host 107 묶음 804 시험 |
| 3fac751 SDA LOW | Host 78·새 4; cerrno→errno.h, TWIM30 P0.00/01 수정 | target 2/2·Host 108 묶음 808 시험 |
| 95c2bde TWIS 지연 | 변경 Host 4; 초안 79/82·C++ 3 개 차단; 기존 output 경로 덮어쓰기 거부 | target 2/2·Host 109 묶음 812 시험 |
| fedaa75 최초 UART 오류 | power Host 7·T13 Host 86, power/S 각 2/2 | Host 109 묶음 816 시험; Software 7성공·Reproducible 대기 |
| 2e5a2c5 CTS 상한 | 관련 Host 8; 초안 T13 86/88·C++ 2 개 차단 | target 2/2·Host 109 묶음 818 시험 |
| UART ARM 후속 수정 | 관련 Host 6·전체 T13 Host 89 | target 2/2; 당시 새 실기 0 |

UART line 초안의 전체 Host는 R03 analog production 12 개 하위 실행도 Windows4551로 차단됐다.
초안 검사와 고정 source의 원격 성공을 합쳐 로컬 전체 PASS로 표시하지 않는다.

### 준비한 오류 조건의 범위

| 시험 | 주입·성공 판정 | 포함하지 않는 범위 |
| --- | --- | --- |
| 충돌 | UART21/22의 block·GPIO·DMA와 UART30 block, 양쪽 역할 총 14 조건; 기존 전송·STOP·재획득 | UART00/20·event/PWM 전체 충돌 |
| 단독 CTS | UART20/21/22/30, peer GPIO RTS→DUT CTS HIGH 100 ms; 실제 시각·대기·payload 복구 | peer HW RTS 자체, RX 지연·line 오류 |
| 동시 CTS | C01/C05 UART30 정지 중 배경 UART/TWI/SPI 양방향 진행·payload·guard | 정상 900/3600 초의 대체 |
| UART line | even/no parity, peer UART 반환 후 원래 TX GPIO LOW 1 ms; 실제 mask·STOP·새 seed | 정상 연속 전송 |
| SPI 경계 | SPIS00/20/21/22/30, master 1024 byte·slave 512 byte 또는 미준비, 8 MHz·전체 RX/STATUS/AMOUNT | CS 조기 해제의 독립 판정 |
| RX 공급 지연 | 두 DMA 반환 후 실제 요청에서 2 ms 한 번 지연; 20 ms·1Mbaud·1024 byte, 새 4선 복구 | 무제한 공급 지연·최대 속도 무손실 |
| SDA LOW | staged A recoverBus, B open-drain LOW 100 ms 후 해제; 처음 실패·해제 뒤 success·0x42 복구 | 활성 stretching 중 disable·PMIC·반대 controller |
| TWIS 공급 지연 | 최초 write_request/buffer_needed 뒤 2 ms; SCL LOW·guard·양방향 복구 | read_request 지연·장시간 stretching |

## System OFF 설계와 최초 실패

기존 M15 timed GRTC·SW0/P1.13 wake PASS는 유지한다. 이 T13 시험은 A 제어/B 시험 보드,
UART21 P1.06/07의 128 byte 양방향 DMA와 기존 P1.14 open-drain wake를 쓰는 별도 경로다.

1. exact image·UID·전체 S 결선 검사 뒤 A의 SWD로 명령/결과를 중계한다.
2. B debug power request를 해제하고 정상 모드 복귀/reset을 확인한다. OFF 중 B SWD에 접근하지 않는다.
3. DMA·buffer·clock을 반환한 뒤 timer/GPIO wake 각각 100 회를 판정한다.
4. nonce·회차·무응답·RESETREAS·retention·새 pattern 복구를 대조한다. RESET_DEBUG나 단순 reset은 PASS가 아니다.

de5ad42의 최초 bridge는 A opcode132 응답 403, 양쪽 UART error 46(41+event 5)이었다.
양쪽 STOP·17 핀 반환은 확인했지만 정상 debug 해제나 OFF에 도달하지 않았다.
최초 event/mask·baud/config/PSEL·핀 수준·clock을 별도 SRAM에 보존하도록 준비했다.
후속 fedaa75는 위 표의 software 준비까지이며 이 기록에서 실제 OFF 성공은 0 회다.

현재 구현 사양은 [T13_POWER.md](../../tests/hil/nu54dk/T13_POWER.md)를 참조한다.
SWD 하드웨어 스위치를 S GPIO로 조작할 수 있다고 가정하지 않는다. 수동 runner 확인을 허위로
통과시키지 않으며 reset으로 정리한 실패를 무reset 복구로 기록하지 않는다.
U의 실제 재결선과 공개 승인은 이 자동 실행에 포함하지 않았다.

## Nordic 사양·errata 대조의 한계

- [SPIM8](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_8.html?contentId=kxYSRXGTZ75bNAvYNrfIlg)은
  CPHA0·PRESCALER>2·첫 송신 bit1 조건의 MOSI 문제다. 현재 SDK nrfx_spim.c는 해당 조건에
  CSNDUR와 START 전/STARTED 후 offset 0xc84 workaround를 적용하는 경로를 포함한다.
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
  clock stretching 중 disable 이후의 무응답과 reset 복구를 설명한다. 당시 미구현이던 stuck-low/
  공급 지연 시험은 LOW 해제와 STOP을 먼저 증명해야 하며, 실패 시 reset으로 복구한 결과를
  무reset 정상 복구로 바꾸어 기록하지 않는다.

이 대조는 source 검토이며 실제 silicon revision별 workaround 동작이나 새 실기 PASS가 아니다.

## 원본과 후속

모든 실패·부분 반복·준비 검사와 source별 실기 결과는 아래 원본을 유지한다.
당시 사용자 확인 종료는 2026-09-08T12:26:14Z(21:26:14 KST)였으며 이 때문에 미실행한 항목은 이력이다.
현재 시간제 재확인 정책과 혼동하지 않는다. firmware pulse/watchdog/lease와 STOP 검증은 유지한다.

- [108번 최종 기록](<108_T13_S_자동_실행_종료와_재개_항목.md>)
- [준비 원본](evidence/t13-flow-bound-preparation-2e5a2c5/manifest.json)
- [준비 원본](evidence/t13-power-diagnostic-preparation-fedaa75/manifest.json)
- [기존 8 개 raw 대조](evidence/t13-cts-gap-analysis-d44cef2/manifest.json)
- [준비 원본](evidence/t13-twi-stuck-preparation-3fac751/manifest.json)
- [C06 실기 원본](evidence/t13-c06-soak-sauto-01-506680f/manifest.json)
- [준비 원본](evidence/t13-twis-delay-preparation-95c2bde/manifest.json)
- [Nordic UARTE 핀 설정](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/uarte.html-concept_wmv_f2m_wr)
- [93e38ff 보존 목록](evidence/t13-uart-line-preparation-93e38ff/manifest.json)
- [4f573f0 보존 목록](evidence/t13-spi-boundary-preparation-4f573f0/manifest.json)
- [e9afcc9 준비 원본](evidence/t13-concurrent-flow-preparation-e9afcc9/manifest.json)
- [RX 지연 준비 원본](evidence/t13-rx-delay-preparation-f77e1cb/manifest.json)
- [506680f 실기 보존 목록](evidence/t13-c05-soak-sauto-01-506680f/manifest.json)
- [Nordic Debug Interface mode](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/debug.html-debuginterfacemode)
- [System OFF](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/pmu.html-unique_1139880052)
- [기존 M15](17_M15_NU54DK_Board_System_기준선.md)
- [현재 S 계획](../../tests/hil/nu54dk/T13_PLAN.md)
- [중단 정지 감사](evidence/t13-handover-interruption-cleanup-506680f/manifest.json)
- [새 serial00 100 회](evidence/t13-serial0-handover-sauto-01-506680f/manifest.json)
- [serial20 실패](evidence/t13-serial20-handover-sauto-01-506680f/manifest.json)
- [serial21 실패](evidence/t13-serial21-handover-sauto-01-506680f/manifest.json)
- [serial22 실패](evidence/t13-serial22-handover-sauto-01-506680f/manifest.json)
- [serial30 100 회](evidence/t13-serial30-handover-sauto-01-506680f/manifest.json)
- [C01 900 초](evidence/t13-c01-soak-sauto-01-506680f/manifest.json)
- [C02 900 초](evidence/t13-c02-soak-sauto-01-506680f/manifest.json)
- [C03 900 초 원본](evidence/t13-c03-soak-sauto-01-506680f/manifest.json)
- [C04 900 초 원본](evidence/t13-c04-soak-sauto-01-506680f/manifest.json)
- [b5d614e 충돌 준비](evidence/t13-conflict-preparation-b5d614e/manifest.json)
- [d44cef2 CTS 준비](evidence/t13-flow-preparation-d44cef2/manifest.json)
- [2114187 TWIM exact build·Host·CI](evidence/t13-twi-proof-preparation-2114187/manifest.json)
- [de5ad42 power exact build·Host·CI와 유한 후속 배치](evidence/t13-power-preparation-de5ad42/manifest.json)
- [SPI20](evidence/t13-serial20-first-fault-sauto-01-b5d614e/manifest.json)
- [SPI21](evidence/t13-serial21-first-fault-sauto-01-b5d614e/manifest.json)
- [SPI22](evidence/t13-serial22-first-fault-sauto-01-b5d614e/manifest.json)
- [보존 목록](evidence/t13-twi-provenance-preparation-772b47e/manifest.json)
