# UarteAsyncEcho

## 목적

32-byte UART 입력을 EasyDMA로 받고 같은 payload를 비동기로 반환한다.

## 준비물과 결선

NU54DK 1대와 3.3 V USB-UART peer. P2.02(`PIN_P2_02`, 27) TX→peer RX, P2.00(`PIN_P2_00`, 25) RX←peer TX, 공통 GND. 5 V 신호는 금지한다. 보드 TX와 RX를 직접 묶는 예제가 아니다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

UARTE20, `p2_dedicated20`/`connector_fixture`, 115200 8N1, flow control off. `payload[32]`는 static RAM이며 RX 완료 뒤 TX 완료와 deactivate까지 수정하지 않는다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

peer serial을 먼저 열고 BUTTON0(P1.13)을 눌렀다 놓은 뒤 32 byte를 한 번 전송한다. peer가 받은 32 byte가 입력과 같은지 비교한다. 예: `bytes(range(32))`. TX loopback의 자동 payload 생성과 달리 이 예제의 payload는 peer가 정한다.

## 예상 결과

`echoed_bytes == 32`, `completed == true`, `stop_result == success`. Serial Monitor 출력은 없다. LED_BUILTIN 출력 HIGH는 완료 표시이며 peer echo 비교를 대신하지 않는다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

3초 이내에 32 byte가 채워지지 않거나 UART error/cancel이 발생하면 취소·100000 us 이내 deactivate를 요청하고 실패를 유지한다. 성공 뒤 버튼 release/press는 새 echo, 실패 뒤에는 원인을 확인하고 명시적으로 reset한다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 `SpiAsyncLoopback`. 연속 UART 무손실 streaming이나 임의 크기 queue는 이 예제의 주장이 아니다.
