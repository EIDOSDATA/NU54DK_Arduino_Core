# NU54DK Arduino Core — M12 CI/CD와 재현 빌드

| 항목 | 내용 |
| --- | --- |
| 문서 ID | BUILD-CI-001 |
| 문서 개정 | 1.1 |
| 문서 상태 | 구현·원격 재현 기준선 완료 |
| 적용 제품 버전 | `v0.2.0` 이후 |
| 작성자 | Quantum / NUCODE |
| 기준 NCS | nRF Connect SDK `v3.4.0` |

---

## 1. 목적

M12는 개발 PC에서만 성공한 결과와 GitHub가 독립적으로 재현한 결과를 분리하고, software
검증과 물리 NU54DK 검증을 서로 다른 gate로 관리한다. 목표는 다음과 같다.

- pull request에서 빠른 host, 문서, package 및 Arduino example-discovery 회귀를 실행한다.
- main에서 exact NCS/Zephyr/Toolchain identity로 대표 Zephyr와 Arduino build를 재현한다.
- NU54DK를 요구하는 upload/UART HIL은 승인된 self-hosted runner에서만 실행한다.
- release 공개는 CI 성공만으로 자동 수행하지 않으며 사람의 승인 경계를 유지한다.

이 구조는 Loader 없는 Full Zephyr 정적 image와 기존 Build Adapter 계약을 변경하지 않는다.

---

## 2. 실행 계층

| 계층 | Trigger | 실행 환경 | 검증 내용 | 물리 보드 |
| --- | --- | --- | --- | --- |
| Software gate | pull request, main push, 수동 | GitHub-hosted Ubuntu/Windows | CI 계약, host unit, Markdown, package, Arduino 예제 열거 | 불필요 |
| 재현 build | main push, 수동 | 공식 Nordic container와 GitHub-hosted Windows | 대표 Zephyr Twister build-only, Arduino compile | 불필요 |
| NU54DK HIL | 수동 | NUCODE self-hosted Windows | pyOCD upload와 UART readiness | 필요 |
| Release | 별도 사람 승인 | 별도 release 절차 | 공개 version/tag/assets 판정 | 정책에 따름 |

GitHub-hosted 결과는 물리 보드 PASS를 추정하지 않는다. 반대로 HIL 한 번의 성공은 package,
문서 또는 exact dependency 검증을 대신하지 않는다.

### 2.1 Pull request software gate

[`m12-software-gates.yml`](../../.github/workflows/m12-software-gates.yml)은 다음 job을 독립적으로
실행한다.

1. `contract`: lock schema, workflow trigger, action SHA와 HIL 경계를 검사한다.
2. `host`: package 전용 시험을 제외한 Python host unit suite를 실행한다.
3. `documents`: Markdown UTF-8과 저장소 내부 상대 link 존재 여부를 검사한다.
4. `package`: Boards Manager package의 재현 생성과 구조 검증을 실행한다.
5. `example-discovery`: Arduino CLI `1.5.1`이 표준 library 예제 7개를 열거하는지 검사한다.

기존 M10/M11 host suite에는 Windows PowerShell 5.1 runtime 계약이 포함되므로 `host` job만
GitHub-hosted Windows에서 실행한다. 나머지 네 software job은 Ubuntu에서 실행한다.

`pull_request_target`은 사용하지 않는다. 따라서 외부 pull request 코드가 repository secret을
가진 권한 높은 context에서 실행되지 않는다.

### 2.2 Main 재현 build

[`m12-reproducible-build.yml`](../../.github/workflows/m12-reproducible-build.yml)은 두 운영체제
경로를 분리한다.

- Linux: digest로 고정한 Nordic toolchain container에서 exact NCS manifest를 별도 checkout하고
  M3, M4, M6, M7 Twister suite를 build-only로 빌드한다.
- Windows: 공개 prerequisite installer로 exact NCS와 toolchain을 설치 또는 검증한 뒤 Arduino
  CLI `1.5.1`로 Blink, M6, M7 및 표준 예제를 compile한다.

Windows Build Adapter는 GitHub Actions가 설치한 Python과 Nordic toolchain Python이 섞이지
않도록 NCS 내장 Python을 `-I`로 실행하고 `PYTHONHOME`, `PYTHONPATH` 및 사용자 site package를
격리한다. 이 경계는 clean runner의 PATH 순서에 의존하지 않는다.

Nordic container는 NCS source archive가 아니라 toolchain 환경이다. 따라서 container 실행만으로
NCS가 준비됐다고 간주하지 않고 `west init`, exact manifest fetch와 `west update --narrow`를
수행한다.

### 2.3 Self-hosted NU54DK HIL

[`m12-nu54dk-hil.yml`](../../.github/workflows/m12-nu54dk-hil.yml)은 자동 PR/main trigger가 없는
`workflow_dispatch` 전용이다.

- runner label: `self-hosted`, `Windows`, `X64`, `nu54dk-hil`
- repository secret: `NU54DK_HIL_AUTHORIZATION`
- device concurrency group: `nu54dk-hil-device`
- 실제 시험: 기존 M8 pyOCD upload와 UART readiness

장치가 없거나 runner가 offline이면 software CI는 계속 판정할 수 있지만 HIL은 별도 미실행 또는
대기 상태로 남는다.

---

## 3. Exact dependency lock

Canonical 입력은 [`ncs-3.4.0.lock.json`](../../tools/ci/ncs-3.4.0.lock.json)에 보관한다.

