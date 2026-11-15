# Host RC1 실기 도구와 증거 절차

현행 위치는 **M33-W07 / HOST-W07, Host6/8·지원3/5**다. Windows11 기준선과 Ubuntu24.04·26.04/WSL2 완료를 보존한다. C11 macOS 실행기 교정·26/27 CI와 남은 실기는 [331번](<../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>), C6~C10 원본은 그 기록에 연결된330번을 따른다. 전체204를 반복하지 않는다.

HOST-W07은 C5 Windows 11 RC1 완료와 C8 부분 실적·FAIL을 보존하며 C9 실적·FAIL을 보존하고 C10 Ubuntu24.04/WSL2 마감과26.04/WSL2 호환성 검증을 완료했다. 지원3/5·Host 완료6/8이다.
마지막으로 완료한 전체 Host 작업 묶음은 [322번 H12의 HOST-W06](<../04_검증 기록/322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md>)이며, 후속 C5의 Windows 11 증거는 위 329번에 구분한다.
현재 도구 통합은 [323번](<../04_검증 기록/323_HOST_W07_도구_통합과_RC1_검증_착수.md>)을 따른다.
C1 Windows 진입점 FAIL·원형 보존과 C2 교정은 [324번](<../04_검증 기록/324_HOST_W07_C1_Windows_진입점_FAIL과_C2_교정.md>)을 따른다.
실제 RC source·archive·kit manifest SHA-256과 해당 CI·Windows 결과가 고정되기 전 이 절차를 PASS로 세지 않는다.

## 실행 단위와 경계

`tools/release/host_rc_kit.py`는 exact clean source에서 검증한 private producer·이전 H12 후보·
고정 세 OS CLI·초기 Python을 묶는다. 공개 tag·Release·catalog는 만들지 않는다.
kit의 `START.cmd` 또는 `START.sh`는 OS 기본 hash 도구로 초기 archive를 확인하고 관리 Python을
실행한다. 시스템 Python/Git 설치를 요구하지 않는다. 각 단계는 kit 원형 hash를 재검사한다.

출력은 kit 밖의 명시한 work root 아래 새 attempt에 남긴다. 같은 source의 실패를 덮어쓰거나
자동 재시도하지 않는다. SDK당 compile1·Ninja2를 유지한다. 기존 SDK 원본을 임시 patch 작업본으로
사용하지 않고 별도의 고정 SDK 설치를 준비한다. SDK upgrade·probe firmware 변경은 하지 않는다.

| 단계 | 도구가 검증하는 것 | 완료로 확대하지 않는 것 |
| --- | --- | --- |
| `plan` | source·version·kit hash·OS/arch·경로·순서 | 설치·build·장치 PASS |
| `install-sdk` | 공통 고정 prerequisite 설치 또는 기존 ready 재검증 | 다른 OS 설치·USB 지원 |
| `lifecycle` | host.1→RC1, 동일 version byte, 제거→재설치, RC post-install, SDK identity·사용자 데이터 보존,204예제 발견 | Windows stable0.5 migration·IDE GUI·물리 USB |
| `build` | 설치본 대표4예제의 cold/warm8compile·실제 manifest·SDK/Host/source | 전체204예제 |
| `build --all-examples` | 전체204cold·대표4warm·profile 거부9개·실제 signed image 검증 | runtime·다른 OS 실적 |
| `inventory` | 새 장치 열거, probe·serial·path의 SHA-256 | open·flash·reset·halt |
| `upload` | 검증된 image, exact probe hash, sector program, 유한 timeout·정리·log | LED·Serial·BLE runtime |
| `blink` | ELF/실제 명령 대조, 실행 중 P2.09 GPIO 출력 변화 읽기 | 광학 센서·외장 결선 검증 |
| `serial` | SerialEcho nonce, 두 번 open/close·재열거 | 실제 cable 분리·재연결 |
| `debug` | ELF symbol/실제 PC 명령 대조, halt→resume·probe close | IDE 자동 Debug·모든 debugger 조합 |
| `ble-pair` | 설치 NUS Peripheral/Central의 두 VCOM 사이 양방향 fresh nonce | 보안·외부 제품 상호운용·#29 분석 |

