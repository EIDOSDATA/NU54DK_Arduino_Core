# M12 CI/CD와 재현 빌드 기준선

## 1. 목적과 현재 판정

M12는 GitHub-hosted software 검증, exact NCS 기반 재현 build와 self-hosted NU54DK HIL을
분리하는 단계다. 2026-08-29 기준 최종 결과는 다음과 같다.

- CI lock과 workflow 계약: **PASS**
- host/document/package/example-discovery 로컬 gate: **PASS**
- NCS v3.4.0 대표 Twister build-only 4개: **PASS**
- GitHub-hosted software gate 5개: **5/5 PASS**
- Linux/Windows 재현 build: **2/2 PASS**
- self-hosted NU54DK HIL workflow: **미실행**

물리 HIL은 수동 self-hosted workflow로 분리된 장치 gate이며 GitHub-hosted software 결과로
추정하지 않는다. 자동 trigger, runner label, 승인 secret와 장치 concurrency 경계까지 고정했으므로
M12의 CI/CD 및 재현 build 기반은 **완료**로 판정한다.

---

## 2. 검증 대상

| 항목 | 기준 |
| --- | --- |
| 저장소 기준 commit | `0f66017` (`fix(ci): NCS 내장 Python을 격리 실행`) |
| 운영체제 | Windows x64 |
| Python | GitHub Actions `3.12.10`; 로컬 기본 Python과 NCS toolchain Python |
| NCS | v3.4.0, `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | 4.4.0, `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Windows toolchain | `dcbdc366a1` |
| 보드 target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, 읽기 전용 |
| Arduino CLI | 1.5.1 |

동시 진행 중인 후속 마일스톤 파일은 M12 변경 범위에 포함하지 않았다.

---

## 3. 구현 결과

### 3.1 Workflow

| Workflow | Trigger | 결과 경계 |
| --- | --- | --- |
| `m12-software-gates.yml` | pull request, main push, 수동 | Windows host 및 Ubuntu document/package/example-discovery |
| `m12-reproducible-build.yml` | main push, 수동 | digest-pinned Linux Zephyr와 exact Windows Arduino build |
| `m12-nu54dk-hil.yml` | 수동 | self-hosted NU54DK pyOCD upload/UART |

기존 M10/M11 host suite의 PowerShell 5.1 runtime 계약 때문에 host job은 GitHub-hosted
Windows를 사용한다. HIL workflow에는 repository secret와 device concurrency lock이 있으며
PR이나 main push에서 자동 실행되지 않는다. 세 workflow 모두 외부 Action을 40자리 commit
SHA로 고정했다.

### 3.2 Canonical lock과 cache

`tools/ci/ncs-3.4.0.lock.json`에 sdk-nrf, sdk-zephyr, board package, Linux container digest,
Linux/Windows toolchain identity와 Arduino CLI version을 고정했다.

- Linux cache key: NCS revision + Zephyr revision + toolchain ID + container digest
- Windows cache key: NCS revision + Zephyr revision + toolchain bundle

공식 container는 NCS source가 아닌 toolchain이므로 exact source workspace 준비를 별도 단계로
구현했다.

---

## 4. 로컬 software gate 결과

### 4.1 Contract

```powershell
python .\tools\ci\run_m12_gate.py contract
```

검사 항목은 lock/repository 일치, cache identity, PR gate, digest pin, HIL 경계, Action SHA,
표준 예제 위치, ccache 비의존 및 Windows 짧은 Twister outdir 계약이다. 결과는 **PASS**다.

### 4.2 Host unit

```powershell
python .\tools\ci\run_m12_gate.py host
```

`test_m10_packaging.py`를 제외한 host test를 파일별로 실행했으며 결과는 **PASS**다. Package는
독립 job에서 실행하므로 같은 gate에서 중복 실행하지 않는다.

### 4.3 Markdown

```powershell
python .\tools\ci\run_m12_gate.py docs
```

Git이 추적하거나 새로 추가할 Markdown의 UTF-8 decode와 저장소 내부 상대 link를 검사했다.
결과는 **PASS**다.

### 4.4 Package

```powershell
python .\tools\ci\run_m12_gate.py package
```

기존 M10 package suite 17개를 실행했으며 **17/17 PASS**다.

### 4.5 Arduino example discovery

```powershell
python .\tools\ci\run_m12_gate.py examples `
  --arduino-cli "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
```

Arduino CLI `1.5.1`에서 표준 library 예제 7개를 열거했으며 결과는 **PASS**다.

---

## 5. Zephyr 대표 build 결과

NCS toolchain 환경에서 다음 명령과 동등한 Twister build-only를 실행했다.

```powershell
C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe `
  .\tools\ci\run_zephyr_build.py `
  --workspace C:\ncs\v3.4.0 `
  --outdir C:\t\m12-b
```

