# HOST-W07 C6~C10 WSL2 지원과 Ubuntu 24.04·26.04 검증

2026-11-15 사용자 지시로 WSL2 지원과 Ubuntu 24.04 LTS의 설치·NU54DK USB 실기를 착수했다.
현재 단계는 **M33-W07 / HOST-W07**, Host 완료6/8·지원표3/5다. Ubuntu26.04/WSL2 호환성도 마감했다.
Ubuntu24.04/WSL2의 C10 새 설치·대표8·Blink·UART·
debug·BLE·잘못된 UID 거부와 실제 USB 재연결 후 첫 UART6개·IDE Verify가 PASS다.
C5 전체 native 기준선에 C10 변경 영향 증거를 연결해 Ubuntu24.04/WSL2 행을 마감했다. 중복 전체204는15cold 뒤 범위 정정으로 중단·정리했다. 전체 PASS로 세지 않는다. C5 Windows 완료와 C6~C9 원본 PASS/FAIL을 보존한다.

2026-11-16 사용자 지시에 따라 Ubuntu24.04/WSL2를 기준선·변경 영향 검증으로 마감했다. Ubuntu 26.04 LTS는 호환성 중심으로 확인한다. C5 Windows 11 완료를 유지하고 공통 도구 변경 영향만 제한 회귀한다. OS 버전 차이만으로 전체204를 반복하지 않으며 macOS 26·27도 보존된 기준선과 버전별 호환성을 구분한다. 각 증거의 실제 source·환경·PASS·FAIL을 보존하고 기준선과 변경 영향의 연결을 서로 다른 source의 단일 시험 실적으로 합산하지 않는다.

## 승인과 source 경계

- 개발 기준 HEAD: `29e2a6bcb17c64b6002d252be3d0a51fbef21cb1`.
- C6 exact source: `8947588458d22c416d3907376daf3ad26345edf2`. producer·kit와 실패 두 번을 원형 보존한다.
- C7 exact source는 `a18bf356fa5d0528e826448c9aa87bf413291485`다. C6를 기준으로 POSIX kit 실행기를 교정했다.
  C6 실적을 C7 실적으로 합산하지 않는다. 후속 문서 기록 커밋은 제품 source와 구분한다.
