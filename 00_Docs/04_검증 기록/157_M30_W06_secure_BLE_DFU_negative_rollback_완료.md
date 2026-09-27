# M30-W06 secure BLE DFU·negative·rollback 완료

## 결과

M30-W06을 고정 NU54DK 두 대와 NCS v3.4.0에서 완료했다. 별도 `secure_ble_dfu` profile의
MCUboot image management를 인증·암호화된 BLE L4 link 위의 SMP로 연결하고, exact Core
`df9ea2a3ee5111c350364a938409021d379810e2`에서 정상 update 10회와 다섯 negative class를
각 20회 검증했다. 미확정 image는 첫 부팅 뒤 confirm하지 않고 다시 reset해 이전 confirmed
image로 복귀하는 것도 확인했다.

| Gate | 결과 |
| --- | --- |
| W06 Host 계약 | **8/8 PASS** |
| 전체 Host 회귀 | **1,247 tests PASS, 2 skipped** |
| Peripheral target | **auto-confirm / unconfirmed 2개 build PASS** |
| Central target | **1개 build PASS** |
| 실제 `M30-DFU-01` | **signed BLE update 10/10 PASS** |
| image hash mismatch | **0** |
| unconfirmed normal boot | **0** |
| 실제 `M30-DFU-NEG-01` | **5 class × 20회 PASS** |
| invalid image accept | **0** |
| rollback accept | **0** |
| 실제 전원 차단 | **0 — W08 전용으로 유지** |
| M30 진행률 | **W06 완료, 작업 묶음 6/8·test ID 8/10 PASS** |

## 구현 범위

`NUCODE_BLE_DFU`는 MCUboot의 현재 image header 조회와 explicit confirm만 Arduino facade로
노출한다. 기본 loaderless profile은 그대로 두고, `secure_ble_dfu`에서만 MCUboot, dual slot,
image manager, OS reset manager와 인증된 BLE SMP transport를 활성화한다. BLE characteristic은
L4와 16-byte encryption key를 요구하고 ATT MTU 247, bounded CBOR/SMP packet, slot 1 전송을
사용한다.

Host runner는 외부에서 생성한 ECDSA P-256 신뢰키와 별도 오키를 사용해 version·security counter가
고정된 후보를 만든다. 저장소에는 private key나 key path를 넣지 않고 공개키 source SHA-256만
증적에 남긴다. raw probe UID, passkey와 OOB 비밀도 보존하지 않는다.

## 실제 시험

고정 Peripheral과 Central을 각각 exact probe·DAPLink volume·VCOM에 결박했다. Central은 실제
BLE L4 link에서 SMP packet을 중계했고 Peripheral은 slot 1에 image를 썼다. 정상군은 version
1~10을 순서대로 올려 각 회차에서 upload SHA, bootable state, test boot, 자동 confirm과 active
hash를 검증했다. 총 upload request는 13,070회였고 실행 시간은 1,182.140초였다.

negative 후보는 다음 다섯 종류다.

| Class | 반복 | state 거부 | boot 거부 | invalid accept |
| --- | ---: | ---: | ---: | ---: |
| unsigned | 20 | 19 | 1 | 0 |
| wrong key | 20 | 19 | 1 | 0 |
| corrupt payload | 20 | 19 | 1 | 0 |
| truncated TLV | 20 | 19 | 1 | 0 |
| downgrade counter | 20 | 19 | 1 | 0 |

각 후보의 첫 test 요청은 MCUboot가 boot 단계에서 거부하고, 이후 19회는 invalid secondary state로
즉시 거부했다. 따라서 각 20회의 분모를 모두 채우면서 실제 실행은 한 번도 허용하지 않았다.
마지막 unconfirmed v11은 첫 boot에서 `confirmed=0`을 확인한 다음 reset해 confirmed v10으로
복귀했다. negative·rollback 구간은 707.242초, 전체 HIL은 1,947.373초였다.

시험은 초기 bootloader·primary image의 exact flash와 inactive slot erase만 사용했다. chip/mass
erase, recover와 실제 전원 차단은 수행하지 않았다. reset을 power-loss 증거로 계산하지 않는다.

- [구조화 evidence](evidence/m30-w06-df9ea2a3-dfu/m30-dfu-evidence.json)
- [Peripheral transcript](evidence/m30-w06-df9ea2a3-dfu/m30-dfu-evidence.peripheral.transcript.log)
- [Central transcript](evidence/m30-w06-df9ea2a3-dfu/m30-dfu-evidence.central.transcript.log)

## 실패와 수정

- 첫 실기에서 MCUboot logical slot 번호와 flash area ID를 혼동해 primary를 `0`으로 기대했다.
  실제 API 계약인 primary area ID `1`을 검증하도록 고쳤다.
- 두 번째 실기에서 이미 진행 중인 bond encryption과 Central의 security 요청이 겹쳐 `busy`가
  발생했다. 이 상태를 실패로 끝내지 않고 기존 절차의 L4 완료 event를 기다리도록 고쳤다.
- 세 번째 실기에서 OS reset 응답 직후 이전 application의 `READY`를 새 부팅으로 오인했다.
  Central이 실제 BLE `UNLINK`를 관측한 뒤에만 Peripheral을 재동기화하도록 protocol을 보강했다.
- 전체 Host 회귀는 새 DFU target 두 개가 canonical build matrix에서 누락된 것을 찾았다. 두 role을
  v0.5.0 group에 등록하고 metadata와 canonical 목록의 일치를 회복했다.

각 실패 증적은 저장소 밖 작업 보존 경로에 분리했다. 원인 분류와 단일 수정 뒤 exact revision을
다시 build·실행했으며, 무한 재시도나 mass erase/recover는 사용하지 않았다.

## 다음 작업

M30은 **6/8 작업 묶음, 8/10 test ID PASS**다. M30-W07에서 세 보드로 두 secure link를 동시에
유지하고 link별 security operation 100회와 cross-link event 0을 검증한다. CAP부터 MULTI까지
아홉 test ID의 통합 상태를 확정하고 `M30-POWER-01` image·runner·두 보드 manifest를 준비한 뒤,
실제 target USB 전원 차단 주입 직전에 멈춘다.
