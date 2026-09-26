# M31-W03 Arduino TMAP·GMAP 완료

고정 NCS v3.4.0과 NU54DK 두 보드에서 공개 Arduino TMAP·GMAP 8개 역할을
순차적으로 배치해 unicast·broadcast 네 scenario를 검증했다. 공개 `.ino`는
사용자가 읽고 수정할 수 있는 NUCODE C++ API 흐름만 사용하며 Zephyr 직접 호출이나
개발 milestone 표식을 포함하지 않는다.

TMAP은 [`TelephonyMediaGateway`](../../libraries/NUCODE_BLE_Audio/examples/TelephonyMediaGateway/TelephonyMediaGateway.ino),
[`TelephonyMediaTerminal`](../../libraries/NUCODE_BLE_Audio/examples/TelephonyMediaTerminal/TelephonyMediaTerminal.ino),
[`TelephonyMediaBroadcaster`](../../libraries/NUCODE_BLE_Audio/examples/TelephonyMediaBroadcaster/TelephonyMediaBroadcaster.ino),
[`TelephonyMediaReceiver`](../../libraries/NUCODE_BLE_Audio/examples/TelephonyMediaReceiver/TelephonyMediaReceiver.ino),
GMAP은 [`GamingAudioGateway`](../../libraries/NUCODE_BLE_Audio/examples/GamingAudioGateway/GamingAudioGateway.ino),
[`GamingAudioTerminal`](../../libraries/NUCODE_BLE_Audio/examples/GamingAudioTerminal/GamingAudioTerminal.ino),
[`GamingAudioBroadcaster`](../../libraries/NUCODE_BLE_Audio/examples/GamingAudioBroadcaster/GamingAudioBroadcaster.ino),
[`GamingAudioReceiver`](../../libraries/NUCODE_BLE_Audio/examples/GamingAudioReceiver/GamingAudioReceiver.ino)를 실행했다.

## exact source·image·고정 lock

HIL 실행 source와 실제 flash image revision을 섞지 않고 따로 보존했다.

| scenario | clean HIL source | image Core | 원본 결과 |
| --- | --- | --- | --- |
| TMAP unicast | `c24cb42e9dfdec6bb3adf9e79660fc00daf855fb` | `960ec93dec59a2ab661f83aefc739c95297fa576` | [`tmap-unicast.json`](evidence/m31-w03-tmap-gmap-ae73a1f1/results/tmap-unicast.json) |
| TMAP broadcast | `2f257b163615c2455385e7a01de2c6f5c5abc502` | `6d51a259988f25f656806b8a627a3bf990e37c49` | [`tmap-broadcast.json`](evidence/m31-w03-tmap-gmap-ae73a1f1/results/tmap-broadcast.json) |
| GMAP unicast | `ae73a1f16a7070b14fec0f7b8ad7fe902cef4bd0` | `db56af1c0cd5257cef366ec93b010f7119cf2c11` | [`gmap-unicast.json`](evidence/m31-w03-tmap-gmap-ae73a1f1/results/gmap-unicast.json) |
| GMAP broadcast | `ae73a1f16a7070b14fec0f7b8ad7fe902cef4bd0` | `db56af1c0cd5257cef366ec93b010f7119cf2c11` | [`gmap-broadcast.json`](evidence/m31-w03-tmap-gmap-ae73a1f1/results/gmap-broadcast.json) |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`, SDK lock
SHA-256 `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3`을
고정했다. source와 sink의 CMSIS-DAP V2 identity는 원문 UID 대신 SHA-256으로
보존했고 target VCOM을 각각 COM10과 COM14로 다시 대조했다.

## 네 scenario 결과

| scenario | 180초 stream | stop/restart | disconnect/reconnect | negative |
| --- | --- | --- | --- | --- |
| TMAP unicast | source 20,000, decode 20,000, drop 0 | 20/20 | 20/20 | role·quality PASS, feature N/A |
| TMAP broadcast | source 22,700, decode 19,500, drop 0 | 20/20 | broadcast N/A | role·quality PASS, feature N/A |
| GMAP unicast | source 19,900, decode 19,900, drop 0 | 20/20 | 20/20 | role·quality·feature PASS |
| GMAP broadcast | source 22,900, decode 19,500, drop 0 | 20/20 | broadcast N/A | role·quality·feature PASS |

모든 scenario에서 role bit, TMAS/GMAS service discovery, stream start·send·read·stop을
같은 원본 transcript와 결과 JSON으로 결합했다. broadcast는 connection-oriented
reconnect 분모에 넣지 않고 stop/restart와 재동기화 경로로 판정했다.

TMAP unicast HIL은 exact `960ec93d…` build record에 묶여 있다. 후속 clean
`6d51a259…` 재빌드가 gateway·terminal에서 같은 HEX SHA-256을 내어 인접 build
log도 보존했지만, image revision을 후속 revision으로 바꿔 기록하지 않았다.
GMAP은 `db56af1c…` exact build manifest·record·log를 사용했다. 모든 파일과
gzip 압축 전 build log의 크기·SHA-256은
[`manifest.json`](evidence/m31-w03-tmap-gmap-ae73a1f1/manifest.json)에 묶었다.

## 판정 경계

M31-AUDIO-01 `W03-10` TMAP CG/CT/UMS/UMR/BMS/BMR과 GMAP UGG/UGT/BGS/BGR의
적용 공개 역할, LC3 실제 RF data path, negative와 복구를 모두 만족해 **PASS**로
판정한다. 이 결과는 합성 PCM과 NU54DK 고정 stack 범위이며 상용 전화기·게임
제품 상호운용, 물리 음질, Bluetooth qualification을 주장하지 않는다. 이 문서는
W03-10만 닫으며 M31-W03과 M31 전체 분자 승격은 별도 종료 audit이 소유한다.
W02 설치본 ISO 11예제·11역할 증거는 변경하지 않았고 CI/CD는 조회하지 않았다.
