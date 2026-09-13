# M29-W07 Signed Write·EATT HIL 준비

| 항목 | 현재 결과 |
| --- | --- |
| 작업일 | 2026-09-14 |
| 준비 기준 HEAD | `d425248b8063cfb4e816c12cab6dd62c88cae446` 이후 미커밋 W07 source |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| W07 공개 계약 | **7/7 PASS** |
| strict Host parser | **14/14 PASS** |
| production GATT Host | **W07 3개 포함 전체 24개 시나리오 PASS** |
| Arduino M29 예제 | **14/14 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| 실제 `M29-SIGN-01` / `M29-EATT-01` | **NOT RUN / NOT RUN** |
| 실제 `M29-MULTI-01` / `M29-REG-01` | **NOT RUN / NOT RUN** |
| M29 진행률 | **6/8 유지** |

## 1. 구현한 정책과 공개 API

Signed Write는 Zephyr `BT_SIGNING`의 deprecated 상태를 숨기지 않고 기본 OFF의
`NUCODE_BLE_LegacySigning` 선택 library로 분리했다. Public characteristic property와
`BLEClient.writeSigned()`를 추가하되 기존 property·event enum ordinal과 무인자 API는 바꾸지
않았다. Bonded key record의 local/remote CSRK와 sign counter를 stack 전송·수신 완료 뒤
`bt_keys_store()`로 저장한다. 수신 측은 서명이 사용되는 L1 link에서만 이 처리를 적용해 암호화
EATT의 일반 Write Command를 sign counter 저장으로 오인하지 않는다. 정상 완료는 main thread
event 처리에서 저장하며, event queue가
포화돼 완료 record를 보존하지 못할 때도 counter를 즉시 저장한다. 이 fallback 저장마저 실패하면
link를 끊어 이후 signed operation을 계속하지 않는다.

EATT는 Zephyr experimental 상태를 표시하는 기본 OFF의 `NUCODE_BLE_EATT` 선택 library다.
암호화되지 않은 link에서는 bearer 연결을 거부하고 connection당 최대 2개만 연다. GATT read/write
overload는 `unenhanced` 또는 `enhanced` bearer를 명시하고, 상세 client event가 실제 선택 bearer를
돌려준다. 기존 GATT client의 link별 단일 pending operation 상한은 유지한다.

공개 예제는 다음 네 개다.

- `LegacySignedWritePeripheral`, `LegacySignedWriteCentral`
- `EattPeripheral`, `EattCentral`

각 예제는 deprecated/experimental 경고, security·discovery·write/read·bearer 연결 실패를 Serial로
출력한다. Callback 완료만 peer 적용 성공으로 표현하지 않는다.

## 2. 고정 HIL protocol과 parser

`tests/zephyr/m29_ble_signed_eatt_hil`의 두 role image는 `M29W07|1`만 출력한다. READY·BEGIN·결과·
END에 full Core revision, 128-bit nonce와 iteration을 붙인다. Signed 단계는 bond/CSRK 생성 뒤 20회
재부팅과 write를 반복하며 local/remote counter가 정확히 증가하는지 보고한다. Replay 단계는 실제
서명한 ATT PDU의 동일 byte를 두 번 RF로 보내 receiver 적용 횟수가 한 번인지 검사한다.

EATT 단계는 암호화 전 연결 거부, 암호화 뒤 bearer 2개, 상한 초과 거부를 확인한다. Production
enhanced read/write 뒤 두 실제 EATT L2CAP channel에서 bearer별 1,000 ATT Write Command를 보내고
peripheral이 sequence·checksum·bearer 분리를 검증한다. TX buffer는 4개 고정 pool이며 무한 재시도는
없다.

`tests/hil/nu54dk/m29_ble_signed_eatt.py`는 source clean·revision·build record·보드 UID/UART를 flash
전에 확인한다. Parser 14개는 정상 두 role 외에 ASCII/non-ASCII noise, 누락·중복·재배치,
wrong revision·stale nonce, counter rollback, replay accept, EATT shortfall, target FAIL과 END 뒤
추가 record를 fail-closed로 거부한다.

## 3. Host·target 준비 결과

W07 공개 계약 7/7, parser 14/14, M13 allowlist·canonical example 11/11(설치본 전용 1 skip),
M22 stable package 경계 7/7, readiness 8/8이 PASS했다. 전체 Host gate에서 W07 신규 예제를 후속
후보 집합에 반영하지 않은 1건은 수정 뒤 동일 시험 7/7 PASS했다. 임시 native EXE 일부는 첫 실행에
Windows Application Control `WinError 4551`로 17회 차단됐다. PAwR·TWIM 실패 module을 같은 source와
컴파일러로 개별 재실행해 모두 PASS했고 기능 회귀가 아닌 정책 판정 race로 분류했다. 공통 실행기는
4551에만 최대 30초 유한 재시도를 적용하고 다른 오류와 한도 소진은 그대로 실패하게 보강했다.
격리 TEMP에서 다시 실행한 전체 Host gate는 **1,106개 PASS, 조건부 2개 skip**으로 끝났다. W07 GATT
binary도 W07 3개를 포함한 전체 24개 production 시나리오가 PASS했다. 첫 실패는 소급 PASS로
바꾸지 않으며 exact commit CI에서 독립 확인한다.

Arduino M29 smoke의 첫 실행은 앞선 13개 예제가 PASS한 뒤 `EattCentral`에서 이 플랫폼의 최소
C++ runtime이 제공하지 않는 `<cstring>`을 사용해 compile 실패했다. 같은 C API를 명시하는
`<string.h>`로 교체하고 `EattCentral` 단독 build를 통과시킨 뒤 전체 그룹을 처음부터 다시 실행해
GATT·CoC 8개, GATT cache 2개, legacy signing 2개와 EATT 2개를 합친 **14/14 PASS**를 확인했다.
첫 실패 로그를 최종 PASS로 소급 변경하지 않는다.

고정 NCS v3.4.0에서 다음 두 build-only suite는 warning 없이 2/2 PASS했다.

- `nucode.m29.ble_signed_eatt_peripheral`
- `nucode.m29.ble_signed_eatt_central`

이 build는 dirty W07 source로 수행했으므로 정확한 물리 실행 identity가 아니다. 먼저 source·문서·
시험을 commit/push하고 exact commit CI를 확인한 뒤, 같은 commit을 새로 build해 HIL runner에
전달한다.

## 4. 남은 유한 실행 순서

1. W07 준비 변경을 commit/push하고 exact GitHub Software·Reproducible Build CI를 확인한다.
2. Clean exact commit으로 Signed/EATT 두 role을 재빌드한다.
3. 두 보드 `M29-SIGN-01`과 `M29-EATT-01`을 한 runner session에서 실행한다.
4. 세 보드 mixed DUT의 두 link에서 GATT/CoC traffic 각 1,000회와 교차 event 0을 검증한다.
5. M19·M20·M21·M28 필수 BLE 회귀 네 그룹을 세 보드 장비 집합에서 실행한다.
6. 실패하면 DAP/UART·전압·RF/GPIO 연결성을 먼저 확인하고, 연결이 정상이면 CMSIS-DAP로
   주변장치·DMA·GPIO·오류 register와 SRAM 상태를 수집한다. 원인을 분류해 한 번 수정한 뒤 같은
   조건으로 재검증하며 무한 재시도하지 않는다.

현재 단계에서는 네 물리 test ID와 W07을 PASS로 표시하지 않는다. SDK source `candidate` 역시
구현·target·HIL PASS와 분리한다.
