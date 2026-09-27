# M30-W02 link별 security와 IO capability 5종 완료

## 결과

M30-W02를 exact Core `4f91e347e8e36e77c959de90def7d9c2622be30b`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0에서 완료했다. SecurityManager의
pairing·bond·security level 상태와 사용자 응답 대기를 두 generation link에 분리했고, IO
capability 5종의 peripheral/central 이미지 10개를 빌드한 뒤 두 NU54DK에서 각각 10회씩 실제
페어링했다.

| Gate | 결과 |
| --- | --- |
| production-linked Security 시나리오 | **17/17 PASS** |
| M30 security·pairing 계약 시험 | **11/11 PASS** |
| M12 전체 Host gate | **PASS** |
| Zephyr target build | **10/10 PASS, warning 0** |
| 실제 `M30-PAIR-01` | **50/50 PASS — IO capability 5종, 인증 실패 0** |
| M30 진행률 | **W02 완료, 작업 묶음 2/8·test ID 2/10 PASS** |

## 구현 경계

- 공개 pairing 요청·승인·passkey 입력·확인·취소와 paired/bonded/bond state/security level 조회에
  `BLEConnectionHandle` overload를 추가했다. 기존 singleton API는 첫 active link를 보는 legacy
  view로 유지했다.
- security link 상태와 pending 사용자 응답은 heap 없이 각각 두 slot로 고정했다. stale generation,
  두 link의 동시 pending, 엇갈린 timeout과 sparse slot의 중복 요청을 서로 섞지 않는다.
- GAP connect/disconnect/security-changed 경로는 exact handle을 SecurityManager에 전달한다.
- LE Secure Connections-only와 16-byte key 정책을 유지한다. IO가 없는 Just Works는 암호화 L2이고,
  MITM 가능한 나머지 네 조합은 L4다. Just Works를 L4로 과장하지 않는다.
- 실제 실행은 F:/COM14 peripheral과 G:/COM10 central을 raw UID가 아닌 exact probe UID 입력으로
  결합했다. 공개 증적에는 UID SHA-256만 남긴다.

## 실제 결과

| 조합 | association method | 보안 수준 | 결과 |
| --- | --- | ---: | ---: |
| No Input No Output / No Input No Output | Just Works | L2 | 10/10 |
| Display Only / Keyboard Only | Passkey Entry | L4 | 10/10 |
| Keyboard Only / Display Only | Passkey Entry | L4 | 10/10 |
| Display Yes/No / Display Yes/No | Numeric Comparison | L4 | 10/10 |
| Keyboard Display / Keyboard Display | Numeric Comparison | L4 | 10/10 |

모든 라운드는 16-byte encryption key, paired 상태와 bond persistence pending을 양쪽 exact handle에서
확인했다. 예상 밖 authentication failure는 0이며 power cut, mass erase, recover는 수행하지 않았다.
최종 원본은 다음에 보존한다.

- [구조화 evidence](evidence/m30-w02-4f91e347-pair/m30-pair-evidence.json)
- [peripheral transcript](evidence/m30-w02-4f91e347-pair/m30-pair-evidence.peripheral.transcript.log)
- [central transcript](evidence/m30-w02-4f91e347-pair/m30-pair-evidence.central.transcript.log)

표시 passkey는 runner 메모리에서만 중계하고 transcript에는 `<redacted>`로 저장했다. 세 probe의 raw
UID와 6자리 passkey가 위 세 파일에 없음을 별도로 검사했다.

## 실패 분류와 수정

- 첫 preflight는 pySerial import helper가 module과 port lister의 tuple을 반환하는 계약을 잘못
  사용했고, board revision validator의 인자도 잘못 전달했다. 장치 접근 전에 두 호출을 교정했다.
- 첫 실제 실행은 UART input buffer를 비운 뒤 boot-time READY를 기다려 응답을 잃었다. nonce가 묶인
  `IDENTIFY` 요청에 target이 현재 image identity를 다시 응답하도록 바꿨다.
- 최초 연결 시험은 No Input No Output에도 L4를 요구해 Just Works를 실패 처리했다. 이 조합만 L2,
  나머지 MITM 가능 조합은 L4가 되도록 기대 수준과 증적을 분리했다.
- 이후 실행은 `keyboard_display` 10번째 라운드에서 central GAP 오류로 중단됐다. scan result 큐의
  같은 peer 결과가 첫 connect 시작 뒤 다시 처리될 수 있었으므로 라운드당 연결 시도를 한 번으로
  고정하고 GAP 오류 코드도 실패 frame에 포함했다. 수정 뒤 같은 5종 50회를 처음부터 통과했다.
- exact `aa1e962a…`의 첫 50/50 PASS는 endpoint volume 직렬화가 빈 문자열임을 사후 검사에서
  발견했다. 원본은 `m30-w02-aa1e962a-pair`에 보존하되 canonical 근거로 사용하지 않는다. Windows
  drive root만 `F:`/`G:` 형식으로 허용하도록 고치고 exact `4f91e347…`에서 빌드와 50회를 다시
  수행했다.

각 실패는 원인 확인 뒤 단일 수정하고 전체 관련 조건을 다시 실행했다. reset으로 성공을 대체하거나
mass erase/recover로 보드를 초기화하지 않았다.

## 다음 작업

M30은 **2/8 작업 묶음, 2/10 test ID PASS**다. 다음은 M30-W03으로, wired USB/DAPLink VCOM을
OOB carrier로 사용해 `M30-OOB-01` 20회와 mismatch accept 0을 실제 검증하고 bond/privacy
migration을 이어서 검사한다. NFC adapter는 구현·Host/target build만 수행하며 RF HIL은 사용자
범위 결정대로 `NOT RUN`이다. 실제 target USB 전원 차단은 M30-W08의 `M30-POWER-01`이며 W07
통합 HIL 뒤 그 주입 직전에 자동 작업을 멈춘다.
