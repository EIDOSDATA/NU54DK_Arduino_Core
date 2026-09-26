# M30 BLE Security·Profile·DFU 착수 계약

| 항목 | 고정값 |
| --- | --- |
| 대상 릴리즈 | `v0.5.0` |
| 착수 Core | `30699be4b58439fbd4c90ffb7df46009f7e893fe` |
| 기준 NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| 기준 Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| 기준 board | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 기준 toolchain | Windows bundle `dcbdc366a1` |
| stable 지원 릴리즈 | `v0.4.1`; 공개 RC는 [v0.5.0 TODO](../TODO_v0.5.0.md) 참조 |
| M30 상태 | **W01~W08 8/8 완료, test ID 10/10 PASS** |
| 기계 원장 | [`m30-ble-readiness.json`](../../variants/nu54dk/m30-ble-readiness.json) |

이 문서는 M30 구현 전에 보안 정책, OOB carrier, profile catalog, MCUboot layout, 신뢰키와 열 개의
유한 test ID를 고정했다. 설치·지원 v0.4.1의 기능 확대를 뜻하지 않는다. M30은 2026-09-15에
`M30-POWER-01` 네 지점 × 3회 실제 전원 차단 12/12까지 통과해 완료됐다.

## 1. 목표와 호환 경계

- M28의 generation 기반 최대 2-link에 link별 pairing·security·bond 상태를 추가한다. 기존 인자 없는
  `SecurityManager` API는 기존 우선 link view로 남기고 handle overload를 추가한다.
- 기존 IO capability 5종, LE Secure Connections, BAS/DIS/HID keyboard와 bond API는 회귀
  기준선이다. 새 기본 보안 profile은 legacy pairing을 끄고 최소 암호키 16 byte를 요구한다.
- OOB의 실제 carrier는 **wired USB/DAPLink VCOM**이다. 두 보드가 자체 VCOM으로 local SC OOB
  record를 내보내고 상대 record를 엄격히 읽은 뒤 주소·nonce·CRC가 맞을 때만 stack에 전달한다.
- NFC는 같은 OOB record를 NDEF로 변환하는 adapter source와 build/contract까지만 구현한다.
  안테나·RF HIL은 사용자 범위 결정에 따라 `NOT RUN`, 기본 OFF, `supported=false`다.
- 기본 loaderless profile과 기존 native HEX upload는 바꾸지 않는다. BLE DFU는 별도의
  `secure_ble_dfu` profile로만 제공한다.

## 2. 보안·키 수명주기

기본 `secure_ble_dfu`와 M30 안정 보안 경로는 LE Secure Connections 전용, 최소 encryption key
16 byte, IO가 허용할 때 MITM 필수다. legacy pairing과 M29 Signed Write는 별도 legacy opt-in에서만
허용한다. 연결 두 개에는 각각 pairing response 하나, bond lifecycle 하나와 generation handle을
둔다. stale generation callback이나 다른 link의 passkey/OOB/bond 결과를 전달하지 않는다.

Bond record는 peer resolved identity를 key로 사용하며 RPA 자체를 영속 key로 사용하지 않는다.
Identity key, LTK, key size, security level, local database revision과 record schema를 검증한다.
잘린 record, 미래 schema, 16 byte 미만 key, identity 불일치와 downgrade된 key는 fail-closed로
폐기한다. Migration은 이전 정상 record만 새 schema로 원자 변환하고 실패 시 기존 record를
부분 수정하지 않는다.

## 3. OOB carrier 계약

유선 frame은 schema, 송신 role, target identity address, SC randomizer와 confirm value, 128-bit
session nonce, payload 길이와 CRC를 포함하며 최대 192 byte다. 각 DAPLink VCOM은 보드의 probe UID와
COM port를 manifest에 명시하고, 여러 port 중 임의 선택하지 않는다. noise, 중복, 누락, 순서 변경,
wrong role/address/nonce/revision/CRC와 timeout을 모두 거부한다.

NFC adapter는 유선 경로와 같은 canonical record를 Bluetooth LE OOB NDEF payload로 serialize하고
parse한다. NFCT pin은 기본적으로 GPIO이며 P1.2/P1.3 `Wire`와 공유하므로 NFC profile에서만 전환한다.
실제 NFC antenna가 없는 현 보드에서 build 성공을 RF pairing 성공으로 기록하지 않는다.

