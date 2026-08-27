# M10 Boards Manager 패키징과 Clean Windows 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | **완료** — 원격 clean Windows 수명주기 11/11 통과 |
| 작성자 | Quantum / NUCODE |
| 검증일 | 2026-08-28 |
| 패키지 기준 Core | `5d965f83a6b8ce385d5014dfcae9b24e2fb0c1a1` |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 검증 run | `m10-20260828-045655`, 최종 상태 `passed` |
| Board FQBN | `nucode:zephyr:nu54dk` |

---

## 1. 목적

이 문서는 공개 Boards Manager preview package를 보유하지 않은 별도 Windows PC가
Git clone, 서브모듈 명령 또는 nRF Connect for VS Code의 기존 설치 없이 다음 수명주기를
재현하는지 검증한다.

1. 공개 package index 갱신
2. 최초 Core 설치와 Nordic prerequisite 설치
3. NU54DK board discovery
4. Blink cold/warm compile
5. 온보드 CMSIS-DAP V2/pyOCD Upload 10회
6. Core upgrade와 downgrade
7. Core uninstall 후 공유 Nordic prerequisite 보존
8. 최신 Core reinstall와 재빌드

설치·패키징 구조와 사용자 절차는
[Boards Manager 설치와 패키징](<../02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)에서
설명한다. 이 문서는 설계가 아니라 실제 실행 결과와 종료 판정을 소유한다.

---

## 2. 고정 입력

### 2.1 공개 index와 preview

공식 검증 index는 다음 URL이다.

~~~text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json
~~~

| 항목 | 값 |
| --- | --- |
| index SHA-256 | `b3593c2cd555b83f2af3d4c2c6b9f01569d507c8967f87a713291850158461f1` |
| 최초 설치·downgrade | `0.0.96` |
| `0.0.96` ZIP SHA-256 | `5b595a142834fee87272b6a48017e6a6c6767dcef38b932000c4effaf1eed296` |
| `0.0.96` ZIP size | `759,743 bytes` |
| upgrade·최종 reinstall | `0.0.97` |
| `0.0.97` ZIP SHA-256 | `699e9f05e818fee87a0c0ca390eb32cc3c6e3e19a1a8cdba0dccfb02cb49890f` |
| `0.0.97` ZIP size | `759,743 bytes` |
| 공통 runtime payload SHA-256 | `3d2bcd74d60d74ae3424a0efa0eadbec07e2db7995c5c8b4992acb8ac11314e2` |

두 ZIP은 각각 공개 GitHub prerelease의 immutable asset이다. 원격 실행기는 index의 URL,
size와 SHA-256뿐 아니라 ZIP 내부 `release-manifest.json`의 Core·board·NCS·Zephyr·Toolchain
identity를 설치 전에 고정한다.

`0.0.90`~`0.0.93`은 PowerShell 5.1, launcher 인코딩 또는 Windows build 경로 결함이
확인돼 공식 index에서 제외한다. `0.0.94`와 `0.0.95`는 PowerShell 5.1 runner의 비동기
Task 반환값이 success stream에 섞여 Arduino CLI identity preflight에서 실패했다. 이미
공개된 자산은 같은 tag에서 덮어쓰지 않고 immutable 실패 이력으로 보존한다. 최종 승인에는
반환값 누출 수정까지 포함한 `0.0.96`→`0.0.97` 수명주기만 사용한다.

### 2.2 Nordic prerequisite

| 구성 요소 | 고정 값 |
| --- | --- |
| nRF Util | `8.2.1` 및 고정 실행 파일 SHA-256 |
| sdk-manager command | `1.16.1` |
| nRF Connect SDK | `v3.4.0` |
| NCS revision | `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` |
| Zephyr revision | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain bundle | `dcbdc366a1` |
| pyOCD | Nordic Toolchain에 포함; 별도 binary 재배포·독립 version pin 없음 |

NCS, Zephyr, Nordic Toolchain, nRF Util과 pyOCD binary는 NUCODE ZIP이나 package index에서
재배포하지 않는다. 설치 script가 Nordic 공식 배포 경로에서 사용자 영역으로 내려받고 실제
byte와 revision을 위 pin에 대조한다.

---

## 3. Clean Windows 환경

대상은 개발 PC와 분리된 Windows x64 PC다. 공개 문서에는 host name, 사용자명, IP 주소,
SSH key와 probe UID를 기록하지 않는다.

