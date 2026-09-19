# M31-W03 Arduino BAP broadcast 비암호화와 재가입

clean Core `6e22c2d26828a614fc4ca88746d140abe71cbb9f`에서 공개
[`BapBroadcastSource`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino)와
[`BapBroadcastSink`](../../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSink/BapBroadcastSink.ino)를
NU54DK Zephyr / BLE로 각각 빌드했다. `.ino`는 일반 C++과
`NUCODE_BLE_Audio`의 `BroadcastSource`, `BroadcastSink`, `Lc3Codec`만 사용한다.
광고·PACS·BASS·BIG/BIS와 Zephyr 호출은 library `.cpp`에만 있다.

## source와 조건

| 항목 | source | sink |
| --- | ---: | ---: |
| Arduino 표시 FLASH | 496,740 B (33%) | 478,992 B (32%) |
| RAM | 222,759 B (84%) | 225,140 B (85%) |
| HEX SHA-256 | `b0fd65a131181301737107c9f43696a0480348ae30f35ef8e59d0990e3ad33ee` | `0abdba5a1c3d6df372f64a019407ac1566d0184056087071034f44294d72ac27` |

[source build](evidence/m31-w03-bap-broadcast-6e22c2d2/source-build.json)와
[sink build](evidence/m31-w03-bap-broadcast-6e22c2d2/sink-build.json)은 같은 Core,
board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, nRF
`99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, toolchain `dcbdc366a1`을 기록한다.
CMSIS-DAP V2 원문 UID는 남기지 않고 SHA-256 identity로 source COM10과 sink
COM14를 골랐다. 두 HEX를 sector flash한 뒤 각각 별도 hardware reset했다.
[flash 원본](evidence/m31-w03-bap-broadcast-6e22c2d2/flash.json)에 세 번째 연결
probe가 이번 두 역할에서 사용되지 않았다는 사실도 분리했다.

## 실제 결과

clean boot 뒤 source가 40-byte LC3 frame 2,000개 이상을 송신했고 sink는
1,800개 이상을 수신·복호화했다. 마지막 PCM energy는 972,087이고 queue drop은
0이다. 이어 공개 `end()`와 `begin()`만 사용해 source와 sink를 순서대로
중단·재시작했다. 20/20회 모두 양쪽 streaming 복귀와 sink LC3 100 frame,
양수 PCM energy, drop 0을 확인했다. 합계는 2,000 frame이며 전체 반복 시간은
34.836초다. [구조화 결과](evidence/m31-w03-bap-broadcast-6e22c2d2/broadcast-plain-rejoin.json),
[transcript](evidence/m31-w03-bap-broadcast-6e22c2d2/broadcast-plain-rejoin.transcript.log),
[manifest](evidence/m31-w03-bap-broadcast-6e22c2d2/manifest.json)에 원본과 hash를 연결했다.

초기 sink는 PACS LC3 capability가 없어 BIS sync에서 `-EINVAL`이 발생했다.
PACS capability와 Scan Delegator를 등록한 뒤에는 종료 시 capability 해제가
notification 비활성 구성에서 `-EINVAL`을 반환했다. 이를
`CONFIG_BT_PAC_SNK_NOTIFIABLE=y`로 교정했고, 두 번째 `begin()`에서 고정 SDK가
이미 설정된 supported context에 `-EALREADY`를 반환하는 단계는
`CONFIG_BT_PACS_SUPPORTED_CONTEXT_NOTIFIABLE=y`로 교정했다. 단계별 원본 오류를
`BroadcastSinkStep`으로 분리한 뒤 추측 없이 해당 SDK 구현과 대조했다.

hardware reset 직전 입력 buffer에 남아 있던 이전 session의 `-ECONNRESET` 줄은
새 `broadcast source preparing`과 `broadcast sink scanning`보다 앞선 값이므로
완료 transcript에서 제외했다. 새 boot 이후의 streaming과 frame만 분자에 넣었다.

## 판정과 잔여

이 결과는 W03-03의 **비암호화 BAP broadcast payload와 명시적 stop/restart 재가입
부분 PASS**다. Broadcast Code 암호화 positive, wrong code 거부, 예기치 않은 sync
loss 뒤 rejoin은 아직 실행하지 않았으므로 W03-03 `functional_hil`은 `NOT_RUN`으로
유지한다. W03-04~11과 M31-W03 전체도 계속 진행 중이다. CI/CD는 조회하지 않았다.