- C8 exact source는 `e1037a4ee51217195f1a715173ce37efec689731`다. C7 기준으로 RC 실행기의 SDK child 환경을 교정한 별도 후보다. C7의 inventory FAIL과 이전 PASS를 보존한다.
- C9 exact source는 `8bdf4c4ae8aeb6f36cb04df94b9ab932daf6704c`다. C8을 기준으로 검증기의 명시적 DTR 수신 준비를 교정했으며 firmware·SDK는 변경하지 않았다.
- C10 exact 제품 source는 `4890f697ab80dfed3cff62bd42acc42b0f3e1a34`다. C9 제품과 문서 후속 `c2c62a6b690b6e81f4c0a4d12b6acc31d4c72e4c`를 기준으로 `serial --synchronize-line`을 추가했으며 이 문서 후속 개정과 제품 source를 구분한다.
- 보존할 C5 제품 source: `5ee7c10368b554ca23d68f8f82e39308b91df6de`.
- WSL2 지원은 C6, POSIX kit 경로 교정은 C7, SDK child 환경 교정은 C8, DTR 검증 절차 교정은 C9, 첫 입력 줄 동기화 교정은 C10이다. 개발 검사를 실제 OS PASS로 세지 않는다.
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
| C8 새 준비 | `9fd8b1/exit0`: 새 producer·kit·plan·SDK 설치/verify·lifecycle·inventory·대표 build 모두 child exit0 |
| C8 대표 build | 새 WSL2 설치본 cold4·warm4 =8/8. 전체204 실적으로 확대하지 않음 |
| C8 Blink | 업로드 `5dfe11/exit0`, 실제 GPIO 변화 `425eb4/exit0` |
| C8 ELF debug | `4983b7/exit0`, halt/resume와 실행 image 확인 |
| C8 UART | SerialEcho 업로드 `72c31f/exit0`, 실제 송수신 `709c53/exit0` |
| C8 잘못된 UID | `8d011b/exit0`, child exit1 예상 거부. `E_PROBE_SHA256`, `NU54_UPLOAD_START` 없음 |
| C8 USB 재연결 | 사용자 분리10.516초·동일 장치 복귀. 첫 attach `d95e0e/exit1` busy 원본 보존, 새 일반 attach `734ab3/exit0` |
| C8 재연결 후 | inventory `a1efcc/exit0`, UART `aab094/exit0`. busy 원인은 미확정 |
| C8 Linux IDE | 공식2.3.11·WSLg·별도 설정. C8 RC1 설치·보드/예제 발견·Blink Verify PASS. 960파일 일치, 정상 종료 |
| C8 최종 자동검증 | push `939eb8/exit0`; 초기 관측에서 exact C8 4 workflow 진행. 이후 관측과 구분하며 완료 전 PASS로 세지 않음 |
| C8 IDE 감사 | `92e010/exit0`, 산출물4개·exact source·WSL2 확인. 첫 감사 `ffaa22/exit1`은 helper의 `v3.4.0` 문자열 조건 오류이며 원본 보존. 재빌드하지 않음 |
| C8 두 번째 보드 | USB 전달 `59bf99/exit0`, inventory `609e80/exit0`, SerialEcho UART `9fcb46/exit0` |
| C8 BLE pair a001 | `52ee47/exit1`, 두 업로드 PASS 뒤 `E_HOST_NUS_TIMEOUT`. 양쪽 SerialEcho 복원 PASS |
| C8 BLE pair a002 | `5d1eec/exit1`, Peripheral-first·수신 전용 UART 수집을 추가해도 timeout. UART A/B0byte, 양쪽 복원 PASS. 원인 미확정 |
| C8 PC 진단 | `d171ff/exit0`, NUS Peripheral 실제 PC271386·arch_cpu_idle·ELF 명령 일치·resume·probe close. BLE PASS로 세지 않음 |
| C8 단일 RAM 진단 | `eb195a/exit0`, BLE 초기화·광고 시작·UART PM active 확인, SerialEcho 복귀 |
| C8 두 보드 RAM 진단 | `c6602a/exit0`, connected1·ready1·UART TX 완료 확인, 양쪽 복귀 |
| C8 네 포트 진단 | `6164de/exit0`, 양쪽 최초 송신 뒤 반대편의 정확 nonce 수신. 정식 PASS로 세지 않음 |
| C8 두 포트 분리 진단 | `22bdde/exit1`, 원형 nonce timeout 보존. A만 최초 송신 실패 → B 최초 송신 성공 → A 재송신 성공. 보조 포트 미개방, 양쪽 복귀 |
| C8 DTR 단독 진단 | `14891e/exit0`, DTR=true·RTS=false만 변경. 사전 payload 없이 기존 순차 nonce2개·10초 제한으로 양방향 일치, 양쪽 복귀 |
| C9 개발 검사 | `2a39dd/exit0`, Windows·Ubuntu 각각15/15. 개발 검사이며 새 source 실기 PASS 아님 |
| C9 새 준비 | `9e268f/exit0`: 새 producer·kit·plan·SDK 설치/verify·lifecycle·inventory·대표 build 모두 child exit0 |
| C9 대표 build | 새 설치본 cold4·warm4=8/8. 전체204 실적으로 확대하지 않음 |
| C9 fresh 실기 | `10c4c4/exit0`: Blink 업로드·GPIO, ELF debug, SerialEcho 업로드·UART, BLE pair, 잘못된 probe 예상 거부 모두 통과 |
| C9 BLE 감사 | `af9fcf/exit0`: RC·실기·worker 세 층 DTR=true·RTS=false, fresh nonce 양방향 일치, 양쪽 SerialEcho 복원 PASS |
| C9 Linux IDE | `d967a4/exit0`: 새 설정·Boards Manager RC1 설치·NU54DK Standard·설치 Blink Verify 통과, 정상 종료, 설치960파일 원본 일치 |
| C9 IDE 감사·SDK | `4865ca/exit0`: 실제 source·WSL2·산출물4개 확인. 종료 후 고정 SDK verify `c572e1/exit0` |
| C9 USB 재연결 | 첫 관찰 `616c83/exit1`은 사용자 분리가 관측되지 않은 OBSERVATION_TIMEOUT이며 원본 보존. 후속 실제 관찰 결과는 아래 행에 분리 |
| C9 첫 실제 재연결 | `02ddf2/exit0`: 분리15.453초·동일 identity 복귀·일반 WSL attach 성공. inventory `3727e5/exit0` |
| C9 재연결 UART a001 | `07f6ef/exit1`, 실제 child exit2·worker exit1, `E_HOST_SERIAL_TIMEOUT`. DTR=false·RTS=false·각5초 원형 FAIL 보존 |
| C9 실행 상태 진단 | `06d026/exit0`: 실제 Flash78,776byte가 C9 SerialEcho와 완전 일치, CPU arch_cpu_idle·resume·probe close 확인. firmware·reset 변경 없음 |
| C9 UART 관측 진단 | `7fcb98/exit0`: firmware·DTR·timeout 변경 없이 원형 oracle의 2회 open×3nonce 모두 일치. 진단 PASS이며 최초 FAIL 해소나 재연결 정식 PASS로 세지 않음 |
| C9 두 번째 재연결 | 사용자 분리10.063초·동일 identity 일반 attach 성공. 첫 helper `a42450/exit1`은 Linux tty/by-id 준비 전 선택 실패이며 UART open 이전. udev settle 뒤 inventory `357aaf/exit0` |
| C9 재연결 UART a003 | `f8bdc2/exit1`, 첫 실제 송수신 syscall에서 `NUCODE_M6_ECHO:` 뒤 `0xF0`+정확 nonce 수신. 원형 정확 비교는 FAIL을 유지. `post-replug-a003/tty-system-calls.log` 보존 |
| C9 전체204 | 01:18:30 KST 시작,13cold·0warm 후 C10 교정을 위해 정상 정리. `351ba6/exit1` 원본 보존, `0edce1/exit0`에서 OwnedInterrupted·leader reap·잔여 build0 확인. 컴파일 결함 판정이나204 PASS가 아님 |
| C9 push·CI | push `6e7d70/exit0`, M12 요청 `23bd2c/exit0`. exact C9 네 workflow 실행 중, 설치 prerequisite workflow success. 최종 완료 아님 |
| C8 CI 후속 관측 | 2026-11-16 01:23:55 KST API `08f3c6/exit0`: M12 9/9·prerequisites 3/3·W06 build 6/6 success. native package 20성공·9진행. metadata 관측이며 artifact byte 감사는 별도 |
| C8 미완료 보존 | 원형 BLE FAIL과 WSL2 전체204 NOT_RUN 유지, exact C8 CI 진행. C9에 실적 이월하지 않음 |
| C10 개발 검사 | Windows·Ubuntu 각각24개/exit0. `D:/w06/h7c10/development/*-a002.json`과 개별 원본 로그, 관측 `42d015/exit0`·`5c046e/exit0`. 새 source 실기 PASS 아님 |
| C10 독립 검토 | read(1)로 setup LF 뒤의 분할 runtime 오류를 소비하지 않도록 교정. 오류 뒤 정상 nonce도 FAIL·close 회귀 검사, 읽기 전용 최종 검토 추가 지적 없음 |

