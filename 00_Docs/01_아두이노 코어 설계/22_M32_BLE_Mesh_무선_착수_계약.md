# M32 BLE·Mesh·무선 확장 착수 계약

## 1. 범위와 기준선

이 문서는 `Dev-0.6.0-M32`에서 완료한 M32-W01~W12의 기계 판정 기준이다. 현재 stable은
Windows 10/11 x64용 v0.5.0이며, M32·M33은 v0.6.0 개발 범위다. M32 완료만으로 v0.6.0
릴리스나 stable 승격을 선언하지 않는다.

| 항목 | 고정값 |
| --- | --- |
| Target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | `dcbdc366a1` |
| 기계 원장 | [`m32-ble-readiness.json`](../../variants/nu54dk/m32-ble-readiness.json) |
| 생성·검증기 | [`m32_contract.py`](../../tools/bluetooth/m32_contract.py) |

NCS v3.4.1 변경·보안 영향은 [별도 검토](<../00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)로
관리한다. M32/v0.6.0의 위 pin은 유지한다. [v0.7.0](../TODO_v0.7.0.md)은 NCS v3.4.1 전체 SDK
전환 전용이며 기존 기능 호환·회귀·설치 검증만 수행하고 신규 기능을 추가하지 않는다.
M32는 **12/12 완료**이며 완료 증거는 [M32 TODO](../TODO_M32.md), 다음 M33 착수 경계는
[HANDOFF](../HANDOFF.md)를 따른다. 후속 개발은 통합된 `main`에서 시작하며 `Dev-0.6.0-M32`는
당시 exact source·검증 이력을 보존한다.

고정 SDK와 전체 sample 원장의 대조는 다음 두 명령을 함께 사용한다. 첫 명령은 전체 190개 sample,
474개 variant, 39개 source-only feature를 원본 SDK와 대조한다. 둘째 명령은 그중 M32 소유
sample 41개와 variant 74개, 기능·자원·시험 연결을 검사한다.

```powershell
python tools/bluetooth/m31_inventory.py --sdk-root C:\ncs\v3.4.0 --check
python tools/bluetooth/m32_contract.py --sdk-root C:\ncs\v3.4.0 --check
```

## 2. 독립 상태와 승격 규칙

기능마다 `source_candidate`, `nu54dk_native_build`, `arduino_build`, `runtime_capability`,
`functional_hil`, `external_peer_interop`를 독립 stage로 기록한다. `PASS`에는 40자리 exact revision과
저장소 안 evidence 경로가 모두 필요하다. `NOT_RUN`에는 revision이나 성공 evidence를 넣지 않는다.
Source 후보 또는 build 성공을 runtime·기능 HIL·외부 peer PASS로 승격하지 않는다.

필수 구현·자동 검사는 `developer/development`, 개발·릴리스 blocker로 유지한다. Apple/Google 등
외부 제품, 외장 저장소, 외부 1-wire 공존 신호의 실제 운용은 `user/user_follow_up/false/false`로
분리한다. Ubuntu/macOS 실물 Host 검증은 해당 OS 지원 릴리스의
`user/final_release/false/true` gate이며, 중간 M32 개발을 차단하거나 Windows v0.5.0 결과에
소급 적용하지 않는다.

## 3. Capability image와 build matrix

`tests/zephyr/m32_ble_capability`는 공개 Arduino 예제가 아닌 시험 전용 image다. 다음 두 구성을 같은
source에서 빌드한다.

| Matrix | 목적 | 연결 / 광고 set / identity / periodic sync |
| --- | --- | --- |
| `m32_capability_baseline_sdc` | 기존 2-link·1-set 계약 보존 | 2 / 1 / 1 / 1 |
| `m32_capability_extended_sdc` | modern LE feature page와 W04 확장 후보 | 2 / 3 / 3 / 2 |

