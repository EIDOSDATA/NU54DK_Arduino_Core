# v0.6.0 설치 및 업로드 문제 해결

| IDE에서 보이는 증상 | 먼저 확인할 항목 |
| --- | --- |
| Windows에서 Verify가 1/5에서 멈추고 `ready.json` 파일이 없다고 표시됨 | 아래의 [Windows SDK 설치 복구](#windows-sdk-설치-복구)를 따르세요. |
| Windows에서 Verify는 성공했지만 Upload 중 `No ACK`, `Unexpected ACK` 또는 `FAULT ACK`가 표시됨 | [Windows에서 SWD 통신 오류가 날 때](#windows에서-swd-통신-오류가-날-때)를 따르세요. |
| Linux에서 Upload 중 `E_PROBE_NONE`이 표시됨 | [CMSIS-DAP USB 접근 권한](#cmsis-dap-usb-접근-권한)을 확인하세요. |
| Linux에서 `NU54_UPLOAD_START`와 `E_LOCK_PERMISSION`이 함께 표시됨 | [업로드 잠금 디렉터리 권한](#업로드-잠금-디렉터리-권한)을 확인하세요. |
| Verify는 성공했는데 LED가 그대로임 | **Upload**까지 끝났는지 확인하세요. 보드 한 대만 연결하고 Blink의 두 지연 값을 바꿔 보면 새 코드가 올라갔는지 구별할 수 있습니다. [Blink 따라 하기](EXAMPLE_WALKTHROUGH.md) |
| 포트가 두 개 보이거나 직렬 모니터에 응답이 없음 | SerialEcho를 올리고 **115200 baud**, **Newline**으로 `test`를 보내세요. 두 포트 중 `NUCODE_M6_ECHO:test`를 돌려주는 쪽이 이 스케치의 콘솔입니다. [SerialEcho 실행 절차](EXAMPLE_WALKTHROUGH.md#2-serialecho로-한-줄-주고받기) |
| 예제의 BLE 또는 주변장치 초기화가 실패함 | 열린 IDE 창에서 권장 Feature set과 보드 역할을 확인하세요. 예제를 복사했다면 같은 폴더의 설정 파일도 있어야 합니다. [메뉴별 준비물](FEATURE_SETS.md) |

## Windows SDK 설치 복구

`[NU54:E_PREREQUISITE_READY]`와 `[Errno 2] No such file or directory`가 함께 나오고 경로가 `prerequisites\ready.json`으로 끝난다면, 빌더가 현재 Windows 계정에서 SDK 설치 완료 기록을 찾지 못한 것입니다. 이 단계는 스케치 컴파일 전에 실행됩니다. NCS 3.4.0이 디스크에 있어도 설치본에 포함된 도구가 검증을 끝내야 이 기록이 생깁니다. 기본 상태 폴더는 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\prerequisites`입니다.

1. Arduino IDE와 같은 Windows 계정으로 일반 PowerShell을 엽니다. 아래는 Boards Manager의 기본 데이터 폴더를 사용하는 v0.6.0 설치본 기준입니다. 데이터 경로를 바꿨다면 첫 줄의 `Arduino15`까지를 실제 경로로 바꾸세요.

   ```powershell
   $core = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.6.0"
   $hook = Join-Path $core 'post_install.bat'
   Test-Path -LiteralPath $hook
   ```

2. 결과가 `True`이면 아래 두 줄을 실행하고 설치가 끝날 때까지 기다립니다. 설치본의 배치 파일은 패키지 전용 Python으로 SDK와 도구를 준비하고 검증한 뒤 `ready.json`을 기록합니다.

   ```powershell
   & $hook
   $LASTEXITCODE
   ```

3. 종료 코드가 **0**이면 현재 계정의 `prerequisites\ready.json`에서 `status`가 `ready`이고 `ncs_version`이 `v3.4.0`인지 확인한 뒤 IDE에서 Blink를 다시 **Verify**하세요. 실패하면 설치 출력에서 첫 오류를 확인하세요. `E_BOOTSTRAP`은 패키지 전용 Python을 찾지 못했다는 뜻입니다. Boards Manager에서 **NUCODE NU54DK Zephyr Boards 0.6.0**과 해당 도구의 설치를 확인하세요.

첫 단계가 `False`이면 IDE의 자세한 컴파일 출력에서 보드 플랫폼 경로를 찾아 그 폴더의 `post_install.bat`를 실행하세요. IDE가 v0.6.0 플랫폼을 찾지 못하면 [Boards Manager 설치 안내](README.md)를 따르세요. SDK 경로를 직접 지정한 설치에서는 IDE와 복구 명령이 같은 SDK 및 사용자 상태 폴더를 사용해야 합니다.

### SDK 다운로드 중 잠금 대기 시간이 초과될 때

`build lock 대기 시간이 초과되었습니다`가 `prerequisites\.adapter.lock`과 함께 표시되고 `owner.operation`이 `host-prerequisites`이면, PowerShell의 `Get-Process -Id`에 출력의 `owner.pid`를 넣어 기존 설치 프로세스가 실행 중인지 확인하세요. SDK 다운로드와 검증이 진행되는 동안 기존 설치가 잠금을 유지합니다. 이때 수동으로 실행한 훅은 30초 후 종료 코드 `1`을 반환할 수 있습니다.

1. 기존 설치가 진행 중이면 종료될 때까지 기다리세요. 다운로드와 검증을 마치면 설치기가 `ready.json`을 기록하고 잠금을 해제합니다.
2. 기존 프로세스가 종료되면 같은 Windows 계정의 PowerShell에서 위의 `& $hook`과 `$LASTEXITCODE`를 다시 실행하세요.
3. 종료 코드가 **0**이고 설치기가 기록한 `ready.json`에서 `status=ready`와 `ncs_version=v3.4.0`을 확인하면, IDE에서 `NU54DK (nRF54L15, Zephyr)`와 `Standard peripherals`를 선택하고 `File > Examples > NUCODE NU54DK > Blink`를 **Verify**하세요. 재실행이 실패하면 첫 오류, `owner` 정보, 종료 코드를 함께 보관하세요.

[Windows 11 복구 및 Blink Verify 기록](<../../04_검증 기록/341_v0.6.0_Windows_SDK_복구와_Blink_Verify.md>)

## Windows에서 SWD 통신 오류가 날 때

`[NU54 5/5]` 이후 `E_SWD_NO_ACK` 또는 `E_PYOCD_EXEC`가 표시되면 그 아래의 오류를 확인하세요. `Error probing AP` 또는 `Error reading AP`에 `No ACK`, `Unexpected ACK`, `FAULT ACK`가 붙으면, CMSIS-DAP 프로브가 MCU의 디버그 접근 포트를 탐색하는 단계에서 실패한 것입니다.

1. 실패한 Upload가 종료되면 대상 NU54DK 한 대만 연결한 상태에서 보드의 데이터 USB 케이블을 한 번 분리했다가 다시 연결하세요.
2. Windows 장치 관리자에서 `CMSIS-DAP v2`와 보드의 COM 포트가 다시 나타날 때까지 기다리세요. COM 번호가 바뀌었으면 IDE의 **Tools > Port**에서 현재 포트를 선택하세요.
3. IDE에서 `NU54DK (nRF54L15, Zephyr)`, `Standard peripherals`, 기본 **CMSIS-DAP** Upload probe로 설치 예제 Blink를 다시 **Upload**하세요. 출력에서 `NU54_UPLOAD_PASS`를 확인하세요.
4. 다시 실패하면 IDE 출력의 첫 SWD 오류와 빌드 폴더의 `nu54-zephyr/logs/flash.log`를 보관하세요.

Windows 11 검증에서는 USB 장치가 다시 인식된 뒤 이전에 실패했던 동일한 HEX를 업로드했습니다. **최초 SWD 오류 원인은 미확정입니다.** [Windows 11 SWD 오류 및 Blink Upload 검증 기록](<../../04_검증 기록/342_v0.6.0_Windows_SWD_오류와_Blink_Upload.md>)

## Linux에서 업로드 오류가 날 때

### CMSIS-DAP USB 접근 권한

`E_PROBE_NONE`은 업로드 도구가 사용할 수 있는 CMSIS-DAP 프로브를 찾지 못했다는 뜻입니다. `/dev/ttyACM0` 같은 시리얼 포트가 보여도 업로드에 쓰는 USB 장치에는 별도 접근 권한이 필요합니다.

1. NU54DK 한 대를 연결한 상태에서 `lsusb -d 0d28:0204`를 실행하세요. 출력이 비어 있으면 데이터 통신용 USB 케이블, USB 포트, 보드 전원을 확인하세요. WSL2에서는 Windows의 `usbipd`로 보드가 Ubuntu에 연결돼 있는지 확인하세요.
2. 장치가 보이면 `lsusb` 출력의 Bus와 Device 번호에 해당하는 `/dev/bus/usb/<Bus>/<Device>`의 권한을 확인하세요. Ubuntu에서 일반 계정에 읽기와 쓰기 권한이 없다면 아래 규칙을 추가합니다. `id -nG`에 `plugdev`가 없다면 `sudo usermod -aG plugdev "$(id -un)"`를 실행한 뒤 로그아웃하고 다시 로그인하세요.

   ```bash
   printf '%s\n' 'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="0d28", ATTR{idProduct}=="0204", GROUP="plugdev", MODE="0660"' |
     sudo tee /etc/udev/rules.d/70-nu54dk-cmsis-dap.rules >/dev/null
   sudo udevadm control --reload-rules
   ```

3. 보드 USB를 다시 연결하고 `lsusb`에서 현재 Bus와 Device 번호를 확인하세요. 해당 장치가 `root:plugdev`, 권한 `0660`으로 잡히면 일반 사용자로 연 IDE에서 다시 **Upload**하세요. 이 규칙은 재부팅 후에도 적용됩니다.

### 업로드 잠금 디렉터리 권한

`NU54_UPLOAD_START`와 함께 `[NU54:E_LOCK_PERMISSION] lock directory의 소유권·쓰기 권한을 확인하십시오.`가 표시되면, 프로브를 찾은 뒤 동시 업로드를 막는 잠금을 잡기 전에 멈춘 것입니다. v0.6.0은 `umask 0002` 환경에서 첫 업로드 때 `/tmp/n54`를 권한 `775`로 만들 수 있습니다. 업로드 도구는 그룹에 쓰기를 허용하는 디렉터리를 거부합니다.

1. 진행 중인 업로드가 끝나면 아래 명령으로 `/tmp/n54`의 소유자와 권한을 확인하세요.

   ```bash
   stat -c '%a %U %F %n' /tmp/n54
   ```

2. 현재 계정이 소유한 실제 디렉터리이고 권한이 `775`이면 `chmod 700 /tmp/n54`를 실행하세요. 소유자가 다르거나 심볼릭 링크라면 경로와 소유권을 관리자에게 확인하세요.
3. IDE에서 다시 **Upload**를 누르고 `NU54_UPLOAD_PASS`와 `Done uploading.`을 확인하세요.

`/tmp`가 초기화되면 v0.6.0에서 이 오류가 다시 발생할 수 있습니다. `/tmp/n54`가 없는 상태라면 첫 업로드 전에 IDE와 같은 일반 계정으로 `mkdir -m 700 /tmp/n54`를 실행해 두세요. [Ubuntu 26.04.1 진단 기록](<../../04_검증 기록/343_v0.6.0_Ubuntu_USB와_업로드_잠금_권한.md>)

## Mac IDE에서 YAML 오류가 뜰 때

C11에서 `Verify`는 성공해도 일반 `Upload`가 `E_RUNNER_UNAVAILABLE`로 중단되고 상세 메시지에 `No module named 'yaml'`가 표시될 수 있습니다. 이 경우에는 IDE가 probe를 선택하기 전에 패키지의 초기 Python 3.12.16이 runner 설정을 읽다가 중단된 것입니다.

1. Boards Manager에 등록된 시험용 인덱스 URL을 제거합니다. 설치 목록에 `0.6.0-rc.1`이 남아 있다면 그 버전을 제거합니다.
2. [설치 안내](README.md)에 따라 공개 v0.6.0을 설치합니다. 설치본의 `release-manifest.json`에 있는 `core_revision`은 `0a63c501ccd0d2e26298f1ad98a81a99cddc565f`입니다. C12에서 확인한 SDK Python과 PyYAML 사용 수정이 포함됩니다.
3. 실제 NU54DK 포트와 `Standard peripherals`를 선택하고 Blink에서 일반 **Upload**를 누릅니다. 정상 출력은 `NU54_UPLOAD_PASS`와 `Done uploading.`입니다. [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)

## 그 밖의 증상

| 환경·증상 | 확인 순서 |
| --- | --- |
| Boards Manager에 0.6.0이 없음 | [정식 인덱스 URL](README.md)이 추가됐는지 확인하고 Boards Manager 목록을 새로 고친다. 표시된 버전이 0.6.0인지 확인한다 |
| Windows 11에서 probe/COM이 바뀜 | 현재 장치를 다시 열거하고 hash를 확인한다. 과거 COM 번호로 장치를 추정하지 않는다. 여러 probe면 명시 UID를 사용한다 |
| WSL2에서 USB가 없음 | WSL VERSION2와 실제 usbipd 연결 상태를 확인하고 Linux에서 probe/serial을 다시 열거한다. 재연결 뒤 attach가 필요한지 확인한다 |
| WSL2 permission/build 경로 오류 | Linux 그룹/udev와 Linux 파일시스템의 SDK·cache 경로를 확인한다. `/mnt/d`의 Windows SDK/cache와 공유하지 않는다 |
| Mac 설치·실행 권한 오류 | Mac의 OS 버전과 아키텍처, kit 해시, 설치 권한, Gatekeeper 메시지를 기록한다. 보안 우회나 전역 권한 완화를 하지 않는다 |
| Mac process 정리 EPERM | C10 원형과 C11을 구분한다. C11에서도 실패하면 같은 PGID·시각·원래 오류를 새 attempt에 보존한다. 그룹 부재 확인 없이 PASS로 처리하지 않는다 |
| IDE Verify와 CLI 결과가 다름 | 후보의 소스 SHA, 보드, Feature set, 예제와 IDE 로그를 확인한다. 다른 source 설치본이나 IDE 창의 동시 빌드 혼입을 확인한다 |
| compile/runtime 실패 | 첫 오류가 설치, 빌드, 보드 연결, 실행 중 어디에서 발생했는지 확인한다. compile PASS와 실제 보드 동작은 별도 판정이다 |

문제를 보고할 때는 OS, IDE와 패키지 버전, 예제 이름, Feature set, 첫 오류 메시지를 적어 주세요. 개발용 kit를 재현할 때는 소스 SHA, kit 해시, 종료 코드도 함께 기록합니다.

구체적인 명령과 기대 출력은 [Host RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>),
고정 설치 입력은 [Nordic 환경 설치](<../../02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)를 따른다.
macOS26의 실제 재연결은 기본 UART timeout 기록을 보존한 뒤 C11의 명시적 `--synchronize-line`을 선택해 통과했다. IDE 2.3.11은 현재 계정의 설정을 사용했고 CLI 실행 환경에서 후보 인덱스·데이터·캐시를 분리했다. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>)