| C10 준비·대표8 | `e7f101/exit0`: 새 producer·kit·plan·SDK 설치/verify·lifecycle·inventory·대표8 PASS |
| C10 실기·감사 | `b61a6a/exit0`·`35f83b/exit0`: Blink·debug·UART·BLE 양방향·양쪽 SerialEcho 복원·UID 거부 PASS |
| C10 실제 USB 재연결 | `59a156/exit0`: 분리10.031초·동일 identity·일반 attach·Linux 준비 확인 뒤 첫 UART6개 PASS. setup payload0byte 두 회, 모든 포트 닫힘 |
| C10 재연결 감사 | `replug-audit-a001.json` PASS. `21d689` 호출은 이 감사를 저장한 뒤 별도 Git helper의 사전 hash guard에서 exit1; 감사 PASS와 helper FAIL 구분 |
| C10 Git helper FAIL·교정 | 잘못 복사된 외부 helper hash 문자열로 인증 전 중단. `github-helper-failure-a001.json`과 failed.py 보존. `61d9a2/exit0` 교정 후 `651658/exit0` push |
| C10 Linux IDE | 새 profile·비공개 RC1 설치·NU54DK Standard·설치 Blink Verify·정상 종료 PASS. `ide-audit-a001/closure-a001.json`에서960파일·산출물4개·source·WSL2 대조 |
| C10 exact CI | push `651658/exit0`, M12 요청 `a5291e/exit0`. M12 43743792396·prerequisite 43743775292·native package 43743775319·W06 build43743775285, 모두 attempt1. 최종 완료 전 PASS 아님 |
| C9 문서 CI 후속 | 문서 source `c2c62a6b`의 M12 43736743850은8PASS+조건부SKIP1. 관측 `d2787e/exit0`. 앞선 observer timeout 원본을 CI 실패로 재분류하지 않음 |

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
C7 USB 준비 당시 Linux `/dev/ttyACM0`·`/dev/ttyACM1`은 dialout0660, USB node는 plugdev0660이며 eidos 접근을 확인했다.
이 문단의 C7 USB 준비 당시에는 실제 probe/serial open·flash·reset·halt를 수행하지 않았다. 후속 C8 실제 결과는 위 표에 분리했다.

