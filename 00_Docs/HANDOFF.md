# 개발 인계 — M31 완료와 v0.5.0-rc.1 공개, stable 승격 보류

최종 정리: **2026-09-27**. 작업 브랜치는 **`0.5.0-RC1`**이며 메모리 최적화
**P0·P1·P2와 M31-W01~W08 8/8을 완료**했다. W04의 지원 CTE TX·response 재검증과
제품 SDC IQ RX·AoD `UNSUPPORTED` 경계는 [263번 완료 기록](<04_검증 기록/263_M31_W04_Direction_Finding_완료.md>)이 소유한다.
P2의 오류·최악 부하, 최종 stack/heap 크기, 동등 Nordic native FLASH/RAM 비교 근거는
[262번 완료 기록](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)에 있다. W07의
설치 예제 49/49와 3보드 역할 HIL은 [266번 완료 기록](<04_검증 기록/266_M31_W07_설치_예제와_3보드_역할_HIL_완료.md>)이 소유한다.
W08 Windows RC 준비와 M31 마감은 [267번 완료 기록](<04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>)이 소유한다.
공개 `v0.5.0-rc.1` 게시와 인증 없는 다운로드·설치 smoke는
[268번 기록](<04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)이 소유한다.
이후 branch squash·`M31-MEM-OPT` 삭제와 문서 정비는
[269번 기록](<04_검증 기록/269_공개_RC_이력_Squash와_문서_전수_정비.md>)을 따른다.

## 1. 다음 작업

M31 기능과 Windows RC 준비, 공개 `v0.5.0-rc.1` Pre-release 및 공개 설치 smoke를 완료했다.
다음 단계는 RC 사용 결과를 검토한 뒤 정식 `v0.5.0` stable 승격 여부를 별도로 결정하는 것이다.

| 순서 | 작업 | 완료 결과 |
| --- | --- | --- |
| 1 | 공개 RC 관찰 | `v0.5.0-rc.1` 사용 결과와 미지원/후속 경계를 검토 |
| 2 | stable 별도 승인 | stable exact 자산·root catalog 변경·공개 설치 smoke 범위를 확정하고 승인 확보 |
| 3 | 승인 뒤 stable 공개 | `v0.5.0` tag/Release/root catalog 게시와 인증 없는 다운로드·설치 smoke |

### 다시 추가하지 않을 조건

- **NCS v3.4.0을 유지한다.** SDK/controller 교체는 P2 완료 수단이 아니다.
- nRF54L15 + 해당 제품 SDC의 **DF IQ RX는 `UNSUPPORTED`, P2 범위 밖**이다.
  [259번 지원 근거](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)를 따른다.
  Zephyr LL 연결형 내부 진단의 20 report·1,640 sample과 connectionless 실패·fault는
  역사 증거이며 제품 수신 PASS나 P2 재시험 의무가 아니다.
- **CS 간헐 RF/controller loss·counter gap은 비차단 관찰값**이다. 무손실·gap별 원인 규명·
  재전송 구현을 완료 조건으로 되살리지 않는다. 유효 raw·step·완료 수·양측 STOP,
  중복/역행 counter와 fault 검사는 유지한다.
- **SDC 내부 high-water 비노출은 추가 gate가 아니다.** 검증된 역할/count와 SDK 요구량·
  8-byte 정렬을 따른다. 안전한 축소 근거가 없으면 pool을 유지하고 그 이유를 기록한다.
  stack/heap도 무조건 줄이는 것이 목표가 아니다.
- 정밀 RF·음질·거리/각도 보정은 범위 밖이다. 외장 PDM/I2S·mic/speaker·상용 peer 실물은
  사용자 후속 `NOT RUN`·비차단이며 검증된 상호운용으로 표시하지 않는다.

## 2. 현재 상태와 증거

| 범위 | 현재 상태 | 원본 |
| --- | --- | --- |
| 공개 설치본 / 개발 소스 | stable·지원 `v0.4.1`; 공개 후보 `v0.5.0-rc.1`; source ID `0.4.1-dev` | [릴리스 안내](<05_릴리스/README.md>) · [RC 문서](<05_릴리스/v0.5.0-rc.1/README.md>) |
| M28·M29·M30 | 각각 8/8 완료. M30 실제 전원 차단 12/12 | [v0.5.0 계획](TODO_v0.5.0.md) |
| M31 | **W01~W08 완료 8/8**, 10개 family 판정 완료. Windows RC 이중 재현·설치 예제 113/113·수명주기·대표 upload/UART/debug와 공개 RC smoke PASS | [readiness](../variants/nu54dk/m31-ble-readiness.json) · [W08](<04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>) · [공개 RC](<04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>) |
| 메모리 P0 / P1 / P2 | **모두 완료**. adaptive는 실험적 선택지, standard/full 기본값과 기존 최종 크기 유지 | [P0](<04_검증 기록/222_M31_메모리_최적화_P0_완료.md>) · [P1](<04_검증 기록/237_M31_메모리_최적화_P1_정적_저장소_완료.md>) · [P2](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>) |
| P2 오류·최악 부하 | CoC peer credit 1 직접 고갈·4 SDU 복구, Audio 양방향 10,000 frame·wrong Code `-61` 후 100 frame 복구, CS 256-step 중 peer reset 뒤 raw 20개 복구 | [P2 원본](<04_검증 기록/evidence/m31-p2-three-axes-20260925/>) |
| P2 최종 크기 / native | MPSL 최소 관찰 여유 264 B 등으로 기존 크기 유지. CoC와 암호화 Audio 두 동등 쌍의 ELF/map 비교 PASS | [메모리 판정](<04_검증 기록/evidence/m31-p2-three-axes-20260925/memory-finalization.json>) · [native 비교](<04_검증 기록/evidence/m31-p2-three-axes-20260925/native-memory-comparison.json>) |
| M32 / M33 / Host | 0/12 / 0/8; HOST-W01~W03 완료 3/8, W04~W08 사용자 보류 | [M32](TODO_M32.md) · [M33](TODO_M33.md) |

