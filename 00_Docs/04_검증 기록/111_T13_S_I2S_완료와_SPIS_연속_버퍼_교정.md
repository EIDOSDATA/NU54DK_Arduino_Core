# T13 S I2S 완료와 SPIS 연속 버퍼 교정

> 과거 체크포인트입니다. 아래 38/58·잔여 20조건은 당시 상태이며, 후속 SPI/TWI 완료는 112번,
> S 56 PASS + System OFF 2건 제외와 U 준비 완료·실기 NOT RUN은
> [113번](113_T13_S_범위_종료와_U_준비.md)에 기록했습니다. 아래 다음 순서는 현행 재실행 지시가 아닙니다.

## 당시 결과

2026-09-09 유지 중인 S 결선에서 I2S20 role2 공급 중단·재시작 정식 100회를 완료했다.
이 결과로 요청한 S 1~3단계는 **38/58(65.5%)**, 잔여는 SPI 10·TWI 4·TWIS 4·
System OFF 2의 **20조건**이다. QDEC와 시리얼 핸드오버는 사용자 결정대로 제외한다.

이어 실행한 SPI short-boundary 정식 묶음은 SPIM00/20/21 각 100회를 마친 뒤 SPIM22의
51회차 정상 재시작에서 실패했다. 다섯 인스턴스를 한 정식 묶음으로 판정하므로 앞의 부분 성공을
SPI 완료 수에 더하지 않았다. 실패 원인을 수정한 exact source로 SPI 5조건 전체를 다시 실행한다.

## 결선 관측의 해석

프로토콜 실행 전 17개 net을 양방향 open-drain LOW로 각각 10회 검사했다. 첫 실행은 net6,
아무 물리 변경 없이 이어진 두 번째 실행은 net7만 실패했고, 첫 실패 net6은 통과했다.
두 실행 모두 340 pulse를 끝냈고 양 보드 STOP·17핀 입력 반환을 확인했다. 실패 위치가 물리 변경 없이
이동했으므로 이 결과만으로 납땜·점퍼 단선을 확정하지 않는다. 사용자는 테스터로 결선을 확인했고
이후 같은 고정 결선에서 I2S 정식 100회와 SPI 5개 인스턴스 예행을 통과했다. 현재 결선을 유지하며,
새 통신 오류는 CMSIS-DAP 주변장치·DMA·GPIO 상태와 함께 판정한다.

- [첫 전수 검사: net6 관측](evidence/t13-s-full-wiring-review-20260909/manifest.json)
- [무변경 재검사: net7 관측](evidence/t13-s-full-wiring-recheck-20260909/manifest.json)

## I2S 정식 완료

source `0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d`, build `C:/t5u04`에서 I2S20
role2 starvation/restart를 100/100 통과했다. 의도한 underrun 100, 새 seed 정상 재시작 100,
양쪽 cleanup 203묶음, 최종 idle 관측 400개가 모두 일치했다. 진단용 반대 endpoint 성공이 아니라
원래 남은 role2 조건의 정식 결과다.

- [I2S 정식 원본과 무결성](evidence/t13-s123-05-i2s-r2-formal100-0dda7f9/manifest.json)

## SPI 최초 실패

같은 source의 SPI short-boundary 예행은 SPIM00/20/21/22/30 모두 통과했다. 정식 묶음에서는
SPIM00/20/21 각 100회를 통과했고 SPIM22 51회차의 의도한 512-byte 경계 시험 뒤 정상 재시작이
실패했다. A SPIM22 RX frame 12의 첫 byte는 기대 `0x5f`, 실제 `0x00`이었고 첫 네 byte가 모두
0이었다. A lane error는 6, B SPIS22는 자체 payload fault 없이 한 frame 앞의 완료 상태였다.
양쪽 cleanup 1,056묶음과 idle 2,106관측은 끝까지 성립했다.