`lifecycle`은 이전 private 후보를 전이 입력으로 사용한다. 이전 source의 build/runtime PASS를
새 RC 실적으로 이월하지 않는다. downgrade는 kit 정책에서 CLI 실행 전에 거부하며, 이 정책 검사와
실제 downgrade 실행을 구분한다. Windows 11에서는 별도 격리 Arduino CLI 환경에서 공개 v0.5.0을 설치하고
C5 RC1으로 갱신해 RC post-install, 예제 204개 발견, Blink 빌드, 사용자 데이터와 SDK 보존을 확인했다.
기존 사용자 IDE 프로필을 통한 갱신과 IDE 검증은 별도로 기록한다.
전체 build의 임시 서명 key는 attempt의 `private/`에만 두며 배포·공유하지 않는다.

## 대상 OS 행

2026-11-15 확정한 v0.6.0 지원 목표와 실기 순서는 아래와 같다. 실행기의 OS 인식 조건과 공개 지원표의 판정은
별도로 기록한다. C5 자동 검증에 사용한 Ubuntu는 24.04 LTS, macOS는 26이며, 각 OS의 실제 장치 검증을
기록해야 한다. Windows 10과 Ubuntu 26.10은 v0.6.0 범위에서 제외했다.

| RC 검증 후보 | arch | 현재 사용자 실물 gate |
| --- | --- | --- |
| Windows 11 | x64 | 조건부 J-Link·격리 CLI 갱신·USB 재연결·잘못된 probe UID 거부 통과. COM17·18 기본 CMSIS-DAP 업로드·Blink PASS. COM5·6 초기화 FAIL 보존. COM18 재연결 후 UART PASS. IDE 2.3.11 비공개 RC1 설치·단독 Verify PASS |
| Ubuntu 24.04 LTS | AMD64 | C5 native CI 보존. C8 WSL2 설치·대표8·Blink·UART·debug·재연결·UID 거부 PASS. IDE PASS·BLE 원형 FAIL 보존. C9 설치·대표8·실기·BLE·IDE PASS 및 재연결 UART FAIL·전체204 중단13개 보존. C10 실기·재연결·IDE PASS; C5 전체 빌드 기준선+C10 변경 영향 검증 완료 |
| Ubuntu 26.04 LTS | AMD64 | C10 WSL2 버전 호환성 완료. 고정 SDK 설치·대표4cold/4warm·lifecycle·한 보드 USB/serial/debug·IDE PASS. 전체204·BLE·물리 재연결 반복 없음; native 사용자 실기 NOT_RUN |
| macOS 26 | Apple Silicon | C5 native 전체 빌드 PASS 보존. C11 실행기 교정·고정 SDK 새 설치·설치/lifecycle·대표4cold/4warm CI PASS. USB·IDE 실기 NOT_RUN; Mac 확보 필요 |
| macOS 27 | Apple Silicon | C11 macOS27 ARM64 고정 SDK 새 설치·설치/lifecycle·대표4cold/4warm CI PASS. USB·IDE 실기 NOT_RUN; Mac 확보 필요. 전체204 반복 없음 |

macOS 실기는 NU54DK와 CMSIS-DAP이 실제로 연결된 Apple Silicon Mac에서 진행한다. 대여 장비나
테스터가 같은 kit를 실행한 결과도 OS·kit hash·단계별 로그가 일치하면 검토할 수 있다.

## 기본 실행 순서

### Ubuntu 24.04 LTS / WSL2 준비와 실제 USB

2026-11-15 승인으로 WSL2는 C6부터 별도 실행 환경으로 검증한다. C5 kit는 WSL을 거부하므로
수정하거나 그 안의 파일을 바꿔 실행하지 않는다. 새 source·새 kit·새 work root를 사용한다.
Host는 `native=false`, `execution_environment=wsl2`로 기록한다. WSL2 PASS를 native Ubuntu
실기로 바꾸거나 기존 C5 Windows 실적과 합성하지 않는다.

1. 공식 WSL·usbipd 설치 파일의 SHA-256·서명을 확인하고 Windows 관리자 권한으로 설치한다.
   Windows 기능 설치가 재부팅을 요구하면 기록을 저장한 뒤 사용자가 재부팅한다.
