# 248 — M31 P2 SDC controller pool 정적 경계 감사

> 현재 판정(2026-09-25): P2 세 기술 축은 [262번](262_M31_메모리_최적화_P2_세_축_완료.md)에서 완료됐다.
> 아래의 미완료·HOLD·다음 작업 문구는 이 기록 작성 당시 상태이며 원본 판정을 보존한다.

## 확인 범위

고정 NCS v3.4.0의 `nrf/subsys/bluetooth/controller/hci_driver.c`는
역할·연결·광고·ISO·CS Kconfig별 `SDC_MEM_*` 요구량을 합쳐
`sdc_mempool[MEMPOOL_SIZE]`를 8-byte 정렬로 예약한다.
추가 메모리가 설정되면 그 값도 배열 크기에 포함한다. controller를
열 때 `sdc_cfg_set()`의 `required_memory`와 실제 배열 크기를 비교하고,
요구량이 더 크면 `k_panic()`으로 진행을 막는다. 이는 **고정 SDK의
구성 요구량 검사**이지 실행 중 pool high-water를 반환하는 API가 아니다.
SDK 원본이나 pool 산식을 수정하지 않았다.

P2에서 사용한 Arduino ELF의 `sdc_mempool` symbol을 고정 toolchain의
`arm-zephyr-eabi-nm -S --size-sort`로 확인했다. 주소는 모두 8-byte
정렬이다. 크기는 정적 예약이며 stack 사용량이나 실시간 여유가 아니다.
이번 재감사 시점의 저장소에는 미커밋 변경이 있으므로 이 감사의
`source_clean=false`다. 각 ELF hash는 동일 파일 식별용이며
clean-source 릴리스 판정을 대신하지 않는다.

| 역할 image | `sdc_mempool` B | ELF SHA-256 |
| --- | ---: | --- |
| GATT Peripheral | 2,828 | `bec44a0563efea9671942d1fae711fb17c057b6dfa822a59ef2e6f82e04d349f` |
| CoC Server | 5,618 | `a396ea02a2d38a7123f3702ab9f6706b953591aeb3cb6722e3d33363697e596c` |
| CIS Central | 8,533 | `c7ad7c6d79ff2e8f45521cde5fffaeceef8705c591455141f72137c934796a4f` |
| Audio unicast Source | 5,616 | `9a2df849e984b3f0545395c16c19990adb596c531d74b5b6de40ecd21d60effe` |
| Audio broadcast Source | 3,050 | `451571dea1eac44a13767471de26e30a07d041f124ab5a27e5acb29d050d2f9a` |
| CS Initiator, 2차 수정·관찰 배열 없음 | 7,672 | `2c4de5ada6347ec99637f058cd2bc8edcce4233a4a02358b2179b96c9ba254c3` |
| CS Reflector | 6,732 | `e5362f087ce9c9a0b2f1354107cbb3db4695db83d255bf0d13ca426c46ec73f2` |
| DF Beacon TX | 1,008 | `903366423594c7269812b9a28caca23965f750d95d25479888412637dbcbc2ff` |

이 이미지들이 Bluetooth 초기화 후 해당 기능을 실제 실행한 근거는
[238~243번 P2 기록](README.md#최근-완료재개-기록)과
[245번 CS 진단](245_M31_P2_CS_장기_연속성_진단.md)에 분리되어 있다.
따라서 해당 설정에서 SDK의 **요구량 초과 판정 없이 시작했다**는
범위만 확인한다. `sdc_mempool`의 전체 예약을 관찰 peak 사용량으로
읽거나, 미사용 byte를 이번에 회수 가능한 절감량으로 계산하지 않는다.

## P2 판정

controller pool은 SDK 계산·8-byte 정렬·초기화 시 요구량 검사 경로를
유지하며 임의로 축소하지 않는다. **SDC 내부 high-water 비노출은 추가 P2 gate가 아니다.**
지원 역할·count를 바꿀 때는 SDK 요구량을 다시 산정하고, 안전한 축소 근거가
없으면 현재 pool 크기를 유지한다. 내부 peak를 측정했다고 주장하지 않는다.

이 정적 감사는 지원 범위의 오류·최악 부하와 stack/heap 여유를 대신하지 않는다.
CS 최대 절차의 정상 256-step 결과는 후속 [260번](260_M31_P2_CS_누락_분류와_256_step_장시간.md)에,
DF 제품 IQ RX의 `UNSUPPORTED`·P2 비차단 경계는 [259번](259_M31_P2_DF_고정_SDK_지원_경계.md)에 있다.
**P2 전체는 미완료**이며 남은 작업은 [M31 TODO](../TODO_M31.md)의 세 축으로 관리한다.
