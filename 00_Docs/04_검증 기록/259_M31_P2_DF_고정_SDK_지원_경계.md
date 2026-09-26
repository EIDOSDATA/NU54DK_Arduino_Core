# 259 — M31 P2 DF 고정 SDK 지원 경계

> 현재 판정(2026-09-25): P2 세 기술 축은 [262번](262_M31_메모리_최적화_P2_세_축_완료.md)에서 완료됐다.
> 아래의 미완료·HOLD·다음 작업 문구는 이 기록 작성 당시 상태이며 원본 판정을 보존한다.

## 고정 버전의 범위

이 프로젝트의 NCS `v3.4.0`에 포함된
[Nordic software maturity 표](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/doc/nrf/releases_and_maturity/software_maturity.rst)는
nRF54L Series의 Direction Finding을 `Experimental`로 표시하고 각주
`Only AoA transmitter is supported`를 붙인다. 따라서 nRF54L15의 이
**고정 SDK·제품 SDC 조합에서는 AoA 수신을 지원 기능으로 판정할 수 없다.**
이 표는 모든 가능한 controller/SDK에서 수신이 영구 불가능하다는 뜻은 아니다.

이 구분은 기존 실기와 일치한다. [242번](242_M31_메모리_최적화_P2_DF_beacon_TX_계측.md)은
공개 beacon TX 20회를 확인했으나 IQ RX는 아니다.
[244번](244_M31_P2_DF_연결_IQ_진단.md)·[246번](246_M31_P2_DF_연결_IQ_메모리_계측.md)의
연결형 Zephyr LL 내부 진단은 IQ report 20건·sample 1,640개와 정상 종료
high-water를 확인했지만 Arduino/SDC 수신 구현이 아니다.
[247번](247_M31_P2_DF_connectionless_재진단과_보류.md)·
[250번](250_M31_P2_native_CS_비교와_DF_재진단.md)·
[256번](256_M31_P2_DF_sync_대기_취소_진단.md)의 connectionless LL 수신은
periodic sync timeout·IQ 0, 종료 중 usage/bus fault가 남았다. 정확한 fault
원인을 특정하지 못했으며 이 실패 image를 반복 실행하지 않는다.

제품 beacon 설정에서 주기적 광고 `options`에 일반 advertising의
`BT_LE_ADV_OPT_USE_TX_POWER`를 잘못 넣은 독립 결함을 발견했다. 해당 비트는
Zephyr periodic API에서 해석되지 않아 실질적으로 `NONE`이었다.
전용 `BT_LE_PER_ADV_OPT_USE_TX_POWER` 비트로 바꾼 첫 수정 image는 빌드됐지만
실기 `beacon.begin()`에서 `native=-5`로 실패했다.
[실패 원본](evidence/m31-p2-four-axes-20260925/df-periodic-tx-power-rejected.json)과
HEX SHA-256
`857e9cc17d3a4079f2490db39881e71a52c4094ec29f1a374dcb11409b3db603`을
보존한다. 이번 고정 SDC·보드 조합은 periodic TX Power 요청에 `-5`를
반환했다. 따라서 제품 option을 명시적 `BT_LE_PER_ADV_OPT_NONE`으로
바꿨다. 이는 TX 설정 정합화이며
**sync timeout·RX fault의 해결 증거가 아니다**.
최종 P2 beacon image는 exact 송신 보드에서 잘못된 CTE 길이 거부,
start/stop **20/20**, STOP과 libc malloc `allocated=0`을 통과했다.
[실기 원본](evidence/m31-p2-four-axes-20260925/df-periodic-none-tx20.json)의
HEX SHA-256은
`62f423073329eb80a99bb70f2b9285c84fac3c35f794ca3d397a796d0e09b402`,
정적 FLASH/RAM은 `115,916/38,676 B`다. MPSL Work 관찰값은
`232/1,024 B`, main은 `784/8,192 B`다. 이 실행은 TX 제어와 메모리
수명 검증이지, 상대 수신자의 IQ callback 증거가 아니다.
실기 직후 송신 보드를 최종 기본 CS initiator image로 sector 복구하고 기존
reflector와 [raw 10건·gap 0·양측 STOP](evidence/m31-p2-four-axes-20260925/cs-recovery-after-df-tx-10.json)을
확인했다. 세 번째 보드는 접근하지 않았다.

공개 `CteBeacon` 예제의 직접 adaptive build는 첫 시도에서 capability
probe가 최종 build에서만 생성되는 revision 매크로 네 개를 참조해 실패했다.
예제의 identity 출력만 `NUCODE_CAPABILITY_PROBE`에서 제외했다. 실제
Arduino 실행의 READY 문자열은 그대로 유지된다. 이 수정 뒤 공개 예제
`adaptive` target build는 FLASH/RAM `114,540/38,314 B`, HEX SHA-256
`797a8afe99b48551a4591c0718ea3ca27f4466b87ff4250305941e24c051c195`로
PASS했다. 기본 `ble` profile 빌드도 `156,684/51,405 B`로 통과했다.
두 정적 크기는 서로 다른 profile이므로 동일 설정의 순수 비용 차이로
해석하지 않는다. 공개 예제 자체의 추가 HIL은 하지 않았고, 위 20회 HIL은
같은 제품 라이브러리를 사용하는 adaptive P2 beacon fixture다.

## P2 판정

DF TX는 기존 실기와 최종 `NONE` 수정 image의 20회 실기에서 국소 PASS다.
제품 SDC IQ RX는 고정 NCS의 지원 범위 밖이므로 **UNSUPPORTED·P2 비차단**으로
확정한다. P2 완료를 위해 수신을 구현하거나 SDK/controller를 변경할 필요는 없다.
별도 Zephyr LL connectionless RX의 실기 FAIL/HOLD와 connected 내부 IQ 진단은
그대로 보존하되, 이 실패 실험을 P2 필수 재시도·메모리 계측 목록에 넣지 않는다.

NCS `v3.4.0`·제품 SDC 전제를 유지한다. 공개 RX를 지원 기능으로 약속하는 별도 확장은
버전·controller 선정, 기존 ISO/Audio/CS 영향 검토와 새 HIL 인수 계약이 필요하며
현재 P2에 합산하지 않는다. 이 범위 판정은 IQ RX의 기능 PASS, W04 전체 완료 또는
메모리 축소 근거가 아니다. P2 잔여는 [M31 TODO](../TODO_M31.md)의 세 축이다.
