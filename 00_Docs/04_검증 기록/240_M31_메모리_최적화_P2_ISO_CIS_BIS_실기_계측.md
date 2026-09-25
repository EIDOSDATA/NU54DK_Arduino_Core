# 240 — M31 메모리 최적화 P2: CIS·BIS 100 SDU × 20세션 실기 계측

> **역사 기록:** 아래 미계측·HOLD는 이 image의 증거 경계다. 후속 결과와 현재 P2
> 세 잔여 축·제외 조건은 [현행 판정 경계](README.md#p2-기록의-현행-판정-경계)를 따른다.

## CIS 판정과 재현 경계

고정 NCS v3.4.0의 두 exact NU54DK에 `adaptive` CIS central/peripheral
계측 image를 각각 기록했다. 공개 `CISCentral`/`CISPeripheral` 예제의
16 B session ID와 8 B sequence payload 검증을 유지하고, Zephyr thread/heap
통계만 test 전용 header로 추가했다. 명시적인 Bluetooth 수동 `prj.conf`는
없다. probe/COM 확인 후 자동 unlock 없이 sector erase로 기록했고,
hardware reset 대신 halt-start 절차를 사용했다.

| 시험 | 판정 | 원본 |
| --- | --- | --- |
| 양 역할 100 SDU × 20 연결·송수신·해제 세션 | **PASS**. central 송신 cycle 1~20, peripheral 순서·내용 검증 수신 cycle 1~20, 각 cycle 100/100·오류 0, 양측 `P2_STOP cycles=20` | [CIS 원본 UART·image/probe hash](evidence/m31-p2-iso-bdd0be53/cis-100x20.json) |

계측 image의 정적 FLASH/RAM 예약은 central 207,096/54,649 B,
peripheral 206,284/54,646 B다. 두 image 모두 loaderless FLASH 분모
1,490,944 B, RAM 분모 262,144 B이며 `sdc_mempool` symbol은 각각
8,533 B다. 정적 RAM에는 아래 stack과 heap 예약이 이미 포함된다.

## 20세션 뒤 관찰 high-water

| Thread/ISR | central used/reserved B | peripheral used/reserved B |
| --- | ---: | ---: |
| BT RX WQ | 464/2048 | 328/2048 |
| BT TX processor | 624/904 | 404/904 |
| BT LW WQ | 1056/2104 | 1056/2104 |
| sysworkq | 288/4096 | 264/4096 |
| MPSL Work | 364/1024 | 364/1024 |
| main | 824/8192 | 848/8192 |
| ISR0 | 544/2048 | 500/2048 |

libc malloc은 양쪽 모두 정지 시점 `free=8108`, `allocated=0`,
관찰 peak 0 B였다. 이 통계는 controller 내부 pool high-water,
미실행 보안·전송 오류·장기 fragmentation이나 비계측 제품 image의
여유를 증명하지 않는다. `sdc_mempool`은 정적 예약 크기일 뿐 실제
controller 고점유가 아니다. 따라서 CIS 결과만으로 stack/heap/pool을
축소하지 않았다.

이 판정은 두 보드의 기본 CIS 공개 payload 경로에 한정한다.

## BIS 판정과 관찰값

동일한 두 보드에 adaptive BIS source/receiver 계측 image를 배치했다.
공개 `BISSource`/`BISReceiver`의 16 B session ID, 8 B sequence SDU,
source 동기화 대기와 receiver 수신·누락 계산을 유지했다. 각 20개 BIG
세션에서 source 100개 송신, receiver 100개 수신·내용/순서 오류 0,
누락 총 0개, 양측 `P2_STOP cycles=20`으로 **PASS**했다.
[BIS 원본 UART·image/probe hash](evidence/m31-p2-iso-bdd0be53/bis-100x20.json)를
보존했다. 한 세션당 1개 이하 누락을 허용하는 공개 예제 계약으로 검사했지만,
이 실행에서 실제 누락은 없었다.

| BIS 역할 | FLASH 사용 B | RAM 예약 B | `sdc_mempool` 예약 B |
| --- | ---: | ---: | ---: |
| source | 160,880 | 46,386 | 4,144 |
| receiver | 129,600 | 45,520 | 4,362 |

| Thread/ISR | source used/reserved B | receiver used/reserved B |
| --- | ---: | ---: |
| BT RX WQ | 336/2048 | 416/2048 |
| BT TX processor | 564/904 | 404/904 |
| sysworkq | 232/4096 | 744/4096 |
| MPSL Work | 364/1024 | 596/1024 |
| main | 840/8192 | 808/8192 |
| ISR0 | 560/2048 | 472/2048 |

BIS 양쪽 libc malloc은 정지 시점 `free=8108`, `allocated=0`,
관찰 peak 0 B였다. BIS 역시 한 payload 크기·동기화 조건의 관찰이며
controller 내부 pool, 암호화·sync loss·재동기화 오류 경로와 장기
fragmentation의 최악값은 아니다. 정적 예약과 runtime 사용을 합산하지
않고 기존 stack/heap/controller pool 크기를 유지한다.

CIS/BIS 기본 payload의 국소 실기 PASS를 Audio-over-ISO의 ASE/codec 조합,
DF, CS 연속성, 역할별 controller 용량 조정·native 동등 조건 비교의
PASS로 확대하지 않는다. P2 전체와 W06은 여전히 **HOLD**다.