## C8 SDK child 환경 교정

C7의 SDK 설치·verify는 공식 bundle 환경을 적용하지만 RC의 inventory/upload/physical/ble-pair는
SDK Python을 직접 호출하며 같은 환경을 빠뜨렸다. `libffi.so.7`은 bundle 내부에 실제로 존재한다.
SDK·apt·pin을 변경하지 않고 공통 `apply_toolchain_environment`에 정리된 실행별 환경을 입력한 뒤
SDK Python 자식에만 전달한다. 관리 Python·Arduino CLI build·lifecycle의 기존 환경은 유지한다.
부모의 NUCODE 값 재유입·PATH 덮어쓰기·compiler flag 혼입·입력 dict 변경을 회귀 검사했다.
C8은 새 source·producer·kit·work·SDK 설치로 검증했고 실적과 FAIL을 보존한다. 고정 공식 archive는 hash 확인 후 새 cache에
복사해 중복 다운로드를 줄일 수 있지만 기존 source의 설치·빌드·실기 PASS를 가져오지 않는다.

최초 관리자 호출은 기본 Windows PowerShell의 Restricted 정책 때문에 설치 결과를 생성하지 않았다.
정책 변경 없이 현재 사용 중인 PowerShell7로 호출한 뒤 실제 설치 결과를 확보했다.
설치 원본은 `D:/w06/h7c6/setup/administrator-install-result.json`과 단계별 MSI/DISM 로그다.
사용자 승인과 보존 hash는 `D:/w06/control/host-w07-c6-wsl2-authorization-20261115.json`,
개발 시험 원문은 `host-w07-c6-development-focused-a001/a002/a003-20261115.log`에 각각 보존한다.
이 파일명 표현은 세 개의 실제 attempt를 뜻하며 하나의 합성 로그가 아니다.

## C8 BLE 원인과 C9 교정

C5 실제 BLE PASS의 두 manifest를 추적해 C8과 비교한 결과 Peripheral·Central의 실제 BIN·HEX가
모두 같다. 각 역할 `.config` 1,991개 중 차이는 SDK 절대 경로2개뿐이다. 다만 C5 BLE는 두 J-Link
probe였고 이번에는 두 CMSIS-DAP probe다. Windows C5와 WSL2 C8의 장치·전달 경로를 같은 조건으로
취급하지 않는다. 이미지 동일성은 원인 분리 근거이며 C5 PASS를 C8로 이월하는 근거가 아니다.

기존 `serial_pair()`는 DTR=false로 두 포트를 열고 A를 먼저 송신한 뒤 B의 수신을 기다렸다.
이번 CMSIS-DAP/WSL2 경로는 DTR=false에서 host 송신 전 수신이 도착하지 않았다. SerialEcho는
같은 포트에 먼저 송신하므로 이 조건을 드러내지 않았다. 보조 포트 개방 없이도 B가 한 번 송신하면
양방향 전송이 가능했고, DTR=true에서는 사전 송신 없이 원형 순차 nonce가 통과했다. 이 증거로
현재 실패를 교정할 검증기 초기화 조건은 확인했다. USB bridge 내부 구현의 상세 원인까지 추정하지 않는다.

