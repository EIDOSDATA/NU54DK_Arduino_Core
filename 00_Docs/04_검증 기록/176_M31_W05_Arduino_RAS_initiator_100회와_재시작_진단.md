# M31-W05 Arduino RAS initiator 100회와 재시작 진단

공개 `RasInitiator`와 `RasReflector` 스케치를 서로 다른 NU54DK 두 대에 실행했다.
`.ino`는 BLE scan·연결·보안/절차 상태·Serial 명령과 공개 API만 다루며 Zephyr
CS·GATT·RAS 처리는 라이브러리 `.cpp`에 둔다. initiator 소스 revision은
`babdf15e0361b1a681ec5c92d493b6bfe65612f3`, 반복 실기 runner revision은
`d934cfcb`이다. 고정 NCS v3.4.0, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, nRF
`99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`을 사용했다.

Arduino CLI clean initiator build는 FLASH 427068 B(28%), RAM 232391 B(88%)였다.
initiator HEX SHA-256은
`f0409a73fc90279bb1e24ccc204e37c46f05b812e9873bfdc11123759d043684`,
reflector HEX는
`cc0919207c424ee52cd2d22aaabbbe98d668c9f8e493a88d74a6c67b2202500b`이다.
두 CMSIS-DAP V2는 SHA-256 probe identity, serial port, DP/AP register 값으로
역할을 확인했다. 원본 UID는 증거에 저장하지 않았다. flash는 sector programming과
hardware reset만 사용했다.

초기 initiator 빌드에서는 raw 결과 몇 개 뒤 `USAGE FAULT Stack overflow`가
발생했다. [Serial fault](evidence/m31-w05-ras-arduino-pair-d934cfcb/tx-stack-fault-serial.json)와
[CMSIS-DAP V2 register](evidence/m31-w05-ras-arduino-pair-d934cfcb/tx-stack-fault-registers.txt)의
`kernel_current=0x2000c678`, `PSP=0x20029490`을 ELF symbol과 대조했다.
`kernel_current`는 `bt_tx_processor_workq`, `PSP`는
`bt_tx_processor_stack`의 시작 주소다. 따라서 이 fault의 thread는 RX가 아니라
**Bluetooth TX processor**였다. `CONFIG_BT_TX_PROCESSOR_STACK_SIZE=3200`으로
올린 뒤 [clean ELF symbol](evidence/m31-w05-ras-arduino-pair-d934cfcb/tx-stack-symbols-after-fix.txt)에서
해당 stack 크기 0xC80을 확인했다. `CONFIG_BT_RX_STACK_SIZE=3200`도 현재
설정에 포함된다.

RTT 출력을 추가한 image의 첫 [flash 구간](evidence/m31-w05-ras-arduino-pair-d934cfcb/flash-run-9-then-timeout.json)은
양쪽 연결·L2 보안·CS 설정과 거리 출력 9개까지 확인됐지만 50초 안에 추가 결과가
없었다. 원인은 확정하지 않았으며 이 구간을 성공으로 판정하지 않는다. 같은 HEX의
SHA-256을 clean build와 대조한 뒤 재flash 없이 hardware reset한
[확정 구간](evidence/m31-w05-ras-arduino-pair-d934cfcb/reset-run-100-procedure-20-cycle.json)은
27.563초에 연속 counter 0~99의 procedure 결과 100개를 받았다. 각 결과의
로컬·상대 raw step 개수가 같고 유효한 RTT 쌍 15~25개가 있었으며, 거리 필드는
모두 유한했다. 이어서 Serial `s`/`r` 명령으로 20회 중단·재시작했고 각 회차의
양쪽 활성 상태와 새 raw 결과를 확인했다. 시험 전체 출력은 120개 raw 결과였다.

RTT 거리는 양쪽 mode 1 timing의 평균으로 계산한 **미보정 추정치**다. 이 실행의
출력 범위는 0~1.489 m, 중앙값은 0.2115 m였고 120개 중 37개는 음수 timing을
0 m로 제한한 결과다. 실제 거리 정확도, 위상 기반 거리, 안테나 배열 또는 각도
성능은 검증하지 않았다. 3번째 peer 분리, 미인증·wrong-peer negative,
disconnect/reconnect 20회와 최초 flash 직후 간헐 중단 원인은 미해결이다.
따라서 이는 `M31-CS-01`의 **100 procedure·20 stop/restart 하위 항목에 대한
부분 PASS**이며 W05 완료 판정이 아니다.

[Evidence manifest](evidence/m31-w05-ras-arduino-pair-d934cfcb/ras-pair-manifest.json)에
각 증거 파일의 SHA-256을 기록했다.
