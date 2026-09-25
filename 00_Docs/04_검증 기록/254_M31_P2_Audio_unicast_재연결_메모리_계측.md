# 254 — M31 P2 Audio unicast source 재시작·sink 재연결 메모리 계측

## 판정

고정 NCS `v3.4.0`의 두 exact NU54DK에서 현재 저장소의 `adaptive`
LC3/CIS source와 기존 sink image를 실행했다. source만 SWD reset하고 sink는
계속 실행해 공개 scan/connect 경로의 재연결, 누적 복호화, 역할별 메모리
고점을 확인했다. probe UID·app/aux COM·HEX를 실행 전에 대조했고 세 번째
보드는 건드리지 않았다. 자동 unlock·mass erase 없이 source image만 sector
flash했다. 실행기는 reset-halt-drain-resume과 양측 STOP을 요구한다.

| 실행 | 결과 | 원본 |
| --- | --- | --- |
| 기존 시험 image | **FAIL 보존**. source 재시작 후 `P2_AUDIO_FAIL scan-restart`, 양측 STOP. | [최초 실패](evidence/m31-p2-native-comparison-2cf92933/audio-unicast-reset-initial-fail-01.json) |
| 실행 중 scan guard만 추가 | **FAIL 보존**. 같은 `scan-restart`, 양측 STOP. 이미 실행 중인 scan 중복 요청만이 원인은 아니었다. | [guard-only 실패](evidence/m31-p2-native-comparison-2cf92933/audio-unicast-reset-guard-only-fail-02.json) |
| legacy scan으로 바꾼 시험 image, 1회 | **국소 PASS**. source SWD reset 1/1, sink 누적 decode 243·drop 0, 양측 STOP. 작업용 원본은 `C:\r31k\p2_audio_unicast_peer-reset-legacy-1.json`에 남겼다. | 아래 image와 실행기 참조 |
| 같은 image, source SWD reset 20회 | **국소 PASS**. 재연결 20/20, 최초 시작 포함 21개 source 수명 각각 100-frame 송신을 확인하고 sink 누적 LC3 decode 2,933·drop 0, 100-frame milestone 연속·PCM energy 양수, 양측 STOP. | [20회 UART·메모리·image/probe hash](evidence/m31-p2-native-comparison-2cf92933/audio-unicast-source-reset-memory-20.json) |

최종 `.config`의 source 역할에는 `CONFIG_BT_EXT_ADV`가 없다. 기존 시험
sketch와 공개 `BapUnicastSource` 예제는 최초 연결에 `BLEScan.start(true)`를
사용하면서 재연결에는 `BLEScan.startExtended(true, false, false)`를
호출했다. EXT_ADV가 없는 adaptive image에서 이 호출은 지원되지 않는다.
두 sketch의 재연결도 최초 연결과 같은 `BLEScan.start(true)`로 맞추고,
이미 scan 중이면 중복 시작하지 않도록 했다. 공개 예제와 시험 sketch는
각각 adaptive 빌드를 통과했다. 이 변경을 다른 GAP 조합 전체의 실기
PASS로 확대하지 않는다.

같은 패턴의 공개 `BapUnicastCycle`, `BapUnicastDuplexClient`,
`CapUnicastInitiator`, `ExternalI2sSpeakerSink`도 일반 scan 재시작으로
맞췄다. 앞의 세 예제는 각각 adaptive 빌드를 통과했다. 정적 FLASH/RAM은
Cycle `331,800/70,797 B`, DuplexClient `347,172/73,937 B`, CAP
Initiator `339,752/71,059 B`다. 외장 I2S 예제는
`nucode-build.json` 선언과 실물 외장 장치가 없어 정적 회귀까지만 다루며,
이 기록의 HIL PASS에 포함하지 않는다.

최종 시험 source HEX SHA-256은
`1fcd6f8cb37539c1edf6ce62db889ad31a7630d5a1507c0432180fd7e030981d`,
sink는 기존 241번의
`25d8576233257bdaa74113ffc7065ad034360ff6812746f13eb1c0422a253a5e`다.
정적 FLASH/RAM은 시험 source `334,020/71,403 B`, sink
`288,628/67,338 B`다. 공개 source 예제의 수정 후 adaptive 빌드는
`331,648/70,793 B`였으며 이 공개 예제 image 자체를 flash한 결과는 아니다.
원본 실패 두 건과 최종 PASS는 서로 다른 source HEX이므로 이전 실패를
소급 삭제하지 않는다.

## 재연결 중 관찰한 high-water

다음 값은 20회 실행의 `used/reserved` byte다. source는 매회 reset하므로
**한 source 수명 중**의 최고치이고, sink는 20회 재연결을 지속한
**한 수명 중**의 최고치다. 서로 다른 수명의 사용량을 더하지 않는다.

| Thread/ISR | source | sink |
| --- | ---: | ---: |
| BT RX WQ | 1,520/3,200 | 1,536/3,200 |
| BT TX processor | 704/3,200 | 404/3,200 |
| BT LW WQ | 936/2,104 | 1,180/2,104 |
| sysworkq | 288/4,096 | 432/4,096 |
| MPSL Work | 356/1,024 | 712/1,024 |
| main | 3,192/8,192 | 2,976/8,192 |
| ISR0 | 504/2,048 | 504/2,048 |

같은 sink HEX의 [241번 정상·장기 부하](241_M31_메모리_최적화_P2_Audio_unicast_실기_계측.md)는
BT RX WQ 최대 `1,248/3,200 B`였지만 이번 재연결 부하는
`1,536/3,200 B`로 288 B 더 높았다. 정상 송수신 고점만으로 복구
수명주기의 stack 예약을 줄일 수 없다는 직접 근거다.

양쪽 libc malloc의 관찰 peak는 0 B, STOP 때 `allocated=0`,
`free=8108`이다. source는 시작·20회 reset·STOP에 걸쳐 22건,
sink는 시작·STOP 2건의 libc 계측을 남겼다. 실행기는 source 수명 수에
맞는 계측 건수도 검사한다.
정적 `sdc_mempool`은 controller 내부 high-water가 아니다. 실물 전원
차단이 아닌 **SWD reset**이며 한 방향·단일 CIS만 다뤘다. 다중 ASE,
반대 방향, 암호화 오류와 장기 RF 간섭·전체 최악 부하는 별도다. 따라서
이 결과로 stack/heap/controller pool을 줄이거나 **P2 전체를 완료**하지
않는다.

## 로컬 회귀와 문서 판정

수정한 시험 sketch와 공개 `BapUnicastSource`, `BapUnicastCycle`,
`BapUnicastDuplexClient`, `CapUnicastInitiator`의 adaptive 빌드가
각각 통과했다. 공개 예제 구조 감사는 library 16개·예제 113개·문제 0건,
Markdown UTF-8/로컬 링크 검사는 410개 PASS였다. 새 scan 정적 회귀
3건을 포함한 전체 Host 단독 실행은 **1,495건, skip 2, 오류 0**으로
통과했다. 앞서 Arduino 빌드 세 건과 병렬로 돌린 전체 Host 시도에서는
GATT·Security C++ 컴파일 두 건이 각각 60초 제한으로 시간초과했다.
빌드를 마친 뒤 두 항목 단독 재실행 및 위 전체 단독 재실행이 통과했으므로
그 시간초과를 firmware 결함이나 첫 실행 PASS로 바꾸지 않는다.
