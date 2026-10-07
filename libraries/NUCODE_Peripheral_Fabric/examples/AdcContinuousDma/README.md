# AdcContinuousDma

## 목적

내부 VDD를 두 DMA buffer로 연속 sampling하고 반환된 buffer를 다시 queue한다.

## 준비물과 결선

NU54DK 1대만 필요하며 외부 analog 결선은 없다. 내부 VDD를 쓰므로 다른 pad에 전압을 인가하지 않는다.

공통으로 Tools → Feature set에서 **Peripheral Fabric (DAP UART disconnected)** (`fabric`)를 선택한다.
`Serial`/`Wire`/`SPI` singleton, analogRead/analogWrite와 동시에 쓰지 않는다. DAP UART 분리 여부와
현재 결선을 직접 확인한다. 이 문서는 결선 변경·flash·unlock·recover를 자동 허가하지 않는다.

## 설정과 buffer 수명

SAADC, 내부 `vdd`, gain 1/4, 12-bit, oversample 1, interval 128 us, 128 samples × 2개 static buffer.
공개 enum의 `vdd_div2`는 nRF54L15에서 승인된 입력이 아니므로 사용하지 않는다.
128 us는 고정 nrfx 내부 timer의 최대 간격이며 1 ms로 늘려 쓰면 지원 범위를 벗어난다.
default gain/reference를 다른 보드에서 추정하지 않는다.

기존 `NUCODE_Peripheral_Fabric.h` 공개 API만 사용한다. 기준은 NCS v3.4.0,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 독립 Nordic sample을 복사한 예제가 아니다.
필수 Kconfig/overlay는 fabric profile이 제공하고 추가 sidecar는 없다.

## 실행 순서

BUTTON0(P1.13)을 누른다. 각 buffer_complete에서 실제 sample의 평균을 계산하고 takeEvent가 반환한 buffer만 queueBuffer로 재공급한다. 8개 buffer 뒤 stop한다.

## 예상 결과

`completed_buffers == 8`, `average_raw`는 마지막 실제 128-sample 평균, `completed == true`, `stop_result == success`. 평균이 특정 고정값이라는 합격 조건은 없다.

Compile/Host mock PASS는 실제 peripheral/결선 PASS가 아니다. 이 예제의 신규 실물 실행은
현재 **NOT_RUN**이며 다른 예제의 과거 HIL을 소급 적용하지 않는다.

## 종료·재시작과 오류

오류·예상 밖 finished·buffer identity/길이 불일치·2초 deadline에서 stop한다. stop_timeout은 DMA lease 반환이 아니므로 RAM 유지 및 reset 전 재시작 금지다. 정상 종료 뒤 버튼을 새로 누르면 같은 설정으로 재시작한다.

시작 시 버튼이 이미 눌려 있으면 먼저 놓았다가 다시 누른다. 실패 후에는 `last_result`,
`stop_result`, 해당 handle의 `lastDriverError()`를 debugger로 확인한다. `completed == false`를
성공으로 처리하지 않는다. GPIO 복원/clock/DMA 반환은 STOP 성공으로 구분하며 reset 전까지
실패 buffer의 저장 공간을 재사용하지 않는다.

## 다음 예제

다음은 `PwmSequencePlayback`. raw 평균은 정밀 전압·온도 보정 결과가 아니며 mV 변환을 새 API처럼 제공하지 않는다.
