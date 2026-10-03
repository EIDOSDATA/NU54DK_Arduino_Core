# 278 — M32-W02 LE Power Control·Path Loss 완료

## 범위와 exact source

M32-W02는 `Dev-0.6.0-M32`의 exact source
`9a7d0351c8cd21ad7ebe3dcd921f29c2ec2b85bd`에서 완료했다. 고정 기준은 NCS
`99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`이다.

## API·예제·오류 경계

공개 GAP API에 link별 local/remote transmit power 조회·변경 요청, local/remote report enable,
RSSI 조회, Path Loss threshold·hysteresis·minimum connection event·enable/disable을 추가했다.
Tx Power와 Path Loss callback은 `BLEEventInfo`의 값 복사본으로 main thread에 dispatch하고
connection generation이 바뀐 stale·late callback은 폐기한다.

Path Loss parameter는 Core HCI 경계인 high threshold+hysteresis, low threshold-hysteresis,
두 zone 경계의 비중첩을 호출 전에 검증한다. 연결 직후 SDC가 `Controller Busy(0x3a)`를 반환할 수 있는
remote power 절차는 HIL에서 고정 50회×100 ms 이내로 제한하고, power 절차가 끝난 뒤 Path Loss 절차를
직렬화했다. 지원하지 않는 peer·범위 밖 값·stale handle·종료 뒤 callback·반복 enable/disable은 Host
mock에서 별도로 거부 또는 무시됨을 확인했다.

공개 예제는 다음 6개이며 사용자가 편집할 수 있는 `setup()`/`loop()` 흐름을 유지한다.

- `LePowerControlCentral`, `LePowerControlPeripheral`
- `PathLossMonitorCentral`, `PathLossMonitorPeripheral`
- `RssiPowerControlCentral`, `RssiPowerControlPeripheral`

## Build와 두 보드 HIL

| Gate | 결과 |
| --- | --- |
| v0.6.0 Zephyr group | 5/5 build-only, warning 0 |
| Arduino 공개 예제 | 6/6 build PASS |
| `M32-PWR-01:primary` | central 20 + peripheral 20 = 40/40, loss 0, 최대 event gap 281 ms |
| `M32-PATH-01:primary` | low/middle/high 20회씩 60/60, loss 0, 최대 event gap 125 ms |
| callback·종료 | main-thread callback PASS, 두 역할 `STOPPED` 2/2 |

실물 실행은 SHA-256 probe identity와 VCOM을 직전에 대조하고 `auto_unlock=false`, sector flash,
별도 hardware reset, nonce, exact source/board/SDK revision과 image hash를 한 attempt에 결합했다.
원시 probe UID는 evidence에 저장하지 않았다. 관측 path loss 범위 54~65 dB는 기능 event 검증값이며
거리·각도·RF 정확도 보증이 아니다.

## 진단 원본과 최종 증거

개발 중 peer 이름이 scan response에만 있던 문제, 동시 controller procedure의 `0x3a`, 잘못된
hysteresis 조합의 `0x12`를 순서대로 재현하고 수정했다. 각 개발 시도의 JSON·transcript는
[development diagnostics](<evidence/m32-w02-development-diagnostics-34d13859/>)에 보존했으며 최종 PASS로
덮어쓰지 않았다.

- [W02 closure](<evidence/m32-w02-exact-9a7d0351/w02-closure-audit.json>)
- [W02 manifest](<evidence/m32-w02-exact-9a7d0351/w02-manifest.json>)
- [Power/Path HIL result](<evidence/m32-w02-exact-9a7d0351/m32-power-path-exact-9a7d0351.json>)
- [Power/Path transcript](<evidence/m32-w02-exact-9a7d0351/m32-power-path-exact-9a7d0351.transcript.log>)
- [Arduino build summary](<evidence/m32-w02-exact-9a7d0351/arduino-build-summary.json>)

외부 제품 peer 상호운용은 사용자 후속 `NOT_RUN`이며 두 NU54DK 간 기능 PASS와 구분한다. 현재 stable과
설치 제품은 계속 v0.5.0이다. 다음 작업은 M32-W03의 Subrating·SCA·Frame Space·Shorter Interval·
확장 feature 구현과 두 보드 HIL이다.
