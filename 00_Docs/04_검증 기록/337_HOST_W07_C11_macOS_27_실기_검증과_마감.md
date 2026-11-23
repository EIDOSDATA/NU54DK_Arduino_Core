# HOST-W07 C11 — macOS 27 실기와 배정 검증 마감

2026-11-24 KST 실제 macOS 27.2.1 (26B131), native Apple Silicon ARM64에서 C11의 배정 실기를 완료했다.
문서 checkout은 `694afb67b53f779688b8c224e1d0aa914ffece87`, 제품은 `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa`이고 board submodule은 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`다.
원본 kit 201,857,017 bytes와 SHA-256 `c1792818979453ce3150d7b19abf960f3d14a31f970c4578f5f41afcf5cf8208`를 대조하고 Mac26에서 승인된 동일 원본 kit를 사용했다. 새 Mac27 work/TMP/cache와 writer를 사용했다.

| 항목 | 관측·판정 |
| --- | --- |
| SDK·lifecycle | `/opt/nordic/ncs`의 NCS 3.4.0·`ccc010f809`를 새 Mac27 상태에 등록·검증했다. lifecycle PASS, 라이브러리 24개·예제 204개 발견. C11 두 버전 fixture이며 공개본 upgrade 증거는 별도다. |
| 대표 build | 4 cold·4 warm PASS. BIN/HEX 8개가 동일 C11 [software CI artifact 14180588447](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43760678488)의 macOS 27.0.1 결과와 일치했다. |
| Blink·ELF debug | 승인된 USB 허브에서 새 inventory로 고른 CMSIS-DAP 명시 probe에 업로드했다. Blink GPIO 전이 9회, 실제 PC 명령 byte의 ELF 일치, resume 및 probe close PASS. |
| SerialEcho | 같은 보드에 업로드, 두 open/close에서 기본 nonce 6/6 PASS. |
| 첫 USB 관찰 | 분리 미감지 타임아웃. 관찰기 exit 1, UART 미실행. |
| 물리 USB 재연결 | 사용자 준비 신호 후 관찰을 다시 시작했다. 13.322초 동안 USB descriptor 부재 뒤 같은 장치·허브 포트·콘솔을 확인했다. 새 inventory와 probe/serial/path hash를 대조했다. 재플래시·리셋 없이 첫 UART에서 명시적 LF 동기화를 진행했고 첫 응답 29 bytes 및 새 nonce 6/6를 기록했다. LF 응답은 nonce 집계에서 제외했다. |
| Arduino IDE 2.3.11 | 현재 계정에서 후보 데이터·다운로드·sketchbook·cache·임시 경로를 분리했다. Boards Manager가 원본 C11 RC1 archive를 설치했고 960개 파일을 대조했다. 명시적 Sketch → Verify/Compile로 설치된 Blink를 검증했다. 실제 FQBN은 `nucode:zephyr:nu54dk:upload_probe=pyocd,feature_set=ble`이며 FLASH 81,528 bytes, RAM 29,439 bytes다. 이 GUI compile은 BLE 두 보드 실기에 포함하지 않는다. |
| 별도 IDE Upload | standard Blink가 컴파일됐으나 Upload는 `NU54:E_RUNNER_UNAVAILABLE`, `No module named 'yaml'`, exit 2로 실패했다. Boards Manager Python 3.12.16의 격리 실행에는 PyYAML이 없고, 고정 SDK Python 3.12.4의 PyYAML 6.0.3으로 같은 runner metadata 검사를 통과했다. parser만 비교했으며 probe 선택 전 오류다. 최종 후보에서 수정 뒤 새 패키지와 명시 probe로 정상 Upload를 검증한다. |
| 종료 | 새 SDK 재검증 및 같은 보드 SerialEcho 6/6으로 상태를 확인했다. IDE exit 0, mirror 종료, 보유 포트·처리기 없음. w06 PAUSED. |
| BLE 두 보드 | 이 Host 호환성 시험의 배정 밖으로 `NOT_RUN`. |

Mac27 배정 실기 완료로 지원 목표 검증 **5/5**, HOST-W07 완료로 Host **7/8**이다. macOS26·Ubuntu24.04는 기존 결과를 보존하며 사용자 지시에 따라 반복하지 않는다. W06은 실제 PASS46과 명시 수락 #29·40·44를 유지한다. M33 수락6/8·기술5/8이며 최종 후보의 정합화·재현성과 IDE Upload 교정 검증, HOST-W08 최종 gate가 남았다.

## 로컬 증거 SHA-256

원형 로그·exit code·manifest·writer 기록은 로컬 `work/mac27-c11-a001.zl2MAI/control` 및 해당 attempt 아래 보존했다.

| 파일 | SHA-256 |
| --- | --- |
| `plan` | `b6892ee0aa2b89cac84dd8b11e89088508944b8d64e7b61d8a274b425fdf8bbf` |
| `sdk_verify` | `59534d6c6af7228e898014e08a43d73e892ae8d11881aea991b83948b89ec131` |
| `sdk_verify_after_IDE` | `59534d6c6af7228e898014e08a43d73e892ae8d11881aea991b83948b89ec131` |
| `lifecycle` | `4bbce99fa5604b5370b9937b50dbc4299647adb7fead4df8feead85ca0ad69a6` |
| `build` | `86b3ef24ec2577b90f71db7451c0cc09959f28455a075da9faabe2335f9afc16` |
| `inventory` | `fad4947de0de1afec6314867a5b28b8ebd8fbd82809cf9921224345a858dcfd3` |
| `reference_BIN_HEX_comparison` | `b1505dc847a4b40fe0da765e9b56f40c0bc5afd4fa8404c5a28d2b844491597f` |
| `blink_worker` | `305dd2033bfaa5fb1392838b33880a1aaed1aef217c346b390bff3ad8bcabdff` |
| `debug_worker` | `d7df6a75c26ad153ec27979b0969d3ec4851e8a9bdac287cdb7b9678daca79cc` |
| `serial_worker` | `fbcde6d438871141617ccb4aa1c8e2721755f4db22c8a7f5e4434d7ad7f9d81a` |
| `first_observation_timeout` | `2167d23a66acd477a40b66204c9a3d7bf2043a30a12bbf4c45863c3e13ee1006` |
| `physical_replug_events` | `597a653d49a0b86590a6c8d4b32391d7a1660cb3d59476ad252d5f34886c343c` |
| `post_replug_inventory` | `fad4947de0de1afec6314867a5b28b8ebd8fbd82809cf9921224345a858dcfd3` |
| `first_replug_UART` | `fea5f92aedcd89ffe73103316a0254aed091c4123eaa5ea2f607cc479750199e` |
| `first_replug_UART_cleanup` | `2e73007778b039c26f7cd5071e7e9671140f5fddf6f2037a76944b42e83ca5e2` |
| `IDE_GUI_verify` | `f3954217fd398fc02d659390e468dd132cabbc6e15a7d046cbbfe74b88882fa4` |
| `IDE_install_verify_audit` | `fe89c3e8024acf6d1f84ebee6b080d2901062b4e5b26ef748a759148de80d7c4` |
| `IDE_verify_build_log` | `c9a1ec261fb8a5595698ab2b86008576803f6c9553a3fee21ea38fac90b8fb6b` |
| `IDE_verify_manifest` | `47053bc89f9558532e89f439935a98fd6ccde5c9ddd3f764fdfb529c46b74203` |
| `IDE_run_log` | `e771ea9b1d7975d8a42df32da67430e23eb67d146afaf064adff78a4a2a7c1a7` |
| `IDE_upload_failure` | `5fe59ecba77e98395df3e8d58e190e2d13d1974cc589a6ae157bd7af76c08f82` |
| `IDE_upload_parser_failure` | `713352c78645e62b794501be2f541410266ee6006092a3fa7bf8bdfd915abcae` |
| `IDE_upload_runtime_comparison` | `7dd0617dcca13eda68837380f46abcbc5b9f707411579ef11354d0fa188ba781` |
| `post_IDE_serial_worker` | `5d5ef83fbefdbf9cd098200fb3c9bba9f15b545b25d7995f07f35d9cd0f26b52` |
| `STOP_cleanup` | `384e1e6702de98ce0cc503847218226294dfad5baedac022d1c36fdcc8136852` |
