# M31-W05 RAS 재연결과 3보드 peer 분리 진단

Arduino `RasInitiator`/`RasReflector`의 공개 `s`(중단), `r`(재시작),
`d`(연결 해제) 명령과 Ranging Service 광고 filter를 실기 검증했다.
고정 NCS/Zephyr/board revision과 CMSIS-DAP V2 역할 매핑은
[앞선 W05 기록](176_M31_W05_Arduino_RAS_initiator_100회와_재시작_진단.md)과
같다. 원본 probe UID는 저장하지 않았고 SHA-256 identity만 증거에 남겼다.

`d1a258161cd439b5b5f2e869538aa00857799b5a` clean build의
initiator HEX SHA-256은
`5ba9c27f5c10a29524acc63e1a49d5e9d2ff785e3b3c6791d1792005fe918dd4`이다.
FLASH 427232 B, RAM 232391 B(88%)였다. [reset-only 실행](evidence/m31-w05-ras-recovery-1c28428c/pair-clean-100-20-20.json)은
27.813초에 연속 procedure 100개를 받고, `s`/`r` 20회와 `d` 이후
scan·연결·L2 보안·CS 설정·새 raw 결과 복구 20회를 통과했다. 같은 image를
다시 flash하지 않은 [두 번째 reset 실행](evidence/m31-w05-ras-recovery-1c28428c/pair-afterflash-reset-100-20-20.json)도
100/20/20을 통과했다.

flash 직후 실행은 아직 일정하지 않다. 같은 image의
[한 sector-flash 실행](evidence/m31-w05-ras-recovery-1c28428c/pair-flash-100-20.json)은
procedure 100개와 중단·재시작 20회를 통과했지만, 다른
[sector-flash 후 추가 reset 실행](evidence/m31-w05-ras-recovery-1c28428c/pair-postflash-counter-gap.json)은
counter 0~7 뒤 연결 해제·재연결이 일어나 counter가 0부터 다시 시작돼
연속 100개 기준에 실패했다. 최초 flash 후 9개에서 멈춘 이전 실패도 보존한다.
한 실패 구간에서 CMSIS-DAP V2로 읽은 [initiator](evidence/m31-w05-ras-recovery-1c28428c/flash-stall-initiator-registers.txt)와
[reflector](evidence/m31-w05-ras-recovery-1c28428c/flash-stall-reflector-registers.txt)는
fault bit 없이 idle 상태였다. 이는 CPU stack fault라는 설명을 지지하지 않는다.
연결 해제 원인과 flash 직후 재현성 원인은 아직 확정하지 않았다.

peer 분리 시험에는 세 번째 NU54DK에 동일한 `NU54-CS-RSP` 이름과 다른
서비스 UUID `0x180D`를 광고하는 시험 firmware를 올렸다. initiator의 이름과
서비스 UUID **동시** scan filter는 실제 [정상 reflector도 찾지 못했다](evidence/m31-w05-ras-recovery-1c28428c/combined-scan-filter-no-peer.json).
현행 scanner는 한 scan result의 payload에서 두 조건을 모두 검사한다. 따라서
사용자 예제는 Ranging Service UUID `0x185B`만 먼저 filter하고, 연결 후 GATT
Ranging Service를 탐색한다. 단일 result에 두 광고 필드가 동시에 있는지는
이번 시험에서 증명하지 않았다.

`907ab2f7` clean initiator build의 FLASH는 427260 B, RAM은 232391 B,
HEX SHA-256은
`07f7905304c718995f20ebdcccc74751880649554e0c2b1038e48a8e18c8bcdf`이다.
세 번째 peer HEX SHA-256은
`c8fdff8dcbe6832e5e6d82a7b2ff5dfdd0afa2634bc7949c126b720319030b34`이다.
[3보드 확정 실행](evidence/m31-w05-ras-recovery-1c28428c/three-board-wrong-service-100.json)은
27.937초에 정상 reflector와 procedure 100개를 교환했고, 같은 이름의 잘못된
서비스 peer는 광고 상태였으며 연결 0회였다. 첫 실행에서 decoy UART 부팅
앞부분의 잡음이 400자 제한에 걸려 광고 문구를 증거에서 누락한
[실패](evidence/m31-w05-ras-recovery-1c28428c/three-board-serial-noise-fail.json)는
시험 runner의 Serial 정규화 문제였다. runner 수정 revision `1c28428c`에서
잡음 뒤 정상 문구를 보존하고 같은 firmware로 재검증했다.

이는 2보드 procedure·명시적 복구와 3보드 **같은 이름/다른 광고 서비스**의
peer 분리를 증명한다. RAS UUID를 위장하지만 GATT 서비스가 없는 peer,
미인증·wrong-key·권한 negative, flash 직후 간헐 연결 중단 원인과 거리 정확도는
아직 미검증이다. `M31-CS-01`/W05 전체 완료로 승격하지 않는다.
[증거 manifest](evidence/m31-w05-ras-recovery-1c28428c/ras-recovery-manifest.json)에
각 파일의 SHA-256을 기록했다.

광고에서 Ranging UUID를 **위장**하지만 GATT 서비스가 없는 peer는
[후속 20회 시험](179_M31_W05_RAS_UUID_위장_peer_거부_20회.md)에서 별도로 거부를 확인했다.
