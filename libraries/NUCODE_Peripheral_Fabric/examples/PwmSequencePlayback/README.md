# PwmSequencePlayback

## 목적

static RAM의 PWM duty sequence를 유한하게 재생하고 완료 후 핀과 DMA lease를 반환한다.

## 준비물과 결선

NU54DK 1대. PWM20 출력은 P1.10(`PIN_PWM0`, canonical 3; `PIN_LED1`은 같은 pad의 alias)이다. 보드 회로/부하를 확인하고 필요시 고입력 임피던스 scope로 관측한다. motor·speaker·고전류 부하나 다른 출력에 직접 연결하지 않는다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

PWM20, 1 MHz base/COUNTERTOP 1000으로 carrier 1 kHz, common decoder, 8개 duty 10..80%, repeats 99. 2회 유한 재생, loop off. 값은 flash const가 아닌 정적 RAM이며 MSB는 polarity 설정이다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

BUTTON0(P1.13)을 누른다. 약 100 ms마다 다음 duty로 바뀌는 8단계를 두 번 재생한다. playback_complete를 받은 뒤에도 stop을 호출해 소유권을 반환한다.

## 예상 결과

`sequence_events > 0`, `completed == true`, `stop_result == success`. LED_BUILTIN HIGH는 lifecycle 완료 표시이며 실제 duty/frequency 실측을 대신하지 않는다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

error·예상 밖 stopped·3초 deadline에서 유한 stop을 요청한다. STOP 실패 시 RAM/pad lease를 유지하므로 재생을 덮어쓰지 않는다. 정상 종료 후 버튼으로 재시작하며 실패 후에는 실제 출력 상태를 확인하고 reset한다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 `ResourceConflictDemo`. analogWrite/Servo/tone과 동시 사용하지 않는다. 파형 정확도·jitter는 계측 후에만 판정한다.
