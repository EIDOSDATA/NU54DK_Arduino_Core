# M16 BLE NUS 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M16-001 |
| 문서 개정 | 1.0 |
| 상태 | **완료** — NUS Peripheral/Central 두 보드 HIL PASS |
| 적용 제품 버전 | `v0.2.0` |
| 기준일 | 2026-08-30 |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |
| 시작 기준 Core | `223fcddb7cd046b5e32c6e123307020254d1765f` — M15 문서 완료 commit |
| M16 구현·HIL 기준 Core | `3b47b86d10219acf96e9b0f5662242e543cf06ef` |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 변경 없음 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 최종 판정

M16은 공식 NCS Nordic UART Service service/client를 Arduino `Stream`으로 노출하고,
Peripheral/Central 양쪽 역할을 실제 NU54DK 두 대에서 검증한다. 이 문서는 API/구성의 정적
계약, Arduino example compile, target build와 실제 BLE link HIL을 분리해 기록한다.

Core `3b47b86d10219acf96e9b0f5662242e543cf06ef`에서 서로 다른 두 NU54DK에 role별 exact HEX를
기록했다. Central이 exact local name으로 Peripheral을 찾아 연결했고 1, 20, 21, 64 byte frame을
왕복했다. 그 뒤 명시적으로 연결을 끊고 자동 재광고·재검색으로 두 번째 연결을 만든 다음 21
byte를 다시 왕복했다. 두 역할의 user callback은 모두 Arduino main-thread 문맥에서 실행됐다.

HIL evidence의 최종 상태가 `passed`이고 양쪽 transcript의 strict protocol 순서, nonce,
frame/byte 합계와 재연결을 모두 만족했으므로 M16은 **완료**다.

## 2. 지원 판정 범위

| 영역 | 구현·시험 범위 | 판정 |
| --- | --- | --- |
| NUS Peripheral | local name, advertising, RX write 수신, TX notify 송신 | PASS |
| NUS Central | exact name scan, 연결, service discovery, notification subscribe, RX write 송신 | PASS |
| Arduino Stream | available/read/peek/write/flush/availableForWrite | HIL 수직 경로 PASS |
| Frame 경계 | 1, 20, 21, 64 byte; 재연결 뒤 21 byte | PASS |
| Lifecycle | disconnect 뒤 Peripheral 재광고·Central 재검색·두 번째 연결 | PASS |
| Callback 문맥 | Bluetooth callback 직접 호출 금지, `poll()`의 Arduino main 문맥 | 두 역할 PASS |
| Queue 경계 | RX 512 byte, event 16개, overflow 오류 계약 | host/target contract PASS |
| 동적 GATT/read/indicate | 구현하지 않음 | **범위 밖** |
| Bonding/SMP | 구현하지 않음 | **범위 밖** |

`bt_nus`의 RX characteristic write와 TX notification만을 검증했다. 이를 일반 GATT read,
indication 또는 임의 service 생성 지원으로 확대하지 않는다. 고급 사용자의 Zephyr `bt_*` 직접
사용 경로는 유지하지만 M16 HIL은 그 전체 API의 검증이 아니다.

## 3. 시험 자산과 결과

| 계층 | 자산 | 결과 |
| --- | --- | --- |
| 공개 API·구성 contract | `tests/host/test_m16_ble_contract.py` | 5/5 PASS |
| Pair runner·evidence contract | `tests/host/test_m16_ble_pair.py` | 9/9 PASS |
| M16 host 합계 | 위 두 suite | 14/14 PASS |
| Arduino source discovery/compile | `NUSPeripheral`, `NUSCentral` | PASS |
| Production target contract | `tests/zephyr/m16_ble_contract` | compile/link PASS |
| Role별 HIL image | `tests/zephyr/m16_ble_hil` | Peripheral/Central build PASS |
| 두 보드 물리 HIL | `tests/hil/nu54dk/m16_ble_pair.py` | PASS |

Host 회귀는 2026-08-30에 다음 명령 범위로 다시 실행해 14/14 PASS를 확인했다.

```text
python -m unittest tests.host.test_m16_ble_contract tests.host.test_m16_ble_pair -v
```

Arduino example compile과 production target build는 M16 구현 commit에서 통과한 결과를 사용한다.
물리 PASS는 아래의 exact role별 image와 raw UART transcript에만 근거한다.

## 4. 두 보드 HIL protocol

Runner는 Peripheral과 Central에 서로 다른 CMSIS-DAP UID, MSD volume과 UART port를 요구한다.
공개 문서에는 raw UID와 COM 번호를 싣지 않고 `보드 P`와 `보드 C`로 익명화한다. 로컬 evidence는
재현 추적을 위해 원본 식별자를 보존하지만 Git 추적 대상이 아니다.

실행 순서는 다음과 같다.

1. 두 UART를 먼저 열고 role별 HEX를 각 CMSIS-DAP MSD에 기록한다.
2. 두 image의 `READY` token을 확인한다.
3. 실행별 128-bit nonce를 Peripheral에 보내 advertising 시작을 확인한다.
4. 같은 nonce를 Central에 보내 exact name scan과 첫 연결을 시작한다.
5. 1, 20, 21, 64 byte payload를 Central→Peripheral→Central로 왕복한다.
6. Central이 연결을 끊고 두 role의 disconnect event를 확인한다.
7. 자동 재광고·재검색으로 두 번째 연결을 만든다.
8. 21 byte를 다시 왕복하고 양쪽 `FINAL:PASS`를 확인한다.