C9은 `ble-pair --assert-dtr`를 RC 진입점·공개 명령·worker에 전달하고 open 전에 DTR=true,
RTS=false를 설정한다. 기본 false와 J-Link 기존 사용 조건은 유지하며 VID/PID로 자동 선택하지 않는다.
PASS·FAIL 기록에 요청한 DTR을 남긴다. nonce2회·각10초·identity·lock·실패 보존 조건은 유지한다.
펌웨어·NUS 예제·SDK·보안·재시도 정책은 변경하지 않는다. C8 진단 PASS는 C9 정식 PASS가 아니다.

## C9 재연결 원인 구분과 C10 교정

C9 첫 FAIL 뒤 read-only 진단에서 Flash78,776byte가 원래 SerialEcho BIN과 일치했고 CPU는
`arch_cpu_idle`에서 정상 대기했다. 이후 원형 nonce6개 진단은 통과했지만 이미 첫 입력 줄이 끝난
상태이므로 최초 재연결 PASS로 세지 않았다. 두 번째 물리 재연결의 첫 UART를 syscall로 기록하자
추가 `0xF0`가 정확한 fresh nonce 앞에 붙었다. 전체 응답은 즉시 도착했지만 정확 비교에 실패해
timeout이 났다. USB bridge/UART의 byte 발생 원인이나 firmware 결함까지 확정한 결과는 아니다.

C10은 `serial --synchronize-line`을 선택했을 때만 각 open에서 LF를 한 번 보내고 완성된 setup
echo 한 줄을 기다린다. 제거한 setup payload의 길이·hash를 별도로 기록하고 nonce 실적으로 세지
않는다. 이후2open×3fresh nonce·정확 응답·각5초·DTR=false·RTS=false를 유지한다. 실제 nonce의
추가 byte를 제거하거나 자동 재송신하지 않는다. setup 부분 쓰기·runtime 오류·timeout도 FAIL이다.
setup LF까지 한 byte씩 읽어 뒤의 오류를 버리지 않는다. C8 BLE DTR 문제와 구분하며 BLE는 C9의
명시적 `--assert-dtr`를 유지한다. firmware·SDK·보안 pin은 바꾸지 않는다.

Windows attach 성공만으로 Linux UART가 준비됐다고 판단하지 않는다. `udevadm settle` 후 새
inventory에서 hashed identity·interface·by-id·접근 권한을 확인한 뒤 포트를 연다. C9 a002의
readiness helper 실패는 UART 실행 이전의 제어기 실패로 보존한다.

## 원본과 남은 순서

C8 kit manifest SHA-256은 `f1ef61550fd52fc2d295cda5eabcbac780bcbd4c5cba41467837b7eb88ed27d3`다.
보존 중인 C8 Linux kit·work·SDK는 `/home/eidos/nu54-c8` 아래에 있고, 단계별 원본은
`D:/w06/h7c8/setup`, `D:/w06/h7c8/physical` 및 Linux work의 새 attempt에 남긴다.
`usb-reconnect-a001.json`의 첫 attach FAIL은 그대로 보존하며 `usb-reconnect-closure-a001.json`이
새 일반 attach와 후속 inventory·UART PASS를 연결한다. 강제 attach·mass erase·unlock·recover·FW 변경은 없다.
DTR 단독 진단 종료 시 두 NU54DK를 C8 SerialEcho로 복귀했다. 후속 역할 image 변경은 새 attempt에 기록한다.

1. 완료한 C5 기준선과 C10 설치·대표8·실기·재연결·IDE·변경 영향 증거를 보존한다. Ubuntu24.04/WSL2 행은 마감했다.
2. 문서·CI 설정 검증을 완료했다. C10의 불필요한 전체 native shard는 smoke 원본을 보존한 뒤 취소했다.
3. Ubuntu26.04/WSL2 호환성을 마감했다. 전체204·BLE·물리 재연결은 반복하지 않았으며 실제 결과는 아래 절에 보존한다.
4. macOS 프로세스 정리 FAIL을 교정·집중 검증하고 macOS26 →27의 설치·장치·IDE 호환성을 확인한다. 실제 Mac 환경 확보가 필요하다.
5. HOST-W08 지원표·설치 안내·제한·검증 원장을 마감하고 M33-W07을 닫는다.
6. M33-W08의 별도 릴리스 승인 뒤 tag·Release·공개 index와 공개 URL 설치 검증을 수행한다.

