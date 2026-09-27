# M31-W03 고정 NCS LE Audio 샘플의 NU54DK native 빌드

고정 NCS nrf `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`에서 upstream Audio 샘플을
`nrf54l15dk/nrf54l15/cpuapp/nu54dk`로 개별 빌드했다. `16/16` target image가 생성되었다.

| 기능 범위 | native sample | 결과 |
| --- | --- | --- |
| BAP unicast | client, server | 2/2 PASS |
| BAP broadcast·BASS | source, sink, assistant | 3/3 PASS |
| CAP | initiator, acceptor | 2/2 PASS |
| PBP | public broadcast source, sink | 2/2 PASS |
| CCP/TBS | call control client, server | 2/2 PASS |
| TMAP | central, peripheral, BMR, BMS | 4/4 PASS |
| HAP | hearing aid | 1/1 PASS |

[빌드 manifest](evidence/m31-w03-native-ncs340/audio-native-build-manifest.json)에
각 sample source, image SHA-256, FLASH/RAM 사용량, log SHA-256과 warning 수를 기록했다.
같은 directory에 `sample-name.build.log.gz`와 `sample-name.hex.gz` 32개 원본을 보존했고,
압축 해제 후 SHA-256이 manifest의 16개 log·image 값과 모두 일치함을 확인했다.

이는 upstream **native target 빌드 적용성**만 증명한다. Arduino API·설치 예제·실제
profile 제어, 오디오 payload 송수신, negative와 상대 보드 HIL은 별도 단계다.
CAP Commander, CSIP, VCP/VOCS/AICS/MICP, MCP/MCS, GMAP, HAS client처럼 이 16개
upstream sample에 없는 역할은 source/test/header 조사와 별도 구현이 필요하다.
따라서 이 결과로 W03나 해당 Audio group 전체를 PASS로 승격하지 않는다.
