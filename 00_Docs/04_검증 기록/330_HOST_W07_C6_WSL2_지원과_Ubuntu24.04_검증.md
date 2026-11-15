# HOST-W07 C6·C7·C8 WSL2 지원과 Ubuntu 24.04 검증

2026-11-15 사용자 지시로 WSL2 지원과 Ubuntu 24.04 LTS의 설치·NU54DK USB 실기를 착수했다.
현재 단계는 M33-W07 / HOST-W07이며 Host 완료는 6/8이다. **Ubuntu 등록·계정 초기화는 완료했다.
C7의 새 kit·SDK 설치·재검증·패키지 수명주기는 통과했다. 장치 점검에서 발견한 SDK Python 환경
누락을 C8에서 교정한다. USB 전달·권한은 확인했으며 빌드·업로드·UART·debug·IDE는 아직 완료되지 않았다.**
C5의 Windows 완료와 전체204·CI 실적은 C5 기록이다.

## 승인과 source 경계

- 개발 기준 HEAD: `29e2a6bcb17c64b6002d252be3d0a51fbef21cb1`.
- C6 exact source: `8947588458d22c416d3907376daf3ad26345edf2`. producer·kit와 실패 두 번을 원형 보존한다.
- C7 exact source는 `a18bf356fa5d0528e826448c9aa87bf413291485`다. C6를 기준으로 POSIX kit 실행기를 교정했다.
  C6 실적을 C7 실적으로 합산하지 않는다. 후속 문서 기록 커밋은 제품 source와 구분한다.
- C8은 C7 기준으로 RC 실행기의 SDK child 환경을 교정하는 별도 후보다. C7의 inventory FAIL과 이전 PASS를 보존한다.
- 보존할 C5 제품 source: `5ee7c10368b554ca23d68f8f82e39308b91df6de`.
- WSL2 지원은 C6, POSIX kit 경로 교정은 C7, 현재 SDK child 환경 교정은 C8이다. 개발 검사를 실제 OS PASS로 세지 않는다.
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
| Windows 기능 | VirtualMachinePlatform exit3010 이후 사용자 재부팅 완료. 자동 재부팅하지 않음 |
| Ubuntu 24.04 | 등록 `4d6b76/exit0`, 계정·OS 확인 `e452ea/exit0`. Ubuntu24.04.5, 커널6.18.58.1-microsoft-standard-WSL2 |
| Linux 의존성 | 공식 apt 기본 의존성 `305f0e/exit0`, bzip2 추가 `0c4207/exit0` |
| C6 producer / kit | `8167a9/exit0`, `7372bd/exit0`. 재현 패키지 생성이며 실기 PASS 아님 |
| C6 첫 Linux plan | `0b74d7/exit1`: 기본 Ubuntu에 bzip2가 없어 bootstrap archive 해제 실패. 원본 보존 |
| C6 두 번째 Linux plan | `55d090/exit1`: 새 kit에서 압축은 풀렸지만 START.sh 실행 경로에 `python/` 누락. 원본 보존 |
| C7 개발 검사 | `4f6b51/exit0`: 실제 Ubuntu WSL2에서 23개 중22 PASS·Windows 전용 SKIP1. 개발 worktree 검사 |
| C7 producer / kit / plan | 세 단계 child exit0 원본을 `D:/w06/h7c7/setup`에 보존. 실제 WSL2 descriptor는 supported=true·native=false |
| NU54DK USB | 중간 COM25·26 관측 뒤 COM17·18의 기존 성공 identity로 복귀. 사용자 동일 보드·동일 연결 확인. 전달 `32126b/exit0`, Linux 권한 `1a9765/exit0` |
| C7 SDK | 설치 `97a57d/exit0`, 별도 verify `a7d93b/exit0`. NCS3.4.0·Linux fbf7391cab·nrfutil8.2.1 유지 |
| C7 패키지 수명주기 | `60ffae/exit0`, 설치·업데이트·동일 버전·제거·재설치·SDK 보존 검사 통과. WSL2_PRIVATE_LIFECYCLE |
| C7 장치 목록 | `e4be9c/exit1`, SDK Python의 libffi.so.7 loader 경로 누락. 장치 접근 전 FAIL, 원본 보존 |
| C7 원인 진단 | `38933f/exit0`, 동일 고정 SDK의 environment.json 적용 후 ctypes·usb·pyocd·serial import 통과. C8 실적으로 세지 않음 |
| C8 개발 검사 | Ubuntu `bc94b4/exit0`:65 PASS·Windows 전용 SKIP1. Windows `a0b2ab/exit0`:59 PASS·조건부 SKIP7 |
| build / upload / UART / debug / IDE | NOT_RUN. USB 전달·권한 확인을 firmware runtime PASS로 세지 않음 |