| 항목 | 값 |
| --- | --- |
| Windows channel | Pro, `25H2` |
| OS build | `26200.9168` |
| architecture | `AMD64` |
| Windows PowerShell | `5.1.26100.9168` |
| Arduino CLI | `1.5.2-rc.1`, commit `fef6e48df` |
| Arduino CLI SHA-256 | `ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538` |
| 기존 `%USERPROFILE%\ncs` | 없음 |
| 기존 NUCODE prerequisite marker | 없음 |
| NU54DK | 온보드 CMSIS-DAP V2를 USB로 연결, probe 1개 요구 |

Arduino CLI executable도 version 문자열만 신뢰하지 않고 SHA-256까지 고정했다. 검증은
CLI backend를 사용한다. Arduino IDE GUI의 화면 동작을 자동으로 시험한 것으로 확대 해석하지
않는다.

---

## 4. 자동 실행 안전 계약

원격 실행기는 다음 조건을 지킨다.

- SSH host key를 `known_hosts`로 고정하고 password 입력 없이 공개키 인증만 사용
- 원격 저장소 clone 없이 SHA-256을 고정한 ASCII target runner와 설정만 전송
- 실행 fingerprint가 다른 기존 run을 resume하지 않음
- 단계 상태를 atomic JSON으로 기록하고 통과한 단계만 안전하게 resume
- 동시 실행 mutex와 abandoned mutex 복구
- Arduino data, download, sketchbook와 build 경로를 run 전용 디렉터리로 격리
- 로그의 credential, host 식별자와 probe UID를 공개 evidence에서 제거
- 일반 Upload에서 mass erase와 recover를 사용하지 않음

검증 명령은 다음 형태다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\remote-windows\m10\invoke-m10-clean-windows.ps1
~~~

실제 SSH identity와 대상 주소는 로컬 비밀 설정으로 전달하며 저장소에 커밋하지 않는다.

---

## 5. 단계별 결과

다음 표는 최종 `evidence.json`의 결과와 시간을 반영한다.

| 단계 | 결과 | 핵심 증거 |
| --- | --- | --- |
| preflight | **PASS**, 0.174 s | Arduino CLI version·commit·실행 파일 byte 일치, NCS·prerequisite·ready marker가 모두 없는 기준선 확인 |
| public index update | **PASS**, 4.092 s | 공개 index와 두 archive의 URL·size·SHA-256·provenance 일치 |
| `0.0.96` 최초 설치 | **PASS**, 2,058.160 s | Nordic 공식 배포에서 NCS v3.4.0과 Toolchain `dcbdc366a1` 설치, exact revision 검증 |
| board details | **PASS**, 0.250 s | `nucode:zephyr:nu54dk` discovery |
| Blink cold compile | **PASS**, 111.991 s | HEX `7e4f228442cca87424df10db60bde67eb74f2be1913df6bb8fc0bb52e4847a0b` |
| Blink warm compile | **PASS**, 5.975 s | 같은 build path 재빌드, cold와 동일한 HEX |
| CMSIS-DAP/pyOCD Upload | **PASS**, 72.979 s | probe 1개를 다시 확인하고 일반 Upload 10/10 성공 |
| `0.0.97` upgrade | **PASS**, 6.568 s | 설치 version, package manifest와 Nordic pin 재검증 |
| `0.0.96` downgrade | **PASS**, 6.136 s | 설치 version, package manifest와 Nordic pin 재검증 |
| Core uninstall | **PASS**, 1.046 s | Core 제거 후 공유 NCS와 `ready.json` 보존 |
| `0.0.97` reinstall | **PASS**, 75.228 s | prerequisite 재사용, 68.945 s Blink 재빌드와 동일 HEX 확인 |

전체 run은 2026-08-27 19:57:04 UTC부터 20:37:11 UTC까지 약 40분 7초가 걸렸다. NCS와
Toolchain은 Core ZIP에 포함하지 않고 Nordic 공식 배포에서 받았다. 최종 hash-bound
evidence는 prerequisite identity와 revision을 기록하지만 다운로드 byte와 설치 후 디스크
사용량은 수집하지 않았으므로 이 문서에 용량 수치를 게시하지 않는다.

---

## 6. 복구 시험과 폐기 preview

공개 검증 과정에서 다음 결함을 발견하고 새 immutable preview로 수정했다.

