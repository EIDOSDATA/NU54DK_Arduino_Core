# 개발 인계 — P2 잔여 작업과 M31 후속 순서

최종 정리: **2026-09-25**. 작업 브랜치는 **`M31-MEM-OPT`**이며 P0·P1은 완료,
**P2는 미완료**다. 이번 변경은 문서 정비이며 새 firmware build·보드 실기·메모리 축소가 아니다.
다음 실행의 단일 체크리스트는 [M31 TODO — P2 남은 작업](TODO_M31.md#p2-남은-작업--세-축)이다.

## 1. 바로 이어서 할 작업

P2의 남은 기술 작업은 아래 **세 축**이다. 문서·영향 회귀·커밋·푸시는 각 축의 마감 절차이며
네 번째 기술 과제로 세지 않는다.

| 순서 | 작업 | 남길 결과 |
| --- | --- | --- |
| 1 | 지원 범위의 오류·최악 부하 계측: CoC 상대 credit 고갈, Audio 지원 다중 stream·암호화 오류, CS 최대 절차 중 peer 이탈 후 복구 | 역할·용량·입력·최대 시간·복구 판정, 실제 송수신/STOP·오류 증거와 같은 수명의 stack/heap 관찰값 |
| 2 | 위 부하의 stack/heap 안전 여유와 최종 크기 결정 | 예약량·관찰 최고치·여유·할당 실패·계측 한계, 유지/조정 이유와 변경 영향 재검증 |
| 3 | 동일 조건 Nordic native 대비 FLASH/RAM 비용 비교 | 고정 SDK/board/controller·기능/보안/MTU·codec/stream·로그/계측 조건 대조, ELF/map별 차이와 최소 API 비용·불필요한 중복 구분 |

첫 행동은 **CoC 상대 credit 고갈을 로컬 송신 버퍼 포화와 구분하는 유한 시험 조건을 고정**하는 것이다.
기존 [257번](<04_검증 기록/257_M31_P2_CoC_송신_버퍼_부하와_복구.md>)은 로컬 `net_buf` 네 개를
채운 시험이지 상대 credit 고갈 증거가 아니다. 지원하는 선언 용량 안에서 오류·복구와 메모리를
함께 계측하며, 물리 전원 차단·임의 다중 link·모든 조합을 새 필수 조건으로 추가하지 않는다.

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
| M31 | **W01~W03 완료 3/8**, W03 Audio 11/11. W04·W05 미완료, W06~W08 미착수 | [readiness](../variants/nu54dk/m31-ble-readiness.json) · [W02](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) · [W03](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>) |
| 메모리 P0 / P1 | 기능 선택·정적 저장소 최적화 완료. adaptive는 실험적 선택지, standard/full 기본값 유지 | [P0](<04_검증 기록/222_M31_메모리_최적화_P0_완료.md>) · [P1](<04_검증 기록/237_M31_메모리_최적화_P1_정적_저장소_완료.md>) |
| P2 CoC | 두 채널 512 B, 로컬 송신 포화 후 ACL 재연결·서버 SWD reset 각각 20/20 | [257번](<04_검증 기록/257_M31_P2_CoC_송신_버퍼_부하와_복구.md>) |
| P2 Audio/ISO | 기본 CIS/BIS 각 20세션, Audio 양방향 각 10,000 frame·drop 0, 즉시 종료 20/20 | [240번](<04_검증 기록/240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md>) · [258번](<04_검증 기록/258_M31_P2_Audio_양방향_장시간과_종료_복구.md>) |
| P2 DF / CS | DF beacon TX 20/20; CS 256-step 유효 raw 1,000건·양측 STOP, gap 3은 비차단 | [259번](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>) · [260번](<04_검증 기록/260_M31_P2_CS_누락_분류와_256_step_장시간.md>) |
| M32 / M33 / Host | 0/12 / 0/8; HOST-W01~W03 완료 3/8, W04~W08 사용자 보류 | [M32](TODO_M32.md) · [M33](TODO_M33.md) |

이전 실행의 최근 전체 Host 기준선은 **1,499건 실행·2 skip·실패 0**이다.
이번 문서 변경의 검사는 [261번 문서 정비 기록](<04_검증 기록/261_P2_잔여_세_축_확정과_문서_전수_정비.md>)에
별도로 남긴다. 과거 Host 통과를 이번 재실행이나 새 HIL PASS로 표시하지 않는다.

## 3. P2 이후 순서 — P2 분모와 별개

1. P2 세 축의 결과·최종 크기·native 비교표와 변경 영향 회귀를 묶어 완료 여부를 판정한다.
2. 최적화 image로 **M31-W04·W05**의 채택 기능·예제·지원표·기계 원장과 잔여 기능을 마감한다.
   DF IQ RX 미지원을 수신 구현 의무로 바꾸지 않는다. W05 wrong-key/one-sided stale-key
   negative·과거 flash 직후 중단 경계는 [M31 TODO](TODO_M31.md)의 기능 계약에서 관리한다.
3. **W06**은 독립 role image별 자원·수명주기와 M19~M30 영향 회귀다.
   ISO·Audio·DF·CS 네 기능을 단일 MCU에서 동시에 실행하는 요구가 아니다.
4. **W07**은 적용 역할의 보드 HIL과 Windows 설치 예제 실행, **W08**은 원장·지원표·문서 마감과
   Windows package·clean 설치·RC 준비다.
5. M31 **8/8 기능 완료**와 **v0.5.0 공개**는 별도다. tag/Release/catalog 공개는 별도 사용자
   승인 후 수행한다. M32/M33·Ubuntu/macOS 확대와 보류한 Host 작업을 자동 재개하지 않는다.

## 4. 재개 전 확인과 고정 환경

| 항목 | 기준 |
| --- | --- |
| 실제 저장소 / 브랜치 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `M31-MEM-OPT` |
| 문서 정비 시작 HEAD | `b3ef5e9d2687cb5c3225a0b31b1709231530e5ae`; 이후 현재 SHA는 `git log -1`로 확인 |
| Target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS / Zephyr | v3.4.0 · `99553055607b2e9885fbc80ccd11fa9da81c2df0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board gitlink / Windows toolchain | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` / `dcbdc366a1` |
| SDK lock | [ncs-3.4.0.lock.json](../tools/ci/ncs-3.4.0.lock.json), SHA-256 `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3` |

- [AGENTS](../AGENTS.md)와 현재 TODO를 읽고 branch·HEAD·미커밋 변경·원격 ref·submodule을 직접 확인한다.
  과거 main 분기·squash 지시를 재실행하지 않으며 사용자 변경을 reset으로 덮어쓰지 않는다.
- 마지막 실기 기록은 두 보드를 기본 CS image로 복구하고 STOP한 상태다. **현재 연결 상태의 보증이
  아니다.** 다음 HIL 직전 probe SHA-256 identity·COM·role·image hash를 재대조한다.
- probe lock·watchdog·명령 lease·양측 STOP·clock/핀 반환을 유지한다. 자동 mass erase/unlock/recover,
  임의 전원·USB·결선 변경을 하지 않는다. 원시 probe UID·인증 정보는 공개하지 않는다.
- 과거 source·image·실패 JSON과 공개 자산은 보존한다. 이력 대응은 [215번](<04_검증 기록/215_M31_W03_이력과_문서_정비.md>)·
  [221번](<04_검증 기록/221_main_마일스톤별_이력_정리.md>), 다른 PC 준비는 [Windows 환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)을 따른다.
- 안정된 변경을 `M31-MEM-OPT`에 커밋·푸시한다. main 반영·이력 재작성·release/tag는 수행하지 않는다.
  **CI/CD 실행 요청·조회·대기는 생략**하고 로컬 검사를 사용한다.
