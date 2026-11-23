# M33-W04 exact 증거

이 디렉터리는 기능 source `e3a663d629bcc22fb3222b99c456fda6c8e2c312`의 로컬 exact
검증 결과다. NCS v3.4.0, Zephyr `bf801e4e…`, board submodule `fe65f2f…`, Windows toolchain
`dcbdc366a1`을 유지했다. 원격 CI는 조회하거나 기다리지 않았다.

## 결과

- 독립 진단 route 10개 target build: 10/10 PASS
- DTM two-wire: 역할 교대 × 1M/2M × 채널 0/19/39, 12/12 PASS
- DTM H4: 역할 교대 × 1M/2M × 채널 0/19/39, 12/12 PASS
- 최소 실제 RX count: two-wire 1,590, H4 1,884
- 두 transport 모두 malformed/range·busy lease negative와 양쪽 STOP 2/2 PASS
- 격리된 세 번째 보드: program/reset/resume 없이 HALTED·RADIO disabled 유지
- Host diagnostics 46/46, readiness 15/15, contract check와 clang-format PASS

정밀 RF 출력·감도·주파수와 외부 HCI Host/adapter 실제 상호운용은 자동 결과로 승격하지 않았다.
RF tester와 UART/async UART/H5/LPUART/SPI 외부 adapter 실기는 사용자 후속 `NOT_RUN`이다.

## 파일

- `build-manifest.json`: 10개 route의 source/SDK/board/image/config/log hash
- `twowire-preflight.json`, `twowire-fixture.json`, `twowire-result.json`: two-wire 준비·실행
- `h4-preflight.json`, `h4-fixture.json`, `h4-result.json`: H4 준비·실행
- `verification-summary.json`: 정량 결과와 파일 SHA-256

## 실패 원본과 진단

완료 결과로 덮어쓰지 않은 후보·exact 실패 원본은 저장소 밖의 새 output 디렉터리에 그대로 보존했다.
초기 후보는 H4 command buffer의 H4 indicator 뒤 opcode를 읽지 않아 timeout이 발생했고, 실제 Zephyr
`bt_buf_get_tx()` buffer 구조와 고정 SDK sample을 대조해 수정했다. 시작 직후 stale UART byte는 1초
settle과 input flush로 차단했다. W02 STOP 뒤 남는 `PHYEND→DISABLE` bit 19는 MDK reset/bit 정의를 근거로
TX/RX 전환에서만 허용하고, active/unknown shortcut은 계속 거부한다.

Exact 준비 중 pyOCD `FlashFailure`가 유한하게 발생했다. 각 실패 뒤 read-only audit로 세 보드가
HALTED·RADIO disabled이고 세 번째 보드가 불변임을 확인한 뒤에만 새 output에서 다시 실행했다.
1 MHz에서 RX 실패가 반복되고 500 kHz target-only sector program/readback이 통과해 기본 SWD를
500 kHz로 낮췄다. 이후 H4 TX에서도 한 번의 transient `FlashFailure`가 있어 이를 SDK 결함으로 단정하지
않았으며, 동일 안전 audit 뒤 새 시도에서 exact program/readback과 전체 runtime이 PASS했다.