2. Ubuntu 24.04 LTS AMD64를 설치하고 `wsl --list --verbose`의 VERSION2, `/etc/os-release`,
   `uname -r`, `uname -m`을 확인한다. USB 전달에는 최신 WSL과 커널5.10.60.1 이상을 사용한다.
   WSL1이나 환경 변수만 있는 판별 불명 환경은 지원하지 않는다.
3. kit·SDK·cache·build는 Linux 파일시스템 안의 별도 절대 경로에 둔다. 이 PC는 WSL 가상 디스크를
   `D:/w06/h7c6` 아래에 두고 Linux 안에서는 `/home/<사용자>/nu54-c6` 같은 경로를 사용한다.
   `/mnt/d`의 Windows SDK·cache를 빌드 작업본으로 공유하지 않는다. Windows mutex와 Linux flock은
   같은 SDK를 보호하는 공통 lock이 아니다. SDK당 compile1·Ninja2는 유지한다.
4. Linux kit의 첫 실행 전 `bzip2`를 설치한다. SDK runtime 의존성과 구분한다. 실패한 부분 추출은
   보존하고 새 kit 디렉터리에서 재개한다. 고정 Linux prerequisite와 공식 nrf-udev 규칙·serial 그룹을 확인한다. 사용자 비밀번호가 필요한
   sudo 입력은 사용자가 한다. 비밀번호를 로그·문서·대화에 저장하지 않는다.
   고정 nrf-udev의 VID1915 규칙은 DAPLink `0d28:0204`에 적용되지 않는다. 이 장치는
   [pyOCD CMSIS-DAP 규칙](https://github.com/pyocd/pyOCD/blob/main/udev/50-cmsis-dap.rules)을 참고해
   해당 VID/PID USB device를 plugdev0660, ttyACM 자식을 dialout0660으로 제한한다.
   사용자 그룹과 새 세션의 실제 접근 권한을 확인하고 최초 attach 전에 규칙을 reload한다.
5. Windows의 `usbipd state`와 현재 NU54DK 두 VCOM의 공통 물리 USB 부모·serial identity를 정확히 대조한다.
   재부팅 전 COM 번호나 BUSID만으로 같은 장치라고 판단하지 않는다.
   해당 BUSID만 관리자 `usbipd bind --busid <BUSID>`로 공유한 뒤, Ubuntu를 실행한 상태에서
   일반 권한 `usbipd attach --wsl --busid <BUSID>`로 전달한다. 첫 장치나 같은 VID/PID 전체를
   선택하지 않는다. 전달 중 Windows에서는 그 USB를 사용할 수 없다.
6. Linux `lsusb`와 kit inventory로 CMSIS-DAP·두 VCOM·권한·probe/serial/path hash를 새로 확인한다.
   Windows COM 번호를 Linux 경로로 추정하지 않는다. 그 후 검증된 새 source image로 upload·
   Blink·Serial·debug를 실행하고 IDE는 Linux판과 WSLg를 사용한다.
   Linux Arduino IDE 2.3.11은 공식 ZIP을 별도 경로에 풀고 WSLg에서 실행한다. 기본 Ubuntu에 없는
   `libnss3`, `libasound2t64`를 준비하고 한국어 표시에는 `fonts-noto-cjk`를 설치한다.
   새 IDE 설정·Boards Manager 데이터·cache를 사용하고 해당 검증 source의 고정 SDK 새 설치 설치본을 지정한다. 언어 서버의
   초기 분석이 끝난 뒤 단일 스케치 창에서 Verify하며 SDK당 compile1을 유지한다.
7. 물리 재연결은 사용자가 신호에 맞춰 분리하고10초 뒤 같은 포트에 연결한다. 새 usbipd state에서
   같은 물리 장치인지 확인한 뒤 attach·Linux inventory를 새로 수집한다. 분리·WSL 재시작 후
   attach 해제와 BUSID/port 변경을 정상적으로 처리하며 이전 identity를 무조건 재사용하지 않는다.

사용자 직접 작업은 Windows 관리자 승인·재부팅·Ubuntu 계정 비밀번호 입력·물리 USB 조작이다.
장치1개로 Blink·UART·debug를 진행하고 두 역할 BLE 검증에는 NU54DK2개를 사용한다.
[공식 WSL 설치](https://learn.microsoft.com/en-us/windows/wsl/install),
[USB 전달](https://learn.microsoft.com/en-us/windows/wsl/connect-usb),
[usbipd 자동화 JSON](https://github.com/dorssel/usbipd-win/wiki/Automation)을 따른다.

### 공통 kit 단계

Windows는 kit directory에서 다음 순서로 실행한다. `D:/w06/host-w07`은 개발 PC의 명시적 작업 예다.

~~~text
START.cmd --work-root D:/w06/host-w07 plan
START.cmd --work-root D:/w06/host-w07 install-sdk
START.cmd --work-root D:/w06/host-w07 lifecycle
START.cmd --work-root D:/w06/host-w07 build
START.cmd --work-root D:/w06/host-w07 inventory
~~~

Ubuntu/macOS에서는 `sh START.sh --work-root "$HOME/nu54-rc1" <단계>`를 사용한다.
macOS SDK root는 고정 `/opt/nordic/ncs`다. 폴더 소유권·실행 권한과 Ubuntu의 공식 `nrf-udev`·
serial 그룹 준비는 사용자 OS 환경에서 확인한다. 전역 권한을 완화하거나 Gatekeeper/quarantine을
자동 우회하지 않는다. 차단 시 OS 원문과 읽기 전용 진단을 실패 증거로 보존한다.

C5 전체 native 기준선을 보존하며 Ubuntu24.04/WSL2 C10과 새 OS 버전은 대표 build·설치·장치 경로와
변경 영향을 판정한다. `build --all-examples`는 SDK/compiler·firmware·compile 설정의 실제 전체 영향이
확인돼 명시한 경우에 사용한다. 매 source·OS 버전 변경의 기본 단계가 아니다.
대표4예제 결과를 전체204 PASS로 바꾸지 않으며 버전 차이만으로 전체204를 반복하지 않는다.
대표 단계에는 NUS Peripheral·Central 두 역할도 포함한다. Windows11 C5 완료에 C10 Windows Server2025 영향 검사134PASS·조건부SKIP7과 SDK 설치·재검증을 연결했다.

inventory의 SHA-256을 사용해 다음 명령을 실행한다. 아래 `A`, `B`, `SA`, `SB`, `PA`, `PB`는
각각 실제 inventory에서 고른 probe·serial·path SHA-256으로 바꾼다. 원시 UID는 기록하지 않는다.

~~~text
START.cmd --work-root D:/w06/host-w07 upload --example blink --probe-sha256 A
START.cmd --work-root D:/w06/host-w07 blink --example blink --probe-sha256 A
START.cmd --work-root D:/w06/host-w07 debug --example blink --probe-sha256 A
START.cmd --work-root D:/w06/host-w07 upload --example serial --probe-sha256 A
START.cmd --work-root D:/w06/host-w07 serial --example serial --probe-sha256 A --serial-sha256 SA --path-sha256 PA
START.cmd --work-root D:/w06/host-w07 upload --example nus-peripheral --probe-sha256 A
START.cmd --work-root D:/w06/host-w07 upload --example nus-central --probe-sha256 B
START.cmd --work-root D:/w06/host-w07 ble-pair --probe-sha256 A --peer-probe-sha256 B --serial-sha256 SA --peer-serial-sha256 SB --path-sha256 PA --peer-path-sha256 PB
~~~

NU54DK CMSIS-DAP의 BLE 검증에서는 C9부터 위 `ble-pair` 명령 끝에 `--assert-dtr`를 추가한다.
이 옵션은 양쪽 VCOM을 열기 전에 DTR 수신 준비 신호를 켜며 RTS는 끈다. C8의 DTR=false 실패와
DTR=true 단독 진단 결과는 [330번](<../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>)에 보존한다.
기본 false를 사용하는 기존 조건부 J-Link 절차와 구분하고, 임의 timeout 연장·사전 payload·자동 재시도는 하지 않는다.

기본 경로는 CMSIS-DAP이다. 조건부 J-Link-via-pyOCD에는 exact identity와 `--allow-jlink-backend`를 장치 명령에 함께 지정한다. 검토한 SDK의 공식 user script가 probe open 전 자동FW 갱신·GUI·전력 제어를 제한한다. 이 실적은 CMSIS-DAP 물리 PASS와 구분한다.

path hash는 같은 serial에 VCOM이 둘 이상일 때 혼동을 막는다. 실제 cable 재연결로 path가 바뀌면
inventory를 새로 수집하고 같은 serial을 대조한다. 자동 첫 port/probe 선택이나 runner fallback은 하지 않는다.
물리 cable 재연결, 잘못된 UID 거부, IDE2.x board/example 설치와 Windows stable migration은
해당 OS 최종 증거 표에 별도로 기록한다.

## 결과와 실패 수집

성공 단계는 `attempts/<단계-UTC>/result.json`과 실제 child log를 남긴다. 장치 작업은 build session·
cache·exact probe lock을 유지하며 timeout·중단 시 소유 process를 정리한 뒤 결과를 남긴다.
정리 상태 `UNCONFIRMED`나 debug `physical_recovery_pending=true`는 PASS가 아니며 후속 장치 작업을
진행하기 전에 상태를 확인한다. SDK 임시 patch 복원 실패도 숨기지 않는다.

실패·부분 출력·실제 nonzero exit와 조건부 skip을 그대로 보존한다. 공유할 자료는 kit manifest SHA,
OS/version/arch, 단계 result·log·build manifest와 허용한 ELF/HEX다. `private/`와 원시 UID·인증정보를
포함하지 않는다. 기존 W06 S19 actual46PASS·수락3·FAIL·soak는 이 kit의 실적과 분리한다.
사용자 실기 전 Host8/8·M33-W07 완료·정식 다중 OS 지원으로 표시하지 않는다.


## Windows IDE 검증의 실행 조건과 배포 경계

IDE 2.3.11은 Arduino 설정을 사용자 홈의 `.arduinoIDE`에서 읽는다. 격리 프로필에서는
AppData/Local·AppData/Roaming을 준비하고 process-local 환경으로 지정한다. 별도 SDK를 쓰면
설치기용 `NUCODE_NCS_INSTALL_ROOT`와 빌더용 `NUCODE_NCS_ROOT`가 같은 SDK 설치를 가리켜야 한다.
예제 창을 연 뒤 초기 빈 스케치 창을 닫고 백그라운드 구성 종료 후 Verify를 실행한다. 서로 다른
작업이 같은 SDK의 임시 patch를 동시에 사용하면 `E_SDK_PATCH`로 거부될 수 있다. 이는 기록된 제한이며
SDK 파일 수동 수정·보호 검사 해제·자동 재시도로 해결하지 않는다. 원본 FAIL은 별도로 보존한다.

C5 Windows 검증 당시 RC1은 고정 C5 ZIP을 로컬 HTTP index URL로 공급해 Boards Manager에서 설치한 비공개 검증이다.
정식 배포는 GitHub의 ZIP·index 게시 후 Preferences URL→Boards Manager 설치를 확인한다.
코드 commit만으로 게시용 ZIP과 index가 생성되거나 갱신되지는 않는다. 공개 URL 검증은 공개 승인 뒤 수행한다.

### C10 SerialEcho 첫 입력 줄 동기화

NU54DK CMSIS-DAP/WSL2의 재연결 UART는 `serial` 명령에 `--synchronize-line`을 추가한다.
각 open의 LF1회·완성된 setup echo를 별도 기록하고, 그 뒤 기존2open×3fresh nonce·정확 비교·
각5초 제한을 적용한다. setup는 PASS nonce에 포함하지 않으며 DTR/RTS=false와 재시도 금지를
유지한다. 옵션 기본값은 false다. setup 오류·timeout도 FAIL로 보존한다. USB attach 후에는
Linux udev 준비와 inventory의 identity·by-id·접근 권한을 확인한다. C9 재연결 FAIL은 보존하며
C10 새 attempt의 결과만 C10으로 기록한다. BLE의 `--assert-dtr`와 다른 옵션이다.