C9 kit manifest SHA-256은 `a210e1b58ea29bd7c10bbcc023bc67219b0aa2587598241d1aadb08d4f4c3ade`다.
새 실기 원본은 `D:/w06/h7c9/physical-sequence-a001`·`ble-pair-a001`, 감사는
`physical-audit-a001.json`·`ide-audit-a001/closure-a001.json`에 보존한다. 전체 빌드는
`/home/eidos/nu54-c9/work/attempts/build-20261115T161830936993Z`와
`D:/w06/h7c9/all-build-a001`에 별도로 기록한다. C9 실기 종료 당시 양쪽은 C9 SerialEcho였고 빌드는 중단·정리됐다.
후속 C10 실기 뒤 현재 양쪽은 C10 SerialEcho이며 포트는 닫혔다. 반복·예약 작업을 추가하지 않았다.

WSL2 PASS는 해당 Ubuntu/WSL2 환경의 실적이다. 지원표에는 OS와 실행 환경을 함께 표시하며
native Ubuntu 실기·다른 Ubuntu 버전·macOS·C5 Windows 결과와 합성하지 않는다.

C10 kit manifest SHA-256은 `9041bd68091e1214c7999bcdb8666390ae4268e2c44ab9425c1a4c303e0c3af2`다.
원본은 `D:/w06/h7c10`과 `/home/eidos/nu54-c10`에 source·attempt별 보존한다.
이번 재연결의 setup payload는 두 회 모두0byte이므로 C9의0xF0가 실제 제거됐다고 주장하지 않는다.
C9 하위 byte 발생 원인은 미확정이며 이번 새 C10 절차의 PASS와 구분한다.

### C10 macOS prerequisite CI 원본 FAIL과 별도 진단