Target은 legacy 또는 Read All Local Supported Features HCI 응답, page 수, 13개 표준 feature bit,
Host Kconfig, 자원 상한을 nonce와 exact Core/board/NCS/Zephyr revision에 묶어 출력한다. Parser는
잡음·부분 출력·과대 출력·중복·알 수 없는 ID·field 순서·nonce·role·image hash·revision·feature bit
재계산 불일치를 거부한다. Capability PASS는 기능별 연결 절차나 RF HIL PASS가 아니다.

## 4. 자원 상한과 충돌

nRF54L15의 물리 RAM은 256 KiB이고 기본 application slot은 712 KiB다. 모든 M32 profile은
RAM 230 KiB, RRAM 640 KiB를 넘지 않아야 하며 각각 26 KiB와 72 KiB를 최소 여유로 남긴다.
실측값은 각 profile build 뒤 별도로 채운다. 미측정 `null`은 0이나 PASS가 아니다.

BLE 기본 profile은 2-link·1 peripheral·1 advertising set·1 identity·1 periodic sync를 유지한다.
확장 profile과 ARF-01은 C1P1/C2P0/C0P2를 각각 독립 preset으로 두며 최대 2-link,
3 advertising set, 3 identity, 2 periodic sync를 넘지 않는다. 요청 초과는 fail-closed로 거부한다.

IEEE 802.15.4와 ESB의 같은 image 동시 소유는 금지한다. Mesh DFU와 각 단독 radio, BLE 최대 profile과
Mesh 관리 최대 profile의 단순 합산도 허용하지 않는다. W09 단독 TX/RX 뒤 W10에서 명시적으로 통과한
coexistence profile만 함께 사용할 수 있다. 후보 조합은 제품 지원이 아니다.

## 5. 시험 분모와 안전 경계

Readiness의 24개 test family는 M32 12개 작업 묶음과 다른 분모다. 모든 case는 역할, 최소 보드 수,
반복 수, timeout, packet 분모, 허용 손실, 지연 상한, 30초 복구 상한, 즉시 중단 조건과 진단 재시험
최대 1회를 가진다. M32-CAP-01은 13개 capability record의 누락·중복·unknown·revision mismatch가
0인지 한 보드에서 확인한다. 나머지 기능 test는 소유 W02~W11에서 실행한다.

실물 실행은 SHA-256 probe identity, serial 경로, role, exact image hash와 source revision을 직전에
대조한다. Sector flash와 `auto_unlock=false`, 배타 lock, bounded UART lease를 사용한다. 자동 mass
erase·unlock·recover, 임의 GPIO·전원 차단은 금지한다. 종료 시 STOP·clock·핀·buffer 반환을 확인하며,
실패·HOLD·NOT RUN 원본을 후속 성공으로 덮어쓰지 않는다.

## 6. W01 완료 조건

W01은 다음이 모두 충족돼야 완료한다.

- 고정 SDK와 전체 parity 원장, M32 소유 41 sample·74 variant가 일치한다.
- Readiness schema와 정상/negative Host test가 누락·중복·unknown·revision drift·부당 PASS를 거부한다.
- Capability parser·runner와 baseline/extended target matrix가 exact source에서 빌드된다.
- 한 보드 extended SDC capability HIL에서 image/source/role/nonce와 13개 feature·자원 record를 대조한다.
- 문서·inventory·coverage·M31/M32 계약과 `git diff --check`가 통과한다.

W01 완료 뒤에도 W02~W10의 Arduino build, 기능 HIL, 외부 peer interop는 실행 전까지 `NOT_RUN`이다.

## 7. W01 완료 결과

Exact source `35aabc84ffb54240d28d82cff3beddba591c9a65`에서 baseline/extended 2개 구성을
warning 없이 build했고, SHA-256으로 식별한 capability 보드에서 두 image의 sector flash와 HCI query를
각각 PASS했다. Baseline은 8-octet legacy page와 2/1/1/1 자원, extended는 16-octet page와
2/3/3/2 자원을 보고했다. 두 profile의 RAM/RRAM은 61,364/199,564 B와 66,396/217,196 B로
고정 상한 안이다. 원본과 hash는 [277번 기록](<../04_검증 기록/277_M32_W01_capability_자원_시험_계약_완료.md>)이 소유한다.

