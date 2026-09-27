# M31-W05 connected Channel Sounding 완료

## 1. 결론

M31-W05를 **PASS·완료**로 판정했다. 고정 NCS v3.4.0·제품 SDC에서 공개
`RasInitiator`/`RasReflector`의 secure RAS, 반복 정지·재연결, 256-step 장시간,
peer-loss 복구, 비암호화·wrong peer·one-sided stale-key negative와 flash 직후
복구 경계를 모두 증거로 닫았다.

이 완료로 M31은 **W01~W05 5/8**이다. 다음은 W06 독립 role image별 자원·수명주기와
M19~M30 영향 회귀다. W07·W08과 v0.5.0 공개·tag·catalog는 완료하거나 승인하지 않았다.

## 2. 고정 조건

| 항목 | 고정값 |
| --- | --- |
| 공개 예제 build 소스 | `bd8bb98af2ca7b7d54104e80175b379375c7e718`, clean |
| stale-key 실기 소스 | `704120b1968c236d4809b5709b83cea7dc38b2fa`, clean |
| SDK / Zephyr | NCS `v3.4.0` / Zephyr `4.4.0` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Arduino 구성 | `nucode:zephyr:nu54dk:feature_set=adaptive` |
| controller | 제품 SDC |
| 플래시 안전 | exact sector flash, `auto_unlock=false`, mass erase/recover 없음 |

probe SHA-256 identity·현재 COM·역할·image hash를 실행 직전 재결합했고, 배타 probe
lock·watchdog·단일 byte command lease를 유지했다. 원시 probe UID·Bluetooth 주소는 증거에
남기지 않았다. 마지막 실기 뒤 양쪽은 명시적 `STOPPED`이고 stale-key fixture image가 남아 있다.

## 3. 지원 경로와 negative 결과

| 조건 | 결과 | 판정 |
| --- | --- | --- |
| secure RAS | raw 100, stop/restart 20/20, disconnect/reconnect 20/20 | PASS |
| 최대 절차 | 256-step, 분할 RAS 유효 raw 1,000, 양측 STOP | PASS |
| 최대 절차 peer loss | 첫 raw 전 peer 이탈 뒤 자동 재연결·유효 raw 20 | PASS |
| 같은 ACL 비암호화 read | ATT `0x05`, 20/20 거부, 재연결·재탐색 0 | PASS |
| wrong peer / RAS service 부재 | 3보드 peer 분리와 위장 UUID 거부 20회 | PASS |
| one-sided stale key | bond 1:0, 자동 repair pairing 0, 보안 오류 1, L2·ready·active·raw 0, 최종 양측 STOP | PASS |
| flash 직후 경계 | 서로 다른 exact source/image에서 raw 100·20/20·20/20 두 차례 | PASS |

stale-key 시험은 reflector bond만 삭제한 뒤 재연결했다. 30초 동안 ACL은 유지됐지만
initiator 보안 facade가 reason `2` 오류를 냈고 L2 이상 보안, RAS ready/active, raw 결과는
한 건도 열리지 않았다. W05의 판정 대상은 secure RAS의 잘못된 수용 0이며, controller가
오류 때 반드시 ACL을 끊는다는 계약은 없다. 따라서 ACL 유지 자체를 실패 조건으로 두지 않고
명시적 STOP에서 연결·scan·광고·CS 상태를 정리했다. 이 결과를 임의 unequal LTK 주입이나
disconnect-on-error 보장으로 확대하지 않는다.

flash 직후 성공은 두 번 재현됐지만 과거 간헐 중단의 단일 원인을 확정하지 않았다. 간헐
CS counter gap·RF/controller loss는 P2에서 정한 `observe_only`를 유지하며, 유효 raw·step·완료 수,
양측 STOP, fault, 중복/역행 counter 검사는 그대로 유지한다.

## 4. 실패 원본과 재검증 상한

첫 stale-key 실행은 실제 controller 보안 실패가 application repair-pairing callback보다 먼저
발생해 callback marker timeout으로 `FAIL`했다. 계측을 보강한 허용 1회 재검증은 bond 1:0,
보안 오류와 CS 무진행을 모두 기록했지만 runner가 ACL teardown까지 요구해 다시 `FAIL`했다.
두 원본은 삭제하거나 PASS로 고치지 않았다. 현재 계약은 두 번째 원본의 정량값을 독립적으로
판정해 secure RAS acceptance 0을 PASS로 분류하며, 재검증 상한에 따라 세 번째 실물 실행은
하지 않았다.

adaptive fixture 빌드에서도 manifest 누락, Security API 역할 누락, bond persistence 계약 누락,
fixture 전용 pairing mode override의 네 실패를 순서대로 보존했다. CS 역할이 실제 사용하는
보안 API·bond persistence를 가짜 Audio 역할 없이 선언하고 제품 pairing mode를 덮어쓰지 않게
정리한 뒤 양쪽 fixture와 공개 예제 build가 PASS했다.

## 5. build와 증거

| image | FLASH | RAM | 결과 |
| --- | ---: | ---: | --- |
| 공개 `RasInitiator` | 256,616 B | 80,337 B | PASS |
| 공개 `RasReflector` | 237,604 B | 62,175 B | PASS |
| 계측 `RasStaleKeyInitiator` | 266,224 B | 79,378 B | PASS |
| 계측 `RasStaleKeyReflector` | 250,312 B | 61,803 B | PASS |

- [완료 audit](evidence/m31-w05-close-20260925/closure-audit.json)
- [build manifest](evidence/m31-w05-close-20260925/build-manifest.json)
- [stale-key 기능 판정](evidence/m31-w05-close-20260925/stale-key-adjudication.json)
- [stale-key 첫 FAIL](evidence/m31-w05-close-20260925/stale-key-attempt-1-f30404e2.json)
- [stale-key 1회 재검증 FAIL 원본](evidence/m31-w05-close-20260925/stale-key-attempt-2-704120b1.json)
- [build 실패·성공 순서](evidence/m31-w05-close-20260925/build-attempts.json)
- [flash 직후 재검증](218_M31_W05_flash_직후_RAS_복구_재검증.md)
- [P2 256-step·peer-loss 복구](262_M31_메모리_최적화_P2_세_축_완료.md)

## 6. 완료 경계

W05는 제품 SDC의 두 CS 역할, 공개 Arduino RAS API, raw·반복·peer 분리·보안 오류·복구와
정지 수명주기를 소유한다. 미보정 RTT의 정밀 거리, 외장 RF·안테나 배열, cross-vendor peer,
Bluetooth qualification은 범위 밖 또는 사용자 후속이다. W06의 전체 자원·수명주기·M19~M30
회귀, W07 설치 예제 전수 실행, W08 마감·릴리스 준비를 W05 분모에 합치지 않는다.
