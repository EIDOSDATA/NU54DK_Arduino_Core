# M24~M26 온보드 재개와 USB·UART 진단

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-V04-ONBOARD-RESUME-001 |
| 기록일 | 2026-09-04 |
| Target image source | `e4d3ae70bb815a2f6a762e7116915729ff8a9b22` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **18/18 build-only PASS, M26 flash/readback 확인, formal HIL HOLD** |

## 1. 실제로 확인한 범위

기존 [M27 HOLD 기록](39_M27_v0.4.0_rc1_자동_준비와_HOLD.md) 이후 USB 재연결로 SWD
CPUID `0x411fd210`을 읽었다. `e4d3ae7`에서 모든 신규 온보드 runner의 pyOCD 호출에
`--no-config -O auto_unlock=false --erase sector`를 명시했다. 자동 unlock에 따른 mass erase와
프로젝트 외부 pyOCD 설정의 유입을 방지하며, recover나 전체 삭제는 수행하지 않았다.

같은 clean source에서 `v0.4.0` 그룹 18개를 새 `C:\v4n`에 build했다. 결과는 **18개 build-only,
failed 0, error 0, warning 0, 372.63초**다. 이 숫자는 target에서 실행한 시험 수가 아니다.

| 증거 | SHA-256 |
| --- | --- |
| 전체 build log | `66f6f794fdc84e2d893def956366dc75b09703e106b79f99a106dfb858f8be7d` |
| M26 `zephyr.hex` | `fd5ad734b9eb21719f3eea1a8732763fe43d0e4740eb78261c1c679d8e2d993a` |

로컬 log는 작업 공간의 `work/v04-resume-e4d3ae7/`에 보존했다. HEX는
`C:\v4n\nrf54l15dk_nrf54l15_cpuapp_nu54dk\zephyr_gnu\nucode.m26.onboard_hil\m26_onboard_hil\zephyr\zephyr.hex`다.
pyOCD load가 성공한 뒤 Intel HEX에 존재하는 두 구간 `[0, 46356)`, `[46368, 78528)`을
target에서 전부 읽어 byte equality를 확인했다. 이는 해당 image의 실제 기록·readback 확인이며
runtime protocol 전체 PASS와는 별개다.

## 2. M26 UART 진단 — PASS로 승격하지 않은 이유

Formal runner는 최초 READY 32바이트를 받지 못해 실패했다. 디버거에서 firmware가 UART30
초기화와 TX completion을 지난 뒤 `receiveCommand()`에서 기다리는 것을 확인했다. 이후 별도
진단으로 기존 시험 보드의 두 VCOM에 command를 전송하자 COM5는 무응답, COM6은 다음 순서로
총 67바이트를 반환했다.

| 구간 | 실제 관측 | 의미 |
| --- | --- | --- |
| `AR26` 32바이트 | TEMP 2825 centi-°C, configure/start/feed 성공 | WDT30 arm 응답 |
| 중간 3바이트 | `fe 3e de` | 예상하지 않은 데이터, 원인 미확정 |
| `NU26` 32바이트 | reset cause `0x10`, supported mask `0x9B3`, retained TEMP 동일 | watchdog reset 뒤 결과 응답 |

두 packet의 checksum은 각각 유효하지만 **READY 누락과 중간 잡음이 있어 formal HIL PASS가
아니다.** 진단에서는 frame을 분리해 내용을 읽었을 뿐, runner에서 잡음을 무시하도록 바꾸거나
PASS evidence JSON을 만들지 않았다. WDT 뒤 SWD `No ACK`가 다시 발생했고, 이후 Windows에서
기존 COM5/COM6도 사라졌다. 별도 보드의 COM7/COM8은 계속 나타났다. 연결 이탈 원인은 아직
확정하지 않았으며, 그 별도 보드의 firmware는 변경하지 않았다.

Host result validator는 firmware의 PASS flag만 믿지 않고 Zephyr `RESET_WATCHDOG = BIT(4)`가
실제로 있는지, reset cause가 supported mask 밖의 bit를 포함하지 않는지 검사하도록 강화했다.
이전 unit fixture의 reset cause `4`는 watchdog bit가 아니므로 `16`으로 교정했다. 실제 진단
packet과 중간 잡음 거부도 회귀 시험으로 고정했다. 이 host-only 변경은 위 target image의
source identity를 소급 변경하지 않는다.

교정 뒤 onboard host unit 20/20, CI contract unit 45/45, Markdown UTF-8·local-link
136개, inventory/M24/M26/M27 계약 검사를 통과했다. 이들은 물리 시험을 대신하지 않는다.

## 3. Windows 차단 알림과 별도 문제

Code Integrity Operational의 3033/3077 이벤트에서 Nordic
`arm-zephyr-eabi-gdb-py.exe`가 외부 WinLibs `iconv.exe`를 실행하려다 차단된 것을 확인했다.
확인한 이벤트 범위에서 pyOCD 자체 차단은 발견하지 못했다. 이후 target 진단은 외부 WinLibs를
뺀 child-session PATH로 실행했다. 보안 정책·허용 목록·전역 PATH는 변경하지 않았다.

따라서 이 알림을 SWD/USB/UART 실패의 공통 원인으로 단정하지 않는다. Host MinGW와 Nordic
target 환경 분리 및 차단 파일 확인 절차는
[Windows 개발환경 설정](<../02_빌드 설계/09_Windows_개발환경_설정.md#host-mingw와-target-도구의-path-분리>)에 추가했다.

## 4. 남은 순서

1. 기존 DUT의 USB/VCOM 연결이 안정적으로 유지되는지 확인한다.
2. READY 송신과 VCOM 수신·reset 순서를 재현해 초기 누락과 reset 경계 잡음의 원인을 분리한다.
3. 수정이 필요한 경우 source를 고정·재build하고 M24 UARTE 4개, TWIM 3개, M25 내부 VDD/event,
   M26 TEMP/WDT30를 exact runner로 다시 실행한다. 현재 상태에서 어느 onboard gate도 상향하지 않는다.
4. 외부 배선·계측 gate와 frozen RC·설치 수명주기는 기존 계획대로 남긴다. 공개 release/index와
   기존 stable 자산은 변경하지 않는다.