Controller bit와 Host Kconfig가 모두 켜졌다는 사실만으로 연결 절차의 기능 PASS를 선언하지 않는다.
W02 이후 기능의 `functional_hil`과 `external_peer_interop`는 계속 독립적으로 판정한다.

## 8. W04 자원·build와 완료 근거

구현 commit `b8d0c0c1e46eeb119c61d40b4042ac319fda9dc9`에서 advertising contract,
scan/initiate contract와 ARF-01 C1P1/C2P0/C0P2 profile을 build했다. 세 preset은 다음 실제 linker
사용량으로 공통 RAM 230 KiB/RRAM 640 KiB 상한을 만족한다.

| Profile | 연결 / peripheral / 광고 set / identity / sync | RAM | RRAM |
| --- | --- | ---: | ---: |
| `ble_c1p1` | 2 / 1 / 3 / 3 / 2 | 65,280 B | 226,048 B |
| `ble_c2p0` | 2 / 0 / 1 / 2 / 2 | 60,344 B | 218,716 B |
| `ble_c0p2` | 2 / 2 / 2 / 2 / 1 | 61,248 B | 207,276 B |

Multiple set·identity/list·directed advertising·EAD·coding selection·scan while initiating API와
공개 예제 12개를 제공한다. Host 21 test, Arduino 12/12, target matrix 5/5가 PASS했다. 이 결과는
`nu54dk_native_build`와 `arduino_build`의 당시 근거이며 기능 HIL과 별개다. 이후 CMSIS-DAP v2
exact HIL에서 ADV·PRIV·EAD와 negative·역할별 STOP을 완료했다. W04는 완료이며 최초 접근 장애와
실패 시도는 [279번 기록](<../04_검증 기록/279_M32_W03_W04_software와_HIL_blocker.md>)에 보존한다.
최종 source·수치·완료 증거는 [290번 기록](<../04_검증 기록/290_M32_W04_광고_identity_privacy_exact_HIL_완료.md>)이 소유한다.

## 9. W05 Nordic 확장 완료와 미지원 경계

구현 commit `85da61226c770ead63ef97512b76cbb3c2bc338e`에서 `m32_nordic_sdc` 전용
target contract를 build했다. `ble_nordic` profile은 연결 2/peripheral 1/광고 set 1/identity 1/
periodic sync 1/방향별 ACL buffer 8이며 RAM 53,380 B, RRAM 184,132 B로 공통 상한을 만족한다.

LLPM·QoS connection event·channel survey·connection anchor time·event-start task·radio notification의
공개 API와 예제 8개를 제공한다. Host 회귀 21 test, Arduino 8/8, target 1/1이 PASS했다. 이 결과는
앞의 여섯 capability에 대해 `nu54dk_native_build`와 `arduino_build`만 PASS로 올린다.

LE Flushable ACL Data는 controller experimental Kconfig가 build되지만 고정 Zephyr Host에 flushable
LE ACL TX path가 없다. 따라서 target applicability는 `unsupported`, runtime은 `UNSUPPORTED`이고
functional/external HIL은 `NOT_APPLICABLE`이다. 이를 packet 기능 PASS로 계산하지 않는다.

후속 exact `f813356c…` CMSIS-DAP v2 HIL에서 `M32-NORDIC-01`·`M32-SYNC-01`·`M32-EVENT-01`의
적용 분모·negative·STOP을 PASS해 W05를 완료했다. `M32-ACL-01`은 고정 Host TX 경계의
`HOLD`이며 packet 기능 PASS가 아니다. 최초 접근 장애와 후속 완료 결과는
[280번 기록](<../04_검증 기록/280_M32_W05_Nordic_확장_software와_HIL_blocker.md>)에서 구분한다.
