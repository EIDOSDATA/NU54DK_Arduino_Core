# M31-W03 Arduino CSIP 완료

clean Core `fcbbfac5fe348c51be0fb4e30f2b8415099b8758`에서 공개
[`CsipSetCoordinator`](../../libraries/NUCODE_BLE_Audio/examples/CsipSetCoordinator/CsipSetCoordinator.ino)와
[`CsipSetMember`](../../libraries/NUCODE_BLE_Audio/examples/CsipSetMember/CsipSetMember.ino)를
다시 빌드·flash하고 set discovery, membership/rank, ordered access, lock/release,
negative와 member loss 복구를 실제 세 보드에서 확인했다. 공개 `.ino`는 사용자가
읽고 수정할 수 있는 NUCODE C++ API만 사용하며 Zephyr 직접 호출이나 개발
milestone 표식을 포함하지 않는다.

## exact source와 3보드

| 역할 | 보드 / target COM | FLASH | RAM | HEX SHA-256 |
| --- | --- | ---: | ---: | --- |
| coordinator | G / COM10 | 311,252 B | 199,544 B | `841cd72d4728050e3e4baa1e6c6eecf7f9def2d1874465125442bcd963746663` |
| member A | F / COM14 | 394,816 B | 210,865 B | `ad654a7f6941615ad39d85468485cf72bb4805aea4eba2fe527c02aaaf76dc32` |
| member B | E / COM13 | 394,816 B | 210,865 B | `ad654a7f6941615ad39d85468485cf72bb4805aea4eba2fe527c02aaaf76dc32` |

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.
새 PC의 CMSIS-DAP V2는 원문 UID를 기록하지 않고 SHA-256 identity로 선택했으며
G/F/E의 target/aux COM을 각각 10/11, 14/15, 13/12로 다시 확인했다.
source, image, build, mapping과 실행 원문은
[manifest](evidence/m31-w03-csip-fcbbfac5/manifest.json)에 묶었다.

## positive와 negative 7/7

[campaign](evidence/m31-w03-csip-fcbbfac5/campaign.summary.json)의 일곱 scenario는 모두 PASS다.

| scenario | 판정 근거 |
| --- | --- |
| positive | member 2개, rank 1/2, ordered access, 양 member lock/release를 확인했고 잘못된 상태 조작 2건을 거부 |
| wrong rank | 중복 rank 1/1에서 set ready·rank 2가 없고 operation을 거부 |
| wrong SIRK | 정상 member만 참가하고 다른 SIRK member는 set에 참가하지 못하며 operation을 거부 |
| security sync failure | 보안 요청의 동기 실패를 보고하고 ready로 잘못 승격하지 않음 |
| security async failure | 비동기 보안 실패를 보고하고 ready로 잘못 승격하지 않음 |
| watchdog | coordinator progress timeout 뒤 ready로 잘못 승격하지 않음 |
| recovery | member B hardware reset 후 정확한 connection 인증·재가입·lock/release를 20/20 회 복구 |

recovery는 각 cycle 6.083~6.987초로 30초 한도 안이었다. 해당 transcript의
`Set ready` 21건, `Set locked` 40건, `Set released` 40건, 합계 **101건**을
M31-AUDIO-01의 valid control/state report 분모로 계산했다. 모든 recovery
cycle은 재가입한 handle의 정확한 인증과 양 member lock/release를 포함한다.

## 진단 이력과 판정

앞선 attempt에서 첫 여섯 scenario는 통과했지만 동일 boot의 member loss 후
coordinator가 재발견을 시작하지 못해 recovery가 실패했다. 해당 실패
summary/transcript를 `diagnostic-history`에 보존했고, secure reconnect 후 discovery
재시작 순서와 알려진 peer에만 적용되는 reconnect fallback을 고친 뒤 동일
조건의 7/7 campaign을 새로 실행했다. 실패 attempt는 최종 PASS에 합산하지
않았다.

M31-AUDIO-01 `W03-06`의 coordinator/member A/member B, valid report 101건,
wrong rank/SIRK/state·security·watchdog 거부, peer loss 복구 20/20을 만족해
PASS로 판정한다. 이 결과는 고정 SDK와 NU54DK 세 보드의 CSIP 기능 검증이며
Bluetooth qualification이나 상용 peer 상호운용을 주장하지 않는다. W03-09~11이
남아 M31-W03 전체는 진행 중이고 M31 완료 분자는 2/8 그대로다. W02 설치본
ISO 11예제·11역할 증거는 변경하지 않았으며 CI/CD는 조회하지 않았다.