## 4. Profile catalog

| 항목 | M30 정책 |
| --- | --- |
| BAS, DIS, HID keyboard | 기존 안정 API·회귀 기준선 |
| HID mouse | 고정 report map과 버튼·X/Y·wheel bounded report를 추가 |
| HID consumer control | 승인된 consumer usage의 고정 report를 추가 |
| Heart Rate Service | measurement·body sensor location·control point의 adopted UUID/형식 |
| Environmental Sensing Service | temperature·humidity의 adopted UUID/형식과 고정 범위 |

모든 service는 Bluetooth 시작 전에 등록하고, callback은 main-thread event로 전달한다. 임의 HID
descriptor 또는 모든 SIG profile 지원을 주장하지 않는다. Profile별 100 operation과 payload·link
격리를 두 보드에서 확인한 뒤에만 `candidate`를 안정 상태로 바꾼다.

## 5. 최소 secure BLE DFU

Nordic 고정 nRF54L15 CPUAPP partition을 그대로 사용한다.

| 영역 | offset | 크기 |
| --- | ---: | ---: |
| MCUboot | `0x000000` | 62 KiB |
| slot 0 | `0x010000` | 712 KiB |
| slot 1 | `0x0c2000` | 712 KiB |
| settings/storage | `0x174000` | 36 KiB |

MCUboot ECDSA P-256 서명 image와 MCUmgr SMP over BLE를 사용하고 transport는 authenticated encrypted
link에서만 연다. Repository에는 production private key와 공유 development private key를 커밋하지
않는다. Test key는 실행 workspace에서 생성하고 public key/hash만 build evidence에 남긴다. Production
사용자는 repository 밖의 key를 명시해야 한다.

초기 설치는 명시적 CMSIS-DAP UID로 MCUboot와 signed slot 0을 flash한다. 이후 BLE update는 slot 1
upload, hash·signature·security counter 검증, test boot, application self-test와 confirm 순서다.
Unsigned, wrong-key, corrupt/truncated, downgrade와 unconfirmed image를 거부하거나 이전 confirmed
image로 되돌린다. Reset 시험은 전원 상실 시험을 대신하지 않는다.

## 6. 작업 묶음

| 작업 | 구현·검증 내용 | 완료 gate |
| --- | --- | --- |
| M30-W01 | capability·정책·자원·test protocol + HOST-W01 inventory | Host 계약, capability target와 실제 1보드 |
| M30-W02 | generation link별 security·pairing·key lifecycle | IO capability 5종, 2-link stale/교차 event 0 |
| M30-W03 | 유선 OOB·bond/privacy migration, NFC adapter source | 유선 20회 HIL, NFC Host/target build와 RF `NOT RUN` |
| M30-W04 | HID mouse/consumer·HRS·ESS catalog | 두 보드 profile operation과 회귀 |
| M30-W05 | 고정 MCUboot layout·P-256 signing·초기 설치 | signed 20 boot, unsigned/wrong-key accept 0 |
| M30-W06 | 인증 BLE DFU·negative·rollback | update 10회, 5 negative class, rollback 검증 |
| M30-W07 | 1/2/3보드 통합 HIL | CAP~MULTI 9개 test ID PASS 후 실제 전원 차단 직전 정지 |
| M30-W08 | 실제 power-loss recovery·전체 회귀·문서·CI | `M30-POWER-01` 포함 10/10 PASS 뒤에만 완료 |

