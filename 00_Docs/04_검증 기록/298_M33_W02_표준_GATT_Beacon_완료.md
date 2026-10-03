# 298 — M33-W02 표준 GATT profile·Beacon 완료

## 1. 판정

`Dev-0.6.0-M33`의 exact 기능 source
`4ebd49521d4a6578beac91ebddbd1bf39d679db4`에서 표준 GATT profile facade와 공개 예제,
iBeacon·Eddystone UID·BTHome 송수신, Host 음성 경계, target build와 두/세 보드 HIL을
검증했다. NCS는 `v3.4.0`, board submodule은
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, Zephyr는
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, toolchain은 `dcbdc366a1`이다.

필수 구현·자동 검사·NU54DK 실기를 모두 통과했으므로 **M33-W02를 완료**하고 M33 진행률을
**2/8**로 올린다. Apple/Google 제품과 외장 Beacon 상호운용, BMS 재부팅 영속성, native
두 번째 peer 실물 거부와 장시간 soak는 이 판정에 포함하지 않는다. 이들은 `PASS`로
간주하지 않고 사용자 후속 또는 M33-W06의 독립 분모로 유지한다.

## 2. 구현 결과

- `NUCODE_BLE_Profiles`에 CTS·HTS·CSC·RSCS·ETS의 typed sensor facade, ANS와 BMS,
  native CGMS 및 OTS/OTC adapter를 추가했다. 공개 Sketch는 같은 연결 흐름을 서비스별로
  복제하지 않고 `StandardSensor`/`StandardCollector`에 모았으며, ANS·BMS·CGMS·OTS는
  목적이 다른 별도 예제로 유지했다.
- OTS/OTC는 RAM object 4개·각 512 byte·32-octet 이름, 48-bit object ID, 목록 이동,
  metadata, CoC read/write, create/rename/delete, cancel·disconnect·bounded retry를 제공한다.
  고정 SDK의 단일 native session 때문에 `CONFIG_BT_MAX_CONN=1`을 fail-closed로 요구한다.
- CGMS는 synthetic SFLOAT record와 SOCP/RACP의 고정 SDK 지원 범위를 사용한다. 실제 의료
  측정이나 의료기기 적합성을 주장하지 않는다.
- BMS는 암호화·bond·일회 무장·application authorization을 모두 요구하고, 요청 peer 한
  건만 삭제한다. 전체 bond 삭제와 소유가 입증되지 않은 기존 bond 삭제는 제공하지 않는다.
- GATT client가 실제 characteristic UUID를 독립 확인하도록 보강했다. 서비스 UUID가
  일치해도 잘못된 characteristic handle/UUID를 성공으로 전달하지 않는다.
- `BeaconAdvertiser`/`BeaconObserver`는 iBeacon, Eddystone UID, 비암호화 BTHome v2의
  encode/decode·filter와 malformed length/company/UUID/frame/version/reserved/range를
  공통 backend에서 처리한다. synthetic BTHome 값임을 예제에 명시했다.
- 기존 M30의 BAS·DIS·HID keyboard/mouse/consumer-control·HRS·ESS 7개는 기존 완료 수와
  증거를 보존한 채 source/Host 회귀만 수행했다. 신규 profile을 과거 완료 수로 재계산하지
  않았다. 기존 Generic GATT/NUS·동시 role·periodic/PAwR·보안·DFU와 Peripheral Fabric은
  catalog의 기존 owner에 연결하고 같은 기능을 새 W02 구현으로 중복 집계하지 않았다.

## 3. Exact 검사 결과

### Host와 build

| 검사 | 결과 |
| --- | --- |
| Beacon codec/HIL parser, profile codec/runtime/native/HIL, GATT UUID 경계 | **PASS**, 38/38 |
| 기존 profile·예제 안내 회귀 | **PASS**, 17 PASS + 환경 비적용 1 SKIP |
| M33 readiness 생성·저장 원장·승격 negative | **PASS**, 13/13 |
| `clang-format`과 `git diff --check` | **PASS** |
| 공개 예제 metadata·7개 안내 필드 | **PASS**, 196/196 |
| 공개 W02 예제 격리 Arduino build | **PASS**, Beacon 2개 + Profile 7개 = 9/9 |
| Profile target | **PASS**, standard server/client/watcher + native server/client = 5/5 |
| Beacon target | **PASS**, advertiser/observer = 2/2 |

