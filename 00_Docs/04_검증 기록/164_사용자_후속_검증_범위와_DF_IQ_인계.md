# 사용자 후속 검증 범위와 DF IQ 인계

작성일: 2026-09-16

작업 성격: 사용자 최종 결정에 따른 현행 문서·TODO·인계 계약 수정. 신규 기능 구현·target build·
실기 완료 기록이 아니다. 이번 종료 범위는 로컬 검사와 `m31-w01` 커밋·푸시까지이며 CI/CD는 확인하지 않는다.

## 1. 입력과 보존 기준

- 시작 branch는 기존 `m31-w01`, Core는 `2adbe1b2d44b99b1c7969780bf69bffc976c002a`다.
  시작 시 변경 없는 상태를 확인했다. 이번에는 main에서 다시 분기하지 않았다.
- Board submodule은 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`을 유지한다. NCS `v3.4.0`의
  nrf `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
  `bf801e4e3d19e1ffa76164346480cb7734dd2800`, nrfxlib
  `d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b`, Windows toolchain `dcbdc366a1`을 변경하지 않았다.
- 설치·지원은 `v0.4.1`, 개발 소스는 `0.4.1-dev`다. M28·M29·M30 완료를 보존한다.
  M30은 8/8 작업·10/10 test ID, 실제 전원 차단 4지점 × 3회·12/12 PASS,
  recovery failure 0·invalid image boot 0이다. 실제 source는
  `ae5186f7790a748641fb04128c16156519ee1017`이다. NFC RF는 NOT RUN·지원 제외이며
  실제 OOB는 USB/DAPLink VCOM이다. [161번 결과](161_M30_W08_실제_전원_HIL과_M30_완료.md)를 수정하지 않았다.
- [163번](163_Bluetooth_전체_기능_예제와_마일스톤_재배치.md)은 당시 조사·계획·검증 이력으로 보존한다.
  그 뒤 확정된 실물 검증 책임과 DF IQ 구분은 이 기록과 현행 계약을 우선한다.

## 2. 최종 사용자 결정

목표는 고정 NCS의 nRF54L15 적용 기능·예제를 NU54DK Arduino 환경에서 실제로 사용할 수 있게
하는 것이다. 추가 외부 장치를 기다리는 대신 사용 가능한 구현·예제·자동 검증을 진행한다.

| 범위 | 개발 중 필수 | 실제 운용·실물 검증 | v0.5.0 차단 정책 |
| --- | --- | --- | --- |
| 적용 가능한 보드 기능 | API/직접 경로·profile·예제·Host/target/Arduino 검사·가능한 1~3보드 기능 HIL | 현재 보드 mapping 확인 후 자동 실행 | 미해결 필수 구현·board-only 시험은 완료로 숨기지 않음 |
| Apple/Google·외부 ecosystem | 작동 가능한 기능·예제·설정/credential 입력 경로·자동 가능한 semantic/negative 검사 | 사용자 후속, 그 전에는 NOT RUN | 실제 제품 운용/interop 미실행은 개발·릴리스 비차단 |
| mic/speaker/codec·외장 장치 | 실제 연결용 구현·예제·설정/연결 안내·가능한 자동 검사 | 사용자 후속, 그 전에는 NOT RUN | 실제 외장 I/O 미실행은 개발·릴리스 비차단 |
| Ubuntu/macOS 실물 Host | prerequisite·path/권한·resolver/launcher·package·자동 검사·검증 절차 | 사용자가 최종 릴리스 단계에서 설치·USB upload·serial·debug·수명주기 검증 | 중간 개발 비차단, 해당 OS 정식 지원의 최종 실물 gate는 유지 |

Windows 회귀는 가능한 자동 개발 범위다. 정밀 RF·음질·절대 거리/각도 보정은 필수 gate 밖이다.
빈 template·success stub·합성 payload PASS를 정상 구현이나 실물 검증으로 대체하지 않는다.
외부 실물 검증의 비차단 결정은 실제 상호운용 보증이나 제품 인증 완료를 뜻하지 않는다.
새 power-loss 확장은 M36 후속이며 M32/v0.5.0의 추가 필수 사용자 시험으로 넣지 않는다.

