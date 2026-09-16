# M31-W05 Arduino RAS reflector 100회 진단

고정 NCS v3.4.0의 native `ras_initiator`와 공개 Arduino `RasReflector` 예제를
NU54DK 두 대에서 연결했다. 공개 Core는 clean revision
`86708d8a`이고 reflector image SHA-256은
`cc0919207c424ee52cd2d22aaabbbe98d668c9f8e493a88d74a6c67b2202500b`이다.
native initiator image SHA-256은
`aaf3fcd3d2d475c21d9ce6d53559c8fc7e6f597f1b224a13c565471d621dbc16`이다.
공개 reflector 빌드는 FLASH 424268 B, RAM 220823 B(84%)였다. 양쪽 CMSIS-DAP V2의
SHA-256 probe identity와 DP/AP register identity를 재확인한 뒤 sector flash와
hardware reset만 사용했다.

처음 flash한 직후에는 보안 L2, CS 설정과 procedure 활성화가 완료되고 거리 결과
31개가 출력된 뒤 initiator가 다시 부팅했다. 해당 [실패 구간](evidence/m31-w05-ras-arduino-reflector-86708d8a/flash-run-31-then-reboot.json)을
성공으로 덮어쓰지 않는다. **같은 두 image를 다시 flash하지 않고** 양쪽을 hardware
reset한 [두 번째 구간](evidence/m31-w05-ras-arduino-reflector-86708d8a/reset-run-100.json)에서는
11.594초 안에 native initiator의 거리 결과 100개를 수집했다. 이때 Arduino reflector는
광고·연결·보안 L2·CS config ready·procedure enabled를 출력했다. 결과 100개의
`ifft`, `phase_slope`, `rtt` 값은 모두 유한했으며 initiator boot banner는 1개였다.

이는 **Arduino reflector의 Ranging Service·CS 설정이 native initiator와 실제 연결돼
100개 결과를 교환한 범위**를 증명한다. 거리 정확도, Arduino initiator API, 명시적
procedure 100회, stop/restart, peer loss와 보안·wrong-peer negative는 증명하지
않는다. flash 직후 재부팅의 원인도 아직 특정하지 않는다. M31-CS-01과 W05 완료
판정은 계속 보류한다.