C10 prerequisite run43743775292/attempt1은 Windows·Ubuntu2PASS, macOS1FAIL이다. 실패 job132902468528의
원형 로그를 `4f59d6/exit0`으로 보존했다. SDK 설치 이전141개 unit 중 정상 leader 종료 후 손자 정리
검사1개가 `OwnedExecutionError: PermissionError`다. SDK·USB·firmware 실행 실패가 아니다.
해당 제품 코드와 test는 C9→C10에서 동일하다. Apple XNU의 zombie-only process group은
[killpg1 구현](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_sig.c#L1580)상 EPERM 후보가 되지만
원형 로그에는 실패 호출·errno가 없어 아래 별도 진단으로 실행 경계를 확인했다.

별도 macOS CI 진단에서 exact C10 원형 test10회와 controlled zombie-only 그룹1회를 고정 관측했다.
signal·예외·PASS 조건을 변경하지 않고 같은 소유PGID 상태와 errno를 추가 기록했다. 진단 성공은
C10 원형 CI FAIL을 PASS로 바꾸지 않는다. SDK 설치·전체 예제·USB/HIL을 반복하지 않으며
Ubuntu24.04의 중단된 전체 빌드 원본과 별도로 완료한 실기·IDE PASS를 보존한다.

## 2026-11-16 전체 문서 검토와 검증 범위 정정

OS 버전별·Host 검증기 수정별 전체204 재실행 요구는 과도했다. 고정 toolchain 선택은 OS+CPU이며
버전별 compiler 교체가 아니다. 최신 전체 기준선은 C5 `5ee7c10368b554ca23d68f8f82e39308b91df6de`,
native run43561469020/attempt1의24worker·OS별204compile/9negative다. H12 이전 기준선도 보존한다.
C5→C10 firmware·SDK pin·board·compile recipe는 그대로다. C10의 WSL2·child 환경·kit 경로·
검증기 옵션은 새 설치·대표cold/warm8·실기·IDE·재연결·관련 Host unit과 CI로 영향 범위를 확인한다.
C9→C10 대표8의 실제 BIN/HEX도 같지만 이는 byte 비교 근거이며 과거 source의 PASS 이월은 아니다.

Windows11 C5 실기에 C10 Windows Server2025 job132902468232의141건(134PASS·조건부SKIP7),
SDK 설치·재검증을 연결했다. `windows-limited-impact-audit-a001.json`과
`compiler-selection-review-a001.json`은 `D:/w06/h7c10`에 보존한다. C10 Windows11 신규 실기나
macOS FAIL을 포함한 전체 prerequisite workflow 성공으로 표시하지 않는다.

C10 전체 빌드 attempt `build-20261115T180802545594Z`는15cold·0warm 뒤 범위 정정으로 중단했다.
실행기 원본 결과는 FAIL/exit1(`f9b9f9`) 그대로이며 전체204 PASS가 아니다. 원인은 compiler 실패가
아니라 중복 실행 중단이다. SIGINT 후 남은 소유 자손은 별도로 정리했고 `c7c638/exit0`에서0개를 확인했다.
원본·중단 의도·cleanup은 `D:/w06/h7c10/all-build-a001`에 보존했다. 완료한 대표8·실기는 별도 attempt다.

본체 Markdown537개와 보드 하위 저장소6개를 검토했다. 현행 계약·지원표·로드맵·TODO·설치·CI·인계의
중복 전체 실행 요구와 오래된 진행 상태를 정리했다. 역사 기록·완료 TODO6개·기존 PASS/FAIL은 수정하지 않았다.
`host-native-package.yml`의 push와 기본 dispatch는 설치·대표 smoke까지만 실행하고, 전체204는 실제 전체 영향 검토 뒤 명시한다.
같은-source/run/attempt 집계 규칙은 유지한다. 미실행 호환성이나 미해결 macOS cleanup FAIL을 PASS로 바꾸지 않는다.

## Ubuntu24.04/WSL2 행 마감과 원본 진단 결과

`673dee/exit0`에서 C5 전체 기준선과 exact C10 증거10개를 대조해 Ubuntu24.04/WSL2 행을 마감했다.
`D:/w06/h7c10/ubuntu24-baseline-impact-closure-a001.json`이 마감 원장이다. C10은 대표4cold/4warm,
lifecycle9단계·설치960파일·발견204·실기·물리 재연결·IDE를 통과했다. Linux prerequisite unit은
140PASS·조건부SKIP1과 SDK 설치·재검증 PASS다. C10 M12는9/9이며 native smoke3OS 원본 byte 재집계는
`f7ddc5/exit0`으로 통과했다. 최초 재집계는 다른 문서 HEAD에서 실행해 source 가드가 거부했다
(`a95518/exit1`). 원본을 보존하고 actual C10 checkout에서 새 감사만 수행했으며 재빌드하지 않았다.
Ubuntu24 행 마감 당시 지원표는 Windows11 기준선 유지와 Ubuntu24.04/WSL2 완료로2/5였다. 당시 C10 직접 마감은1행이었다. 이후 Ubuntu26 결과는 아래에 분리하며 native Ubuntu 사용자 실기와 HOST-W07/W08 미완료 경계는 유지한다.

C10 native run43743775319는 완료한 producer·세 smoke·비교5job과 원본 artifact8개를 보존한 뒤
중복 전체 shard를 취소했다. 실행 전체는 CANCELLED이며 전체204 PASS가 아니다. 취소 원문과
남은 partial artifact는 해당 run에 보존하며 새 정규 workflow는 `full_examples=false`를 기본으로 사용한다.

macOS 진단 run43745916309의 원형10회 중3회(case0·4·9)에서 동일PGID의 SIGTERM 성공 뒤
SIGKILL이 EPERM(errno1)을 반환했고 `OwnedExecutionError`로 기록됐다. 오류 직후 그룹 멤버는0이었다.
별도 실험은 실제 zombie 상태에서 같은 EPERM을 확인했다. 원형 실패 순간 zombie-only 상태를 직접
관측한 것은 아니므로 그 세부 원인은 실험·XNU에 부합하는 설명으로 구분한다. SDK·firmware·USB
실행 실패가 아니며 제품 교정 전의 미해결 FAIL이다. 진단 workflow 성공은 제품 PASS로 세지 않는다.
원본 ZIP hash는 `e01b128bde4e760b987a20742a641138f8131d2908f516429ad87525e1c8c1af`,
보존은 `24009a/exit0`·`ee0889/exit0`이다.

## Ubuntu26.04/WSL2 호환성 마감

`a93b76/exit0`과 `D:/w06/h7u26/closure-a001.json`에서 C10 `4890f697…`의
Ubuntu26.04.1/WSL2 버전 호환성을 마감했다. 지원표는 Windows11 기준선 유지와
Ubuntu24.04·26.04/WSL2 완료로 **3/5**, C10 직접 완료는 **2행**이다.
macOS26·27, HOST-W07/W08 및 M33-W07은 아직 미완료다. native Ubuntu 실기로 확대하지 않는다.

| 항목 | 실제 결과 |
| --- | --- |
| 새 배포판 | 공식 Ubuntu26.04.1/WSL2, eidos 일반 계정. 기존 Ubuntu24와 기록 유지 |
| 고정 도구 | NCS3.4.0·Linux bundle `fbf7391cab`·Zephyr SDK1.0.1/GCC14.3.0. 공식 archive만 hash 확인 후 재사용, 설치본·compiled cache 복사 없음 |
| 설치·대표 빌드 | `0162dd/exit0`: SDK 설치·verify, lifecycle9단계·설치960파일·발견204, 대표4cold/4warm PASS |
| 이미지 비교 | `2a820d/exit0`: 대표4역할의 실제 BIN·HEX가 동일 C10 Ubuntu24 결과와 모두 같음. 이 비교로 다른 환경의 시험 실적을 이월하지 않음 |
| 한 보드 USB 실기 | `b00eb8/exit0`·`24cb1d/exit0`: 새 inventory로 선택, Blink/SerialEcho 업로드, GPIO9회, ELF 명령 일치·resume, nonce6개와 sync2회, probe·port 닫힘 |
| IDE | 공식2.3.11·WSLg·별도 profile. Boards Manager RC1 설치·NU54DK Standard·설치 Blink Verify322/322·Flash81572/RAM29439·정상 종료 `bf3885/exit0`, 설치960파일 일치 |
| IDE 감사 a001 | `ef1d70/exit1`: IDE 정상 종료로 임시 sketch가 삭제되어 사후 helper가 FileNotFoundError. 원본 helper·부분 산출물·FAIL 보존, 제품 빌드 FAIL 아님 |
| IDE 감사 a002 | `85287f/exit0`: 빌드시 sketch tree hash=설치 예제 tree hash, 실제 compiled source SHA와 산출물4개 대조. 새 감사만 수행하고 재빌드하지 않음 |
| 한글 표시 | 최초 GUI의 글꼴 미설치 관측은 보존. 종료 뒤 공식 `fonts-noto-cjk` 설치 `8adde9/exit0`, `fc-match :lang=ko`에서 Noto Sans CJK KR 확인 |
| 범위 | 전체204·두 보드 BLE·물리 USB 재연결은 반복하지 않음. Ubuntu24 기준선과26 버전 호환성을 별도 연결 |

## 문서·CI 범위 교정의 최종 결과

문서537개와 보드 하위 문서6개를 검토해 기존 관련 문서41개를 교정했고, 이 후속은 Ubuntu26 실제 결과만 갱신한다.
`441eca8f…` native CI run43749521754는5PASS·의도한SKIP2이며 artifact8개를 보존했다.
OS 버전별 전체204 반복은 기본 실행에서 제외했고 명시적인 전체 영향 검증에만 남겼다.

문서 source `6a8da3f…` M12 run43750924124 attempt1의 Windows Host unit은 첫 CMake configure의
90초 timeout으로 FAIL이다. raw SHA `3ef43cd2045ceb972f5b83fdd83dcebbbef78baebc40003b4d68993dc3d5c969`를 보존했다.
코드·환경·timeout을 바꾸지 않고 실패 job만1회 새로 실행한 attempt2는8PASS·조건부SKIP1로 완료했다.
같은 CMake 시험은7.760초에 통과했으나 최초 내부 지연 원인은 미확정이다. NCS 펌웨어 빌드 실패로 분류하지 않는다.
후속 PASS raw SHA는 `9c0dab42cc1c777ad695d7bc645d8ce9205fff17369b1cbc5b1884e8b3022e6d`다.
이후 증거 기록 전용 변경은 문서·원장 검사로 확인하며 같은 Host unit·전체 예제를 다시 실행하지 않는다.
