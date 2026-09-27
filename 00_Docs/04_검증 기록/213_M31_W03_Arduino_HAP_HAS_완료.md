# M31-W03 Arduino HAP·HAS 완료

clean Core `56612730d0518f0d75ffab2a2a81a74ba589ce97`에서 exact
`ae73a1f16a7070b14fec0f7b8ad7fe902cef4bd0` image의 공개
[`HearingAccessClient`](../../libraries/NUCODE_BLE_Audio/examples/HearingAccessClient/HearingAccessClient.ino)와
[`HearingAccessServer`](../../libraries/NUCODE_BLE_Audio/examples/HearingAccessServer/HearingAccessServer.ino)를
두 NU54DK에 flash했다. preset 발견·조회·선택·이름/사용 가능 상태 변경,
invalid·synchronized request 거부, 연결 종료 후 재발견·재연결을 공개 Serial API로
검증했다. 공개 `.ino`는 NUCODE C++ API만 사용하며 Zephyr 직접 호출이나 개발
milestone 표식을 포함하지 않는다.

## exact build·board mapping

| 역할 | target VCOM | image SHA-256 | config SHA-256 |
| --- | --- | --- | --- |
| hearing client | COM14 | `138d38a48d493e9853afc5be88049a56ddb96b6a1fd2a7a9a50f03ac530121bf` | `c7abf2fb2775c3bacdfd728d73e3c2f2fee91147298eb9170f874ad8e577cb53` |
| hearing server | COM13 | `53394d749464ba59fc86a794925ce8ee0bbfac2789b57204d8fe94db9121597a` | `91965c0f3af5703d2ec8ef9c554e1ae6969f16044f8947f770ddfdbadcbde095` |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC의 CMSIS-DAP V2는 원문 UID를 기록하지 않고 client/server probe SHA-256
`4574ee31…` / `32f71533…`로 선택했다. 양쪽에서 DP IDCODE
`0x6ba02477`, observed TARGETID `0xf0000f40`, AHB-AP IDR `0x84770001`,
CTRL-AP IDR `0x32880000`, APPROTECT `0x00000000`을 읽어 동일 target·접근 상태를
재확인했다.

exact build manifest·record·gzip log, PASS 원본과 진단 이력의 크기·SHA-256은
[`manifest.json`](evidence/m31-w03-hap-56612730/manifest.json)에 묶었다. 실제 실행 원본은
[`hap-final.json`](evidence/m31-w03-hap-56612730/results/hap-final.json)이다.

## 기능·negative·복구

| 항목 | 결과 |
| --- | --- |
| preset operation | 100/100 |
| invalid preset index 거부 | 20/20 |
| synchronized preset request 거부 | 20/20 |
| disconnect/reconnect·rediscovery | 20/20 |
| recovery 시간 | 6.187~10.079초, 30초 한도 이내 |
| client/server settings 초기화 | offset `0x174000`, 36,864 byte `0xff`, readback 양쪽 PASS |

첫 실행은 normal operation 100건과 invalid index 20건을 통과한 뒤 synchronized preset
rejection의 두 번째 반복을 기다리며 timeout으로 중단됐다. 이 결과를
[`hap-first-attempt-fail.json`](evidence/m31-w03-hap-56612730/diagnostic-history/hap-first-attempt-fail.json)로
보존했고 최종 PASS 분모에 합산하지 않았다. 연결 회복 상태를 안정적으로
대기하도록 고친 clean source에서 같은 image와 양쪽 settings 초기화 후 전체를
다시 실행해 100/100·20/20·20/20·20/20을 모두 통과했다.

## 판정 경계

M31-AUDIO-01 `W03-11` HAP/HAS client/server의 합성 preset, active index·name·availability,
invalid·synchronized request fail-closed와 peer reconnect를 만족해 **PASS**로 판정한다.
이 결과는 실제 보청기 상호운용, 의료 성능, 음향·음질, Bluetooth qualification을
주장하지 않는다. 이 문서는 W03-11만 닫으며 M31-W03과 M31 전체 분자 승격은
별도 종료 audit이 소유한다. W02 설치본 ISO 11예제·11역할 증거는 변경하지
않았고 CI/CD는 조회하지 않았다.
