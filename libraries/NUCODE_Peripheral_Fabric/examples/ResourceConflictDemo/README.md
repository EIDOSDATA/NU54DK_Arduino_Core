# ResourceConflictDemo

## 목적

같은 serial block을 다른 personality가 동시에 소유하지 못하게 하는 공개 API 계약을 읽기 쉬운 흐름으로 보여준다.

## 준비물과 결선

NU54DK 1대. 외부 peer나 jumper는 필요 없지만 P2.00/01/02/04의 외부 driver를 분리한다. UART/SPI의 idle 출력은 생길 수 있으므로 미확인 장치에 연결하지 않는다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

UARTE20과 SPIM20, `p2_dedicated20`/`connector_fixture`. UART TX P2.02/RX P2.00, SPI SCK P2.01/MOSI P2.02/MISO P2.04. 데이터 전송과 DMA queue는 시작하지 않는다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

BUTTON0을 누르면 두 설정 stage→UART activate→SPI activate 거부→UART 상태 보존 확인→UART deactivate→SPI activate→SPI deactivate 순서로 한 번 수행한다.

## 예상 결과

`conflict_result == ownership_conflict`, `owner_preserved == true`, `last_result == success`, `stop_result == success`, `completed == true`. Serial Monitor 없이 debugger 변수와 LED_BUILTIN HIGH를 확인한다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

충돌 외 오류나 STOP 실패를 성공으로 바꾸지 않는다. 활성 handle은 각각 100000 us 제한으로 종료하고 실패를 유지한다. 성공 뒤 버튼 release/press는 새 실행이며 reset 없는 무한 handover stress 보증이 아니다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 실제 데이터 경로인 `SpiAsyncLoopback`. 다른 peripheral이 소유한 핀을 자동으로 재배치하거나 owner를 강제로 빼앗지 않는다.
