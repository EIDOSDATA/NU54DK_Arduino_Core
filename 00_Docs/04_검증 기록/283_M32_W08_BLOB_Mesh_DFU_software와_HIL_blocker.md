# M32-W08 BLOB·Mesh DFU software와 HIL blocker

> **과거 실패·준비 기록:** W08은 후속 clean exact 실행에서 BLOB 10/10회와 signed MDFU
> 5회 × 두 target 10/10 배포를 완료했다. 최종 결과는
> [294번 §8](294_M32_W08_BLOB_PASS와_MDFU_timeout_진단.md#8-최종-clean-exact-pass와-w08-마감)을 따른다.
> 아래 FAIL·NOT_RUN과 2026-10-01 원인 가설은 당시 상태로 보존한다.

> **2026-10-01 문서 재검토 — 원인 판단 보완:** §4의 UART 재개방 경합은 관측 증거에 따른
> 원인 가설이며, 최종 출력이 target UART·USB/VCOM·Host 수집 중 어디에서 누락됐는지는
> 직접 계측하지 않았다. 확인된 사실은 target B의 최종 `RESULT/END`와 세션 STOP 완료 증거가
> 수집되지 않았다는 점이다. 디버거의 완료 계수·정상 idle·CFSR/HFSR 0은 data path 완료를
> 뒷받침하지만 모든 오류의 부재나 공식 HIL PASS를 입증하지 않는다. 원본 FAIL은 유지하며,
> 결과 반복·중복 허용 보강의 효과는 새 clean HEAD의 exact 재시험 전까지 미검증이다.
> §3의 `5회 × 10 target 배포`는 분모 오기다. MDFU 계약은 **5회 × 2 target = 총 10회 배포**이며,
> 이 정정은 미실행 MDFU를 실행 또는 PASS로 바꾸지 않는다.

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W08` BLOB·Mesh DFU·Firmware Distribution |
| 구현 revision | 기반 `1a57eaae55acec26dd2903ab05c807062b6bfb9a`, model binding `b6d1630c…`, BLOB HIL `19c390ba…`, signed MDFU HIL `bceb1817…`, BLOB 관측 `8dcb033e…` |
| 고정 기준 | NCS `v3.4.0`, Zephyr `bf801e4e3d19…`, board package `fe65f2f0880b…` |
| software/build 판정 | **PASS — signed MDFU 네 exact sysbuild·build-set 검증 포함** |
| exact 실기 HIL | **FAIL — BLOB data path는 세 보드 10/10 완료, target B 최종 UART 증거 유실로 runner FAIL; MDFU NOT_RUN** |
| W08 작업 판정 | **진행 — BLOB 최종 증거 재전송 보강 후 exact 재확인과 MDFU HIL 필요** |

## 1. 구현 결과

`NUCODE_BLE_Mesh_Update` library와 `nucode.ble.mesh-update` feature를 추가했다. 공개 header는
Zephyr type을 노출하지 않고 다음 경계를 제공한다.

- 최대 네 target의 BLOB push/pull, raw BLOB Server receive, suspend/resume/cancel과 진행률
- 내부 inactive `slot1_partition`을 사용하는 bounded flash stream
- 최대 720,896 byte object, 4,096 byte block, 128 byte chunk와 단일 distribution slot
- SHA-256 staged image 검사와 MCUboot header·version·application core·composition hash metadata 검사
- `BOOT_UPGRADE_TEST`만 허용하는 test upgrade, 명시적 reboot와 정상 동작 뒤 image confirm
- Mesh DFU Target·Firmware Distributor model과 distribution phase 관찰

영구 upgrade 요청은 공개하지 않으며 실제 MCUboot 서명 검증은 bootloader trust boundary가 소유한다.
Mesh DFU profile은 Secure Connections pairing·bonding과 M30의 signed sysbuild를 재사용한다. 외장 flash가
없는 현재 NU54DK는 내부 slot만 지원하며, 비활성 overlay template와 적용·검증 안내를 제공했다. 외장
storage 실제 운용은 별도 사용자 후속 `NOT_RUN`이고 내부 slot 결과로 대체하지 않는다.

## 2. 예제·build 결과

Exact implementation source의 Arduino 예제는 **4/4 PASS**했다.

| 역할 | 예제 |
| --- | --- |
| BLOB | `MeshBlobClient`, `MeshBlobServer` |
| Mesh DFU | `MeshDfuTarget`, `MeshFirmwareDistributor` |

네 예제 모두 `secure_ble_dfu` profile에서 외부 validation key를 사용해 sysbuild했다. Test key는
검증 중에만 생성했고 저장소·manifest·문서에 private key 내용이나 경로를 넣지 않았다. MCUboot와
application domain, signed HEX/BIN, security counter, dual-slot layout과 public key 일치를 검사했다.

NU54DK native target `tests/zephyr/m32_mesh_update_contract`는 exact revision에서 PASS했다. 이 target은
API·Kconfig·link 계약용이므로 loaderless unsigned 경고를 허용하고, 실제 Arduino 경로는 위 signed
sysbuild 결과로 따로 판정했다. Footprint는 RRAM **277,712 B**, RAM **72,460 B**이며
`mesh_dfu_internal` 상한 RRAM 655,360 B, RAM 235,520 B 이하다. Build record의 Core revision은
`1a57eaae55ac`, board `fe65f2f0880b`, NCS `99553055607b`, Zephyr `bf801e4e3d19`, compiler는
GNU 14.3.0이다.

Host·생성 계약 검사는 다음과 같다.

- `test_m32_mesh_update.py`: 5/5 PASS
- `test_m32_mesh_update_hil.py`: 4/4 PASS
- `test_m13_profiles.py`, `test_p0_capabilities.py`: 60 PASS, 1개 환경 의존 검사 skip
- Arduino signed example smoke: 4/4 PASS
- example guidance: 179개 일치
- `git diff --check`: PASS

후속 `19c390ba…`에서는 provisioner BLOB Client와 두 BLOB Server target의 3-role target를 추가했다.
32 KiB deterministic object를 128-byte chunk 256개로 나누어 두 target에 10회 push하도록 고정해
client 분모는 5,120 chunk, target별 분모는 2,560 chunk다. 첫 전송 suspend/resume, 없는 AppKey의
동기 거부, target의 잘못된 SHA-256 거부, 정상 digest와 STOP cleanup을 bounded protocol에 포함했다.
공개 backend도 설치되지 않은 AppKey를 전송 시작 전에 거부하며, 완료 callback 뒤 Zephyr Client
progress가 0으로 초기화되는 동작은 공개 `UpdatePhase::completed`로 판정하도록 교정했다.

세 역할 native build는 모두 PASS했다. Footprint는 client RRAM **348,380 B**, RAM **82,655 B**,
target별 RRAM **343,228 B**, RAM **82,551 B**다. M32 Host 회귀는 77/77,
`m32_contract.py --check`는 PASS했다. 이 native image는 3-role compile·link와 runner 준비 결과이며,
exact 실기에는 같은 clean commit에서 역할별 image를 다시 만들고 signed profile·image hash를
확정해야 한다. 준비 결과를 signed Mesh DFU 배포 또는 rollback PASS로 확대하지 않는다.

후속 `bceb1817…`에서는 `FirmwareDistribution`의 slot metadata·receiver 등록·start/cancel과 Target·
Distributor foundation model dependency binding을 실제 NCS DFU/DFD backend에 연결했다. Sysbuild
HIL은 ECDSA P-256 MCUboot와 downgrade prevention을 사용하고 base 0.0.0+0/counter 1,
candidate 2.0.0+0/counter 2를 고정한다. 정상 배포는 5회 × 두 target으로 분모 10이며 처음 네 번은
두 target의 unconfirmed test image rollback, 마지막은 target A confirm과 target B rollback을
검증한다. wrong key·old version metadata·truncated image와 cancel/restart도 bounded protocol에
포함했고 runner는 CMSIS-DAP v2만 허용한다.

Clean exact source에서 Distributor·target A·target B·candidate 네 sysbuild와 build record를 다시
검사했다. 네 bootloader의 public key source hash는 같고, 세 base image에는 candidate signed BIN
343,442 B와 SHA-256 `ce66e4ad4015…`가 고정됐다. 역할별 signed image hash·version·security counter와
M32 Host 94/94, `m32_contract.py --check`, `git diff --check`가 모두 PASS했다. 세부 값은
[`build-audit.json`](<evidence/m32-w08-mdfu-preparation-bceb1817/build-audit.json>)에 보존한다. 이는
compile·link·서명·정적 build-set 판정이며 실제 Mesh transport·boot rollback PASS는 아니다.

## 3. exact HIL blocker와 다음 판정

F/G probe는 CMSIS-DAP v2 DP/AP identity를 통과하지만 E probe는 v2 interface·drive·COM 열거 뒤에도
DP/AP 조회에 응답하지 않아 세 역할을 동시에 확정할 수 없다. `bceb1817…` exact build 뒤에도 같은
결과를 유한 재확인했고 어떤 보드도 flash하지 않았다. V1 fallback은 사용하지 않았고,
mass erase·recover·unlock과 임의 flash는 수행하지 않았다. 두 runner는 clean source, 세 개의 서로
다른 V2 identity, sector flash, hardware reset과 `auto_unlock=false` 경계를 강제하며 evidence ID는
각각 `M32-BLOB-01:traffic`, `M32-MDFU-01:primary`로 분리한다.

따라서 다음은 아직 PASS가 아니다.

- BLOB Client/Server의 실제 10회 × 256 chunk/target, bad digest·wrong key·suspend/resume와 유한 재검증
- Distributor와 두 target의 5회 × 10 target 배포, image/object hash와 단계별 counter
- wrong image·version·key·부분 image 거부, unconfirmed test image rollback과 정상 confirm
- peer loss·취소·정상 reset 뒤 재시작, STOP·clock·buffer 반환
- `M32-BLOB-01`, `M32-MDFU-01` exact source/image/role 증거

새 실제 전원 차단 시험은 M36 범위이며 수행하지 않았다. E의 v2 DP/AP 접근이 복구되면 identity·role·
signed image hash를 다시 대조하고 sector 방식, `auto_unlock=false`로 BLOB traffic부터 재개한다.
이어 준비된 Distributor→두 target 배포·서명·rollback 분모를 실제 실행하기 전까지 W08을 완료
분자에 넣지 않는다.

## 4. 2026-10-01 BLOB exact 관측과 중단 지점

Clean source `8dcb033e0fcbf7e939fc7b8f45c9654ffba866b1`의 역할별 signed image를
CMSIS-DAP v2, sector flash, `auto_unlock=false`로 세 보드에 기록하고
`M32-BLOB-01:traffic` 10회를 실행했다. 실행기는 다음 이유로 FAIL을 기록했다.

- client는 두 target, 10/10회, 5,120 chunk, digest·suspend/resume·wrong key 거부를 완료했다.
- target A는 10/10회, 2,560 chunk, digest·bad digest 거부를 완료했다.
- target B는 마지막 회차 50% 뒤 VCOM이 조용해졌고 두 차례 재개방 뒤에도 `RESULT/END`가
  다시 오지 않아 `target_b serial progress timeout`이 발생했다.
- CMSIS-DAP v2 attach로 target B를 비파괴 halt해 확인한 결과 `iterations=10`,
  `received_chunks=2560`, `bad_digest_rejected=1`, `session_complete=1`, `failed=0`이었다.
  CFSR·HFSR은 0이고 CPU는 Zephyr idle에 있어 BLOB data path·digest·target 실행 fault는 없었다.

따라서 이 결과는 기능 전송 10/10 관측이지만 공식 HIL PASS는 아니다. 실패 원본은
[`m32-blob-01.json`](<evidence/m32-w08-blob-8dcb033e-exact/m32-blob-01.json>)과
[`m32-blob-01.transcript.log`](<evidence/m32-w08-blob-8dcb033e-exact/m32-blob-01.transcript.log>)에
보존한다. 레지스터·전역 상태 판정은
[`target-b-debug-analysis.json`](<evidence/m32-w08-blob-8dcb033e-exact/target-b-debug-analysis.json>)에
원시 probe UID 없이 별도로 남겼다. 원인은 STOP 전 최종 `RESULT/END`를 한 번만 출력하는 target와 45초 무응답 때 VCOM을
재개방하는 runner 사이의 경합이다. 최종 결과를 5초마다 반복하고 동일 중복 RESULT를 멱등 허용하도록
보강했다.

사용자 지시에 따라 이 지점에서 재시험과 MDFU를 시작하지 않는다. 다음 PC에서는 새 clean HEAD로
세 BLOB image를 다시 빌드해 `M32-BLOB-01:traffic` 10회 exact PASS를 확보한 뒤, signed MDFU 네
build를 같은 HEAD에서 다시 만들고 `M32-MDFU-01:primary`를 실행한다. 두 시험 전에는 W08을 완료로
승격하지 않는다.

## 5. 후속 결과

2026-10-02 `40e4c46b…` clean source의 BLOB 재시험은 10/10회·negative·세 역할 STOP/cleanup까지
PASS했다. 이 절의 과거 FAIL은 소급 변경하지 않는다. 이어진 첫 MDFU timeout과 보강 내용은
[294번 기록](294_M32_W08_BLOB_PASS와_MDFU_timeout_진단.md)이 소유한다.