정책의 단일 원본은 [전체 기능·예제 계약](<../01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이다.
미래 원장은 case별 `verification_owner`, `verification_stage`, `development_blocker`,
`release_blocker`를 가진다. 사용자 후속 외부 실물은 `user`/`user_follow_up`/`false`/`false`,
Ubuntu/macOS 실물은 `user`/`final_release`/`false`/`true`로 분리한다. 구현/예제/자동 검사는
별도 필수 case다. 이 필드·parser·원장·negative는 **M31-W01 구현 TODO**이며 이번에 생성하지 않았다.

## 3. DF raw IQ와 CS의 정확한 경계

원시 IQ report 수집, 안테나 전환, 실제 AoA 각도 산출을 서로 다른 기능·증거로 관리한다.

| 고정 source 근거 | 말할 수 있는 사실 | 아직 증명하지 않은 내용 |
| --- | --- | --- |
| nrf `subsys/bluetooth/controller/Kconfig`의 SDC DF 선택과 nrfxlib SDC 문서 | 기본 SDC는 AoA CTE TX를 제공하며 DF IQ RX/AoD 지원으로 확대할 수 없음 | 다른 LL 또는 SoC 전체의 RX 불가능 |
| Zephyr `subsys/bluetooth/controller/Kconfig.ll_sw_split`, `dts/vendor/nordic/nrf54l_05_10_15.dtsi`의 `dfe-supported` | 대체 Zephyr LL RX를 조사할 source 근거가 있음 | NU54DK RX target build/runtime PASS |
| Zephyr `samples/bluetooth/direction_finding_connectionless_rx/README.rst` | AoA antenna matrix는 optional로 안내됨 | 고정 RX sample의 nRF54L15 자동 지원; sample target 목록만으로 적용 가능 확정 |
| nrf `samples/bluetooth/channel_sounding/ras_initiator/src/main.c`의 `A1_B1`·peer antenna 1 | 기본 CS initiator/reflector 2보드 기능시험은 DF antenna-array 시험과 별개 | 정밀 거리 성능이나 DF IQ 수신 PASS |

따라서 M31-W01에서 기본 SDC TX와 Zephyr LL RX를 분리해 기본 안테나/배열 없는 NU54DK 구성의
적용성·Kconfig·DT·target build를 조사한다. W04에서는 build/runtime 적용 가능성과 mapping이
확인되면 두 보드로 IQ report/sample count·형식·status·start/stop·복구를 검증한다.
안테나 배열 구매·배선을 raw IQ 조사/build/HIL의 일괄 선행조건으로 요구하지 않는다.
실제 안테나 전환·각도 계산의 외장 확장 경로는 구현·설정/연결 안내 후 사용자 실기로 구분한다.
CS W05의 `A1_B1` 기본 기능 HIL은 독립적으로 진행한다.

기본 SDC 미지원은 그 controller의 제약이고, Zephyr LL source 존재는 후보 근거다.
NU54DK raw IQ RX는 이번에 build/HIL하지 않았으므로 `source_candidate`·실행 `NOT RUN`이다.
실험적 경로·실제 build 실패·미해결 결함을 지원 PASS로 만들거나 장비 부재로 위장하지 않는다.

## 4. 수정 범위와 검증

관련 Markdown 24개를 수정했다. AGENTS·README·문서 색인·HANDOFF·M31/M32/M33/v0.5.0 TODO·
제품 로드맵·기능 매트릭스·
경쟁/개선 마일스톤·전체 예제 계약·업로드/예제 배포/다중 Host 계약·CI/Windows 환경 안내·
저장소 구조·시험 계층·패키징 안내를 맞췄다.
완료 M30 계약에는 후속 Host 검증 시점만 보충하고 기존 test ID·수치·정책을 보존했다.
과거 실패/HOLD/NOT RUN과 공개 package·SDK·runtime code·기계 JSON은 변경하지 않았다.

| 로컬 검사 | 결과 |
| --- | --- |
| 변경 전 runtime 기준선 전체 Host | PASS — 1,300 tests, 1,298 PASS + 2 SKIP, 실패 0 |
| 변경 후 전체 Host | PASS — 1,300 tests, 1,298 PASS + 2 SKIP, 실패 0 |
| 문서 gate | PASS — Markdown 308개 UTF-8·내부 상대 링크 |
| 로컬 contract·inventory gate | PASS — 계약 46 tests, 생성물·기존 원장·release 계약 일치 |
| JSON·계획 분모 대조 | PASS — 추적 JSON 1,508개 parse, M31/M32/M33 작업 ID 8/12/8·HOST 완료 3/8 |
| 로컬 package gate | PASS — 21 tests, 실패 0 |
| 최종 diff 검토 | PASS — 작업/스테이징 공백 오류 0, 코드·JSON·gitlink 변경 없음 |
| 신규 target build·보드 HIL·Ubuntu/macOS 실물 | NOT RUN — 문서 작업이므로 수행하지 않음 |
| 원격 CI/CD | 확인 생략 — 최신 사용자 지시, PASS로 표시하지 않음 |

기준선은 runtime 변경 전에 시작했으나 문서 편집과 병행했다. SKIP 두 건은 설치 Arduino CLI 입력이
필요한 검사와 dirty checkout에서 생략하는 clean-submodule 검사다. SKIP을 통과로 계산하지 않는다.
로그는 작업 PC의 채팅 작업 디렉터리 `work/ble-plan-audit/scope-*.log`에 보존한다. 이 경로는
저장소 추적 대상이 아니며 다른 PC에서는 아래 명령으로 다시 검사한다. 실패 원본을 후속 성공으로
덮어쓰지 않는다. 이번 전체 Host 로그 identity는 다음과 같다.

| 로그 | SHA-256 |
| --- | --- |
| `scope-baseline-host.log` | `2221d94036cd13a189b06632ee8562869b5bccb5c813289124ea8969b6e0305c` |
| `scope-final-host.log` | `6baf4658530c920c800fd8bdf27203adb295e2f7d6d3b776c22966fad0e8dcd4` |

재현은 실제 사용 가능한 Python 환경에서 `python -B tools/ci/run_m12_gate.py`의 `host`,
`contract`, `inventory`, `docs`, `package`를 각각 실행한다. Windows에서는 현재 PC의 C/C++
compiler를 `CC`/`CXX`로 지정하고 `PYTHONUTF8=1`을 사용한다. 과거 PC의 절대 경로를 그대로
복사하지 않는다. Dirty 상태의 clean-submodule SKIP은 커밋 뒤
`python -B -m unittest discover -s tests/host -p test_m27_release.py -v`로 별도 재확인한다.

## 5. 다른 PC 재개

1. `AGENTS.md`와 [HANDOFF](../HANDOFF.md)를 읽고 기존 변경의 소유권을 확인한다.
2. `git fetch origin` 뒤 기존 `m31-w01`을 이어받아 `git pull --ff-only`한다. 로컬 branch가 없을
   때만 `git switch --track origin/m31-w01`로 만들고, 전달받은 exact commit이 HEAD에 포함됐는지
   확인한다. main 재분기·강제 reset/rebase/push를 하지 않는다.
3. 고정 submodule·SDK/toolchain과 전체 Host 기준선을 확인한 뒤 M31-W01 + HOST-W04를 구현한다.
   M31-W01 계약/원장/수집기/parser/negative/capability target과 build matrix 후 W02 raw ISO로 간다.
4. 보드 3개는 사용자 보유 조건일 뿐 현재 mapping 보증이 아니다. 실제 시험 전에 probe SHA-256
   identity·COM/serial·role·firmware revision을 다시 대조한다. 원문 UID를 채팅·문서·로그에
   노출/저장하지 않고 여러 probe 중 임의 선택하지 않는다.
5. 자동 mass erase/recover·전체 flash 초기화·임의 GPIO·전원 차단은 하지 않는다. mapping 미확정이면
   해당 HIL만 NOT RUN으로 남기고 독립 구현/build를 계속한다.
6. 최신 사용자 변경 전까지 CI/CD 실행 요청·조회·대기는 생략한다. Commit/push는 작업 branch에만
   수행하고 main 병합·force-push·tag/Release 공개는 별도 요청 없이 하지 않는다.

현재 구현 완료 수는 **M31 0/8·M32 0/12·M33 0/8·HOST 3/8**이다. 문서 정비 완료와 혼합하지 않는다.
