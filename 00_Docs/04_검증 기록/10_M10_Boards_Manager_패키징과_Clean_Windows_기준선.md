# M10 Boards Manager 패키징과 Clean Windows 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 진행 중 — 원격 clean Windows 수명주기 실행 완료 후 판정 |
| 작성자 | Quantum / NUCODE |
| 검증일 | 2026-08-28 |
| 패키지 기준 Core | Windows-safe `0.0.94`/`0.0.95`를 생성할 exact commit에서 확정 |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 검증 run | 진단 실패 `m10-20260828-022627`; Windows-safe 최종 run 대기 |
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
| index SHA-256 | `0.0.94`/`0.0.95` 공개 뒤 확정 |
| 최초 설치·downgrade | `0.0.94` |
| `0.0.94` ZIP SHA-256 | 공개 뒤 확정 |
| `0.0.94` ZIP size | 공개 뒤 확정 |
| upgrade·최종 reinstall | `0.0.95` |
| `0.0.95` ZIP SHA-256 | 공개 뒤 확정 |
| `0.0.95` ZIP size | 공개 뒤 확정 |

두 ZIP은 각각 공개 GitHub prerelease의 immutable asset이다. 원격 실행기는 index의 URL,
size와 SHA-256뿐 아니라 ZIP 내부 `release-manifest.json`의 Core·board·NCS·Zephyr·Toolchain
identity를 설치 전에 고정한다.

`0.0.90`~`0.0.93`은 PowerShell 5.1, launcher 인코딩 또는 Windows build 경로 결함이
확인돼 공식 index에서 제외한다. 이미 공개된 자산은 같은 tag에서 덮어쓰지 않고 실패
이력으로 보존한다. 최종 승인에는 Windows-safe launcher와 짧은 cache root를 포함한
`0.0.94`→`0.0.95` 수명주기만 사용한다.

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

다음 표는 `evidence.json`의 완료된 단계와 시간을 반영해 원격 실행 종료 후 확정한다.

| 단계 | 결과 | 핵심 증거 |
| --- | --- | --- |
| preflight | 대기 | Arduino CLI byte 고정과 빈 NCS/prerequisite 상태 확인 |
| public index update | 대기 | 공개 index와 두 archive identity 일치 |
| `0.0.94` 최초 설치 | 대기 | Nordic 공식 download와 exact pin 검증 |
| board details | 대기 | `nucode:zephyr:nu54dk` discovery |
| Blink cold compile | 대기 | Full Zephyr ELF/HEX와 build manifest |
| Blink warm compile | 대기 | 같은 build path의 증분 재빌드 |
| CMSIS-DAP/pyOCD Upload | 대기 | probe 1개와 일반 Upload 10회 성공 |
| `0.0.95` upgrade | 대기 | 설치 version과 manifest 재검증 |
| `0.0.94` downgrade | 대기 | 설치 version과 manifest 재검증 |
| Core uninstall | 대기 | 공유 NCS와 `ready.json` byte 보존 |
| `0.0.95` reinstall | 대기 | prerequisite 재사용과 Blink 재빌드 |

최종 PASS/FAIL, 단계별 duration, firmware artifact hash와 설치 용량은 원격 실행 종료 후 이
절에 추가한다. 실행 중이라는 이유로 아직 수행하지 않은 단계를 PASS로 기록하지 않는다.

---

## 6. 복구 시험과 폐기 preview

공개 검증 과정에서 다음 결함을 발견하고 새 immutable preview로 수정했다.

| preview | 증상 | 원인 | 처리 |
| --- | --- | --- | --- |
| `0.0.90` | PowerShell target runner 초기 실패 | 빈 결과의 `.Count`가 StrictMode에서 예외 | 배열 강제 변환과 host 회귀 추가 |
| `0.0.91` | prerequisite child process 결과 회수 실패 | Windows PowerShell 5.1의 `Start-Process.ExitCode` 신뢰 문제 | `ProcessStartInfo` 기반 timeout·exit 수집으로 교체 |
| `0.0.92` | post-install 재개 중 log 처리 실패 | PowerShell 5.1의 `Tee-Object` parameter 모호성 | `Add-Content` 기반 명시 기록으로 교체 |
| `0.0.93` | 최초 Full Zephyr compile 실패 | UTF-8 no-BOM BAT/CMD의 한글 주석 오해석과 긴 cache 경로의 MAX_PATH 초과 | launcher ASCII·strict CRLF, 기본 cache `%LOCALAPPDATA%\NU54\c` 적용 |
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

**진행 중.** 진단 run `m10-20260828-022627`은 Nordic prerequisite 최초 설치와 exact pin
검증까지 통과했지만 첫 Full Zephyr compile에서 launcher 인코딩·MAX_PATH 결함을 찾아
실패로 종료했다. 해당 결과를 PASS로 승격하지 않는다. 수정한 `0.0.94`→`0.0.95`를
NCS와 prerequisite가 다시 없는 상태에서 실행하고 raw evidence를 교차 검증한 뒤 M10
완료 여부를 확정한다.