| Scenario | 결과 |
| --- | --- |
| `nucode.m3.runtime` | built, not run |
| `nucode.m4.api_contract` | built, not run |
| `nucode.m6.core_api` | built, not run |
| `nucode.m7.core_api` | built, not run |

Twister 최종 결과는 4개 선택, 4개 build-only 완료, failed 0, error 0, warning 0이며
총 355.59초가 걸렸다. `m12-build-evidence.json`도 생성됐다.

### 5.1 Windows 경로 관찰

저장소 아래의 긴 Twister outdir에서는 nRF Security/Cracen object 경로가 Windows legacy
`MAX_PATH`를 넘어 archive 입력 파일을 찾지 못했다. 이는 Core source나 API 결함이 아니라
실행 환경 경로 문제다.

같은 source와 toolchain을 `C:\t\m12-b` 짧은 outdir에서 다시 실행해 4/4 PASS를 확인했다.
회귀 방지를 위해 Windows에서는 32자 이하 outdir만 허용하도록 실행 script가 build 전에
검사한다.

---

## 6. GitHub Actions 원격 결과

| Workflow / job | Run | 결과 |
| --- | --- | --- |
| Software Gates — contract, host, documents, package, example-discovery | [33191659417](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33191659417) | **5/5 PASS** |
| Reproducible Builds — pinned Nordic Linux container | [33191659394](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33191659394) | **PASS** |
| Reproducible Builds — pinned Windows prerequisites | [33191659394](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33191659394) | **PASS** |
| Self-hosted NU54DK HIL | 수동 workflow | **미실행** |

Linux job은 `M12_ZEPHYR_BUILD_PASS=4`를 기록했고 evidence artifact `9694314540`의 upload
SHA-256은 `acace7728c6b8d38fd4840d16726989dc00b2928ccc13372b71588601da1c776`다.
Windows job은 `blink`, `m6`, `m7`, `examples` 네 gate를 통과했고 artifact `9694592854`의
upload SHA-256은 `7d7b67925b27b1a581a50e1b44eea889c47d93d7ed270fb926f27ce2f4c87fb7`다.

첫 Windows 원격 시도 [33190658940](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33190658940)은
GitHub Actions Python `3.12.10` 환경에서 NCS Python `3.12.4`의 `ctypes` 표준 library와 extension이
섞여 실패했다. `nu54-builder.cmd`가 NCS 내장 Python executable directory를 PATH 앞에 두고
`-I` 격리 mode로 Builder를 실행하도록 수정했다. 오염시킨 `PATH`/`PYTHONHOME`/`PYTHONPATH`
로컬 회귀와 위 clean Windows 원격 compile이 모두 통과해 수정 근거를 닫았다.

GitHub-hosted runner는 NU54DK가 없으므로 physical HIL 결과를 추정하지 않는다. HIL은 보드가
연결된 승인 self-hosted runner에서 필요할 때 별도로 실행한다.

GitHub는 고정 commit의 `arduino/setup-arduino-cli`가 선언한 Node 20 대신 Node 24 runtime을
강제 적용한다는 비차단 annotation을 남겼다. Action source와 설치되는 Arduino CLI `1.5.1`은
계속 고정·검증하지만 GitHub-hosted runner의 관리형 Node runtime 자체는 저장소가 고정하지
못하는 외부 실행 환경으로 기록한다.

---

## 7. 완료 판정

1. `0f66017` 기준 `M12 Software Gates`의 다섯 job이 성공했다.
2. 같은 commit의 `M12 Reproducible Builds` Linux와 Windows job이 성공했다.
3. exact lock, cache 재검증, 실패 log와 evidence 보존 계약이 원격에서 실행됐다.
4. self-hosted HIL은 장치 사용 시 수동 실행하고 software 결과와 별도로 기록한다.

따라서 M12는 완료다. HIL 미실행을 PASS로 바꾸지 않았으며, 물리 장치가 필요한 후속
마일스톤의 완료 근거로 재사용하지 않는다.

Release tag나 공개 asset을 만드는 자동 job은 M12에 포함하지 않았다. 최종 공개는 계속 사람의
승인을 요구한다.

---

## 8. 관련 문서

- [M12 CI/CD와 재현 빌드 설계](<../02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)
- [M9 증분 빌드, 캐시와 재현성 기준선](./09_M9_증분_빌드_캐시와_재현성_기준선.md)
- [M8 업로드와 디버그 기준선](./08_M8_업로드와_디버그_기준선.md)
