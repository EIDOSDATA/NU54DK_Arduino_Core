# SpiAsyncLoopback

## 목적

한 board의 MOSI-MISO 외부 jumper를 통해 application이 만든 32-byte SPI payload를 실제 RX와 비교한다.

## 준비물과 결선

NU54DK 1대. P2.02(`PIN_P2_02`, 27) MOSI와 P2.04(`PIN_P2_04`, 29) MISO를 연결한다. P2.01(`PIN_P2_01`, 26) SCK는 scope 입력 외 다른 출력과 연결하지 않는다. 이 단순 loopback에는 CS/외부 SPI device가 필요 없다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

SPIM20, `p2_dedicated20`/`connector_fixture`, mode 0/MSB first/1 MHz. 독립 static TX/RX RAM을 lease한다. TX는 index·세션 generation으로 만들고 RX 전체를 비교한다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

다른 bus driver를 분리한 뒤 BUTTON0(P1.13)을 눌렀다 놓는다. debugger에서 `matched_bytes`와 `completed`를 확인한다. jumper가 없는 경우 성공을 기대하지 않는다.

## 예상 결과

`matched_bytes == 32`, `completed == true`, `stop_result == success`. Serial Monitor 출력 없음. LED_BUILTIN HIGH는 완료 표시다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

길이·buffer identity·payload 하나라도 다르거나 1초 deadline이 지나면 cancel/deactivate 후 실패를 유지한다. STOP 실패 시 RAM을 보존하며 자동 재시작하지 않는다. 성공 뒤 새 버튼 press로 다른 generation payload를 보낸다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 `ResourceConflictDemo`. 실제 slave timing·CS 경계·신호 무결성 검증은 별도다.
