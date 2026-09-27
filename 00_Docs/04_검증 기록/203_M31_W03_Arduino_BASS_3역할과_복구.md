# M31-W03 Arduino BASS 3역할과 복구 완료

clean Core `a318c7ba9b5fa84d586c35fadab88c1675163100`에서 공개
[`BapBroadcastSource`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino),
[`BapBroadcastAssistant`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastAssistant/BapBroadcastAssistant.ino),
[`BapBroadcastDelegatorSink`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastDelegatorSink/BapBroadcastDelegatorSink.ino)을
다시 빌드·flash했다. `.ino`는 사용자가 읽고 바꿀 수 있는 NUCODE C++ API로 검색, 보안 연결,
source add/modify/remove, Broadcast Code, receive-state notification과 LC3 decode를 수행한다.
Zephyr 직접 호출과 개발 milestone 표식은 공개 예제에 없다.

## exact source와 3보드 mapping

| 역할 | FLASH | RAM | HEX SHA-256 | programmed bytes |
| --- | ---: | ---: | --- | ---: |
| source | 496,872 B (33%) | 222,759 B (84%) | `911f87c9b67d4a753017f12790c5760d94bff143041f47e3d8c88d62dee82beb` | 499,712 B |
| assistant | 413,892 B (27%) | 218,799 B (83%) | `6c34e962898aa22dfdb41010ebc59cfa3ed3052d15d729c02162578594fc7827` | 417,792 B |
| scan delegator sink | 500,600 B (33%) | 229,716 B (87%) | `b4a0e5852697e7355fff238f89b73cf4a251f18881a9a36364010b977c34b1d7` | 503,808 B |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC의 세 CMSIS-DAP V2는 원문 UID를 남기지 않고 SHA-256 identity로 선택했으며 target/aux
COM은 source 10/11, assistant 13/12, delegator 14/15로 다시 확인했다. 세 image 모두 sector
flash 뒤 별도 hardware reset을 통과했다. [build와 flash 원장](evidence/m31-w03-bass-a318c7ba/manifest.json)에
revision과 image hash를 연결했다.

## BASS control과 negative

Assistant가 broadcast source를 찾아 Delegator에 add하고 Broadcast Code를 전달한 뒤
PA/BIS와 LC3 stream을 시작했다. 공개 API로 stop, remove, re-add, code, 복구 frame의 다섯
유효 동작을 20회 실행해 **100/100**을 완료했다. 각 회차 receive state는 제거 시
`source=255 pa=0 bis=0`, 복구 시 `pa=1 bis=1`이었고 state mismatch와 drop은 0이다.

빈 scan result를 사용한 invalid source와 이미 등록된 source의 duplicate add는 각각
20/20 거부됐다. Assistant의 비동기 GATT 완료에서 duplicate가 ATT application error 252로
완료되는 것까지 기다렸으므로 동기 함수의 시작 성공을 잘못된 수락으로 세지 않았다.
[구조화 결과](evidence/m31-w03-bass-a318c7ba/bass-exact.json)와
[control transcript](evidence/m31-w03-bass-a318c7ba/bass-exact.transcript.log)에 분모를 보존했다.

## peer loss와 180초 stream

Delegator probe만 hardware reset하는 peer loss를 20회 주입했다. 매 회 Assistant disconnect,
Delegator ready, 재검색, 새 receive state의 `pa=1 bis=1`, streaming과 `dropped=0` frame이
30초 timeout 안에 모두 돌아와 **20/20** 통과했다. reset identity와 결과는
[peer-loss transcript](evidence/m31-w03-bass-a318c7ba/peer-loss-exact.transcript.log)에 있다.

마지막 복구 뒤 180초 연속 캡처에서 source는 65,300에서 83,000으로 17,700 frame,
Delegator는 3,300에서 20,800으로 17,500 frame 증가했다. PCM energy 관측 176개가 모두
양수이고 drop은 0이며 Assistant disconnect/error 출력은 0줄이다.
[soak transcript](evidence/m31-w03-bass-a318c7ba/soak-exact.transcript.log)에 시작·종료값을 고정했다.

## 진단과 수정 경계

고정 SDK의 수동 receive-state read는 이전 GATT write offset이 read parameter union에 남아
ATT 0x07을 만들고, 제거된 source cache가 re-add를 `-EINVAL`로 막았다. 이 결함을 공개 API로
감추지 않고 수동 read를 제거했으며 표준 notification을 상태 경로로 유지했다.

빠른 반복에서는 PA 종료 callback 전 resource 재사용과 BASS 종료 요청·Arduino poll 사이 경쟁을
분리했다. periodic termination 완료를 기다리고, 수락한 PA/BIS 종료 요청은 즉시 stopping으로
표시하며, HCI reason을 원본 음수 값으로 보존했다. SDK reference와 같은 periodic timeout ratio
20을 사용했다. Assistant ACL에는 공개 `requestParameters()`를 적용했고, peer 소실 시 Delegator는
공개 `end()`/`beginDelegated()`로 상태와 광고를 다시 연다. 개발 실패와 host runner의 Windows
`0xC0000005` 분리는 [진단 audit](evidence/m31-w03-bass-a318c7ba/diagnostic-audit.json)에 남겼고
실패 시도를 exact PASS에 합치지 않았다.

## 판정

M31-AUDIO-01 `W03-04`의 3역할, valid 100/100, invalid source·duplicate 20/20 거부,
peer loss 복구 20/20, 180초 연속 stream을 만족해 W03-04를 PASS로 판정한다. Host M31
52/52와 공개 예제 감사 16 libraries·86 examples·0 issue도 통과했다. M31-W03 전체는
W03-05~11이 남아 **진행 중**이고 M31 전체 완료 분자는 **2/8** 그대로다. W02 설치본
ISO 11예제·11역할 증거는 변경하지 않았으며 CI/CD는 조회하지 않았다.