| 입력 | 고정 값 |
| --- | --- |
| sdk-nrf | `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| sdk-zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| NU54DK board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Linux toolchain ID | `fbf7391cab` |
| Windows toolchain bundle | `dcbdc366a1` |
| GitHub Actions Python | `3.12.10` |
| Arduino CLI | `1.5.1` |
| Container platform | `linux/amd64` |
| Container digest | `sha256:f1dca44678dae83e37404e33f369786f5b2ffe2ed497eec1815f66c3a868bace` |

Container tag는 사람이 읽기 위한 provenance이고 workflow image 선택에는 digest만 사용한다.
GitHub Action도 mutable tag가 아니라 검증된 40자리 commit SHA로 고정한다.

Cache key는 다음 identity를 포함한다.

- Linux: schema, NCS revision, Zephyr revision, toolchain ID, container digest
- Windows: schema, NCS revision, Zephyr revision, Windows toolchain bundle

Cache hit는 다운로드 최적화일 뿐 신뢰 근거가 아니다. 복원 후에도 source revision과 toolchain
identity를 다시 검사한다.

---

## 4. 출처와 license 경계

공식 container 근거는 다음과 같다.

- [Nordic `sdk-nrf-toolchain:v3.4.0` package](https://github.com/nrfconnect/sdk-nrf/pkgs/container/sdk-nrf-toolchain/949615715?tag=v3.4.0)
- [NCS v3.4.0 toolchain Dockerfile](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/scripts/docker/Dockerfile)
- [NCS repository v3.4.0](https://github.com/nrfconnect/sdk-nrf/tree/v3.4.0)

이 저장소는 Nordic container나 Windows toolchain을 재배포하지 않는다. CI가 공식 외부 배포본을
직접 가져와 사용한다. sdk-nrf source license는 `LicenseRef-Nordic-5-Clause`로 기록하고,
여러 구성요소를 포함한 toolchain 배포물은 단일 license라고 추정하지 않아 `NOASSERTION`으로
기록한다. J-Link가 필요하지 않으므로 J-Link license 자동 수락 환경 변수도 설정하지 않는다.

---

## 5. 로컬 진입점

CI workflow는 별도 구현을 중복하지 않고 다음 script를 호출한다.

| 파일 | 역할 |
| --- | --- |
| [`verify_ci_lock.py`](../../tools/ci/verify_ci_lock.py) | lock, repository, workspace identity 및 cache key 검증 |
| [`run_m12_gate.py`](../../tools/ci/run_m12_gate.py) | contract, host, docs, package, examples gate 실행 |
| [`prepare_ncs_workspace.py`](../../tools/ci/prepare_ncs_workspace.py) | exact NCS west workspace 준비 |
| [`run_zephyr_build.py`](../../tools/ci/run_zephyr_build.py) | 대표 Twister suite 4개 build-only 및 evidence 생성 |

대표 로컬 명령은 다음과 같다.

```powershell
python .\tools\ci\run_m12_gate.py contract
python .\tools\ci\run_m12_gate.py host
python .\tools\ci\run_m12_gate.py docs
python .\tools\ci\run_m12_gate.py package
python .\tools\ci\run_m12_gate.py examples --arduino-cli "<arduino-cli.exe>"
```

Windows에서 Twister를 직접 재현할 때는 nRF Security/Cracen object 경로가 legacy `MAX_PATH`에
걸리지 않도록 `C:\t\m12`처럼 짧은 outdir를 사용한다. 실행 script도 32자를 넘는 Windows
outdir를 build 전에 거부한다.

```powershell
C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe `
  .\tools\ci\run_zephyr_build.py `
  --workspace C:\ncs\v3.4.0 `
  --outdir C:\t\m12
```

---

## 6. Evidence와 판정 규칙

- software build artifact는 GitHub Actions run에 14일 보존한다.
- HIL artifact는 30일 보존한다.
- Zephyr evidence에는 board, scenario 목록, NCS/Zephyr revision과 container digest를 기록한다.
- `if: always()` artifact 단계는 실패 log도 보존하지만 실패를 PASS로 바꾸지 않는다.
- workflow가 실행되지 않았으면 `미실행`이며 PASS로 기록하지 않는다.
- release version, tag와 공개 asset은 CI가 자동 생성하지 않는다.

M12 완료 판정은 local 구현 존재만으로 내리지 않는다. 기준 commit `0f66017`에서
[Software Gates 33191659417](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33191659417)의
5개 job과
[Reproducible Builds 33191659394](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33191659394)의
Linux/Windows 2개 job이 모두 PASS했다. HIL workflow는 장치가 있는 self-hosted runner에서만
수동 실행하는 경계까지 검증했으며, 이번 software infrastructure 완료 판정에 물리 HIL PASS를
대입하지 않았다.

---

## 7. 현재 의도된 제약

- Windows Arduino build는 기존 prerequisite installer와 Windows 전용 Build Adapter 계약을
  사용한다. Linux container에서 Arduino package 전체를 빌드할 수 있다고 추정하지 않는다.
- GitHub cache 용량 또는 eviction은 외부 서비스 상태다. cache miss에서도 exact dependency를
  다시 준비해 같은 검증을 수행해야 한다.
- self-hosted runner 등록, 장치 연결 및 secret 설정은 NUCODE 운영 책임이다.
- BLE, Thread와 셀룰러 같은 후속 기능 suite는 각 마일스톤에서 추가하며 M12가 지원 범위를
  선행해서 주장하지 않는다.

---

## 8. 관련 문서

- [M12 검증 기준선](<../04_검증 기록/14_M12_CI_CD_기준선.md>)
- [테스트와 검증 정책](../03_펌웨어%20설계/04_테스트와_검증.md)
- [Boards Manager 설치와 패키징](./06_Boards_Manager_설치와_패키징.md)
