# HOST-W07 C6 WSL2 지원과 Ubuntu 24.04 검증

2026-11-15 사용자 지시로 WSL2 지원과 Ubuntu 24.04 LTS의 설치·NU54DK USB 실기를 착수했다.
현재 단계는 M33-W07 / HOST-W07이며 Host 완료는 6/8이다. **C6는 개발 검증 단계이며 Ubuntu
설치·빌드·USB 실기는 아직 완료되지 않았다.** C5의 Windows 완료와 전체204·CI 실적은 C5 기록이다.

## 승인과 source 경계

- 개발 기준 HEAD: `29e2a6bcb17c64b6002d252be3d0a51fbef21cb1`.
- 보존할 C5 제품 source: `5ee7c10368b554ca23d68f8f82e39308b91df6de`.
- 새 후보는 C6로 구분한다. 개발 worktree 검사를 최종 clean source의 실제 OS PASS로 세지 않는다.
- C5 kit·ZIP·manifest와 [328번](328_HOST_W07_C5_필수_자동검증과_사용자_OS_gate.md),
  [329번](329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md), 원본 FAIL은 보존한다.
- W06 실제 PASS46·수락29/40/44와 분석 유예를 유지한다. w06 PAUSED, 새 예약 없음.

## 변경 내용

기존 Host 검사는 WSL을 발견하면 실제 build·USB 작업 이전에 거부했다. 이번 변경은
Ubuntu AMD64의 확인된 WSL2를 허용하면서 `native=false`, `execution_environment=wsl2`로 기록한다.
WSL1·환경 변수만 있는 판별 불명 WSL·지원하지 않는 배포판/CPU/Ubuntu 버전은 계속 거부한다.
캐시 identity에 실행 환경을 넣고 lifecycle은 `WSL2_PRIVATE_LIFECYCLE`로 구분한다.
native CI 집계의 `host.native is True` 조건은 유지한다. WSL2 결과로 native Ubuntu 실적을 채우지 않는다.
USB 미발견 메시지는 usbipd와 Linux 권한 확인을 안내한다. SDK pin·probe identity·sector flash·
금지된 erase/unlock/recover·FW 변경 방지는 유지한다.

## 현재 실제 결과

| 항목 | 결과와 근거 |
| --- | --- |
| 관련 Host 검사 | `3b3c9a/exit0`, 107개 중 102 PASS·POSIX 조건부 SKIP5. 개발 worktree 검사이며 Linux 실기 아님 |
| 첫 검사 호출 | `c760f1/exit1`, 비격리 SDK Python의 ctypes 초기화 오류로 시험 시작 실패. 원본 보존 |
| 두 번째 검사 호출 | `e33e88/exit1`, 초기 bootstrap Python의 PyYAML 미설치로 오류2·실패1. 원본 보존 |
| 검사 실행 교정 | 같은 코드에서 SDK Python `-I`를 사용해 정상 의존성을 격리. 세 번째 호출에서 통과 |
| WSL | 공식 MSI 3.0.5 설치 exit0, 실제 `wsl --version` 3.0.5.0·커널6.18.58.1-1 확인 |
| usbipd-win | 공식 MSI 5.3.0 설치 exit0, 실제 version5.3.0 확인 |
| Windows 기능 | VirtualMachinePlatform exit3010, 설치 성공·재부팅 필요. 자동 재부팅하지 않음 |
| Ubuntu 24.04 | 배포판 등록·첫 부팅·계정 초기화 대기 |
| NU54DK USB / build / IDE | NOT_RUN. 재부팅 후 새 환경에서 수행 |

최초 관리자 호출은 기본 Windows PowerShell의 Restricted 정책 때문에 설치 결과를 생성하지 않았다.
정책 변경 없이 현재 사용 중인 PowerShell7로 호출한 뒤 실제 설치 결과를 확보했다.
설치 원본은 `D:/w06/h7c6/setup/administrator-install-result.json`과 단계별 MSI/DISM 로그다.
사용자 승인과 보존 hash는 `D:/w06/control/host-w07-c6-wsl2-authorization-20261115.json`,
개발 시험 원문은 `host-w07-c6-development-focused-a001/a002/a003-20261115.log`에 각각 보존한다.
이 파일명 표현은 세 개의 실제 attempt를 뜻하며 하나의 합성 로그가 아니다.

## 남은 순서

1. Windows 재부팅 후 WSL2 시작 가능 여부와 설치 버전을 확인한다.
2. 새 D 드라이브 위치에 Ubuntu 24.04 LTS AMD64를 등록하고 사용자 계정을 초기화한다.
3. Linux 파일시스템 안에 새 SDK·cache·kit·attempt를 준비한다. Windows SDK를 공유하지 않는다.
4. 고정 kit 생성과 source/hash 확인, plan·SDK 설치/재검증·lifecycle을 수행한다.
5. 대표 예제 build 후 COM17/18의 정확한 물리 USB 장치를 식별해 usbipd로 전달한다.
6. Linux udev/serial 권한·probe/port identity를 확인하고 Blink·UART·debug·재연결·IDE를 검증한다.
7. 교정이 끝난 source를 고정하고 기존 classifier가 요구하는 최종 검증을 한 번 배치한다.
   이번 builder 변경은 six-profile/all-examples 대상이다. C5 PASS를 C6 PASS로 재명명하지 않는다.

WSL2 사용 승인은 Ubuntu native 검증 완료가 아니다. 지원표에는 OS와 실행 환경을 함께 표시한다.
다섯 OS 분모와 환경별 결과를 구분하며 미실행 항목은 NOT_RUN을 유지한다.
