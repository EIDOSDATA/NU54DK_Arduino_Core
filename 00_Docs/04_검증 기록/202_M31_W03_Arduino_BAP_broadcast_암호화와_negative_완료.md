# M31-W03 Arduino BAP broadcast 암호화와 negative 완료

clean Core `473929f20d6c71503ae460c933d413268ec35222`에서 공개
[`BapBroadcastSource`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino)와
[`BapBroadcastSink`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSink/BapBroadcastSink.ino)를
다시 빌드·flash했다. 사용자는 `.ino`의 16-byte `BroadcastCode`를 읽고 바꾸며
`begin(name, code)`로 암호화 방송을 시작한다. BAP/ISO와 Zephyr 호출은 공개 예제에
없고 library backend에만 있다.

## exact source와 flash

| 항목 | source | sink |
| --- | ---: | ---: |
| Arduino 표시 FLASH | 496,832 B (33%) | 479,180 B (32%) |
| RAM | 222,759 B (84%) | 225,156 B (85%) |
| programmed bytes | 499,712 B | 479,232 B |
| HEX SHA-256 | `f67962c2f56d8e2745dea279e447b8cb4dcdb7f3ec9b4b7da0b1bdf034a2c60c` | `08c2cbca980e83e17bfec3955deadac2baee6a8a7b548d10d0742d23a64341c7` |

[source build](evidence/m31-w03-bap-broadcast-473929f2/source-build.json)와
[sink build](evidence/m31-w03-bap-broadcast-473929f2/sink-build.json)은 Core,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, nRF
`99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, toolchain `dcbdc366a1`을 고정한다.
CMSIS-DAP V2는 원문 UID 없이 SHA-256 identity로 선택했고, 두 역할 모두 sector
flash 뒤 별도 hardware reset을 통과했다. 세부 값은
[flash 증거](evidence/m31-w03-bap-broadcast-473929f2/flash.json)에 있다.

## 암호화 positive와 수명주기

동일 Broadcast Code로 source가 LC3 frame 2,000개 이상을 전송하고 sink가 1,800개
이상을 복호화했다. PCM energy는 양수이고 drop은 0이다. 그 뒤 공개 `end()`와
암호화 `begin(name, code)`로 양쪽을 정지·재시작한 20/20회 모두 sink가 LC3
100 frame을 복호화했다. 합계 2,000 frame, nonzero energy 20/20, drop 0이다.

## wrong code와 sync loss

sink 예제의 `w` 명령은 첫 byte가 다른 code로 재동기화한다. controller는 20/20회
HCI MIC Failure `0x3d`를 `-61`로 보고했고 잘못된 code에서 유효 frame은 0이다.
매 회 정상 code로 다시 시작해 LC3 100 frame, 양수 energy, drop 0을 확인했다.

예기치 않은 손실은 source probe만 hardware reset해 주입했다. sink는 BIG stop의
HCI Connection Timeout `-8`을 15회, periodic sync callback의 `-ECONNRESET(-104)`을
5회 먼저 관찰했다. 이는 같은 reset에서 callback 선착 순서가 달라진 것이며 두 값
외에는 수락하지 않았다. 20/20회 source 자동 부팅과 sink 정리·재검색 뒤 LC3
100 frame을 다시 받았다. 복구 시간은 3.422~3.783초로 30초 한도 이내이고 drop은 0이다.

[구조화 결과](evidence/m31-w03-bap-broadcast-473929f2/broadcast-encrypted-exact.json),
[원본 transcript](evidence/m31-w03-bap-broadcast-473929f2/broadcast-encrypted-exact.transcript.log),
[진단 audit](evidence/m31-w03-bap-broadcast-473929f2/diagnostic-audit.json),
[manifest](evidence/m31-w03-bap-broadcast-473929f2/manifest.json)에 수치와 hash를 연결했다.
source의 정상 `end()`는 sink 오류가 아니므로 sync-loss 분자에서 제외했고, 새 boot
marker 앞의 Serial 잔류 줄도 제외했다.

## 판정

W03-03 BAP broadcast의 source/sink, 실제 암호화 LC3 payload, stop/restart,
wrong Broadcast Code, 강제 sync loss와 rejoin을 완료해 `functional_hil=PASS`로
판정한다. W03-04 BASS부터 W03-11까지와 M31-W03 전체는 계속 진행 중이다.
CI/CD는 조회하지 않았다.
