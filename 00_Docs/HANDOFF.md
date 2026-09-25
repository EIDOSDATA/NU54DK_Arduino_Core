# 개발 인계 — M31-W04 완료와 후속 순서

최종 정리: **2026-09-25**. 작업 브랜치는 **`M31-MEM-OPT`**이며 메모리 최적화
**P0·P1·P2와 M31-W04를 완료**했다. W04의 지원 CTE TX·response 재검증과
제품 SDC IQ RX·AoD `UNSUPPORTED` 경계는 [263번 완료 기록](<04_검증 기록/263_M31_W04_Direction_Finding_완료.md>)이 소유한다.
P2의 오류·최악 부하, 최종 stack/heap 크기, 동등 Nordic native FLASH/RAM 비교 근거는
[262번 완료 기록](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)에 있다.
다음 실행의 단일 체크리스트는 [M31 TODO](TODO_M31.md#2-작업-묶음--8개-유지)다.

## 1. 바로 이어서 할 작업

P2와 W04를 다시 열지 않고 M31의 미완료 작업 묶음을 이어간다. 순서는 **W05 → W06 → W07 → W08**이다.

| 순서 | 작업 | 완료 결과 |
| --- | --- | --- |
| 1 | W05 Channel Sounding 마감 | 기존 secure RAS·256-step·P2 peer-loss 근거와 별도로 wrong-key·flash 직후 경계를 기능 계약대로 닫음 |
| 2 | W06 자원·수명주기·영향 회귀 | 독립 role image manifest, stop/disconnect 반환, M19~M30 변경 영향 회귀. 네 기능 전체 동시 실행은 요구하지 않음 |
| 3 | W07·W08 | 적용 역할의 HIL·설치 예제, 원장/지원표/문서·Windows package/clean install/RC 준비. 공개는 별도 승인 |

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
| 공개 설치본 / 개발 소스 | v0.4.1 단독 지원 / 0.4.1-dev | [지원 안내](<05_릴리스/v0.4.1/README.md>) |
| M28·M29·M30 | 각각 8/8 완료. M30 실제 전원 차단 12/12 | [v0.5.0 계획](TODO_v0.5.0.md) |
| M31 | **W01~W04 완료 4/8**, W03 Audio 11/11·W04 DF 완료. W05 미완료, W06~W08 미착수 | [readiness](../variants/nu54dk/m31-ble-readiness.json) · [W03](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>) · [W04](<04_검증 기록/263_M31_W04_Direction_Finding_완료.md>) |
| 메모리 P0 / P1 / P2 | **모두 완료**. adaptive는 실험적 선택지, standard/full 기본값과 기존 최종 크기 유지 | [P0](<04_검증 기록/222_M31_메모리_최적화_P0_완료.md>) · [P1](<04_검증 기록/237_M31_메모리_최적화_P1_정적_저장소_완료.md>) · [P2](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>) |
| P2 오류·최악 부하 | CoC peer credit 1 직접 고갈·4 SDU 복구, Audio 양방향 10,000 frame·wrong Code `-61` 후 100 frame 복구, CS 256-step 중 peer reset 뒤 raw 20개 복구 | [P2 원본](<04_검증 기록/evidence/m31-p2-three-axes-20260925/>) |
| P2 최종 크기 / native | MPSL 최소 관찰 여유 264 B 등으로 기존 크기 유지. CoC와 암호화 Audio 두 동등 쌍의 ELF/map 비교 PASS | [메모리 판정](<04_검증 기록/evidence/m31-p2-three-axes-20260925/memory-finalization.json>) · [native 비교](<04_검증 기록/evidence/m31-p2-three-axes-20260925/native-memory-comparison.json>) |
| M32 / M33 / Host | 0/12 / 0/8; HOST-W01~W03 완료 3/8, W04~W08 사용자 보류 | [M32](TODO_M32.md) · [M33](TODO_M33.md) |

이전 실행의 최근 전체 Host 기준선은 **1,499건 실행·2 skip·실패 0**이다.
P2 마감의 새 build·HIL·메모리/native 비교와 로컬 회귀는
[262번](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)에 분리했다.
과거 Host 통과를 이번 재실행이나 새 HIL PASS로 표시하지 않는다.

## 3. P2 이후 순서 — P2 분모와 별개

1. **M31-W05**의 잔여 기능을 마감한다. 완료한 W04의 제품 SDC IQ RX·AoD
   `UNSUPPORTED` 경계를 수신 구현 의무로 바꾸지 않는다. W05 wrong-key/one-sided stale-key
   negative·과거 flash 직후 중단 경계는 [M31 TODO](TODO_M31.md)의 기능 계약에서 관리한다.
2. **W06**은 독립 role image별 자원·수명주기와 M19~M30 영향 회귀다.
   ISO·Audio·DF·CS 네 기능을 단일 MCU에서 동시에 실행하는 요구가 아니다.
3. **W07**은 적용 역할의 보드 HIL과 Windows 설치 예제 실행, **W08**은 원장·지원표·문서 마감과
   Windows package·clean 설치·RC 준비다.
4. M31 **8/8 기능 완료**와 **v0.5.0 공개**는 별도다. tag/Release/catalog 공개는 별도 사용자
   승인 후 수행한다. M32/M33·Ubuntu/macOS 확대와 보류한 Host 작업을 자동 재개하지 않는다.

## 4. 재개 전 확인과 고정 환경

| 항목 | 기준 |
| --- | --- |
| 실제 저장소 / 브랜치 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `M31-MEM-OPT` |
| P2 실행 시작 HEAD | `46d4fb101513143d89b8533636e3ed671212fea4`; 이후 현재 SHA는 `git log -1`로 확인 |
| Target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS / Zephyr | v3.4.0 · `99553055607b2e9885fbc80ccd11fa9da81c2df0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board gitlink / Windows toolchain | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` / `dcbdc366a1` |
| SDK lock | [ncs-3.4.0.lock.json](../tools/ci/ncs-3.4.0.lock.json), SHA-256 `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3` |

- [AGENTS](../AGENTS.md)와 현재 TODO를 읽고 branch·HEAD·미커밋 변경·원격 ref·submodule을 직접 확인한다.
  과거 main 분기·squash 지시를 재실행하지 않으며 사용자 변경을 reset으로 덮어쓰지 않는다.
- 마지막 실기 기록은 W04 beacon STOP, 내부 connected receiver STOP, responder disconnect를
  확인한 상태다. **현재 연결 상태의 보증이 아니다.** 다음 HIL 직전 probe SHA-256
  identity·COM·role·image hash를 재대조한다.
- probe lock·watchdog·명령 lease·양측 STOP·clock/핀 반환을 유지한다. 자동 mass erase/unlock/recover,
  임의 전원·USB·결선 변경을 하지 않는다. 원시 probe UID·인증 정보는 공개하지 않는다.
- 과거 source·image·실패 JSON과 공개 자산은 보존한다. 이력 대응은 [215번](<04_검증 기록/215_M31_W03_이력과_문서_정비.md>)·
  [221번](<04_검증 기록/221_main_마일스톤별_이력_정리.md>), 다른 PC 준비는 [Windows 환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)을 따른다.
- 안정된 변경을 `M31-MEM-OPT`에 커밋·푸시한다. main 반영·이력 재작성·release/tag는 수행하지 않는다.
  **CI/CD 실행 요청·조회·대기는 생략**하고 로컬 검사를 사용한다.
