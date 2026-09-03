# v0.1.0-rc.2 문제 해결

| 항목 | 내용 |
| --- | --- |
| 배포 상태 | **공개 완료 — `v0.1.0-rc.2` index와 ZIP checksum 검증 완료** |
| 작성자 | Quantum / NUCODE |
| 공식 지원 범위 | Windows 10/11 x64, NCS v3.4.0, NU54DK |
| 기본 Upload | 온보드 CMSIS-DAP V2 + pyOCD |

## 1. Core가 Boards Manager에 보이지 않음

Additional Boards Manager URLs에 다음 공개 주소를 한 줄로 등록한다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.1.0-rc.2/package_nucode_nu54dk_rc_index.json
```

```powershell
arduino-cli core update-index
arduino-cli core search nucode
```

회수된 `v0.1.0-rc.1` index를 사용하지 않는다. HTTP 오류가 나면 Release 공개 상태,
GitHub 접근, proxy, TLS 검사 제품과 시스템 시간을 확인한다. checksum이 다르면 우회
설치하지 말고 download cache를 지운 뒤 다시 받는다.

## 2. invalid UTF-8 gRPC 오류

rc.1에서 다음 오류가 설치 완료 뒤 표시될 수 있었다.

```text
Error: 13 INTERNAL: grpc: error while marshalling: string field contains invalid UTF-8
```

rc.2는 `post_install.bat`의 console code page와 PowerShell/native command 출력 인코딩을
UTF-8로 고정한다. rc.2에서도 같은 오류가 재현되면 반복 설치나 NCS 전체 삭제를 먼저 하지
말고 다음을 보존한다.

- Arduino IDE version과 bundled Arduino CLI version
- `%APPDATA%\Arduino IDE`의 해당 시각 log
- `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`의 prerequisite log
- 설치된 platform version과 prerequisite `ready.json` 존재 여부

공개 issue에 첨부하기 전 사용자 이름, device UID, token과 사설 경로를 제거한다. 화면이
실패를 표시해도 설치가 완료됐을 수 있으므로 IDE를 재시작하고 NU54DK board 열거 여부를
함께 확인한다.

## 3. prerequisite 검증 실패

rc.2 설치 디렉터리의 `post_install.bat`을 일반 사용자 권한으로 다시 실행할 수 있다.
단, 위 invalid UTF-8 오류만 발생했고 platform이 이미 설치됐다면 무조건 재실행하지 않는다.

```powershell
& "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.1.0-rc.2\post_install.bat"
```

| 진단 | 의미와 조치 |
| --- | --- |
| `E_PREREQUISITE_PINS` | package와 설치 pin이 다름. rc.2를 index에서 다시 설치 |
| `E_PREREQUISITE_READY` | 완료 marker가 없거나 불일치. installer log 확인 후 재개 |
| `E_PREREQUISITE_TOOLCHAIN` | 고정 Toolchain bundle이 없거나 손상됨 |
| `E_PREREQUISITE_NRFUTIL` | nRF Util byte hash 불일치. 임의 binary 사용 금지 |
| `E_PREREQUISITE_NCS` | NCS revision 불일치. 다른 workspace와 섞지 않고 고정 설치 복구 |

## 4. build path 또는 command 오류

M9 cache는 긴 Nordic object path를 피하기 위해 기본적으로 `%LOCALAPPDATA%\NU54\c`를
사용한다. 이를 더 긴 OneDrive·network path 아래로 옮기지 않는다. cache 이상이 의심되면
Core나 NCS 전체를 삭제하기 전에 Build Adapter의 cache diagnostic과 단일 entry 정리 절차를
사용한다.

## 5. NU54DK, Upload 또는 Serial 문제

- data 통신이 가능한 USB cable과 다른 USB port를 사용한다.
- DAPLink mass-storage와 UART port가 Windows 장치 관리자에 나타나는지 확인한다.
- Arduino Serial Monitor, debugger와 다른 pyOCD process를 닫는다.
- probe가 0개 또는 2개 이상이면 자동 선택하지 않는다.
- DAP UART를 115200 8N1로 연다. `Serial`은 target native USB CDC가 아니다.

일반 Upload는 mass erase/recover를 실행하지 않는다. 보안 상태 복구나 전체 erase는 별도
고위험 유지보수 작업이다.

## 6. Sketch compile 오류

- `nucode:zephyr:nu54dk`가 선택됐는지 확인한다.
- 지원표에서 API가 `미구현` 또는 `하드웨어 미지원`인지 확인한다.
- Zephyr API를 직접 사용할 때 필요한 header를 Sketch에 명시한다.
- AVR register, `PROGMEM`, USB 또는 특정 vendor HAL을 요구하는 library는 그대로 호환되지
  않을 수 있다.
- 이전 build directory를 재사용하지 말고 새 directory에서 한 번 compile한다.
