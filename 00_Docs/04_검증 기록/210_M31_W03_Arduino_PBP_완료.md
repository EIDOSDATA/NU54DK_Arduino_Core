# M31-W03 Arduino PBP 완료

clean Core `fcbbfac5fe348c51be0fb4e30f2b8415099b8758`에서 공개
[`PublicAudioBroadcastSource`](../../libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/PublicAudioBroadcastSource.ino)와
[`PublicAudioBroadcastSink`](../../libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/PublicAudioBroadcastSink.ino)를
다시 빌드·flash하고 public announcement·metadata, broadcast discovery·selection,
LC3 수신, stop/restart, wrong code, unsupported quality와 sync loss 복구를 실제
두 보드에서 확인했다. 공개 `.ino`는 사용자가 읽고 수정할 수 있는 NUCODE
C++ API만 사용하며 Zephyr 직접 호출이나 개발 milestone 표식을 포함하지 않는다.

## exact source와 두 보드

| 역할 | 보드 / target COM | FLASH | RAM | HEX SHA-256 |
| --- | --- | ---: | ---: | --- |
| source | G / COM10 | 499,812 B | 223,274 B | `1b5d5adcdf62a5974a9edddcbd8f88f7f658252d5224e22b6b0ca8d5cbbefa1e` |
| sink | F / COM14 | 488,776 B | 225,708 B | `ca5f1db5ded8792cb833d3ac7f0dab351d685607170fc6e966397800a2a560cb` |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC의 CMSIS-DAP V2는 원문 UID를 기록하지 않고 SHA-256 identity로 선택했으며
G/F의 target/aux COM을 각각 10/11과 14/15로 다시 확인했다. source, image,
build, mapping과 실행 원문은 [manifest](evidence/m31-w03-pbp-fcbbfac5/manifest.json)에
묶었다.

## 기능·negative 5/5

[campaign](evidence/m31-w03-pbp-fcbbfac5/campaign.summary.json)의 다섯 mode는 모두 PASS다.

| mode | 판정 근거 |
| --- | --- |
| positive | 180.003초 연속 stream, sink frame 100→17,800으로 17,700 증가, valid report 177건, drop 0 |
| stop/restart | public API 정지·재시작 후 수신 복구 20/20, 최대 3.333초 |
| wrong code | MIC failure `-61`로 20/20 거부, report-level invalid frame 0, 정상 code 복구 20/20, 최대 5.041초 |
| quality | source와 sink의 unsupported quality를 각각 20/20 거부하고 정상 설정으로 20/20 복구, 최대 4.976초 |
| sync loss | source hardware reset으로 loss 20/20 탐지, 재검색·재동기·LC3 수신 20/20 복구, 최대 6.826초 |

wrong-code의 0건은 공개 sketch가 보고한 invalid frame line의 수이며 개별
미보고 controller frame을 관측했다는 의미가 아니다. 모든 recovery는 30초 한도
안이었고 정상 LC3 frame과 양수 PCM energy, drop 0을 다시 확인했다.

## 진단 이력과 판정

앞선 v1~v3 campaign은 positive, stop/restart, wrong-code, quality를 통과한 뒤
sync-loss에서 runner가 reset UART noise를 너무 엄격하게 파싱해 실패했다. 원문
로그에는 device의 preparation·streaming·resync가 있어 firmware 실패로 판정하지
않았다. reset boundary 안에서만 제한적으로 noise token을 허용하고 평상시
출력은 fail-closed로 유지한 runner로 표적 sync-loss 20/20 preflight와 최종
5/5 campaign을 새로 실행했다. v1~v3 실패 요약과 transcript는
`diagnostic-history`에 보존했으며 최종 PASS에 합산하지 않았다.

M31-AUDIO-01 `W03-07`의 source/sink, public announcement·metadata·discovery·selection,
180초 stream, stop/restart·wrong code·unsupported quality·sync loss와 recovery를 만족해
PASS로 판정한다. 이 결과는 PBP 기능 검증이며 **Auracast 명칭 사용 승인,
Bluetooth qualification, 상용 peer 상호운용**을 주장하지 않는다. W03-09~11이
남아 M31-W03 전체는 진행 중이고 M31 완료 분자는 2/8 그대로다. W02 설치본
ISO 11예제·11역할 증거는 변경하지 않았으며 CI/CD는 조회하지 않았다.
