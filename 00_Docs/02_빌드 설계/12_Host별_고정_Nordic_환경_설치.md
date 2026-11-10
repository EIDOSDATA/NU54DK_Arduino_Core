# Host별 고정 Nordic 환경 설치

상태: HOST-W04 설치 범위 완료(같은 H4 source의 native3OS 설치·재검증3/3), W05 경로·cache·lock native 검증 완료, HOST-W06 완료·HOST-W07 준비 중.
현재 Windows stable 지원과 후속 OS 지원 판정은 구분한다.
순서는 [다중 Host 계약](10_v0.5.0_다중_Host_지원_착수_계약.md), 진행은
[Host 원장](../../variants/nu54dk/host-readiness.json)이 소유한다.

## 고정 입력

[OS별 manifest](../../tools/nu54-prerequisites/platform-pins.json)는 공식 URL·SHA-256·byte 크기를 고정한다.
NCS `v3.4.0`/`99553055…`, Zephyr `bf801e4e…`, board `fe65f2f0…`, core`8.2.1`,
launcher`1.4.1-f15ff58`, sdk-manager`1.16.1`, Arduino CLI`1.5.1`을 유지한다.
고정 core·toolchain archive를 검증한 뒤 sdk-manager에 전달하며 최신 core 자동 bootstrap을 사용하지 않는다.
SDK archive는 검증 후 별도 staging에 안전하게 추출하고 원형 `VERSION` byte를 유지한다.
SDK `v3.4.0`·SDK 절대 경로·고정 toolchain bundle ID를 명시하여 `sdk-manager sdk register`로 등록한다.
Windows·Ubuntu는 설치와 등록에 같은 `--install-dir`를 지정한다. macOS는 upstream 고정 위치를 사용한다.
등록 단계의 `--toolchain-path`는 `--install-dir`와 충돌하고 기본 root를 조회하므로 이 조합을 사용하지 않는다.
sdk-manager1.16.1의 SDK `--tarball` 설치는 이 archive의 다중 행 `VERSION`을 해석하지 못하므로 사용하지 않는다.
기존 SDK 경로는 덮어쓰지 않고 revision을 재검사한다. 추출 실패 staging은 진단용으로 보존한다.

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

## 장치·OS 권한 진단

설치된 toolchain Python에서 다음 읽기 전용 진단을 실행한다. serial·pyOCD가 없는 초기 Python은
해당 항목을 `ERROR`와 실패 exit로 기록하므로 설치 후 bundled Python을 사용한다.

```sh
python3 -I tools/nu54-prerequisites/host-doctor.py --include-probes --evidence host-diagnostic.json
```

포트 열기·flash·reset·halt는 수행하지 않는다. 실제 serial 열거 결과를 COM·Linux ACM/USB·macOS
종류로 분류하고 Linux by-id symlink의 실제 target을 결합한다. 공개 가능한 JSON에는 익명 alias와
SHA-256만 남긴다. serial 없는 장치에 임의 보드 identity를 만들지 않는다. Ubuntu에서는
`dpkg-query`로 `libc6`, `libstdc++6`, `libusb-1.0-0`, `libudev1`, `ca-certificates`, `xz-utils`의
실제 설치 version을 기록한다. 기준 OS는 Ubuntu24.04이며 별도 upstream 최소 version이 명시되지 않은
공유 library에 임의 하한을 만들지 않는다. 설치된 고정 toolchain의 실제 실행·CI 결과와 함께 판정한다.

Ubuntu에서 접근 오류가 발생하면 `id`, `ls -l /dev/ttyACM* /dev/ttyUSB*`, 해당 장치의 `udevadm info`를
사용자 PC에서 확인한다. 그룹·장치 mode와 현재 세션 권한을 대조하고 필요한 규칙 설치·그룹 변경 및
재로그인은 OS 관리자 절차로 진행한다. raw serial·by-id 경로가 나오는 원문은 공개 로그에 붙이지 않는다.
manifest의 [고정 nrf-udev README](https://github.com/NordicSemiconductor/nrf-udev/blob/1e057483a14d91f8ea2ff598a846767b079ea47b/README.md)는
기본 규칙이 모든 사용자에게 Nordic USB 접근을 허용한다고 명시한다. 이 설치기는 이를 자동 적용하지 않으며,
사용자 보안 정책에 따라 장치별 접근 범위를 검토한다. 전역 `chmod 777`은 사용하지 않는다.
macOS의 quarantine·Gatekeeper 상태와 `/opt/nordic/ncs` 쓰기 권한도 진단 후 정식 OS 절차로 해결한다.
보안 기능 비활성화·quarantine 일괄 제거를 설치 단계에 넣지 않는다.

## 증거와 사용자 최종 검사

[native CI](../../.github/workflows/host-native-prerequisites.yml)는 세 OS에서 같은 backend를 실행하고
exact commit·manifest hash·실제 version·SDK/Zephyr revision을 보존한다. 사용자 PC의 USB 동작을 대신하지 않는다.
최초 세 OS CI의 SDK 설치 실패와 교정 검증은 [312번 기록](<../04_검증 기록/312_HOST_W04_최초_CI_실패와_교정_검증.md>)에 구분한다.
Ubuntu/macOS 실제 설치·업로드·시리얼·ELF debug·갱신/재설치/제거는 M33-W07 시험용 RC1 준비 후
사용자가 검증하며 그 전에는 해당 행을 `NOT_RUN`으로 유지한다.

Windows 개발용 Host C++ 검사는 컴파일러와 동일한 배포본의 런타임 DLL을 사용해야 한다.
다른 MinGW 배포본이 PATH 앞에 있으면 빌드 성공 후에도 표준 library의 파일 I/O가 오동작할 수 있다.
SDK용 PATH와 Host 시험용 PATH를 실행 범위별로 구성하며, 이를 펌웨어 EEPROM 결함으로 판정하지 않는다.
macOS bundle은 `environment.json`의 `bin`·`usr/bin`·`usr/local/bin` 등 내부 경로를 선언한다.
고정 후보 외 도구도 이 선언 안에서 찾으며 전역 Python이나 bundle 밖 symlink를 대신 사용하지 않는다.
설치 확인 시 Python·west·compiler·size의 실제 version 출력을 함께 저장한다.
Twister의 PLY 생성물은 고정 SDK가 제공하는 `PARSETAB_DIR`를 사용해 실행별 경로로 분리한다.
병렬 build가 SDK의 같은 `parsetab.py`를 생성하는 경쟁을 피하며 SDK 원본은 수정하지 않는다.

공식 근거는 [고정 NCS 요구사항](https://github.com/nrfconnect/sdk-nrf/blob/99553055607b2e9885fbc80ccd11fa9da81c2df0/doc/nrf/installation/recommended_versions.rst),
[nrfutil 특정 version 설치](https://docs.nordicsemi.com/r/bundle/nrfutil/page/guides/installing.html/installing-a-specific-version-of-nrf-util),
[sdk-manager 기본 설치 위치](https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-sdk-manager/nrfutil-sdk-manager-install.html/default-installation-locations)다.
