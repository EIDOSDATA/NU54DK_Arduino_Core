# TwisTargetDoubleBuffer

## 목적

I2C target의 두 TX/RX buffer를 미리 예약하고 외부 controller가 수행하는 두 write와 두 read를 처리한다.

## 준비물과 결선

NU54DK target 1대, 3.3 V I2C controller, SDA/SCL 외부 pull-up(예: 각 4.7 kΩ), 공통 GND. P1.04(`PIN_P1_04`, 20) SDA, P1.05(`PIN_P1_05`, 21) SCL. 해당 DAP UART 경로를 물리 분리한다. PMIC P1.02/P1.03에 연결하지 않는다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

TWIS21, `p1_flexible`/`dap_uart_disabled`, 7-bit 주소 0x42, internal pull-up off. static `buffers[0..1]`은 TX, `[2..3]`은 RX이며 모두 한 workspace에 포함한다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

BUTTON0을 누른 뒤 5초 안에 100 kHz controller에서 16-byte write 두 번과 16-byte read 두 번을 수행한다. 매 transaction은 STOP으로 끝내고 다음 transaction 전에 20 ms 여유를 둔다. 첫 read 기대값은 0x10..0x1F, 둘째는 0x80..0x8F다. 세 번째 read/write를 보내지 않는다.

## 예상 결과

`reads == 2`, `writes == 2`, `received_sum`은 두 실제 RX payload byte의 합, `completed == true`, `stop_result == success`. controller의 실제 read 비교도 별도로 확인한다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

짧은/초과 transaction, overrun/bus/error, 5초 미완료는 실패다. cancelBuffers/deactivate 후에만 RAM을 다시 쓴다. 기존 API에는 실행 중 한쪽만 독립 재공급하는 기능이 없으므로 무제한 target streaming을 주장하지 않는다. 성공 후 버튼으로 두 쌍을 새로 준비하고, 실패 후에는 controller를 멈춘 뒤 reset한다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 `UarteAsyncEcho`. target의 read-request clock stretch와 controller timeout은 별도 현장 조건이다.
