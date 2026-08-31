# M20 범용 GATT server/client 검증

## 판정

| 항목 | 결과 |
| --- | --- |
| Host API/profile/negative contract | PASS |
| NU54DK target contract build | PASS |
| Peripheral role image build | PASS |
| Central role image build | PASS |
| 두 보드 RF GATT HIL | **NOT RUN — exact commit 뒤 실행 필요** |
| 외부 배선 | 없음 — 각 보드 USB만 사용 |

2026-08-31 dirty 개발 checkout에서 구현과 build-only 검증을 완료했습니다. Compile/link 성공은
실제 ATT/GATT 교환 증거가 아니므로 physical HIL을 별도 NOT RUN으로 유지합니다.

## 구현 범위

- 시작 전 선언하는 bounded primary service/characteristic schema
- read/write/write-without-response/notify/indicate property와 permission
- cached read, bounded offset write, prepare/execute long write 명시적 거부
- notification local TX 완료와 indication confirmation/failure 구분
- exact service/characteristic discovery와 portable remote handle
- bounded client read, 두 write mode, notify/indicate subscribe와 unsubscribe
- disconnect 시 remote service/characteristic/CCC handle 선무효화
- reconnect 뒤 명시적 rediscovery/resubscribe
- 단일 operation, 단일 peer, 고정 queue/buffer와 main-thread callback
- cached value spinlock과 notify/indicate snapshot, caller buffer lifetime 계약
- client/server operation별 exact connection·session generation token
- CCC 응답 전 early notify/indicate type 보존과 unsubscribe/error fail-closed
- 전체 schema 사전 검증과 다중 service 등록 실패 rollback
- ISR 공개 operation의 `invalid_context` 거부
- 실제 Arduino bundle과 같은 NUS+GAP+GATT source 공존 build

## 자동 검증 결과

M20 host contract 6건과 HIL transcript parser 6건이 PASS했습니다. Target contract와
peripheral/central role image도 `nrf54l15dk/nrf54l15/cpuapp/nu54dk`에서 compile/link됐습니다.
Board baseline의 `NRF_PLATFORM_LUMOS` deprecation 경고는 남지만 M20 C++ source 경고는 없습니다.
경계 review에서 zero-length write의 null copy, notify/indicate MTU underflow와
구독 상태 재조회 문제를 교정했습니다. CCC 값이 0인 unsubscribe 완료 응답을 subscribe 완료로
오인하던 경로도 분리해, `subscribed` 이벤트를 만들지 않고 실제 unsubscribe 알림에서만 해제를
확정하도록 교정했습니다.

Host negative gate는 schema 등록 순서와 rollback, long-write 거부, ISR 차단, disconnect handle
무효화, stale callback token, operation API와 profile resolver 구성을 확인합니다. HIL parser는
짧거나 stale인 nonce, 누락된 rediscovery, write mode 순서 변경과 target FAIL을 거부합니다.

## Exact-commit role image build

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$M20Peripheral = "C:\t\m20-peripheral"
$M20Central = "C:\t\m20-central"

Push-Location $NcsRoot
& $Python -I -m west build --sysbuild -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $M20Peripheral "$CoreRoot\tests\zephyr\m20_ble_gatt_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" `
  "-DM20_ROLE=peripheral"
& $Python -I -m west build --sysbuild -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $M20Central "$CoreRoot\tests\zephyr\m20_ble_gatt_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" `
  "-DM20_ROLE=central"
Pop-Location
```

Role image는 각각 다음 위치입니다.

- `C:\t\m20-peripheral\m20_ble_gatt_hil\zephyr\zephyr.hex`
- `C:\t\m20-central\m20_ble_gatt_hil\zephyr\zephyr.hex`

## 두 보드 HIL 실행

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m20_ble_gatt.py" `
  --peripheral-hex "$M20Peripheral\m20_ble_gatt_hil\zephyr\zephyr.hex" `
  --central-hex "$M20Central\m20_ble_gatt_hil\zephyr\zephyr.hex" `
  --peripheral-board-id "<peripheral CMSIS-DAP UID>" `
  --central-board-id "<central CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --evidence "$CoreRoot\build\m20\hil\m20-gatt.evidence.json"
```

별도 GPIO 점퍼나 외부 저항은 사용하지 않습니다. Runner가 실제로 검증하는 순서는 UUID filter
scan, connect, service/characteristic discovery, runner nonce의 128-bit binary cached read challenge,
response write `WR`, command write
`WC`, notification `NTF1`, indication `IND1` confirmation, unsubscribe, disconnect와 handle 무효화,
reconnect, rediscovery, notification `NTF2` 재구독, 최종 disconnect입니다. 두 role callback이 모두
Arduino main thread에서 실행돼야 FINAL PASS가 생성됩니다.

128-bit challenge가 exact 일치해야 `NONCE_CHALLENGE:PASS`가 기록되므로 동일 UUID를 광고하는
stale/병렬 peripheral과 각각 연결된 두 transcript를 하나의 pair PASS로 잘못 결합하지 않습니다.

Exact JSON evidence와 두 raw transcript가 생기기 전까지 M20 physical HIL 상태는 NOT RUN입니다.
