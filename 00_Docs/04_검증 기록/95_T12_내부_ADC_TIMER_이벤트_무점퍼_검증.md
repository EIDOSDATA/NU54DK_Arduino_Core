# T12 내부 ADC·TIMER·이벤트 무점퍼 검증

2026-09-07. 사용자가 보드 간 결선을 해제하고 자동으로 가능한 작업을 진행하도록 승인했다.
[94번 PWM 수정·실기](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md) 이후의 T12 내부 기능을 준비한다.
이 문서는 실행 전 checkpoint이며 아직 확장 실기 PASS가 아니다.

## 범위와 현재 상태

- 제품 source는 PWM 수정본 080d771이다. 이번 확장은 전용 HIL·Host 판정기·문서만 변경한다.
- [전용 HIL](../../tests/zephyr/m25_nojumper_hil/README.md)의 ADC 12·TIMER 352·EGU/DPPI 480·PPIB 44·GRTC 4와 PWM 반복 회귀 12개를 보드별로 실행한다.
- ADC calibration 완료·역순 scan·guard/tail, TIMER shortcut·capture, 내부 전달·disable·group·시험용 예약 거부, 기존 시간 함수를 대상으로 한다.
- SWD 10 MHz, exact 두 UID, sector flash, auto_unlock=false, controlled reset/start, 최초 실패 후 후속 명령 차단을 유지한다.
- 초기 네 DPPI CHEN과 두 EGU INTEN이 0인지 확인하고, 끝에는 ADC/PWM off·DPPI 해제·P1.14 입력 복원을 읽는다.
- Source를 커밋으로 고정한 뒤 canonical 단독 target을 새 디렉터리에서 빌드한다. 원본 실행기는 work/t12-internal-nojumper에 준비했다.

외부 PWM 파형·GPIO/GPIOTE 결선, I2S 연속/단방향·QDEC 추가 조건과 T13 이후는 별도다.
TIMER의 10회 compare/capture와 EGU 계열의 1000 event × 10회 조건을 구별하며 전체 T12로 승격하지 않는다.

[PPIB 쌍과 register](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/ppib.html-topic),
[handshake와 overflow](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/ppib.html-doc_ppib_handshake_overflow)를
고정 SDK의 register/metadata와 대조했다. Group-enable은 public API가 소유한 group의 HAL task로 시험한다.
