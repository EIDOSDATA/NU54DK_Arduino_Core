# T13 S SPI·TWI 완료와 System OFF 원인

> **후속 상태:** 이 기록의 56/58은 당시 체크포인트다. 이후 T13 peer 제어 System OFF 2조건은
> 기존 M15의 GRTC·사용자 버튼 System OFF 실기와 중복되는 추가 결합 회귀로 범위에서 제외했다.
> T13 PASS로 바꾸지 않으며, 최신 S 종료 상태는 [113번](113_T13_S_범위_종료와_U_준비.md)을 따른다.

## 당시 결론

고정 S 결선에서 SPI 경계 10조건, TWI stuck-low 4조건, TWIS 공급 지연 4조건을 모두
정식 완료했다. 당시 요청한 S 1~3단계는 **56/58(96.6%)**였다. 이후 S 범위는 113번에서
종료했으며, 아래 System OFF 추가 결합 진단은 현재 문제·재실행 목록이 아니다.

System OFF 실패는 GPIO 단선이나 T13의 GRTC/GPIO 설정 실패가 아니다. 재연결 뒤 17개 신호를
양방향 3회 검사해 **102/102**, UART21 DMA bridge와 양 보드 cleanup을 통과했다. nRF54L15
레지스터에서는 GRTC compare가 약 2초 뒤로 설정됐고 P1.14는 input/pull-up/SENSE_LOW이며,
A가 예약한 LOW도 실제 도착했다. pyOCD의 DP power request/ack 해제와 Arm SWD Dormant까지
적용해도 wake하지 않았다.

T13과 독립된 NCS v3.4.0 공식 `system_off` 예제도 같은 보드에서 2초 GRTC wake를 두 조건으로
실행했으나 모두 유지 RAM이 `boots=1, off_count=1`에 머물렀다. 당시에는 NU54DK의 온보드
debug-control 2연 SW1에서 B의 `DISABLE_SWD`만 격리하는 진단을 후속으로 제안했다.
이 추가 진단은 이후 범위 종료했으므로 현재 스위치 조작이나 재실행을 요구하지 않는다.

## 정식 완료 결과

| 범위 | exact source | 결과·해결 상태 | 당시 S 누계 |
| --- | --- | ---: | ---: |
| SPI short, SPIM00/20/21/22/30 | `914ccd16` | **해결 완료**, 5조건 × 100회 | 43/58 |
| SPI unready, SPIM00/20/21/22/30 | `1c02f9de` | **해결 완료**, 5조건 × 100회 | 48/58 |
| TWI SDA stuck-low, TWIM20/21/22/30 | `d39f0742` | **해결 완료**, 4조건 × 100회 | 52/58 |
| TWIS 2ms 공급 지연, TWIS20/21/22/30 | `e8e776e9` | **해결 완료**, 4조건 × 100회·사용자 수용 완료 | 56/58 |

SPI 두 묶음은 각각 계획한 경계 오류 1,000회, TWI는 기대한 error/recovery 400회,
TWIS는 기대한 지연 800회를 관측했다. 각 묶음의 정상 재시작, 측정 종료, 양 보드 STOP과
최종 핀 반환도 통과했다. 앞선 실패는 진행률에 더하지 않았고 수정된 exact source의 전체 묶음을
처음부터 다시 실행했다.

- [SPI short 정식 원본](evidence/t13-s123-spi-short-formal-914ccd16/manifest.json)
- [SPI unready 정식 원본](evidence/t13-s123-spi-unready-formal-1c02f9de/manifest.json)
- [TWI stuck-low 정식 원본](evidence/t13-s123-twi-stuck-formal-d39f0742/manifest.json)
- [TWIS 공급 지연 정식 원본](evidence/t13-s123-twis-delay-formal-e8e776e9/manifest.json)

## 재연결과 GPIO 판정

두 CMSIS-DAP를 100 kHz SWD로 다시 열어 양쪽 CPUID `0x411FD210`을 확인했다. 이어 17개 net을
A→B와 B→A로 각각 3회 구동했고 102개 전달이 모두 일치했다. 같은 세션에서 UART21 DMA bridge와
fresh challenge, 양 보드 STOP·핀 입력 반환도 통과했다. 공식 예제 진단 뒤에는 exact T13 image를
다시 기록하고 같은 102/102와 bridge를 재확인했다.

- [재연결 뒤 연결성·bridge](evidence/t13-s123-reconnect-bridge-2d283a3e/manifest.json)
- [공식 예제 뒤 exact T13 복구](evidence/t13-s123-power-restore-6ae56e41/manifest.json)

따라서 이후 System OFF wake 무응답을 납땜·GPIO 결선 실패로 분류하지 않는다. 새 오류가 생기면
먼저 같은 연결성 검사를 수행하되, 통과하면 주변장치·DMA·GPIO·reset 원인 레지스터로 판정한다.

## System OFF 레지스터 진단

exact source `6ae56e41`, build `C:/tz15`에서 OFF 직전과 cleanup debug wake 뒤의 유지 RAM을
96 byte로 보존했다.

| 진단 | OFF 직전 관측 | 결과 |
| --- | --- | --- |
| GRTC timer | MODE 2, LFTIMER 1, active CC5, compare delta `1,999,804 us` | 2초 설정 정상, GRTC wake 없음 |
| GPIO P1.14 | PIN_CNF `0x3000c`, IN high, SENSE_LOW | A pulse 뒤 controller IN bit14 low, GPIO wake 없음 |
| DP power | CTRL/STAT power request·ack mask 0 | 논리 debug power 해제 확인 |
| SWD Dormant | line reset 뒤 dormant code `0xe3bc`, 이후 DP/AP 접근 없음 | 물리 연결 상태에서는 timer wake 없음 |

실패 뒤 cleanup에서만 B SWD를 다시 열었고, 이때의 raw reset cause `1024`와 Zephyr debug cause
`32`는 GRTC `2048`이나 GPIO `128`로 확대하지 않았다.

- [GRTC compare·reset 원본](evidence/t13-s123-power-grtc-registers-6ae56e41/manifest.json)
- [GPIO 설정·LOW 원본](evidence/t13-s123-power-gpio-registers-6ae56e41/manifest.json)
- [SWD Dormant 원본](evidence/t13-s123-power-swd-dormant-6ae56e41/manifest.json)

## Nordic 공식 예제 기준선

NCS v3.4.0 `zephyr/samples/boards/nordic/system_off`를 NU54DK overlay, LFXO,
`CONFIG_PM_DEVICE=y`, GRTC 2초 wake와 0x2002e000 유지 RAM으로 별도 빌드했다.
일반 pyOCD disconnect와 Arm SWD Dormant 두 실행 모두 8초 뒤에도 `boots=1, off_count=1`이었다.
T13 image·UART bridge·Arduino wrapper를 전혀 사용하지 않는 예제에서도 같은 결과이므로,
T13 코드만 수정해 해결할 수 있는 현상이 아니다.

- [공식 예제 artifact hash와 유지 RAM](evidence/t13-s123-power-official-baseline-20260910/manifest.json)

## 후속 종료 상태

당시 System OFF 추가 실행 순서는 폐기했다. 공개 API의 M15 GRTC·버튼 wake 실기 완료를 확인하고
S 56 PASS + 추가 결합 2조건 범위 종료, U 준비 100%로 정리했다([113번](113_T13_S_범위_종료와_U_준비.md)).
실행하지 않은 추가 결합을 PASS로 바꾸지 않으며 U 실기는 미실행이다.