Strict parser는 이전 실행 nonce, 누락·잘못된 frame 크기, 106/21 byte 합계 불일치, 재연결 누락,
target FAIL과 FINAL 뒤 추가 protocol token을 모두 거부한다. 양쪽 final token이 모두 완결되기
전에는 evidence JSON을 PASS로 기록하지 않는다.

## 5. 실기 결과

| 역할 | 익명 보드 | 결과 |
| --- | --- | --- |
| Peripheral | 보드 P | advertising, 연결 round 1·2, 106 byte+21 byte 수신/echo, main-thread callback PASS |
| Central | 보드 C | scan, 연결 round 1·2, 1/20/21/64+21 byte echo, main-thread callback PASS |

세부 결과는 다음과 같다.

- 첫 연결 frame: `1`, `20`, `21`, `64` byte
- Peripheral 첫 연결 수신 합계: `106` byte
- 명시적 disconnect: `1`회
- 연결 round: `1`, `2`
- 재연결 뒤 frame: `21` byte
- Peripheral 재연결 수신 합계: `21` byte
- Callback context: Peripheral/Central 모두 `arduino-main-thread`
- 안전 조건: mass erase 요청 없음, PMIC write 실행 없음

## 6. Image와 build provenance

두 image는 같은 exact source/board/NCS/Zephyr provenance를 가지되 role compile define 때문에 HEX
digest와 크기가 다르다.

| 항목 | Peripheral | Central |
| --- | --- | --- |
| Core revision | `3b47b86d1021` | `3b47b86d1021` |
| Core source SHA-256 | `a8de62606c2035a4c65679e554097b6cd1a8b32ee948d4938966d24a9a3c0a9f` | 동일 |
| Application source SHA-256 | `2a61953fdabd5b7c8f7a645a55b974f14c173776bf1b313da3ae4944734acbb5` | 동일 |
| Board revision | `fe65f2f0880b` | `fe65f2f0880b` |
| Board source SHA-256 | `00305e847d6844c401a78f0dbf449c1c37dda4fd707afaacb43ca6217bf9f72e` | 동일 |
| NCS revision | `99553055607b` | 동일 |
| Zephyr revision | `bf801e4e3d19` | 동일 |
| HEX 크기 | `516337` bytes | `517298` bytes |
| HEX SHA-256 | `608eeb63a39ea0a18e5a1a5051c74ec2ecc2aa2a9bce7bd15e1521170a1b7437` | `3b08043ccb2dfffb776c1373ba6f61f0595728d45576b243ea1d6a0288c910cd` |
| Build record 크기 | `629` bytes | `629` bytes |
| Build record SHA-256 | `d846fab566b05f2c5e17492de0fd6d0493738fe067e423c2cd8b178329412495` | 동일 |

HEX와 build record의 크기·SHA-256은 HIL에 사용한 로컬 파일에서 직접 다시 계산했다. Evidence가
기록한 image digest와 일치한다.

## 7. Evidence와 transcript 무결성

| 자산 | 로컬 경로 | 크기 | SHA-256 |
| --- | --- | ---: | --- |
| PASS evidence JSON | `build/m16/hil/m16_ble_pair_3b47b86.json` | 4104 bytes | `08e882b3a121759d245265dbb6b9dac51474877f445e6f508cd41588ffa01de4` |
| Peripheral raw UART | `build/m16/hil/m16_ble_pair_3b47b86.peripheral.transcript.log` | 789 bytes | `c9efc0b24c7bf1bc9a622bbfba985067f65de67690e078c88b97d39f8bab3b2f` |
| Central raw UART | `build/m16/hil/m16_ble_pair_3b47b86.central.transcript.log` | 1105 bytes | `1a19df5e5118ead9cf6f31fe957797c16955bdeffb0af3702afe8c195cbe95ee` |

이 파일들은 로컬 `build/` 증적이며 Git 추적 대상이 아니다. 공개 문서에는 raw 장치 UID, MSD
root, COM port와 실행 nonce를 복사하지 않는다. 대신 exact Core/board revision, image/build
record와 evidence/transcript digest를 기록해 실행 provenance를 고정한다.

## 8. 제외·후속 범위

다음은 실행하지 않았고 M16 완료 증거로 사용하지 않는다.

- 동적/custom GATT service와 characteristic 생성
- GATT read와 indication
- pairing, bonding, SMP와 passkey
- BLE HID, Mesh, Channel Sounding와 ISO
- BLE/802.15.4/Thread/ESB multiprotocol
- RF 거리, throughput, 장기 soak와 저전력 전류 계측

NUS echo HIL의 성공을 위 기능의 지원으로 확대하지 않는다. Zephyr/NCS 공개 `bt_*` API 직접
사용은 가능하지만 각 기능은 별도 build/semantic/HIL 증거를 가져야 지원으로 선언한다.

## 9. 완료 조건과 다음 단계

M16은 NUS Peripheral/Central Stream, 두 Arduino 예제, `BLE NUS` profile, host/target contract와
두 보드 물리 HIL을 모두 통과했다. 이 명시적 범위에서 M16 상태는 **완료**다. 다음 단계는 M17
NCS v3.4.0 기능·예제 coverage record, 대표 sensor/direct build와 무선 기능 build feasibility다.