M30과 병행하는 `HOST-W01`~`HOST-W03`은
[다중 Host 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 따른다. W01은
Windows 전용 가정 inventory, W02는 OS/architecture·executable/path resolver, W03은 같은 Python
backend를 호출하는 얇은 `.cmd`/`.sh` 진입점이다. Linux/macOS prerequisite asset과 실제 Host
build/upload는 후속 HOST-W04~HOST-W07의 필수 `NOT RUN` 상태를 유지한다.

위 문장은 M30 종료 시점의 미실행 상태다. 현재 후속 순서는
[다중 Host 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)과
[전체 기능·예제 계약](19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md)을 따른다.
2026-09-21 결정으로 v0.5.0은 M31 완료 후 Windows 우선으로 릴리스한다. Ubuntu/macOS 구현·
자동 검사·검증 절차는 후속 Host 확대 범위이며 실제 설치·USB upload·serial·debug·수명주기는
해당 OS를 지원할 후속 릴리스 때 사용자가 검증한다. M31 Windows 공개는 이 장비를 기다리지
않으며 M30의 완료 수치·시험 정책은 변경하지 않는다.

이후 사용자 지시로 **Host 작업은 W01~W03 완료(3/8)에서 보류**했다. 위 구현 순서는 재개 시의
계약이며 HOST-W04~W08 착수 허가가 아니다. 최신 작업 범위는 [HANDOFF](../HANDOFF.md)를 따른다.

## 7. 고정 test ID

| Test ID | 보드 | 핵심 합격 조건 | timeout |
| --- | ---: | --- | ---: |
| `M30-CAP-01` | 1 | source/runtime capability 7군, revision mismatch 0 | 120초 |
| `M30-PAIR-01` | 2 | IO 5종 × 10회, 예상 밖 인증 실패 0 | 600초 |
| `M30-OOB-01` | 2 | 유선 SC OOB 20회·MITM 20회, mismatch accept 0; NFC RF 0회 | 600초 |
| `M30-BOND-01` | 2 | bonded reconnect 20회·privacy rotation 3회, stale key accept 0 | 900초 |
| `M30-PROFILE-01` | 2 | catalog 7개, service별 100 operation, payload 오류 0 | 900초 |
| `M30-BOOT-01` | 1 | signed boot 20회, unsigned/wrong-key accept 0 | 900초 |
| `M30-DFU-01` | 2 | BLE update 10회, hash mismatch·unconfirmed boot 0 | 1200초 |
| `M30-DFU-NEG-01` | 2 | 5 negative class × 20회, invalid/rollback accept 0 | 1200초 |
| `M30-MULTI-01` | 3 | 두 link security operation 각 100회, cross-link event 0 | 1200초 |
| `M30-POWER-01` | 2 | 4 injection point × 3회 실제 차단, recovery failure·invalid boot 0 | 1800초 |

모든 protocol은 full revision, role/image hash와 128-bit nonce를 사용한다. 정량 수치 미달, 필수
원본 log 누락 또는 reset만 수행한 전원 시험은 PASS가 아니다.

## 8. 자동 중단점과 실제 전원 조작

`M30-POWER-01` 실행은 image·runner·두 보드 manifest를 준비한 뒤 각 주입 창에서 멈추고 사람에게
DUT의 target USB 전원만 실제로 뽑았다가 다시 연결하도록 요청한다. DAPLink reset, CPU reset,
`west reset`은 인정하지 않는다.

전원 차단 지점은 slot 1 transfer, image validation/write, MCUboot test swap, 새 image 첫 boot의 네
상태이며 각 3회다. 각 복구에서 이전 confirmed image 또는 검증된 새 image만 boot하고, settings와
bond가 구조적으로 유효하며 DFU 재시도가 가능해야 한다. Programmable USB power switch가 확인되면
같은 protocol로 자동 주입할 수 있지만 현재는 이를 가정하지 않는다.

M30-W08과 M30 완료는 이 실제 시험과 영향 회귀·문서 마감 뒤에만 판정한다.
Exact `ae5186f7790a748641fb04128c16156519ee1017`에서 12/12 실제 차단, recovery failure 0,
invalid image boot 0을 확인했으며 [161번 완료 기록](<../04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)을
최종 근거로 사용한다.

### 8.1 2026-09-15 재개 조건 보완

과거 `05b639b4…` 준비/preflight PASS는 [159번 기록](<../04_검증 기록/159_M30_W08_전원_HIL_주입_직전_준비.md>)에,
재개 검증 보강은 [160번 기록](<../04_검증 기록/160_전체_문서_검토와_마일스톤_개정.md>)에 보존한다.
완료 실행은 A 도구·provenance 안정화, B 확정 image/manifest·preflight, 사람 준비 확인,
C 실제 12회 주입, D 증거·문서 마감을 따랐다. 기존 8개 작업·10개 test ID·12회 주입 기준은
변경하지 않았다.