M29-W01~W08의 계약·상태는 [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)과
[`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json), M30-W01~W08과
`M30-POWER-01`은 [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)과
[`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json)에 보존한다.

W08 실물·CI 기준선은 [267번 기록](<04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>),
공개 후 Host 회귀와 문서 감사는 [문서 원장](document-review.json)에서 source별로 확인한다.
W07의 설치 예제 49/49, 공개 예제 감사 113/113, 3보드 4-family HIL도 그대로 유효하다.
P2 build·HIL·메모리/native 비교는 [262번](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>),
W06 current build·Host·회귀와 당시 실물 `HOLD`는 [265번](<04_검증 기록/265_M31_W06_자원_수명주기와_영향_회귀_완료.md>)에,
전원 재인가 뒤 W07 최종 실기는 [266번](<04_검증 기록/266_M31_W07_설치_예제와_3보드_역할_HIL_완료.md>)에 분리했다.

## 3. M31 이후 순서 — stable 승격과 후속 개발은 별도

1. 완료한 **M31-W04~W08**의 증거와 실패/HOLD 원본을 다시 열지 않는다. 제품 SDC IQ RX·AoD
   `UNSUPPORTED` 경계도 수신 구현 의무로 바꾸지 않는다.
2. M31 **8/8 기능 완료**, **공개 RC**, **정식 stable**은 각각 별도다. `v0.5.0-rc.1`은
   공개했지만 stable tag/Release/root catalog는 별도 사용자 승인 후 수행한다.
   M32/M33·Ubuntu/macOS 확대와 보류한 Host 작업을 자동 재개하지 않는다.

## 4. 재개 전 확인과 고정 환경

| 항목 | 기준 |
| --- | --- |
| 실제 저장소 / 브랜치 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `0.5.0-RC1` |
| 공개 RC source | `v0.5.0-rc.1` → `7786984a186980f6220271cd506636e4564bc55d` |
| 정리된 개발 이력 | main `4b6afa7a...` 이후 squash 1개; 현재 SHA는 `git log -1`로 확인 |
| Target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS / Zephyr | v3.4.0 · `99553055607b2e9885fbc80ccd11fa9da81c2df0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board gitlink / Windows toolchain | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` / `dcbdc366a1` |
| SDK lock | [ncs-3.4.0.lock.json](../tools/ci/ncs-3.4.0.lock.json), SHA-256 `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3` |

- [AGENTS](../AGENTS.md)와 현재 TODO를 읽고 branch·HEAD·미커밋 변경·원격 ref·submodule을 직접 확인한다.
  과거 main 분기·squash 지시를 재실행하지 않으며 사용자 변경을 reset으로 덮어쓰지 않는다.
- W06 진단의 두 protected probe `HOLD`는 당시 원본이다. 전원 재인가 뒤 W07에서 세 보드의
  probe SHA-256 identity·COM·role·image hash와 DP/AP 접근성을 다시 결합했고 최종 HIL을 PASS했다.
  이후 실물 작업도 직전에 실제 연결 상태를 새로 확인한다.
- probe lock·watchdog·명령 lease·양측 STOP·clock/핀 반환을 유지한다. 자동 mass erase/unlock/recover,
  임의 전원·USB·결선 변경을 하지 않는다. 원시 probe UID·인증 정보는 공개하지 않는다.
- 과거 source·image·실패 JSON과 공개 자산은 보존한다. 이력 대응은 [215번](<04_검증 기록/215_M31_W03_이력과_문서_정비.md>)·
  [221번](<04_검증 기록/221_main_마일스톤별_이력_정리.md>), 다른 PC 준비는 [Windows 환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)을 따른다.
- M31 완료와 후속 문서는 squash한 `0.5.0-RC1`에 보존한다. `M31-MEM-OPT`는 사용자 요청으로
  삭제했고 원본 커밋은 공개 RC tag와 복구 bundle에 남아 있다. 이전 checkout을 갱신할 때는
  [재동기화 안내](../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)를 따른다.
  main 반영과 stable release/tag/root catalog 공개는 별도 단계다.
