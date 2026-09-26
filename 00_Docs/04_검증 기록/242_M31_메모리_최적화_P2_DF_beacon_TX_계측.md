# 242 — M31 메모리 최적화 P2: AoA CTE beacon TX 계측

> **후속 지원 판정:** 제품 SDC IQ RX는 고정 NCS `v3.4.0`에서 `UNSUPPORTED`·P2 비차단이다.
> 아래 RX 미계측을 추가 완료 조건으로 적용하지 않는다. [259번](259_M31_P2_DF_고정_SDK_지원_경계.md)

## 국소 판정

고정 NCS v3.4.0의 exact NU54DK 한 대에 `adaptive`
`ble-df-cte-beacon` 계측 image를 실행했다. 공개 `CteBeacon`과 같은
CTE 길이 160 µs·광고 event당 5회 설정으로 2초 송신/중단을 20회
반복하고 광고 set을 반환했다. 잘못된 CTE 길이 0 입력은 시작 전에
거부됐다. 자동 unlock·mass erase 없이 sector 플래시 후 halt-start로
실행했다.

[원본 UART·image/probe hash](evidence/m31-p2-df-bdd0be53/beacon-20-cycle.json)에서
negative 거부, start/stop cycle 1~20 순서 일치, `P2_STOP cycles=20`,
firmware failure·fault 0을 확인해 **beacon TX 수명만 PASS**했다.
실제 peer의 IQ report·sample, 안테나 배열·각도 계산은 관찰하지 않았고
이 기록으로 W04 RX를 PASS로 만들지 않는다.

## 정적 예약과 high-water

계측 image의 FLASH 사용량은 115,920 B/1,490,944 B, RAM 예약은
38,676 B/262,144 B다. `sdc_mempool` symbol은 1,008 B 예약이며
controller 실제 high-water를 나타내지 않는다.

| Thread/ISR | used/reserved B |
| --- | ---: |
| BT RX WQ | 232/2048 |
| BT TX processor | 468/904 |
| sysworkq | 232/4096 |
| MPSL Work | 232/1024 |
| main | 784/8192 |
| ISR0 | 400/2048 |

libc malloc 정지 시점은 `free=8108`, `allocated=0`, 관찰 peak 0 B다.
이 값은 한 beacon TX 역할·정상 반복의 계측 image에서만 유효하다.
connectionless/connected IQ RX와 오류·복구 부하, controller pool의
실제 사용량 및 native 동등 조건 비교가 없어 stack/heap/pool을 줄이지
않는다. P2 전체와 W04/W06은 계속 **HOLD**다.
