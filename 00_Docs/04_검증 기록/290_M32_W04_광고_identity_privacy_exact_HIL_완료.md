# M32-W04 광고·identity·privacy exact HIL 완료

## 1. 판정

| 항목 | 결과 |
| --- | --- |
| 대상 branch | `Dev-0.6.0-M32` |
| 광고 exact source | `3829f144d8caba43bea65f01445ab392f5e7ec12` |
| privacy 최종 exact source | `386bc37983b27baed8d271c4a3c78c2125657d5b` |
| EAD exact source | `4af5b15a54aacc9d15f8257e535bbd7bc635b78b` |
| 고정 환경 | board `fe65f2f0880b…`, NCS `99553055607b…`, Zephyr `bf801e4e3d19…` |
| probe 경로 | **CMSIS-DAP v2**, 500 kHz, under-reset, `auto_unlock=false` |
| `M32-ADV-01:primary` | **PASS** |
| `M32-PRIV-01:primary` | **PASS** |
| `M32-EAD-01:primary` | **PASS** |
| W04 상태 | **완료** |
| M32 완료 수 | **6/12** |

세 NU54DK의 mass-storage·target UART·CMSIS-DAP v2를 역할별 SHA-256 identity로 다시 고정했다.
원본 probe identity는 문서와 명령 출력에 저장하지 않았다. 각 실행은 exact Core revision, 고정
board/NCS/Zephyr revision, image SHA-256, 비파괴 DP/AP identity, bounded UART transcript와 역할별
STOP을 한 evidence envelope에 묶었다. 자동 unlock·recover·mass erase는 사용하지 않았다.

## 2. 광고 scale 결과

`M32-ADV-01:primary`은 advertiser 두 대와 scanner 한 대에서 20회 실행했다.

| 분모 | 결과 |
| --- | ---: |
| 광고 set | 역할별 3개 |
| payload update | 역할별 20/20 |
| scan raw report | 1,210 |
| 고유 set/SID report | 120/120 |
| packet 분모 | 600/600 |
| 손실·손상·queue drop | 0 / 0 / 0 |
| over-capacity 거부 | 2/2 |
| stale set 거부 | 2/2 |
| scan/initiate 충돌 거부 | 1/1 |
| callback context | 3/3 PASS |

세 광고 set의 SID와 갱신 sequence를 scanner가 중복 제거 뒤 모두 관측했다. 자원 상한 초과,
삭제된 generation handle 재사용과 동시 scan/initiate 충돌도 각각 독립 분모로 거부했다.

## 3. identity·privacy 결과와 실패 보존

첫 privacy 실행은 exact `3829f144…`에서 `identity_a_session_timeout`으로 **FAIL**했다. target이
Filter Accept List에 peer의 고정 identity를 등록했지만 peer도 RPA를 사용했고, bond IRK가 없는
target은 해당 RPA를 허용하지 못했다. 이 실패 envelope와 UART transcript는 삭제하거나 PASS로
덮어쓰지 않았다.

`386bc379…`에서 peer 역할만 RPA를 끄고 identity scan을 사용하도록 sysbuild 경계를 고정했다.
identity_a와 identity_b는 privacy를 계속 사용한다. 세 역할을 다시 build하고 같은 CMSIS-DAP v2
경로로 실행한 최종 결과는 다음과 같다.

| 분모 | 결과 |
| --- | ---: |
| identity_a 연결·해제 | 20/20 · 20/20 |
| identity_b 연결·해제 | 20/20 · 20/20 |
| peer의 A/B 연결 | 각 20/20 |
| packet | 200/200 |
| packet loss | 0 |
| 최대 latency | 212 ms / 상한 1,000 ms |
| 잘못된 identity 거부 | 2/2 |
| 미허가 peer 거부 | 1/1 |
| 활성 list 변경 거부 | 2/2 |
| callback context | 3/3 PASS |

## 4. EAD와 W04 자원 경계

EAD는 exact `4af5b15a…`에서 인증 sequence 20/20, raw report 400/400, loss·drop 0을 완료했다.
replay, ciphertext 변조, 잘못된 key와 잘못된 IV는 각각 20/20 거부했다. software/build 기준선
`b8d0c0c1…`의 공개 Arduino 예제 12/12, Host 21 test와 target build 5/5도 함께 W04 완료
근거로 유지한다. C1P1/C2P0/C0P2 자원 profile은 각각 RAM/RRAM 65,280/226,048 B,
60,344/218,716 B, 61,248/207,276 B로 고정 상한 안이다.

외부 상용 peer 상호운용은 `NOT_RUN`이며 이번 개발 완료 판정에 포함하지 않는다.

## 5. 증거

- 광고: [`m32-adv-01.json`](evidence/m32-w04-exact-3829f144/m32-adv-01.json) ·
  [`transcript`](evidence/m32-w04-exact-3829f144/m32-adv-01.transcript.log)
- 보존한 privacy FAIL: [`m32-priv-01.json`](evidence/m32-w04-exact-3829f144/m32-priv-01.json) ·
  [`transcript`](evidence/m32-w04-exact-3829f144/m32-priv-01.transcript.log)
- 최종 privacy PASS: [`m32-priv-02.json`](evidence/m32-w04-exact-386bc379/m32-priv-02.json) ·
  [`transcript`](evidence/m32-w04-exact-386bc379/m32-priv-02.transcript.log)
- EAD: [`m32-ead-01.json`](evidence/m32-w04-exact-4af5b15a/m32-ead-01.json) ·
  [`transcript`](evidence/m32-w04-exact-4af5b15a/m32-ead-01.transcript.log)
- 완료 감사: [`w04-closure-audit.json`](evidence/m32-w04-exact-386bc379/w04-closure-audit.json)

Envelope SHA-256은 광고
`6e0f742cdf2a9c1a25b200d9cc27a13288bf61706cf695cd9fb1a8d14ab48cc0`, 보존한 privacy FAIL
`947b6d296ea97e713ecfda32d1ffe87afd97dddc95a51d4b1111bd07e607dbaf`, 최종 privacy PASS
`a32c36dea46a9fb530ff7428229302653f91794afe7cfa3d5805cc874031c87a`, EAD
`fb399c1f27871244fc06907dc10dec3a12b7cfc33db7a1e607a46d0ab34aa94f`다.
