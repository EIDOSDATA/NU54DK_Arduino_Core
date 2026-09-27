# M31-W03 Arduino CAP 3역할과 broadcast 복구

clean tracked source `bfe69aec76ccdc19af73d51a27ec385afacd791f`에서 공개
[`CapInitiator`](../../libraries/NUCODE_BLE_Audio/examples/CapInitiator/CapInitiator.ino),
[`CapAcceptor`](../../libraries/NUCODE_BLE_Audio/examples/CapAcceptor/CapAcceptor.ino),
[`CapCommander`](../../libraries/NUCODE_BLE_Audio/examples/CapCommander/CapCommander.ino)를 같은 revision으로
clean build하고 세 보드에 다시 flash했다. `.ino`는 사용자가 읽고 수정할 수 있는 NUCODE C++ API로
CAP 역할 초기화, CAS/BASS discovery, 암호화 broadcast source 선택, 수신 시작·중단·code 배포와
복구를 수행한다. 공개 예제에 Zephyr 직접 호출이나 개발 milestone 표식은 없다.

## 고정 환경과 3보드 mapping

| 역할 | FLASH | RAM | HEX SHA-256 | programmed bytes |
| --- | ---: | ---: | --- | ---: |
| Initiator | 498,088 B (33%) | 223,212 B (85%) | `f65ba38f896d5032aeba5bd2d6f305b5c5171c324f2912584b0a03686e192c3d` | 499,712 B |
| Acceptor | 500,552 B (33%) | 229,724 B (87%) | `84f2ead6e43175ba676add42a9b5c4cc784da052fd95003a4611e89dcdde3748` | 503,808 B |
| Commander | 420,552 B (28%) | 219,889 B (83%) | `aa56a1a88e5d89deb66c18bf3500d78f3350a23f213c54246a829723405da746` | 421,888 B |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC에서 CMSIS-DAP V2 원문 UID를 기록하지 않고 SHA-256 identity로 역할을 다시 선택했다.
target/aux COM은 Initiator 10/11, Acceptor 14/15, Commander 13/12이다. 세 image 모두 sector flash와
별도 hardware reset을 통과했다. revision, 안전한 probe identity, image hash와 역할 연결은
[exact manifest](evidence/m31-w03-cap-bfe69aec/manifest.json)에 있다.

## CAP broadcast control과 negative

Commander가 Acceptor의 CAS/BASS를 발견한 뒤 Initiator의 암호화 broadcast를 선택하고 수신 절차와
Broadcast Code를 배포했다. 공개 API의 stop, restart, code 세 연산을 34회 반복해 **102/102**를
완료했다. 각 회차는 source 제거, 재추가, PA/BIS sync와 실제 LC3 frame까지 확인했다. 회복 시간은
2.022~3.197초, native failure 출력은 0줄이다.

빈 scan result의 invalid source와 streaming 중 duplicate start는 각각 **20/20** 거부됐다.
예기치 않은 수락은 0이고 시험 중 수신 frame은 계속 증가했으며 drop은 0이다.
[control 구조화 결과](evidence/m31-w03-cap-bfe69aec/control-102ops-summary.json)와
[negative 구조화 결과](evidence/m31-w03-cap-bfe69aec/negative-20x2-summary.json)에 분모를 보존했다.

## peer loss와 185초 stream

Initiator probe만 실제 hardware reset하는 source loss를 20회 주입했다. 매회 기존 BIG의 HCI
connection timeout `-8`, Commander의 loss 탐지, stop/remove, 새 source 검색, code 배포, PA/BIS sync와
실제 LC3 frame을 확인했다. **20/20**이 4.525~5.305초 안에 복구됐고 ACL fallback 재연결은 0회다.
[peer-loss 결과](evidence/m31-w03-cap-bfe69aec/peer-loss-20-summary.json)에 각 회차를 남겼다.

마지막 복구 뒤 185초 연속 캡처에서 Initiator는 18,100 frame, Acceptor는 18,000 frame 증가했다.
drop은 0이고 failure·disconnect 출력은 0줄이다.
[stream 결과](evidence/m31-w03-cap-bfe69aec/stream-185s-summary.json)에 시작·종료값을 고정했다.

## 로그로 확인한 경쟁과 수정

이전 `a751ddee` 같은-revision 시험에서 의도한 stop의 늦은 `bis=1` 알림 뒤 `bis=0` 알림을
peer loss로 오인했다. 자동 복구가 사용자 stop과 겹치면서 Acceptor에 `-EAGAIN(-11)`이 1회 발생했다.
해당 실행은 최종 PASS에서 제외하고
[원 로그](evidence/m31-w03-cap-a751ddee/same-revision-control-102ops.log)를 진단 이력으로 보존했다.

Commander가 CAP 절차 수행 중이 아니라 유휴일 때만 BIS 소실을 peer loss로 판정하도록 수정했다.
수정 뒤 102연산에서 거짓 loss 0, native failure 0을 확인했고 실제 hardware reset 20회는 모두 정상
loss로 판정됐다. 오류의 원인과 수정은 추측이 아니라 state update·procedure stage·원본 HCI 오류의
시간순 로그로 구분했다.

## 판정과 잔여 범위

M31-AUDIO-01 `W03-05`의 **CAP broadcast 3역할 부분 범위**는 build/runtime, control 102,
negative 20×2, peer loss 20회와 185초 stream을 만족해 PASS다. Host M31 55/55와 공개 예제 감사
16 libraries·89 examples·0 issue도 통과했다.

그러나 W03-05 계약의 CAP unicast group procedure, cancel·부분 실패, handover 적용성과 callback
범위는 아직 미완료다. 따라서 W03-05 전체와 M31-W03 전체는 **진행 중**이며 M31 완료 분자는
**2/8** 그대로다. W03-06~W03-11, W04 raw IQ RX와 W05 잔여도 남아 있다. W02 설치본 ISO
11예제·11역할 증거는 변경하지 않았고 CI/CD는 조회하지 않았다.