| preview | 증상 | 원인 | 처리 |
| --- | --- | --- | --- |
| `0.0.90` | PowerShell target runner 초기 실패 | 빈 결과의 `.Count`가 StrictMode에서 예외 | 배열 강제 변환과 host 회귀 추가 |
| `0.0.91` | prerequisite child process 결과 회수 실패 | Windows PowerShell 5.1의 `Start-Process.ExitCode` 신뢰 문제 | `ProcessStartInfo` 기반 timeout·exit 수집으로 교체 |
| `0.0.92` | post-install 재개 중 log 처리 실패 | PowerShell 5.1의 `Tee-Object` parameter 모호성 | `Add-Content` 기반 명시 기록으로 교체 |
| `0.0.93` | 최초 Full Zephyr compile 실패 | UTF-8 no-BOM BAT/CMD의 한글 주석 오해석과 긴 cache 경로의 MAX_PATH 초과 | launcher ASCII·strict CRLF, 기본 cache `%LOCALAPPDATA%\NU54\c` 적용 |
| `0.0.94`, `0.0.95` | Arduino CLI identity preflight 실패 | PowerShell 5.1에서 stdout/stderr Task의 `GetResult()` 반환값이 success stream에 섞여 native command 결과가 배열로 변환됨 | 반환값을 `[void]`로 억제하고 StrictMode 단일 결과 회귀 추가; 후속 `0.0.96`/`0.0.97`로 재검증 |
| 최종 run 첫 upload 호출 | 1·2회 성공 후 3회차 `Timeout reading from probe` | CMSIS-DAP의 일시적 read timeout | 같은 run ID의 fail-closed resume로 probe 1개를 재확인하고 최종 upload 단계 10/10을 새 증거로 확정 |
| 공통 복구 | 실패 후 Arduino CLI가 Core를 installed로 남김 | CLI 재호출이 post-install을 건너뜀 | 설치된 `post_install.bat` 직접 재시도와 검증 추가 |

수정 후 host 자동 시험은 marker 손상, 설치 중단, timeout, 잘못된 archive/index, resume
fingerprint, mutex와 uninstall/reinstall 경계를 포함한다.

---

## 7. Evidence 보관

원본 evidence와 log는 다음 로컬 경로에 회수하되 Git source history에는 넣지 않는다.

~~~text
build/m10/remote/<windows-safe-run-id>/
  evidence.json
  state.json
  runner.log
  orchestrator.json
  package-index.snapshot.json
~~~

저장소에는 개인정보와 장치 UID를 제거한 이 요약, 공개 artifact checksum과 raw evidence의
SHA-256만 기록한다. 대용량 NCS/Toolchain과 build tree도 Git에 포함하지 않는다.

최종 run의 증거 무결성 값은 다음과 같다.

| 파일 | SHA-256 |
| --- | --- |
| `evidence.json` | `2f7a7231ab35200cc6d214c2629f0afe76bf27795aa52ee82e7ccaca8cdb47c7` |
| `orchestrator.json` | `fbcd1b4bb9ec013fc3984215a01e5aea281d804abe9f0816d4656ac95d1d792c` |
| target runner | `25e29fd2aec19c4129a5431fc1e368ca314145946b6e7c3e327d6d3529076473` |

---

## 8. 라이선스와 공개 경계

패키징 자동화는 archive file provenance, SPDX 2.3 SBOM, license inventory,
`THIRD_PARTY_NOTICES.md`와 checksum을 생성·검증한다. 또한 Nordic와 SEGGER binary가 Core
ZIP/index에 포함되지 않았음을 검사한다.

M10의 기술 완료 판정은 공개 preview의 clean Windows 설치·빌드·업로드와 수명주기 결과로
내린다. 이는 모든 법률 의무가 충족됐다는 법률 자문이 아니다. 최종 stable `v0.1.0` 공개는
M11의 전체 release regression 이후 프로젝트 소유자의 라이선스 검토와 명시적 출시 승인
직전까지 HOLD한다. 이 경계는 M10 자동 실행에 사람 개입이 필요하다는 뜻이 아니다.

---

## 9. 완료 판정

**완료 — 2026-08-28.** `m10-20260828-045655`에서 clean baseline, 공개 artifact identity,
Nordic prerequisite 최초 설치, cold/warm Full Zephyr build, 온보드 CMSIS-DAP V2/pyOCD Upload
10/10과 Core upgrade·downgrade·uninstall·reinstall을 모두 통과했다. 최종 evidence와
orchestrator의 상태·checksum도 교차 검증했다.

진단 run과 폐기 preview는 결함 발견 이력으로만 남기며 PASS로 승격하지 않는다. M10의 기술
완료 조건은 충족했으며 M11 release candidate 검증을 시작할 수 있다. stable `v0.1.0` 공개는
M11의 전체 기술 gate와 프로젝트 소유자의 최종 승인 전까지 계속 HOLD한다.
