# M30-W07 3보드 secure multi-link 완료

## 결과

M30-W07의 `M30-MULTI-01`을 고정 NU54DK 세 대와 NCS v3.4.0에서 완료했다. exact Core
`d94f5ec310e99611ab021854c43dd6d72031e825`의 Peripheral·Mixed·Central role image를 각각
build하고, `Peripheral ← Mixed ← Central` 두 BLE link를 동시에 유지하면서 generation handle별
보안 연산을 실행했다.

| Gate | 결과 |
| --- | --- |
| W07 Host 계약 | **7/7 PASS** |
| M30 Host 회귀 | **82 tests PASS** |
| 세 role target build | **3/3 PASS** |
| 실제 `M30-MULTI-01` | **PASS** |
| 동시 BLE link | **2** |
| Peripheral server 연산 | **100/100** |
| Mixed client/server 연산 | **100/100 + 100/100** |
| Central client 연산 | **100/100** |
| Security level·key | **L2·16 byte** |
| Cross-link event | **0** |
| Security·key-size 오류 | **0·0** |
| Callback context | **세 role PASS** |
| 실제 전원 차단 | **0 — `M30-POWER-01` 전용으로 유지** |
| M30 진행률 | **W07 완료, 작업 묶음 7/8·test ID 9/10 PASS** |

## 구현과 build

W07 target은 같은 128-bit nonce와 exact Core revision을 UART와 RF 양쪽 identity에 결합한다.
Peripheral과 Mixed는 role marker가 들어간 connectable advertising을 사용하고, Mixed와 Central은
일치하는 marker·nonce만 scan해 연결한다. Mixed의 upstream link가 L2·16-byte가 된 뒤에만
downstream advertising을 시작하므로 두 link의 순서와 소유권도 고정된다.

각 role은 `BLESecurity.requestSecurity(handle)`, `currentLevel(handle)`와 실제
`bt_conn_enc_key_size()`를 generation handle별로 100회 확인한다. Mixed는 client/server handle을
같은 loop에서 각각 전진시킨다. callback이 Arduino setup thread와 다르거나, 다른 link의 security
event가 전달되거나, 예상하지 않은 연결 역할이 생기면 즉시 실패한다.

세 build는 알려진 deprecated board Kconfig 경고 외 C/C++ warning 없이 완료했다.

| Role | FLASH | RAM |
| --- | ---: | ---: |
| Peripheral | 245,196 B | 70,736 B |
| Mixed | 247,556 B | 70,808 B |
| Central | 243,628 B | 70,616 B |

## 실제 시험과 증거

세 DAPLink UID는 원문 대신 SHA-256으로만 evidence에 기록했다. 자동 탐색은 target UART interface
3을 선택했고 역할별 endpoint를 `Peripheral=E:/COM13`, `Mixed=F:/COM14`, `Central=G:/COM10`으로
확정했다. 추가 GPIO·전원 배선은 사용하지 않았으며 각 보드는 독립 USB/DAPLink 경로를 사용했다.

Runner는 exact image/build record/source digest를 검사한 뒤 probe를 임의 선택하지 않고 sector
flash했다. READY 뒤 Peripheral 광고, Mixed upstream 보안과 downstream 광고, Central 연결을
순서대로 진행했다. 세 role이 모두 LINK를 보고한 뒤에만 RUN을 보내 400회의 local handle 연산을
완료했다.

- [구조화 evidence](evidence/m30-w07-d94f5ec3-multi/m30-multi-evidence.json)
- [Peripheral transcript](evidence/m30-w07-d94f5ec3-multi/m30-multi-evidence.peripheral.transcript.log)
- [Mixed transcript](evidence/m30-w07-d94f5ec3-multi/m30-multi-evidence.mixed.transcript.log)
- [Central transcript](evidence/m30-w07-d94f5ec3-multi/m30-multi-evidence.central.transcript.log)

## 실패 진단

첫 실행은 역할 mapping에서 E 보드의 보조 VCOM인 COM12를 target UART로 잘못 명시해 READY가
오지 않았다. UART를 연 채 exact image를 다시 flash해도 수신 byte가 0이었고, SWD로 확인한 코어는
hard fault가 아니라 Zephyr idle 상태였다. 같은 보드의 DAPLink interface 3인 COM13에서 READY가
즉시 응답해 firmware 문제가 아닌 endpoint 선택 오류로 분류했다.

그 뒤 runner의 기존 `auto` 탐색으로 세 target UART를 다시 결합하고 동일 exact image를 한 번
실행해 PASS했다. 이 진단 중 reset은 사용했지만 실제 target USB 전원 차단으로 계산하지 않았다.
Chip/mass erase와 recover도 사용하지 않았다.

## 다음 작업과 중단 경계

M30은 **7/8 작업 묶음, 9/10 test ID PASS**다. 이제 `M30-POWER-01`용 image·runner·두 보드
manifest와 네 주입 지점별 3회 절차를 자동 준비한다. 준비 검증과 문서·CI를 완료한 뒤, 실제 target
USB 전원 차단 첫 주입 직전에 중단한다. Reset은 power-loss 증거를 대체하지 않으며 물리 주입 전에는
M30-W08 또는 M30 전체를 완료 처리하지 않는다.
