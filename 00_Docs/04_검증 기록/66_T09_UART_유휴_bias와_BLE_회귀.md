# T09 UART 유휴 bias 교정과 BLE 무배선 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | T09/T14 추가 USB·온보드·BLE; 외부 current-source T11 직전 정지 |
| 최초 exact source | `18a7cbec9cceed38d6c866131afdac9e6ffbc4b8` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 최신 사용자 확인 | 전원 OFF 후 DAP UART 연결 전환·USB 재연결 완료, SWD 연결 유지, 보드 간 선 없음 |
| 진행 상태 | BLE M19/M20/M21 PASS; idle bias 수정 뒤 온보드 실제 회귀 대기 |

## 최초 결과와 교정 근거

`C:/u2a` exact 18a7cbe의 17개 target은 build-only 17/17, failed/error/warning 0이다.
두 보드는 D/COM5·COM6과 E/COM7·COM8로 식별했고 UID 원문은 기록하지 않았다.
앞선 65번의 UART 분리 상태는 역사적 사실이며 이번 사용자 확인으로 연결 상태가 바뀌었다.

TWIM20/21은 두 보드 모두 PMIC `0x41`을 반환했으나 TWIM22 READY는 A 34바이트,
B 33바이트로 실패했다. B에서는 정확한 32바이트 앞의 `f8`을 포착했다.
A의 같은 TWIM22 image를 flash 없이 한 번 reset한 진단에서는 정확한 READY·PMIC 결과가
통과했다. 이 진단을 최초 suite PASS로 대체하지 않는다. M25 A도 READY prefix 6바이트로 실패했다.
UART20은 양쪽 보드 모두 선택 P1 VCOM에서 정확한 32바이트 역순 응답을 받았으나
비선택 P0 VCOM에 각각 11/12바이트가 들어와 strict oracle이 실패했다.

B UART20의 동일 firmware에서 비선택 P0.00 PIN_CNF는 `0x2`(입력, pull 없음)였다.
한 번의 비교 진단에서 원래 설정은 비선택 COM8 9바이트로 실패했고, PULL 필드만 임시
pull-up `0xe`로 바꾸면 선택 COM7의 정확한 응답과 COM8 무응답이 함께 통과했다.
진단 뒤 PIN_CNF `0x2` 복원을 readback으로 확인했다. 흐름제어·CTS 시험은 하지 않았다.
이 근거는 온보드 fixture의 유휴 bias 누락을 가리키며 납땜 위치나 모든 USB 잡음 원인을
확정하는 전기적 측정은 아니다.

`onboard_start.py`는 exact CPUID와 HALTED 상태 확인 뒤 P0.00·P1.04가 입력인지 먼저
검사하고 PULL만 변경한다. 두 pin 모두 검사한 뒤 쓰며 readback 실패 시 resume하지 않는다.
그 뒤 초기 VCOM buffer를 비우고 앱을 시작한다. READY·응답의 추가 byte, 중복 응답과
비선택 포트의 데이터 거부는 그대로다. 제품 runtime·공개 API·저장 형식·board·SDK는 변경하지 않는다.
신규 Host 3개는 수정 전 3 FAIL, 수정 후 3 PASS이며 온보드 전체 관련 Host 28개 PASS다.
현재 이 단계의 교정은 실제 보드 재검증 전이므로 완료 PASS로 선언하지 않는다.

## BLE actual pair 결과

모두 clean exact 18a7cbe에서 canonical runner·DAPLink MSD flash·COM5/COM7·128-bit nonce를
사용했다. 두 보드 사이 전선 없이 RF로 실행했고 raw transcript와 원본 JSON을 작업 폴더
`work/t09-connected`에 보존했다. 후속 evidence 등록 시 원본 byte와 hash를 함께 남긴다.

| Gate | 실제 결과 |
| --- | --- |
| M19 GAP | scan filter·advertising·link request·connect/disconnect·재광고·재연결·callback 문맥 PASS |
| M20 generic GATT | discovery·read/write·notify/indicate·unsubscribe·disconnect 뒤 handle 무효화·재발견 PASS |
| M21 security/profile | pairing·bond warm-reboot 복원·삭제 뒤 재부팅 zero·old-key 거부·repair·BAS/DIS/HID protocol PASS |

M21은 시험 bond를 clear/erase/re-pair하며 factory reset이나 mass erase를 하지 않았다.
Windows/스마트폰 HID 입력 수동 확인, AC-03 EEPROM/LittleFS 파괴 시험과 최종 RC lifecycle은
이번 BLE PASS에 포함하지 않는다. 기존 peer P0 CTS 납땜 이슈의 중단 지시도 유지한다.

## 다음 재개

이 교정 commit 뒤 exact 온보드 9개와 마지막 pair 역할 2개 이미지를 새로 build한다.
두 보드의 UART/TWIM/M25/M26을 strict canonical runner로 재검증하고 실패하면 원본을 보존한다.
종료 시 TODO·문서 진입점·증거를 갱신하고 commit/main push·clean/process 검사를 수행한다.
외부 Fixture 101 명령은 실행하지 않는다. 기존 R13 software 근거와 c94298f 904 PASS는
각각 64/65번의 source에 보존하며 새로운 physical PASS로 복사하지 않는다.
