# T12 내부 ADC·TIMER·이벤트 무점퍼 검증

2026-09-07. 사용자가 보드 간 결선을 해제하고 자동으로 가능한 작업을 진행하도록 승인했다.
[94번 PWM 수정·실기](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md) 이후의 T12 내부 기능을 준비한다.
이 문서는 실행 전 checkpoint이며 아직 확장 실기 PASS가 아니다.

첫 실행 exact 35f30b2는 A 보드 ADC·TIMER·EGU/DPPI·PPIB 888개 명령 PASS 뒤 첫 GRTC 명령에서
중단했다. 요청 1000us에 micros 995us, 별도 TIMER와 차이 16us였다. Zephyr의
[busy-wait 계약](https://docs.zephyrproject.org/latest/doxygen/html/group__thread__apis.html)은
delay clock과 system clock 간 오차를 명시하고, 기존 V04-EVENT 시험표도 허용 오차 5%다.
새 HIL의 일방적인 1000us 하한을 busy-wait ±5%로 교정하며 상한도 105%로 엄격하게 제한한다.
제품 시간 구현은 변경하지 않는다. 최초 실패를 PASS로 바꾸지 않고 새 image를 빌드해 재시험한다.
실패 직후 PWM·ADC·DPPI 모두 off, P1.14 입력 복귀·controlled reset/halt를 확인했다.
B 보드와 나머지 15개 명령은 첫 실행에서 미실행이다.

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
