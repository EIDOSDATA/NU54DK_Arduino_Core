# M31-W03 Arduino Media·Call Control 완료

고정 NCS v3.4.0과 NU54DK 두 보드에서 공개
[`MediaControlPlayer`](../../libraries/NUCODE_BLE_Audio/examples/MediaControlPlayer/MediaControlPlayer.ino),
[`MediaControlClient`](../../libraries/NUCODE_BLE_Audio/examples/MediaControlClient/MediaControlClient.ino),
[`CallControlServer`](../../libraries/NUCODE_BLE_Audio/examples/CallControlServer/CallControlServer.ino),
[`CallControlClient`](../../libraries/NUCODE_BLE_Audio/examples/CallControlClient/CallControlClient.ino)를
실행했다. Media Control Service와 Call Control Profile의 공개 명령, 상태 통지,
negative 거부, 복구와 재연결을 실제 두 보드에서 확인했다. 공개 `.ino`는 사용자가
읽고 수정할 수 있는 NUCODE C++ API만 사용하며 Zephyr 직접 호출이나 개발 milestone
표식을 포함하지 않는다.

## exact source·image·고정 lock

HIL 실행 source와 실제 flash image revision을 분리해 보존했다.

| profile | clean HIL source | image Core | aggregate build manifest | 최종 결과 |
| --- | --- | --- | --- | --- |
| media | `dc312cce5d56bf50a5acc0ed3e7788b8ada804c6` | `424e263e7a984c5260d6d93109d5785377f6af80` | [`aa546700…`](evidence/m31-w03-media-call-dc312cce/build-provenance/media-424e263e/build-manifest.json) | [`media-final5.json`](evidence/m31-w03-media-call-dc312cce/results/media-final5.json) |
| call | `56612730d0518f0d75ffab2a2a81a74ba589ce97` | `8a07ca4f065db73d3581644212ad118884c61c51` | [`2cabf56f…`](evidence/m31-w03-media-call-dc312cce/build-provenance/call-8a07ca4f/build-manifest.json) | [`call-final2.json`](evidence/m31-w03-media-call-dc312cce/results/call-final2.json) |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을
고정했다. 각 aggregate manifest와 인접 `*.nu54-build.json`, final `.config`,
gzip build log의 크기와 SHA-256은
[`manifest.json`](evidence/m31-w03-media-call-dc312cce/manifest.json)에 묶었다.

| 역할 | target VCOM | image SHA-256 | config SHA-256 |
| --- | --- | --- | --- |
| media player | COM13 | `fe8b237fa4346037a5efef4ffd006b61178984777986f0098c4037234e30a74b` | `85711b5c4b3aa5452dfc27966182c7c1c9b20bf8ee9ff473df07c0b5b9ac2123` |
| media client | COM14 | `e12eda220c0b0a20de29db1a8e504f63ae61292f3cfba227a20415b5264092e8` | `a39282e48c3e20b0e49b3987312b652dfe544eba8871b6a6d4dd2b5ad88e0696` |
| call server | COM13 | `f4d8c8b90783f3d76eb702a47a743e22e389e0e7f0f7f91baf5c9cc0e5eda68f` | `1ddfeee51455f701256049101b1eafe5f67453078b17a2ba8cc3957000a04689` |
| call client | COM14 | `817d4eab146199501a1774278dab70d0025979c5b9289f97599096264f7a3ff0` | `1cb03bdea4824fe1027c68732121cf7a947ce5f0a399095396a9d4427b3d6a17` |

CMSIS-DAP V2는 원문 UID를 기록하지 않고 SHA-256 identity로 선택했다. 두 target에서
DP IDCODE `0x6ba02477`, observed TARGETID `0xf0000f40`, AHB-AP IDR
`0x84770001`, CTRL-AP IDR `0x32880000`, APPROTECT `0x00000000`을 읽어
동일 target과 접근 상태를 재확인했다.

## Media·Call 결과

| profile | 정상 동작 | negative | recovery | reconnect | 상태 통지 | soak |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| media | 100/100 | unsupported opcode 20/20, stale object 20/20 거부 | 40/40 | 20/20 | 30 | 180.000초 |
| call | 100/100 | stale index 20/20, invalid transition 20/20 거부 | 40/40 | 20/20 | 160 | 180.015초 |

media 정상 분모는 play 15, pause 15, seek 14, next 14, previous 14,
select 14, refresh 14다. call 정상 분모는 incoming 12, originate 10,
accept 12, hold 22, retrieve 22, terminate 22다. media client는 현재 연결에서
실제로 관찰한 48-bit track object만 선택하도록 fail-closed 처리해, 고정 NCS의
존재하지 않는 object write 성공 경계를 공개 API 앞에서 차단했다. 최종 transcript
SHA-256은 media `f0ef3465288633830caa938ee4bdd7c50ef8ab1eebb772daaec4a24ebd7fd61f`,
call `fd15f7f193b473c89f9cf97c01d9789ea73cdef4f6eaaed3bf2eea2a325ddb1b`다.

## 진단 이력과 판정

최종 PASS 전에 발생한 실패는
[`diagnostic-history`](evidence/m31-w03-media-call-dc312cce/diagnostic-history)에
원본 JSON과 transcript로 분리했다.

- media final2는 DP/AP register 조회 실패로 실행을 시작하지 못했다.
- media final3은 고정 NCS MPL이 존재하지 않는 track object write를 성공 처리해
  stale object 요청이 승인됐다.
- media final4는 firmware negative 동작이 아니라 runner의 opcode submission
  boundary 판정 불일치로 실패했다.
- 앞선 call-final 두 건은 각각 정상 originate 거부와 stale-index recovery UART
  timeout으로 실패했다.

이 실패들은 원인 진단과 수정 근거로만 보존하며 최종 PASS 분모에 합산하지 않았다.
수정 뒤 media와 call의 전체 정상·negative·recovery·reconnect campaign을 각각
처음부터 다시 실행한 결과만 PASS로 판정했다.

M31-AUDIO-01 `W03-09`의 MCS player/controller와 CCP server/client 공개 역할,
상태·명령 통지, object/index/state negative fail-closed, 180초 soak와 20회 재연결을
만족해 **PASS**로 판정한다. 이 결과는 NU54DK 두 보드와 합성 media/call 상태 범위이며
상용 전화기·media player 상호운용, 물리 음질, Bluetooth qualification을 주장하지
않는다. 이 문서는 W03-09만 닫으며 M31-W03과 M31 전체 분자 승격은 별도 종료 audit이
소유한다. W02 설치본 ISO 11예제·11역할 증거는 변경하지 않았고 CI/CD는 조회하지
않았다.
