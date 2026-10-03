# 277 — M32-W01 capability·자원·시험 계약 완료

## 범위와 exact source

M32-W01은 `Dev-0.6.0-M32`의 exact source
`35aabc84ffb54240d28d82cff3beddba591c9a65`에서 완료했다. 고정 기준은 NCS
`99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`이다.

전체 Bluetooth parity 원장의 190 sample·474 variant·39 source-only feature를 고정 SDK와 다시
대조했다. 이 중 M32 소유 범위는 41 sample·74 variant이며 selected-row hash는
`806714f1323c65eaaa012ab6492da494620ffbe5af7ba4c6c6d4a290ad4bd4ac`다.

## 계약과 자동 판정

[`m32-ble-readiness.json`](../../variants/nu54dk/m32-ble-readiness.json)은 12개 작업 묶음,
42개 capability, 15개 자원 profile, 24개 test family를 고정한다. 기능마다 source candidate,
NU54DK native build, Arduino build, runtime capability, 기능 HIL, 외부 peer interop를 독립 상태로 둔다.
Host 단위시험 14개는 누락·중복·unknown·nonce/revision·raw bit·자원·시험 분모·부당 PASS·raw UID
유출을 fail-closed로 거부했다.

## Build와 실물 capability query

| Profile | Build | RAM / RRAM | HCI query | 핵심 자원 |
| --- | --- | --- | --- | --- |
| `ble_baseline` | PASS | 61,364 / 199,564 B | PASS, page 0·8 octets·13 records | 2 link, 1 peripheral, 1 adv set, 1 identity, 1 sync, ACL 6/6 |
| `ble_extended` | PASS | 66,396 / 217,196 B | PASS, max page 1·16 octets·13 records | 2 link, 1 peripheral, 3 adv sets, 3 identities, 2 syncs, ACL 8/8 |

두 image는 warning 0의 build-only 2/2다. 실물 query는 SHA-256 probe identity와 VCOM을 직전에
대조하고 `auto_unlock=false`, sector flash, 별도 hardware reset, nonce, exact source/board/SDK revision,
image hash를 같은 attempt에 묶었다. 원시 probe UID는 evidence에 저장하지 않았다.

초기 baseline flash는 pyOCD의 post-program reset 반환 오류로 증거 생성 전에 중단했다. Programmed byte
출력 뒤 실행 image의 serial protocol 자체는 별도 진단에서 정상임을 확인했고, runner를 `--no-reset` 뒤
bounded hardware reset 방식으로 교정해 새 exact source에서 다시 build·실행했다. Extended 첫 실행은
Coded PHY 선행 Kconfig 누락을 Host profile mismatch로 거부했고, `CONFIG_BT_CTLR_PHY_CODED=y`를 추가한
새 exact source에서 허용된 1회 진단 재시험으로 PASS했다. 실패를 성공 evidence로 덮어쓰지 않았다.

## 증거와 판정 경계

- [W01 closure](<evidence/m32-w01-exact-35aabc84/w01-closure-audit.json>)
- [Capability manifest](<evidence/m32-w01-exact-35aabc84/capability-manifest.json>)
- [Parity audit](<evidence/m32-w01-exact-35aabc84/parity-audit.json>)
- [Negative audit](<evidence/m32-w01-exact-35aabc84/negative-audit.json>)
- [Baseline result](<evidence/m32-w01-exact-35aabc84/m32-cap-baseline-clean-35aabc84-01.json>)
- [Extended result](<evidence/m32-w01-exact-35aabc84/m32-cap-extended-clean-35aabc84-02.json>)

W01은 capability·자원·시험 계약의 완료다. Controller feature bit와 Host Kconfig 조회를 W02 이후의
연결 절차·RF 동작·다중 링크 격리·오류 복구 HIL PASS로 확대하지 않는다. 다음 작업은 M32-W02의
LE Power Control·Path Loss 구현과 두 보드 기능 HIL이다. 현재 stable과 설치 제품은 계속 v0.5.0이다.
