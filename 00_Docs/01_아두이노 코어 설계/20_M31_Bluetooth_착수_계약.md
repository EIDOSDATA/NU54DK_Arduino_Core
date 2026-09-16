# M31 Bluetooth 착수 계약 — 고정 NCS의 ISO·Audio·DF·CS

| 항목 | 고정값 |
| --- | --- |
| 제품선 | `v0.5.0`; M31-W01~W08 8개 작업 묶음 |
| source 기준 | NCS nrf `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| board 기준 | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, 정확한 `nrf54l15dk/nrf54l15/cpuapp` qualifier |
| 원장 | `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`, `variants/nu54dk/m31-ble-readiness.json` |
| 기능 시험 | `M31-CAP-01`, `M31-PARITY-01`, `M31-ISO-01`, `M31-AUDIO-01`, `M31-DF-01`, `M31-CS-01`, `M31-NEG-01`, `M31-REG-01`, `M31-EXAMPLE-01`, `M31-CLOSE-01` |
| 현 단계 | W01 완료 1/8; ISO 고정 시험 sketch 11/11 build와 7개 실제 보드 case PASS. 공개 CIS·BIS 네 역할 새 payload API 실기 PASS, 나머지 7개 ISO 예제 재작업과 W03 전체 LE Audio 진행 |

이 계약은 [전체 기능·예제 계약](19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md)의
source 발견, NU54DK build, Arduino build, HCI query, 실제 기능 HIL, 외부 상호운용을 각각
판정한다. M30의 8/8·10/10·전원 차단 12/12 완료 판정은 그대로 보존한다. 고정 lock이나
기본 controller를 임의로 교체하지 않는다.

## 원장과 수집 범위

`tools/bluetooth/m31_inventory.py`는 NCS/Zephyr `samples/bluetooth`를 재귀 조사하고,
Bluetooth tag·의존성·설정이 있는 별도 `samples`/`applications` root를 이유와 함께 수집한다.
`sample.yaml`의 `common`/각 `tests` override 원문과 해석 metadata를 분리하고 allow,
exclude, integration의 nullable 필드를 보존한다. 정확한 L15 qualifier만 긍정 metadata로
세며, `filter` 미평가·일반 allowlist 부재·`build_only`를 실행 지원 판정으로 바꾸지 않는다.
sample subtree 경로·원본 byte SHA-256과 YAML 자체 SHA-256을 별도로 기록한다. 현행 고정
source에서 sample 190개, test variant 474개, M31 Kconfig symbol 후보 39개를 수집했다.
전체 703행은 M31 또는 M32/M33 소유 작업에 매핑되며 모든 실행 상태는 독립 필드다.

parity 원장은 기능 예제의 계획·실제 Sketch, controller, role, 외장 장비, RAM/RRAM/slot/buffer,
정량 시험, 익명 증거 identity를 별도로 담는다. 검증 전 수치와 sketch는 `null`이고,
`NOT_RUN`을 `PASS`로 승격하지 않는다. M31의 정량 수치·role subcase 원본은 readiness 원장이며,
후속 M32/M33 행은 해당 owner가 기능 시험 전에 수치를 고정한다. source-only 행의 기능
실행은 이 수집기만으로 승격할 수 없다. parity 생성 후 `--check`로 source/원장 drift를 찾는다.

## Controller와 기능 판정 경계

| 구성 | 현행 관찰 | 다음 기능 판정 |
| --- | --- | --- |
| 기본 SDC | 기본 설정 HCI LE feature에는 ISO·DF·CS가 활성화되지 않는다. ISO·CS·DF TX opt-in target 3종을 분리 빌드했고 각 HCI bit와 Host 설정을 실기 query했다. | CIS/BIS payload, CS procedure, CTE 송신은 기능별 HIL 필요 |
| Zephyr LL IQ 후보 | `bt-ll-sw-split`와 기본 1개 안테나, TX/RX 안테나 전환 없는 구성을 NU54DK에 build했다. HCI connectionless CTE RX bit 20과 Host 설정은 확인했고 안테나 정보는 1개다. | raw IQ report 수신·형식·stop/restart를 W04에서 실제 두 보드로 검증 |
| 기본 SDC DF | opt-in `CONFIG_BT_CTLR_DF=y`에서 connectionless CTE TX bit 19를 확인했다. SDC AoD bit와 IQ RX bit는 제공되지 않는다. | TX 예제/실기와 LL RX 후보를 구분; 칩 전체 IQ 불가 판정 금지 |
| LE Audio profile | 11개 W03 기능 묶음의 source 후보·역할 분모를 등록했다. | profile별 opt-in·target/Arduino build·합성 PCM/payload·role HIL 필요 |

Zephyr Host AoA API는 안테나 2개 이상 및 ANT_SWITCH_RX를 검사하므로 현재 1안테나
구성에서 고수준 AoA API를 바로 사용하면 거부된다. 이 사실은 HCI raw CTE RX bit와 별도이며,
W04의 직접 raw IQ 가능성은 실제 report 수신 전까지 `source_candidate`로 둔다.
안테나 배열·정밀 각도·정밀 거리·음질 측정은 기본 데이터 경로 검증의 선행 gate가 아니다.

## 유한 시험과 증거 형식

readiness의 10개 family·28개 subcase가 검증 분모다. W03의 11개 Audio 묶음과 설치
예제 role 42개는 별도 분모로 유지한다. `M31-CAP-01`은 한 보드에서 7개 HCI LE feature와
Host 설정, 4개 revision, controller variant, 동일 nonce/image hash를 대조한다.
`M31-PARITY-01`은 703개 원장의 owner·중복·status 경계를 검사한다.
`M31-ISO-01:cis`는 중앙/주변 두 보드에서 20회 START→100개 SDU→STOP, 매회
유효 수신 최소 99개, 중복/손상 0개, 종료 후 재시작을 요구한다. BIS·combined·time sync,
Audio 11개, DF, CS의 상세 timeout·반복·수락·negative는 readiness 각 case가 소유한다.
수치 미확정 M32/M33 sample은 기능 실기 전에 계약을 채운다.

실기 evidence는 clean commit revision, board/submodule/SDK lock, HEX SHA-256, probe
SHA-256, 역할·COM mapping, AP register identity, nonce, UART 원본 SHA-256, 시각과
attempt ID를 함께 가진다. probe UID 원문은 메모리의 장치 선택에만 사용하고 채팅·원장·
파일에 쓰지 않는다. 복수 보드는 배타 lock을 잡고 비파괴 CMSIS-DAP V2 DP/AP register
조회 뒤 sector flash만 수행한다. 자동 mass erase/recover·전원 차단을 수행하지 않는다.
실패 원본은 보존하며 한도 없는 진단 재시도를 금지한다. UART protocol은 READY/BEGIN/
IDENTITY/결과/STOPPED의 누락·중복·잘못된 nonce/role/feature·절단·잡음을 거부한다.

구현·자동 검사 case는 `developer/development`와 개발·릴리스 blocker를 가진다.
외부 mic/speaker/codec·안테나 확장의 물리 운용은 `user/user_follow_up`, 양 blocker
`false`의 `NOT_RUN`으로 남긴다. Ubuntu/macOS 실제 설치·USB·serial·debug는
`user/final_release`, 개발 blocker `false`, 릴리스 blocker `true`다. 제품 사용 가능한
외장 연결 경로·예제·설정 안내와 가능한 자동 검사는 별도의 필수 개발 case다.

## 현재 개발 시도와 후속 판정

한 보드 capability의 5개 구성은 local target build와 HCI query 개발 시도에서 통과했다.
원본은 [M31-W01 후보 증거](<../04_검증 기록/evidence/m31-w01-dev-candidate>)에 있으며
`source_clean=false`이므로 W01 완료 증거가 아니다. 두 보드 CIS 20회 × 100개 유효
SDU 및 해제/재시작 역시 [W02 후보 증거](<../04_검증 기록/evidence/m31-w02-dev-candidate>)로
기록했다. 각 ISO event의 무효 빈 slot은 유효 payload 분모와 구별한다.
clean `8c125a220c4df722e4922887fdf6c5a5e3793612`을 기준으로 다시 빌드했고,
[W01 exact manifest](<../04_검증 기록/evidence/m31-w01-exact-8c125a22/capability-manifest.json>)의
5개 HCI query와 [W02 exact manifest](<../04_검증 기록/evidence/m31-w02-exact-8c125a22/cis-manifest.json>)의
20회×100 CIS는 PASS다. 이는 controller query와 CIS subcase의 범위만 닫는다.
BIS의 두 보드 20회×100 유효 SDU 개발 후보도
[W02 BIS 개발 원본](<../04_검증 기록/evidence/m31-w02-dev-candidate/m31-bis-dev-04.json>)에
보존했다. clean `c097b15d3f323d81751af269d348312a02dc1ca9`에서
[BIS exact positive manifest](<../04_검증 기록/evidence/m31-w02-exact-c097b15d/bis-manifest.json>)의
2,000/2,000 유효 SDU와 양 BIG 해제·재시작을 다시 확인했다. 이 positive 판정만으로
BIS 전체 subcase를 닫지 않았다. clean `078587471637db187e508db2deec7d091a8262ef`의
[BIS 전체 case](<../04_검증 기록/evidence/m31-w02-exact-07858747/bis-case-manifest.json>)는
20회×100의 매회 최소 99개 수신과 wrong broadcast code의 MIC failure·유출 0,
sync loss 뒤 각 100/100 새 BIG 복구를 확인해 `M31-ISO-01:bis`를 PASS로 판정했다.
이전 단계에서는 combined 세 보드 기능이 남아 있었고, 이후 clean `9e49bee2…`에서
native combined 기능을 닫았다. 최종 clean `e6ae812e…` package에서는 설치 ISO sketch
11개를 모두 빌드하고 CIS·BIS·암호화·두 negative·time sync·combined를 새 image로 다시
실행했다. [W02 closure audit](<../04_검증 기록/evidence/m31-w02-arduino-e6ae812e/closure-audit.json>)로
W02를 완료했으며 M31 작업 묶음은 2/8이다.
이 문장은 2026-09-16 당시 판정이다. [191번 재점검](<../04_검증 기록/191_M31_W02_공개_ISO_예제_재점검.md>)에서
공개 payload 예제 결함으로 W02 완료를 철회해 현행 분자는 **1/8**이다.
[192번 공개 CIS](<../04_검증 기록/192_M31_W02_공개_CIS_사용자_SDU_실기.md>)와
[193번 공개 BIS](<../04_검증 기록/193_M31_W02_공개_BIS_사용자_SDU_실기.md>)의
네 역할은 새 clean 실기 PASS이며, 나머지 7개 공개 ISO 역할은 진행 중이다.
clean `504badeec81723f4949879611b0b19371389b56d`의
[ISO time sync exact manifest](<../04_검증 기록/evidence/m31-w02-exact-504badee/time-manifest.json>)는
20회×100 receiver timestamp와 양 BIG 해제·재시작을 PASS로 판정했다. 첫 clean
99/100 실패는 [원본 감사](<../04_검증 기록/evidence/m31-w02-exact-0c7849c2/time-failure-audit.json>)로 보존한다.
Audio/DF raw IQ·CS procedure와 해당 역할 예제 기능 단계는 별도로 판정한다.
[W01 clean 감사 결과](<../04_검증 기록/evidence/m31-w01-exact-8c125a22/w01-closure-audit.json>)는
parity 703행, Host 오류 입력 20/20 거부, 전체 Host 회귀를 확인해 W01만 완료했다.
CI/CD 조회·실행은 이번 로컬 개발·커밋·푸시의 단계에 넣지 않는다.
