# M29-W02 link별 GATT client와 long read 완료

> 이 기록의 진행률·미실행·다음 작업은 해당 W 단계 완료 당시의 상태입니다. 후속 W07-C의
> Signed Write·EATT 2보드 결과는 [147번 기록](147_M29_W07_Signed_Write_EATT_HIL_준비.md)에,
> 현재 작업과 남은 범위는 [v0.5.0 TODO](../TODO_v0.5.0.md)에 있습니다.

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| exact Core | `dacf6341b2326235f4daf85d9582212a475a9cf9` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| Host | **전체 M12 Host gate PASS** |
| W02 parser / source 계약 | **11/11 / 6/6 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| Arduino 예제 build | **LongGattPeripheral·LongGattCentral 2/2 PASS** |
| 실제 2보드 long read | **MTU 247, 512 byte × 100/100 PASS** |
| M29 진행률 | **W02 완료, 2/8** |

## 1. 구현 범위

기존 전역 GATT client 상태를 central·peripheral link가 각각 소유하는 두 개의 고정 context로
분리했다. 각 context는 discovery/read/write/subscription Zephyr parameter, remote handle,
operation·subscription connection token과 512-byte read/write buffer를 따로 소유한다. heap
fallback은 추가하지 않았고 link당 pending operation 하나라는 계약을 유지했다.

기존 `BLEClient.discover()/read()/write()/subscribe*()`는 central 우선 legacy view로 유지한다.
신규 overload는 `BLEConnectionHandle`을 받고 상세 callback은 connection, offset, ATT error,
status와 bearer를 main thread에서 전달한다. GAP이 central만이 아니라 두 역할 모두를 GATT에
등록하고 disconnect는 일치하는 context만 해제한다.

Long read callback은 각 ATT fragment를 512-byte 고정 buffer에 누적하고 명시적인 null-data 종료
callback에서만 `read_complete` 한 건을 queue한다. 513 byte, zero-length fragment, stale native
connection, 잘못된 generation과 다른 link의 callback을 거부한다. legacy callback 안에서
`BLEDevice.end()`가 호출되면 session generation을 다시 확인해 같은 record의 detailed callback이
종료 뒤 실행되지 않게 했다.

## 2. Host와 target 결과

Production GATT를 실제 링크하는 Host 실행은 전체 14개 시나리오를 통과했다. W02 시나리오는 두
link의 246+246+20 byte fragment를 교차 전달해 서로 다른 512-byte payload를 확인하고, 한 link
disconnect가 다른 link의 진행 중 read를 중단하지 않는지 검사했다. 500+13 byte overflow는
`BLEError::value_overflow`와 link별 `operation_failed`로 닫혔다.

Fail-closed protocol parser 11개는 정상 두 role transcript와 noise, 비 ASCII, 누락, 중복, 재배치,
stale nonce, wrong revision, wrong role, 수치 불일치와 target FAIL을 검사했다. 전체 M12 Host gate는
기존 M28 link 계약을 양 역할 GATT 등록 계약으로 갱신한 뒤 처음부터 재실행해 PASS했다.

첫 W02 target compile은 불필요하게 포함한 legacy NUS translation unit과 role별 미사용 counter의
`-Werror`로 2/2 실패했다. CMake source 범위를 W02 production GATT에 맞추고 counter를 명시적으로
`maybe_unused` 처리한 뒤 동일 두 role을 재빌드해 PASS했다. 구현 commit 확정 뒤 `D:\5`에서 다시
생성한 exact image도 2/2, warning 0으로 PASS했다.

`LongGattPeripheral`·`LongGattCentral` 공개 예제는 generation handle로 exact link를 선택하고
512-byte payload 전체를 검증한다. Arduino CLI 1.5.1의 BLE profile로 2/2 compile했고,
`v0.5.0` Windows Arduino matrix와 IDE 예제 목록 allowlist에 추가해 후속 CI에서 회귀한다.

## 3. 실제 두 보드 결과

Runner는 UID·MSD·target UART를 교차 확인하고 peripheral을 먼저 광고시킨 뒤 central scan을
시작했다. 두 image는 서로 다른 SHA-256이며 UID 지정 pyOCD sector erase, 500 kHz SWD,
`auto_unlock=false`로 기록했다. 외부 GPIO·전원 결선과 mass erase, PMIC write는 사용하지 않았다.

| 판정 | 관측값 |
| --- | ---: |
| peripheral / central ATT MTU | 247 / 247 |
| central long read | 100 / 100 |
| read payload 길이 | 512 byte |
| payload corruption | 0 |
| stale·cross-link event | 0 |
| callback context 오류 | 0 |
| peripheral peer disconnect | PASS |

원시 transcript와 구조화 증거는 다음 파일에 보존한다.

- [`m29-w02-long-read-evidence.json`](evidence/m29-w02-dacf6341-long-read/m29-w02-long-read-evidence.json)
- [`peripheral transcript`](evidence/m29-w02-dacf6341-long-read/m29-w02-long-read-evidence.peripheral.transcript.log)
- [`central transcript`](evidence/m29-w02-dacf6341-long-read/m29-w02-long-read-evidence.central.transcript.log)

## 4. 실패 분류와 재검증

- 전체 Host gate 첫 실행은 M28의 과거 문자열 계약이 central-only GATT route를 요구해 실패했다.
  M28의 역할 2-slot 검증을 유지하면서 두 역할이 exact handle로 GATT에 전달되는 계약으로 고쳤고
  전체 gate를 처음부터 한 번 재실행해 PASS했다.
- 장치 탐색 중 시스템 Python은 pySerial이 없어 중단됐고, 고정 toolchain Python으로 전환했다.
  수동 추정한 COM과 UID가 다를 때 runner가 flash 전에 거부했으며 pySerial UID로 다시 매핑했다.
- 첫 실기 명령의 full Core SHA 입력 오기는 exact revision 검사에서 flash 전에 거부됐다. Git에서
  full SHA를 다시 읽어 같은 image·보드·조건으로 한 번 실행했고 실제 HIL이 PASS했다.

실제 RF/GATT 실행 실패는 없었으므로 GPIO 연결성 검사나 CMSIS-DAP fault·주변장치 register 수집은
필요하지 않았다. 위 실패들은 원인을 확인한 뒤 입력 또는 계약을 한 번 수정하고 같은 조건으로
재검증했으며 반복 재시도로 PASS를 만들지 않았다.

## 5. 지원 판정 경계와 다음 작업

W02는 512-byte long **read**와 link별 client context의 실제 근거다. W03의 long/reliable write,
server prepare/execute, cancel·offset·overflow negative와 atomic commit은 아직 구현·실행하지 않았다.
따라서 결합 test ID `M29-LONG-01`은 계속 `NOT RUN`이며 source capability
`gatt_long_reliable`도 전체 PASS가 아니라 `in_progress`다. 다음 작업은 M29-W03이다.