전체 공개 예제 경계 감사에서는 W02 기능 밖의 기존 7개 Sketch가 남았다. 파일은
`RadioEventTrigger`, `ScalableBleResources`, `MeshBlobClient`, ESB 두 역할, IEEE 802.15.4
두 역할이며 W05 후보가 안내 경계를 보강한다. 이 7건을 W02 기능 실패나 W02 예제 9개의
PASS로 섞지 않았다.

### Profile 3보드 HIL

- standard server/client/watcher는 7개 profile, client 측정 30건, watcher 측정 25건,
  역할별 malformed ATT/GAP 거부 3건을 통과했다.
- server는 동시 link 최대 2개, ANS email 전달 5건, CCC 없는 send 거부 10건,
  dropped event 0을 확인했다.
- BMS는 새 시험 bond만 대상으로 금지 opcode·미무장 요청을 거부하고, server 삭제 1건과
  client 측 scoped cleanup 1건을 확인했다. watcher와 기존 bond 목록은 바뀌지 않았다.
- 세 역할 모두 종료 후 native link·link·pending·scan·advertising·watchdog가 0이었다.

### Native profile HIL과 bond 정리

- fresh phase에서 server/client 각각 L4 security 3/3, 숫자 비교 event 1회를 확인했다.
  OTS object operation 14건, CGMS 두 record, native control 7건, session 3건,
  정상 reconnect·CoC cancel·cancel 뒤 reconnect·read/write를 통과했다.
- 같은 exact image의 restored phase는 새 passkey event 0, bond 후보/검증 3/3과 L4 3/3을
  확인했다. fresh evidence hash를 선행 조건으로 묶어 한 실행의 재사용을 거부했다.
- 실기 뒤에는 exact pair와 이전 비공개 RAM ownership proof를 다시 검사했다. sector flash와
  `auto_unlock=false`를 사용하고 server/client에서 시험 소유 bond 각 1개만 제거했다.
  양쪽 모두 기존 목록 불변과 STOP 자원 0을 확인했다. mass erase·unlock·recover는 실행하지
  않았다.

### Beacon 2보드 HIL

- observer는 광고 600건을 수집했다. iBeacon 205, Eddystone 200, BTHome 195이며 unique
  sequence는 각각 30, 30, 29다.
- advertiser는 형식 전환 90회와 형식별 sequence 30회를 완료했다. semantic error와 dropped
  packet은 모두 0이고 callback context·codec negative는 `pass`다.
- 두 역할 모두 `STOPPED` 뒤 advertising·scan·device가 0이다.

## 4. 증거

Exact 공개 증거는
[`m33-w02-exact-4ebd4952`](<evidence/m33-w02-exact-4ebd4952>)에 보존한다.

- `standard-exact-001.json`과 transcript: standard 3보드 profile 분모·BMS scoped 삭제·STOP.
- `native-fresh-exact-001.json`, `native-restored-exact-001.json`,
  `native-pair-exact-001.json`: L4 fresh→restored exact chain.
- `native-owned-cleanup-exact-001.json`과 transcript: 시험 소유 bond 두 건의 제한 정리.
- `beacon-exact-001.json`과 transcript: 두 보드 600광고와 종료 자원.
- profile 역할별 build record 5개와 `arduino-examples-summary.json`: exact source/image/hash와
  공개 예제 9/9 build.

개발 중 실패와 진단 기록은 기존 `m33-w02-profile-development-20261003`과
`m33-w02-beacon-development-20261003`에 남겨 두었다. 최종 판정은 위 exact 폴더만 사용한다.

## 5. 남은 경계와 다음 작업

1. Apple/Google 제품, 외장 Beacon·센서 상호운용은 사용자 후속 `NOT_RUN`이다. build와
   보드 간 synthetic peer 결과를 실제 제품 상호운용 PASS로 확대하지 않는다.
2. BMS 재부팅 영속성, native 두 번째 peer 실물 거부와 장시간 재연결/부하 시험은 W06의
   회귀 분모로 유지한다.
3. 긴 격리 경로에서 관측한 GNU ar object 경로 문제는 짧은 exact 경로에서 재현되지 않았다.
   경로 길이 민감성 관측으로 남기며 SDK 결함으로 단정하지 않는다. HOST-W05는 M33-W06 뒤
   정식 OS별 경로 회귀를 수행한다.
4. 다음 작업은 M33-W03의 Fast Pair·ANCS·AMS 구현, credential fail-closed와 scripted peer
   HIL이다. 실제 Apple/Google peer 운용은 별도 사용자 후속으로 분리한다.
