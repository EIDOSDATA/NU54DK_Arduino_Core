# HOST-W07 C11 — macOS 26 실기와 물리 USB 재연결

2026-11-23 macOS 26.7.3 (25G342) 네이티브 ARM64, 제품 `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa`, 원본 C11 kit `mac26-a002`에서 실행했다. SDK·패키지 설치와 대표 빌드 근거는 [335번](335_HOST_W07_C11_macOS_26_SDK_설치와_대표_빌드.md)에 있다. 사용자 지시에 따라 기존 USB 허브 경유 연결을 사용했다. 준비 문서 commit `870b69b9`의 [exact CI 45185528829/1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/45185528829)은 8 PASS·범위 SKIP 1로 완료됐다.

| 실기 항목 | 관측·판정 |
| --- | --- |
| Blink 업로드·런타임 | CMSIS-DAP 명시 probe로 업로드 PASS. P2.09 GPIO 출력 전이 9회, probe close 확인 |
| ELF 디버그 | 실제 PC의 명령 byte가 해당 ELF와 일치. CPU resume·probe close PASS |
| SerialEcho 업로드와 기본 UART | 업로드 PASS. 2회 open/close에서 새 nonce 6/6 일치, 포트 close 확인 |
| 첫 물리 재연결 | 사용자 분리와 같은 USB 위치의 재열거를 관측. USB 장치가 11.588초간 사라졌고 같은 serial 및 path 해시를 확인 |
| 재연결 직후 기본 UART | 재플래시·리셋 없이 첫 nonce를 송신했다. `E_HOST_SERIAL_TIMEOUT`, 외부 exit 1·worker exit 1. 처리기 종료 확인. 원형 FAIL |
| 명시적 줄 동기화 진단 | 같은 상태에서 기존 C11 `--synchronize-line`으로 LF setup 2회와 nonce 6/6 PASS. 첫 재연결 FAIL 후의 진단이며 새 물리 재연결 증거가 아니다 |
| 별도 재연결 관찰 | 줄 동기화 적용 조건을 검증하기 위해 새 관찰을 시작했으나 120초 이내 분리 이벤트가 없었다. 새 첫 UART는 `NOT_RUN` |
| 줄 동기화 사용 물리 재연결 | 사용자 준비 확인 후 11.587초간 분리, 같은 USB 위치·probe·serial·path를 재확인. 재플래시·리셋 없이 첫 LF 응답 17 bytes와 새 nonce 6/6 일치. UART close·처리기 종료 PASS |
| Arduino IDE 2.3.11 ARM64 | Boards Manager에서 C11 RC1 설치, 960개 archive 파일 대조, NU54DK 보드·설치 예제 발견 및 단일 Blink GUI Verify PASS. FLASH 81,572 bytes, RAM 29,439 bytes. 번들 CLI 1.6.0 |
| BLE 두 보드 | 이 Mac 호환성 실행에는 별도 BLE pair를 배정하지 않아 `NOT_RUN` |
| macOS 27 실기 | `NOT_RUN` |

첫 재연결의 USB 동일성, 포트 open 이후 응답 시간 초과와 프로세스 정리를 확인했다. 해당 시도의 UART byte 원문은 C11 실행기가 노출하지 않았으므로 WSL2에서 관측된 선두 byte 문제와 같은 원인이라고 확정할 수 없다. 새 물리 재연결에서 줄 동기화 첫 응답의 제거 payload는 0 bytes였다. 첫 응답 SHA-256은 `ac5d48c5ed20cdb76b82a63f20f04944f6835fc6d867531a48184b39c96cc83e`이다. 이후 6개 nonce만 PASS 분모에 포함했다.

IDE 첫 기동에서는 설정 경로 override가 적용되지 않아 기존 계정의 설정·최근 작업·기본 인덱스 파일 수정 시각이 갱신됐다. 그 시도는 후보 설치 전에 종료했다. 후속 실행은 사용자 승인으로 기존 계정의 IDE 설정을 사용했다. 후보 package data·downloads·sketchbook·build cache·임시 경로는 실행별 폴더로 지정하고 실제 백엔드 로그로 대조했다. 기본 `arduino-cli.yaml`의 SHA-256은 후속 실행 전후 동일했다. GUI Verify 뒤 IDE와 loopback 서버를 종료했다.

## 로컬 증거 해시

| 항목 | SHA-256 |
| --- | --- |
| `blink_worker` | `3f3373f2c0a0b9f583e59d5409b20a158fabc6fc156fb8fccf776c6e7c308cb3` |
| `debug_worker` | `870d1521cd671206217ad0f166490ff1d80b8244db989aa7f2ef36a2dd70e91a` |
| `serial_worker` | `499bf579b31c5d86515f4486ed1a5881db6b762f28843e4e66392c3686aabedb` |
| `replug_first_UART_failure` | `3cae3bf48ef8e5eb588dbfd9f4dc63e62bb2b999b74145d1e07fb82237747a60` |
| `replug_events` | `3e89c4ab9451b60b0128b544e5e0c8ab4c10fce1891c33dce75acb1b3f21a01c` |
| `line_sync_diagnostic` | `172eb459394e729a914a953fef6fde7cbca2623e613647fb15c5a816e955292c` |
| `second_observation_events` | `5a86b7d86fc80db63be101f8e6c046e1403b24fa70e148295e812beb0e38faf3` |
| `IDE_startup` | `8d2011d6550990722f2a0a4d15318806ea27212baa0238df35ea78d5b25b8fa1` |

| `sync_replug_events` | `bd0fe8578ff1d84049982907c0e9ba9219dfc7cb80e5601dabab2b2c02226da6` |
| `sync_replug_UART` | `f85f1b34ec3a216336389086713a23926b8797b31b7deeb88fc992d20ea3b137` |
| `sync_replug_physical_cleanup` | `9609d677742b79c21cd313e51dcab7a721c514eceb039518f246995832d54215` |
| `IDE_GUI_receipt` | `b662269e2af5d11802f07f362547e5e8a44979521cfe3f156a8674a0589610cd` |
| `IDE_GUI_stdout` | `25ba6ccae249019fe5a5ddf2cf93aa0da453803b6351fe869f0aff99c85898f6` |
| `IDE_Blink_manifest` | `360de965004c21f0ae968bca4a3ed26115767f92f96d4bc7abc19186192c9e22` |

raw log·exit code·장치 소유권과 정리 기록은 Mac control 원장에 보존한다. 사용자 승인 USB 허브와 명시적 UART 옵션의 macOS26 검증을 완료했다. Host 6/8, 지원 목표 검증 4/5, M33 수락 6/8·기술 5/8이다. macOS27 실기와 최종 후보 정합화 뒤 HOST-W07/W08과 M33-W07을 마감한다.
