# Host RC1 실기 도구와 증거 절차

상태: HOST-W07 준비 중, Host6/8. 비공개 RC1 도구 구현과 실제 완료 판정을 구분한다.
마지막 완료 기술 source는 [322번 H12 마감](<../04_검증 기록/322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md>)이다.
현재 도구 통합은 [323번](<../04_검증 기록/323_HOST_W07_도구_통합과_RC1_검증_착수.md>)을 따른다.
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
실제 downgrade 실행을 구분한다. 기존 Windows0.5 stable migration은 별도 미실행 행이다.
전체 build의 임시 서명 key는 attempt의 `private/`에만 두며 배포·공유하지 않는다.

## 대상 OS 행

2026-11-10 현재 descriptor의 최소 조건은 Windows10 x64·Ubuntu24.04 AMD64·macOS26 Apple Silicon이다.
이는 실행 가능 후보 판별이며 정식 지원 선언이 아니다. 고정 [NCS3.4.0 요구사항](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/doc/nrf/installation/recommended_versions.rst)의
시험 OS는 Windows11·Ubuntu24.04·macOS26이다. Windows Server2025 CI를 Windows10/11 실기로 바꾸지 않는다.

Ubuntu는 [공식 유지보수 표](https://ubuntu.com/about/release-cycle)의 현재 release 중 최소 조건 이상을,
macOS는 [Apple 보안 release 목록](https://support.apple.com/en-us/100100)의 major 중 최소 조건 이상을
검토했다. 아래 **모든 행**의 필수 gate를 판정하며 최소·최신 표본으로 줄이지 않는다.

| RC 검증 후보 | arch | 현재 사용자 실물 gate |
| --- | --- | --- |
| Windows10 | x64 | NOT_RUN — 기존 Core 호환 범위의 별도 회귀 |
| Windows11 | x64 | NOT_RUN — 현재 개발 PC 회귀는 별도 결과가 필요 |
| Ubuntu24.04 LTS | AMD64 | NOT_RUN |
| Ubuntu26.04 LTS | AMD64 | NOT_RUN |
| Ubuntu26.10 | AMD64 | NOT_RUN |
| macOS26 | Apple Silicon | NOT_RUN |
| macOS27 | Apple Silicon | NOT_RUN |

Ubuntu22.04와 macOS15는 현재 최소 조건 아래여서 지원 후보에 넣지 않는다. beta·다른 architecture·
미래 release를 descriptor의 version 비교만으로 정식 지원에 추가하지 않는다. RC 공개 전 공식 표를
다시 확인하고 실제 source/package에 결과를 결합한다.

## 기본 실행 순서

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

최종 Target build 행은 `build --all-examples` 결과가 필요하다. 대표4예제만 실행한 결과를
전체204PASS로 바꾸지 않는다. 해당 단계에는 NUS Peripheral·Central 두 역할도 포함된다.

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