상위 예외 문자열은 lease renewal 실패였지만 STOP 전 보존한 최초 lane 원본에는 그보다 앞선
payload 불일치가 있다. 따라서 lease 문자열을 최초 원인으로 쓰지 않는다. 실패 seed는
`3832777470`, 정상 재시작 seed는 `2051339079(0x7a44f347)`이다.

- [SPI short 정식 실패 원본과 무결성](evidence/t13-s123-05-spi-short-failure-0dda7f9/manifest.json)

## CMSIS-DAP 진단과 원인

nRF54L15 양쪽 core의 SPIM22/SPIS22 DMA PTR/MAXCNT/AMOUNT, PSEL, EVENT, semaphore 상태,
GPIO, clock, SCB/NVIC, lane와 RX RAM을 첫 `lane.error`에서 정지·보존하도록 DWT 진단기를 구성했다.
무작위 seed 100회와 위 정확한 실패 seed 쌍 100회에서 watch hit는 0이었다. 두 진단 모두
cleanup 300묶음·idle 600관측을 통과했지만, 오류가 재현되지 않았으므로 SPI 자격에는 더하지 않는다.

- [무작위 seed DWT 100회](evidence/t13-s123-05-spi22-dwt-random-0dda7f9/manifest.json)
- [정확한 실패 seed DWT 100회](evidence/t13-s123-05-spi22-dwt-exactseed-0dda7f9/manifest.json)

실패 원본과 고정 nrfx state machine을 함께 대조해 다음 구조 결함을 확인했다.

1. 기존 `SpisFabric`은 두 번째 pair를 소프트웨어 `next`에만 보관했다.
2. `nrfx_spis_buffers_set(next)`는 현재 transaction이 끝난 `NRFX_SPIS_XFER_DONE` callback 뒤에야
   호출됐다.
3. nRF54L15 SPIS semaphore의 CPU pending handover는 transaction 실행 중 다음 pair를 요청해야
   다음 CS 경계 전에 준비된다. 기존 구현에는 pair 재순환 경계마다 무버퍼 구간이 있었다.
4. 기존 단독 fixture는 다음 SPIS pair의 armed를 확인한 뒤 SPIM을 시작해 이 간격을 가렸다.
   T13 연속 frame에는 매 CS의 같은 장벽이 없어 frame 12의 zero RX와 일치한다.

## 수정과 소프트웨어 검증

`SpisFabric`은 첫 pair의 `BUFFERS_SET_DONE`에서 두 번째 pair를 즉시 요청해 현재 transaction 중
CPU pending을 만든다. 완료 뒤 승격된 pair가 동작하는 동안 `buffer_needed`를 내보내며,
새 `SpisHandle::provideNextBuffers()`가 반환된 pair를 다음 transaction으로 선행 예약한다.
T13 peer도 완료 slot을 다음 전역 frame으로 채워 이 API로 재공급한다.

NRFX fake는 첫 pair armed 뒤 두 번째 `buffers_set`이 발생하는지, END 뒤에는 늦은 요청이 없는지,
승격 pair armed 뒤 반환 pair가 다시 선행 예약되는지를 검사한다. 집중 Host 49/49, C++ 정렬 420/420,
현재 수정본의 T13 S DUT/peer target 2/2가 경고 없이 빌드됐다. 이 dirty-source 빌드는 컴파일 확인이며
실기 자격은 다음 exact 커밋의 새 image에만 부여한다.

## 당시 다음 순서

1. 수정·계약·증거 문서를 커밋하고 push한 exact SHA에서 S DUT/peer image를 새로 빌드한다.
2. SPIM22 집중 예행 뒤 SPI short 다섯 조건을 각 100회 정식 재실행한다.
3. SPI unready 다섯 조건, TWI stuck-low 네 조건, TWIS 지연 네 조건, System OFF 두 조건을 실행한다.
4. S 증거를 감사하고 UARTE00 전용 U image·실행 준비까지만 확정한다. U 재결선·실기는 실행하지 않는다.
