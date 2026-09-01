# M12 CI/CD와 재현 빌드 기준선

## 1. 목적과 현재 판정

M12는 GitHub-hosted software 검증, exact NCS 기반 재현 build와 self-hosted NU54DK HIL을
분리하는 단계다. 2026-08-29 기준 최종 결과는 다음과 같다.

- CI lock과 workflow 계약: **PASS**
- host/document/package/example-discovery 로컬 gate: **PASS**
- NCS v3.4.0 현재 대표 Twister build-only 7개: **PASS**
- GitHub-hosted software gate 6개: **6/6 PASS**
- Linux/Windows 재현 build: **2/2 PASS**
- self-hosted NU54DK HIL workflow: **미실행**

물리 HIL은 수동 self-hosted workflow로 분리된 장치 gate이며 GitHub-hosted software 결과로
추정하지 않는다. 자동 trigger, runner label, 승인 secret와 장치 concurrency 경계까지 고정했으므로
M12의 CI/CD 및 재현 build 기반은 **완료**로 판정한다.

---

## 2. 검증 대상

| 항목 | 기준 |
| --- | --- |
| 최초 M12 완료 commit | `0f66017` (`fix(ci): NCS 내장 Python을 격리 실행`) |
| 현재 cache 기준 commit | `2d791cec614e7ee73334983c1dcdc927c179e94d` (`fix(ci): Windows 캐시를 Builder 범위로 축소`) |
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
- Windows Builder cache key: NCS revision + Zephyr revision + toolchain bundle + `builder-v1`

공식 container는 NCS source가 아닌 toolchain이므로 exact source workspace 준비를 별도 단계로
구현했다. Linux는 exact source workspace를 cache하고 Windows는 source/context 검증형 Builder
cache만 보존한다. Windows NCS와 toolchain은 매 run 공식 installer로 준비한 뒤 revision을
다시 검증한다.

