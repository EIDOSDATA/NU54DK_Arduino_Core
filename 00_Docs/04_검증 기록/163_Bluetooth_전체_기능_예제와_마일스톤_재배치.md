# Bluetooth 전체 기능·예제와 마일스톤 재배치

작성일: 2026-09-16

작업 성격: 계획·TODO·예제 제공 계약 정비. Firmware/API 구현 또는 새 HIL 완료 기록이 아니다.

## 1. 입력과 보존한 기준선

- 작업 저장소는 `NU54DK_Arduino_Core`, 작업 브랜치는 `m31-w01`이다. 시작 시 변경 없는 상태를
  확인하고 `git fetch origin`, `main` 전환과 `git pull --ff-only` 후 브랜치를 만들었다.
- 기반 Core는 `eff575da948f96fe8361b16f0475f7eb113ccf50`이며 요청한 최소 commit
  `ebe74f47e7d623c719eb8692489d750b2b4793a0`이 조상임을 확인했다.
- Board submodule 초기화·갱신 뒤 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`을 확인했다.
  Board/SDK/third-party/runtime code와 기계 원장을 변경하지 않았다.
- 고정 NCS v3.4.0의 nrf `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
  `bf801e4e3d19e1ffa76164346480cb7734dd2800`, nrfxlib
  `d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b`의 sample metadata·Kconfig·문서를 조사했다.
- 현재 설치·지원 버전 v0.4.1, 개발 소스 0.4.1-dev를 유지한다. M28/M29/M30 완료를 보존한다.
  M30은 8/8 작업·10/10 test ID, 실제 전원 차단 4지점 × 3회·12/12 PASS다. 실제 HIL source는
  `ae5186f7790a748641fb04128c16156519ee1017`, recovery failure 0, invalid image boot 0이다.
  NFC RF는 사용자 결정의 NOT RUN·지원 제외이고 실제 OOB는 유선 USB/DAPLink VCOM이다.

## 2. 사용자 결정과 재배치

사용자는 NU54DK 보드 3개만 보유한 조건에서 **nRF54L15에 적용 가능한 NCS 예제를 Arduino에서
실제로 사용할 수 있게 하는 것**을 핵심 목표로 확정했다. 정밀 RF 보정·음질·절대 거리/각도 정확도는
필수 gate 밖이다. 이를 지원되는 모든 기능의 build/runtime 자동 PASS로 해석하지 않는다.

| 트랙 | 새 계획·기능 소유권 | 구현 완료 |
| --- | --- | --- |
| M31 | W01 inventory/capability, W02 raw ISO, W03 Audio 11개 하위 기능군, W04 DF, W05 CS/RAS, W06~W08 통합·HIL·인계 | 0/8 |
| M32 | W01~W05 modern LE·Nordic 확장, W06~W08 Mesh 1.1·DFU, W09~W10 radio·공존, W11~W12 통합·마감 | 0/12 |
| M33 | W01 catalog, W02 GATT/beacon, W03 ecosystem, W04 DTM/HCI, W05~W08 예제·설치·통합·공개 | 0/8 |
| HOST | W01~W03 완료 유지; W04 Ubuntu prerequisite/path/권한, W05 cache, W06 CI/package, W07 실제 Host, W08 공개 | 3/8 |

- 신규 [전체 기능·예제 계약](<../01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)에
  기능별 source 근거·Arduino 제공 방식·예정 예제·보드 수·negative·owner·상태 축을 정리했다.
- [M31 TODO](../TODO_M31.md)를 전면 개정하고 [M32 TODO](../TODO_M32.md)와
  [M33 TODO](../TODO_M33.md)를 신설했다. ARF-01 role budget은 M32-W04로 통합했다.
  Throughput·표준 channel map 제어는 M32-W03, Nordic QoS survey는 M32-W05가 소유한다.
- M34~M45의 번호와 큰 주제는 유지하고 security/storage·Mesh DFU·radio/network/Thread/Matter의
  기능·예제 인계 관계를 명시했다. 비-BLE 무선은 BLE 전체 지원률에 합산하지 않는다.
- README·AGENTS·HANDOFF·v0.5.0 TODO·구현 로드맵·기능 매트릭스·경쟁 마일스톤·개선 계획·
  예제 배포·다중 Host 계약과 색인을 맞췄다. 과거 기록의 실패/HOLD/NOT RUN을 수정·삭제하지 않았다.

## 3. 실제 사용과 자동화 경계

- 예제는 `wrapper`/고급 `direct`/`profile`/독립 `template`/사유 있는 `excluded`로 제공한다.
  단순 API 이름 나열 대신 역할별 sketch·설치/compile·runner·예상 출력·종료·negative·증거를 요구한다.
