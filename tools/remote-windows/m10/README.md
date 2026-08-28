# M10 clean Windows 원격 검증기

> **역사적·동결된 v0.1 검증 절차:** 이 문서는 `0.0.96`→`0.0.97` preview와 `v0.1.0`
> 릴리스 판단에 사용한 M10 수명주기 시험을 보존한다. 차기 릴리스는 버전·index·도구
> identity를 새로 고정한 별도 실행 계획을 사용한다.

이 디렉터리의 실행기는 공개 Boards Manager 패키지를 별도 Windows PC에서 검증한다.
대상 PC에는 저장소를 clone하지 않으며, 실행 스크립트와 JSON 설정만 SSH로 전송한다.

## 실행 전 조건

- 대상: `nu54ci@<CLEAN_WINDOWS_HOST>`
- 개발 PC private key: `%USERPROFILE%\.ssh\nu54dk_m10_ed25519`
- 개발 PC `known_hosts`에 사용자가 확인한 대상 host key 등록
- 대상 Arduino CLI: `C:\Program Files\Arduino CLI\arduino-cli.exe`
- 대상 Arduino CLI exact identity: `1.5.2-rc.1`, commit `fef6e48df`, 고정 executable SHA-256
- `package_nucode_nu54dk_preview_index.json`과 `0.0.96`, `0.0.97` archive가 공개 URL에서 다운로드 가능
- 기본 승인 실행에는 NU54DK CMSIS-DAP probe 연결 필수
- 최초 실행 전 `%USERPROFILE%\ncs`와
  `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\prerequisites`가 없는 clean 상태

private key, GitHub token, probe UID는 대상 설정 파일과 evidence에 저장하지 않는다.
SSH는 `BatchMode`, `IdentitiesOnly`, `StrictHostKeyChecking`으로 실행한다.

`0.0.94`와 `0.0.95`는 PowerShell 5.1 runner 수정 전에 공개된 immutable preview다.
비동기 Task 반환값이 native command 결과에 섞여 Arduino CLI identity preflight에서
실패했으므로 현재 실행, resume 또는 최종 PASS 증거에 사용하지 않는다.

## 새 실행

개발 PC에서 저장소 root를 기준으로 다음을 실행한다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\remote-windows\m10\invoke-m10-clean-windows.ps1
~~~

기본 실행은 probe가 없거나 Upload가 실패하면 전체 M10 검증을 실패 처리한다. 패키지 설치와
빌드 경로만 조사하며 HIL 승인을 의도하지 않을 때에만 다음 option을 명시할 수 있다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\remote-windows\m10\invoke-m10-clean-windows.ps1 `
  -AllowMissingProbe
~~~

`-AllowMissingProbe` 실행은 probe가 없을 때 `skipped-no-probe`를 기록하므로 M10 최종 HIL
PASS 근거로 사용할 수 없다. probe가 발견된 경우에는 이 option을 주어도 Upload 실패를
허용하지 않는다. probe가 둘 이상이면 개수를 evidence에 기록하고, 명시적으로 하나를
선택하는 interface가 없는 현재 M10 runner는 모호한 Upload를 실행하지 않고 실패한다.

기본 package index URL은 다음 공개 raw URL이다.

~~~text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json
~~~

다른 공개 preview index를 시험할 때만 `-IndexUrl`을 명시한다.

## 중단된 실행 재개

실행 ID가 `m10-20260828-120000`이라면 동일 설정으로 다음처럼 재개한다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\remote-windows\m10\invoke-m10-clean-windows.ps1 `
  -ResumeRunId m10-20260828-120000
~~~

이미 PASS한 단계는 `state.json`을 기준으로 건너뛴다. index URL, 두 package version,
FQBN, NCS version, toolchain bundle ID, target runner byte, Arduino CLI executable byte,
index byte 또는 두 archive identity가 달라지면 재개를 거부한다. 같은 실행 ID를 동시에
두 번 실행하면 global OS mutex가 두 번째 process를 거부하며, 비정상 종료로 abandoned된
mutex는 Windows 소유권 규칙에 따라 복구한다. state/evidence는 같은 directory에서
write-through 임시 파일을 만든 뒤 원자적으로 교체한다.
core uninstall 성공 직후 checkpoint 기록 전에 중단된 경우에는 다음 실행에서 이미 제거된
상태를 감지하고 uninstall을 반복하지 않은 채 NCS와 prerequisite state 보존 검증을 계속한다.

## 자동 검증 순서

1. Arduino CLI와 격리 디렉터리 확인
2. 개발 PC에서 공개 index와 고정 EIDOSDATA release archive를 사전 다운로드해
   filename, URL, size, SHA-256, release manifest와 core revision 고정
3. 대상에서 공개 package index 갱신 후 사전 snapshot SHA-256과 재검증
4. `nucode:zephyr@0.0.96` 설치와 `post_install.bat` 실행
5. 설치된 platform의 release manifest byte/core revision과 사전 검증 archive identity 비교
6. 설치된 platform의 `verify-nordic.ps1 -Json` 명시 실행
7. board details 확인
8. Blink cold/warm compile
9. pyOCD probe 확인 및 Upload 10회(기본 필수, 조사 실행만 명시적 생략 허용)
10. `0.0.97` upgrade
11. `0.0.96` downgrade
12. core uninstall 뒤 공유 NCS와 prerequisite state 보존 확인
13. 최신 `0.0.97` reinstall, Nordic 재검증 및 Blink compile

대상 디렉터리는 `%USERPROFILE%\NU54CI\M10\runs\<run-id>`이다. Arduino data,
downloads, sketchbook과 build를 실행별로 분리한다. Nordic SDK/toolchain은
의도적으로 `%USERPROFILE%\ncs`와 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core`의
공유 prerequisite 계약을 사용한다.

## 결과

개발 PC의 `build\m10\remote\<run-id>`에 다음 파일을 회수한다.

- `evidence.json`: 단계별 결과, 시간, archive/core/Nordic 검증 상태
- `state.json`: 재개 checkpoint
- `runner.log`: 장치 식별자와 자격 증명 패턴을 제거한 대상 로그
- `orchestrator.log`: 장치 식별자와 자격 증명 패턴을 제거한 SSH 전송 로그
- `orchestrator.json`: 대상 evidence SHA-256과 최종 상태
- `package-index.snapshot.json`: 실행 전에 검증하고 fingerprint에 포함한 공개 index 원본 byte

원격 명령 timeout, 허용되지 않은 종료 코드, Nordic pin 불일치, archive 설치 실패,
산출물 누락 또는 evidence 회수 실패가 발생하면 실행기는 실패로 종료한다.