양쪽 전체 NCS를 동시에 cache하면 압축 archive 합계가 11,668,878,529 byte가 되어
[GitHub 기본 repository cache 한도](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching#usage-limits-and-eviction-policy)
10 GB를 넘는다. 최종 구조는 Linux 3,680,507,477 byte와 Windows Builder 9,266,879 byte,
합계 3,689,774,356 byte만 유지한다. cache 경로에는 `.` 또는 `..` segment를 허용하지 않는다.

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

최초 M12 기준 결과는 4개 선택, 4개 build-only 완료, failed 0, error 0, warning 0이며
총 355.59초가 걸렸다. `m12-build-evidence.json`도 생성됐다. M14 구현 후 현재 gate에는
`m14.core_contract`, `m14.variant_contract`, `m14.pin_hil`을 추가했으며 원격에서 7/7
build-only와 QEMU actual-runtime 3/3을 통과한다.

### 5.1 Windows 경로 관찰

저장소 아래의 긴 Twister outdir에서는 nRF Security/Cracen object 경로가 Windows legacy
`MAX_PATH`를 넘어 archive 입력 파일을 찾지 못했다. 이는 Core source나 API 결함이 아니라
실행 환경 경로 문제다.

같은 source와 toolchain을 짧은 outdir에서 다시 실행해 4/4 PASS를 확인했다. 이후 AC-02B 전체
target gate에서 실제 archive 입력 object 경로가 261자에 도달하는 사례를 재현했다. 회귀 방지를
위해 현재 실행 script는 Windows에서 `C:\t\m12`처럼 **절대경로 전체가 8자 이하**인 outdir만 build
전에 허용한다. 이는 병렬 archive 경합 우회가 아니라 Windows legacy `MAX_PATH` 위험을 입력 단계에서
차단하는 계약이다.

---

## 6. GitHub Actions 원격 결과

### 6.1 최초 M12 완료 증적

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

최초 완료 run의 기능 결과는 유효하지만, 후속 로그 감사에서 Linux와 Windows cache 경로에
각각 `/../`와 `\..\`가 들어가 post-save를 거부한 사실을 확인했다. 따라서 최초 run을
cache 저장·복원 증거로 사용하지 않는다.

### 6.2 Cache 경로 수정과 용량 경계

`b454d0072336628e8bfbfbe7b18b76ca1fd1fd0c`에서 cache 입력을 정규 절대경로로 바꿨다.
[cold run 33199480089](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33199480089)은
Linux와 Windows 기능 gate를 모두 통과하고 양쪽 cache를 실제 저장했다. 같은 commit의
[warm run 33201447829](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33201447829)은
양쪽 exact primary key를 복원한 뒤 NU54DK build 7/7, QEMU 3/3과 Arduino 네 gate를 다시
통과했다. `Invalid pattern` 경고는 0건이었다.

다만 이 시험의 Linux archive는 3,680,507,477 byte, Windows full-NCS archive는
7,988,371,052 byte로 기본 quota를 넘었다. 경로 fix 증거는 보존하되 이 구성을 운영
기준으로 채택하지 않았다. `2d791cec614e7ee73334983c1dcdc927c179e94d`에서 Windows cache를
9,266,879 byte의 Builder 범위로 축소하고 7.99 GB cache를 삭제했다.

### 6.3 최종 cache 구조의 cold·warm 증적

| 실행 | Linux | Windows | 기능 결과 |
| --- | --- | --- | --- |
| [cold run 33202807554](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33202807554) | 기존 exact workspace cache hit | `builder-v1` miss 후 9,266,879 byte 저장 | NU54DK 7/7, QEMU 3/3, Arduino 4/4 PASS |
| [warm run 33204800541](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33204800541) | exact primary-key hit | exact `builder-v1` primary-key hit | NU54DK 7/7, QEMU 3/3, Arduino 4/4 PASS |

warm Linux [job 98963009158](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33204800541/job/98963009158)은
`M12_ZEPHYR_BUILD_PASS=7`, `M14_QEMU_RUNTIME_PASS=3`을 출력했다. artifact `9699440219`는
185,916,849 byte이며 upload SHA-256은
`23587523d6b5c70cd0535ee8096297caa0abd2474f55d0a4fd764ed8583fa6dd`이다.

warm Windows [job 98963008808](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33204800541/job/98963008808)은
exact NCS·Zephyr·toolchain revision을 다시 검사하고 `blink`, `m6`, `m7`, `examples`를 모두
통과했다. artifact `9699643416`은 443 byte이며 upload SHA-256은
`78fd77a4fbe68d701f5ac8ffb707b6a802780b42decd1b953655509c100cbf0e`이다. Windows job은
cold 25분 43초에서 warm 15분 59초로 줄었다. cache API에는 Linux `7100805117`과 Windows
Builder `7102167112` 두 항목만 남아 있으며 구 7.99 GB Windows cache는 재생성되지 않았다.

---

## 7. 완료 판정

1. `0f66017` 기준 최초 `M12 Software Gates` 다섯 job과 Linux/Windows 재현 build가 성공했다.
2. 현재 `2d791ce` 기준 software job 6/6, NU54DK build 7/7, QEMU 3/3과 Arduino 4/4가 성공했다.
3. Linux exact workspace와 Windows Builder cache의 cold-save·warm-hit를 각각 확인했다.
4. 최종 cache 총량은 3,689,774,356 byte이며, quota를 넘긴 7.99 GB Windows full cache를 제거했다.
5. exact lock, cache 후 revision 재검증, 실패 log와 evidence 보존 계약이 원격에서 실행됐다.
6. self-hosted HIL은 장치 사용 시 수동 실행하고 software 결과와 별도로 기록한다.

따라서 M12는 완료다. HIL 미실행을 PASS로 바꾸지 않았으며, 물리 장치가 필요한 후속
마일스톤의 완료 근거로 재사용하지 않는다.

Release tag나 공개 asset을 만드는 자동 job은 M12에 포함하지 않았다. 최종 공개는 계속 사람의
승인을 요구한다.

---

## 8. 관련 문서

- [M12 CI/CD와 재현 빌드 설계](<../02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)
- [M9 증분 빌드, 캐시와 재현성 기준선](./09_M9_증분_빌드_캐시와_재현성_기준선.md)
- [M8 업로드와 디버그 기준선](./08_M8_업로드와_디버그_기준선.md)