C6 kit manifest SHA-256은 `c9281b8ee65cb896bc3a4e58ccf0f370968a84dc21fdd4c136795a541554dcfe`다.
두 실패는 firmware나 SWD 실행 이전의 kit 준비 단계다. C7은 raw archive의 `python/` 루트를 실행 경로에
반영하고, Linux bzip2를 추출 전에 검사한다. 완전한 추출 후 archive hash marker를 기록하며 실행파일만
남은 부분 추출은 재사용하지 않는다. Windows 실행기·Arduino 설치 후 executable pin·SDK pin은 유지한다.
실제 sh/tar 검사에서 cold/warm 진입, archive·entry 변조 거부, bzip2 누락, 부분 추출 보존을 확인했다.

C7 kit manifest SHA-256은 `4cc5b18e928ac72712c947b1db6aa50a90a6a938de905fd7d767d0646b743654`다.
단계별 `producer-a001.json`, `kit-a001.json`, `linux-kit-plan-a001.json`은 실제 child exit0를 기록한다.
SDK까지 묶은 준비 프로세스 전체 종료와 단계별 종료는 구분한다.

USB의 중간 식별값 변화 원인은 미확정이다. 첫 bind는 예상 identity가 없어 장치 조작 전에 거부했고
`usb-bind-a001.json`을 보존했다. 새 조회에서 기존 성공 identity를 확인한 뒤 a002 bind와 attach가 성공했다.
현재 Linux `/dev/ttyACM0`·`/dev/ttyACM1`은 dialout0660, USB node는 plugdev0660이며 eidos 접근을 확인했다.
실제 probe/serial은 열지 않았고 flash·reset·halt도 아직 수행하지 않았다.

## C8 SDK child 환경 교정

C7의 SDK 설치·verify는 공식 bundle 환경을 적용하지만 RC의 inventory/upload/physical/ble-pair는
SDK Python을 직접 호출하며 같은 환경을 빠뜨렸다. `libffi.so.7`은 bundle 내부에 실제로 존재한다.
SDK·apt·pin을 변경하지 않고 공통 `apply_toolchain_environment`에 정리된 실행별 환경을 입력한 뒤
SDK Python 자식에만 전달한다. 관리 Python·Arduino CLI build·lifecycle의 기존 환경은 유지한다.
부모의 NUCODE 값 재유입·PATH 덮어쓰기·compiler flag 혼입·입력 dict 변경을 회귀 검사했다.
C8은 새 source·producer·kit·work·SDK 설치로 검증한다. 고정 공식 archive는 hash 확인 후 새 cache에
복사해 중복 다운로드를 줄일 수 있지만 기존 source의 설치·빌드·실기 PASS를 가져오지 않는다.

최초 관리자 호출은 기본 Windows PowerShell의 Restricted 정책 때문에 설치 결과를 생성하지 않았다.
정책 변경 없이 현재 사용 중인 PowerShell7로 호출한 뒤 실제 설치 결과를 확보했다.
설치 원본은 `D:/w06/h7c6/setup/administrator-install-result.json`과 단계별 MSI/DISM 로그다.
사용자 승인과 보존 hash는 `D:/w06/control/host-w07-c6-wsl2-authorization-20261115.json`,
개발 시험 원문은 `host-w07-c6-development-focused-a001/a002/a003-20261115.log`에 각각 보존한다.
이 파일명 표현은 세 개의 실제 attempt를 뜻하며 하나의 합성 로그가 아니다.

## 남은 순서

1. C8을 고정하고 새 producer·kit·Linux SDK 설치·재검증·lifecycle·inventory를 수행한다.
2. Linux 파일시스템의 새 C8 SDK·cache·kit·attempt 경계를 유지하며 대표 예제를 cold/warm build한다.
3. 연결된 NU54DK의 probe/port identity를 다시 확인한다.
4. Linux udev/serial 권한·probe/port identity를 확인하고 Blink·UART·debug·재연결·IDE를 검증한다.
5. 교정이 끝난 source를 고정하고 기존 classifier가 요구하는 최종 검증을 한 번 배치한다.
   이번 builder 변경은 six-profile/all-examples 대상이다. C5·C6·C7 PASS를 C8 PASS로 재명명하지 않는다.
6. Ubuntu26.04 LTS, macOS26, macOS27의 환경별 실기를 순차 완료한다.
7. HOST-W08 지원표·설치 안내·알려진 제한·검증 원장을 마감하고 M33-W07을 닫는다.
8. M33-W08의 별도 릴리스 승인 뒤 tag·Release·공개 index와 공개 URL 설치 검증을 수행한다.

WSL2 사용 승인은 Ubuntu native 검증 완료가 아니다. 지원표에는 OS와 실행 환경을 함께 표시한다.
다섯 OS 분모와 환경별 결과를 구분하며 미실행 항목은 NOT_RUN을 유지한다.