- Raw ISO·합성 PCM/LC3와 Audio control·connected CS·modern LE·Mesh·DTM 등은 적용 가능한
  1~3보드 기능 HIL을 계획한다. DTM은 2보드 TX/RX·수신 수·역할 교대·유한 STOP을 포함한다.
- 고정 SDC의 DF TX experimental과 AoD 미지원, RX/IQ의 별도 controller/fixture, native USB
  controller 비적용을 구분한다. 합성 PCM 성공을 실제 audio I/O·음질로 확대하지 않는다.
- Apple/Google 등 외부 peer·credential, 실제 audio I/O, 필요한 antenna fixture와 실제
  Ubuntu/macOS 설치·USB upload·serial·debug는 해당 환경이 없으면 NOT RUN으로 남긴다.
- JSON schema/parser/generator와 `m31-ble-readiness.json` 및
  `ncs-v3.4.0-bluetooth-sample-parity.json`은 **M31-W01 구현 예정**이다. 문서만으로 생성·PASS 처리하지 않았다.
- Probe를 열거하거나 보드에 flash/명령을 보내지 않았다. 새 전원 차단·mass erase/recover·GPIO 조작은 0회다.

## 4. 검증

| 검사 | 결과 |
| --- | --- |
| 변경 전 전체 Host gate | PASS — 1,300 tests, 1,299 PASS + 설치 Arduino CLI 명시가 필요한 1 SKIP, 실패 0 |
| 변경 후 전체 Host gate | PASS — 1,300 tests, 1,298 PASS + 2 SKIP, 실패 0 |
| 로컬 CI contract·inventory·문서 gate | PASS — contract 46 tests, 원장/생성물·기존 release 계약 일치, Markdown 307개 UTF-8·상대 링크 |
| JSON·상태/owner 대조 | PASS — 추적 JSON 1,508개 parse, M31/M32/M33 작업 ID 8/12/8·기능 소유권·지원/실행 분리 대조 |
| 로컬 package gate·최종 diff check | PASS — package 21 tests, 작업/스테이징 diff 공백 오류 0 |
| 새 target build·HIL·실제 Ubuntu Host | NOT RUN — 이번 작업은 문서 정비 |

재현 명령은 저장소의 Python 가상환경에서 `python -B tools/ci/run_m12_gate.py`의
`host`, `contract`, `inventory`, `docs`, `package` gate를 실행한다. Windows의 실제 사용 가능한 `CXX`/`CC`를
명시하고 UTF-8 mode를 사용했다. 과거 문서의 다른 PC Python 경로가 이 PC에 없어 현재 저장소
가상환경을 사용했으며, 없는 경로의 명령 시도는 test FAIL로 집계하지 않았다.

변경 후 SKIP은 명시적 설치 Arduino CLI 입력이 필요한 1건과 문서 변경 중이라 clean checkout을
전제로 실행하는 `test_clean_submodule_status_survives_trimmed_first_prefix` 1건이다. 후자는 변경 전
clean 기준선에서 실행됐으며, 변경 중의 SKIP을 신규 실패나 물리 검증 성공으로 집계하지 않는다.

시작 시 `ebe74f47`의 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34979944172)는
success, [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34979944114)는
cancelled였다. 기반 `eff575da`의 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34986568631)는
success, [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34986568705)는
확인 당시 실행 중이었다. 이를 새 문서 commit의 CI 결과로 재사용하지 않는다.

최종 사용자 지시로 **이번 문서 commit의 CI/CD 실행 요청·확인은 생략**한다. 위 기존 CI 조회는
해당 지시 이전의 시작 상태 기록이며, 새 commit의 CI PASS를 주장하지 않는다. 문서 commit은
`m31-w01`에 push하고 exact commit을 종료 보고에 남긴다. 로컬 검증은 수행하며 `main` 병합·
force-push·공개 release는 하지 않는다.

## 5. 다음 구현

1. M31-W01의 전체 sample inventory/schema·capability parser·Host negative·target image와
   build matrix를 구현한다. 지원성 판정과 source/build/runtime 결과를 분리한다.
2. HOST-W04 Ubuntu 24.04 이상 AMD64 manifest·resolver/launcher·path/권한·udev·CI unit을 병행한다.
3. 실제 보드 시험을 시작할 때 SHA-256 identity·serial·role·firmware를 다시 대조한다. Mapping
   미확정이면 build까지만 수행하고 HIL을 NOT RUN으로 남긴다.
4. W01의 test별 유한 timeout·수량·정량/negative 계약과 적용성을 확정한 뒤 M31-W02 raw ISO로 이동한다.
