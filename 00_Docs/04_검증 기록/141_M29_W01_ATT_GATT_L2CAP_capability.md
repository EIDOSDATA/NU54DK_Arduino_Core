# M29-W01 ATT/GATT·L2CAP capability 완료

> 이 기록의 진행률·미실행·다음 작업은 해당 W 단계 완료 당시의 상태입니다. 후속 W07-C의
> Signed Write·EATT 2보드 결과는 [147번 기록](147_M29_W07_Signed_Write_EATT_HIL_준비.md)에,
> 현재 작업과 남은 범위는 [v0.5.0 TODO](../TODO_v0.5.0.md)에 있습니다.

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| exact Core | `d604642b1b439fda2840f613f7f157672d801597` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| protocol | `M29CAP/1`, 14줄 고정 순서, 128-bit nonce |
| Host parser | **16/16 PASS** |
| target build | **1/1 PASS, warning 0** |
| `M29-CAP-01` | **7/7 PASS** |
| M29 진행률 | **W01 완료, 1/8** |

## 1. 구현·검증 범위

W01은 [M29 착수 계약](<../01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)과
[`m29-ble-readiness.json`](../../variants/nu54dk/m29-ble-readiness.json)에 공개 정책, 고정 자원과
10개 test ID를 고정했다. capability image는 고정 NCS에서 실제 `bt_enable()`·settings load,
dynamic GATT service와 LE CoC server 등록을 수행한다.

Host parser는 READY·BEGIN·IDENTITY·HOST·PROBE·CONTRACT·CAP 7개·END의 고정 순서를 검사한다.
noise, 누락, 중복, 재배치, stale nonce, wrong revision, Host 자원 부족, 등록 실패, 동적 PSM 범위
위반, 계약 상한 변경, SDK 상태 승격, target FAIL과 timeout을 거부한다.

## 2. 실제 보드 결과

| 항목 | 관측값 |
| --- | ---: |
| 보드 | M28 peripheral peer와 같은 DAP/UART, evidence에는 UID SHA-256만 기록 |
| UART | `COM14` |
| GATT dynamic service 등록 | 1 |
| LE CoC server 등록 | 1 |
| 할당된 dynamic PSM | 128 |
| ATT TX / prepare buffer | 8 / 8 |
| L2CAP TX MTU / buffer | 512 / 4 |
| EATT 설정 bearer 상한 | 2 |

원시 transcript와 구조화 증거는 다음 파일에 보존한다.

- [`m29-capability-evidence.json`](evidence/m29-w01-d604642b-cap/m29-capability-evidence.json)
- [`m29-capability-evidence.transcript.log`](evidence/m29-w01-d604642b-cap/m29-capability-evidence.transcript.log)

## 3. 실패 분류와 수정

첫 build 실행은 긴 Twister 경로와 시스템 Python의 누락 의존성 때문에 image 생성 전에 닫혔다.
고정 toolchain Python만 지정했을 때는 DLL 검색 경로가 완전하지 않아 역시 build 전 실패했다. 고정
bundle의 `environment.json`과 같은 PATH/PYTHONPATH/toolchain 변수를 적용해 환경 원인을 제거했다.

첫 실제 compile은 존재하지 않는 `BT_GATT_CHRC_RELIABLE_WRITE`를 사용한 오류를 냈다. 고정 Zephyr
API에 맞춰 characteristic에는 `BT_GATT_CHRC_EXT_PROP`, descriptor에는
`BT_GATT_CEP_RELIABLE_WRITE`를 사용하도록 수정했다. 같은 target을 깨끗한 출력 경로에서 다시
빌드해 warning 없이 PASS했다. HEX 경로 오기 1회는 flash 전 검증에서 거부됐고 실제 산출물을
열거해 같은 image로 재실행했다.

## 4. 지원 판정 경계

W01 PASS는 Host Kconfig와 local 등록 경로가 고정 target에서 실행된 근거다. 정적 source capability는
계속 candidate이며 long/reliable payload 교환, cache migration, CoC credit traffic, Signed Write와
EATT peer negotiation을 대신하지 않는다.

Signed Write는 `deprecated` legacy opt-in, EATT는 `experimental` opt-in으로 출력했다. 두 CAP의
probe 값은 `peer_required`이며 실제 지원 PASS가 아니다. 다음 작업은 M29-W02의 generation link별
GATT client context와 512-byte long read다.
