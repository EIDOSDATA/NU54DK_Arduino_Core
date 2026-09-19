# M31-W03 Arduino Audio Control 완료

clean Core `119c3bd7a2a87b9c0827691ee2092793d531a788`에서 공개
[`AudioControlController`](../../libraries/NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino)와
[`AudioControlDevice`](../../libraries/NUCODE_BLE_Audio/examples/AudioControlDevice/AudioControlDevice.ino)를
다시 빌드·flash하고 VCP/VOCS/AICS와 MICP 제어, 잘못된 범위 거부, peer loss 복구를
실제 두 보드에서 확인했다. 공개 `.ino`는 사용자가 읽고 수정할 수 있는 NUCODE C++ API만
사용하며 Zephyr 직접 호출이나 개발 milestone 표식을 포함하지 않는다.

## exact source와 보드

| 역할 | 보드 / target COM | FLASH | RAM | HEX SHA-256 |
| --- | --- | ---: | ---: | --- |
| controller | G / COM10 | 415,500 B (27%) | 211,730 B (80%) | `493d00967cfca12e47be78abce3bb22f82b1a3dadefe8f254c6df4cc81381ae4` |
| renderer + microphone device | F / COM14 | 402,284 B (26%) | 212,797 B (81%) | `42b9175e1947530a3a507314de6e4a87af5538a4f3f0fad723a6ad4e9fdc1d74` |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC의 CMSIS-DAP V2는 원문 UID를 기록하지 않고 SHA-256 identity로 선택했으며 G/F의
target/aux COM은 각각 10/11과 14/15로 다시 확인했다. exact source, image, runner와 mapping은
[manifest](evidence/m31-w03-control-119c3bd7/manifest.json)에 묶었다.

## 기능·범위 negative

[functional 결과](evidence/m31-w03-control-119c3bd7/w08-control-119c3bd7-functional-v3.json)는
118.204초 동안 1,951 event와 control report 276건을 보존한다. volume, mute, VOCS offset,
VCP AICS gain, microphone mute, MICP AICS gain의 write 8회와 비동기 read 5회, 장치에서 시작한
notification 5종을 왕복 확인했다. 이어 volume은 255에서 포화되고 offset 256, VCP input 101,
MICP input 101은 `invalid_argument`로 거부되며 양쪽 상태가 바뀌지 않았다. 정상 report 273건,
invalid 거부 3건, state mismatch 0으로 100-operation 분모를 넘겼다. 원문 event는
[transcript](evidence/m31-w03-control-119c3bd7/w08-control-119c3bd7-functional-v3.transcript.log)에
있다.

## hardware-reset peer loss 20회

Device F에만 probe hardware reset을 주입해 controller disconnect, device ready/advertising,
재검색·재연결, VCP와 MICP discovery가 같은 cycle에서 순서대로 복구되는지 20회 확인했다.
[recovery 결과](evidence/m31-w03-control-119c3bd7/w08-control-119c3bd7-recovery-v4.json)는
20/20 PASS, 각 cycle 6.950~23.517초로 30초 이내, 전체 campaign 178.128초, state mismatch 0이다.
[recovery transcript](evidence/m31-w03-control-119c3bd7/w08-control-119c3bd7-recovery-v4.transcript.log)는
reset 직전 경계 이후의 disconnect와 새 discovery만 각 cycle의 근거로 사용한다.

기능 100-operation과 복구 20-cycle은 같은 exact revision/image에 묶인 서로 독립적인
180초 이하 campaign이다. runner는 완성 line을 drain하고 partial line을 fail-closed 처리해
이전 report가 새 명령이나 다음 cycle을 통과시키지 못한다. JSON과 transcript event 수도 각각
1,951/1,951 및 439/439로 일치하며 raw address나 긴 장치 식별자는 없다. 독립 최종 리뷰에서도
P0/P1/P2가 없었다.

## 판정과 경계

M31-AUDIO-01 `W03-08`의 controller/renderer/microphone 역할, control 100회 이상,
invalid argument 수용 0, peer loss 복구 20/20와 각 30초 이내를 만족해 PASS로 판정한다.
이는 합성 상태와 BLE control path의 개발 검증이며 실제 speaker/microphone 음향 성능,
상용 peer 상호운용, Bluetooth qualification을 주장하지 않는다. M31-W03 전체는 W03-06·07과
W03-09~11이 남아 진행 중이고 M31 완료 분자는 2/8 그대로다. W02 설치본 ISO 11예제·11역할
증거는 변경하지 않았으며 CI/CD는 조회하지 않았다.
