# Host별 고정 Nordic 환경 설치

상태: HOST-W04 구현·검증 진행 중. 현재 Windows stable 지원과 후속 OS 지원 판정은 구분한다.
순서는 [다중 Host 계약](10_v0.5.0_다중_Host_지원_착수_계약.md), 진행은
[Host 원장](../../variants/nu54dk/host-readiness.json)이 소유한다.

## 고정 입력

[OS별 manifest](../../tools/nu54-prerequisites/platform-pins.json)는 공식 URL·SHA-256·byte 크기를 고정한다.
NCS `v3.4.0`/`99553055…`, Zephyr `bf801e4e…`, board `fe65f2f0…`, core`8.2.1`,
launcher`1.4.1-f15ff58`, sdk-manager`1.16.1`, Arduino CLI`1.5.1`을 유지한다.
고정 archive를 검증한 뒤 sdk-manager에 전달하며 최신 core 자동 bootstrap을 사용하지 않는다.

| Host 후보 | Toolchain bundle | 설치 위치 |
| --- | --- | --- |
| Windows 10/11 x86-64 | `dcbdc366a1` | 사용자 `ncs`, 명시적 절대 경로 override 가능 |
| Ubuntu 24.04+ AMD64 | `fbf7391cab` | 사용자 `~/ncs`, 명시적 절대 경로 override 가능 |
| macOS 26+ Apple Silicon | `ccc010f809` | upstream 고정 `/opt/nordic/ncs` |

macOS 고정 경로의 쓰기 권한은 OS 관리 절차로 준비한다. 설치기는 전역 권한·Gatekeeper·quarantine을
변경하지 않는다. Linux USB 접근은 manifest에 고정한 upstream `nrf-udev`와 장치 권한 절차를 따른다.
실제 upload·serial·debug는 최종 사용자 Host 검사에서 검증한다.

## 저장소 개발용 명령

초기 backend에는 Python3.12 이상이 필요하다. 설치 후 SDK 검증·build에는 toolchain의 Python·Git를 쓴다.
Boards Manager 초기 runtime 공급과 post-install 연결은 HOST-W06의 별도 작업이다.
현재 Windows stable의 `post_install.bat`·PowerShell 경로는 보존한다.

```sh
python3 -I tools/nu54-prerequisites/nordic.py plan
python3 -I tools/nu54-prerequisites/nordic.py bootstrap
python3 -I tools/nu54-prerequisites/nordic.py install
python3 -I tools/nu54-prerequisites/nordic.py verify
```

`plan`은 설치하지 않는다. `bootstrap`은 고정 Nordic commands만 설치한다. `install`은 SDK·toolchain과
실제 revision을 검사한 뒤 ready marker를 쓴다. `verify`는 저장 상태를 재검사하며 새 설치 실적이 아니다.
Windows에서는 `python3` 자리에 명시한 Python 실행 파일을 사용한다.
`--state-root`, `--cache-root`, `--install-root`는 절대 경로만 받으며 macOS 설치 root는 고정이다.
`--evidence`는 수행 범위·Host·manifest/backend hash를 저장한다. 부분 다운로드·hash·OS/architecture·
version·revision 불일치는 실패하며 완료 marker로 승격하지 않는다.

## 증거와 사용자 최종 검사

[native CI](../../.github/workflows/host-native-prerequisites.yml)는 세 OS에서 같은 backend를 실행하고
exact commit·manifest hash·실제 version·SDK/Zephyr revision을 보존한다. 사용자 PC의 USB 동작을 대신하지 않는다.
Ubuntu/macOS 실제 설치·업로드·시리얼·ELF debug·갱신/재설치/제거는 M33-W07 시험용 RC1 준비 후
사용자가 검증하며 그 전에는 해당 행을 `NOT_RUN`으로 유지한다.

공식 근거는 [고정 NCS 요구사항](https://github.com/nrfconnect/sdk-nrf/blob/99553055607b2e9885fbc80ccd11fa9da81c2df0/doc/nrf/installation/recommended_versions.rst),
[nrfutil 특정 version 설치](https://docs.nordicsemi.com/r/bundle/nrfutil/page/guides/installing.html/installing-a-specific-version-of-nrf-util),
[sdk-manager 기본 설치 위치](https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-sdk-manager/nrfutil-sdk-manager-install.html/default-installation-locations)다.
