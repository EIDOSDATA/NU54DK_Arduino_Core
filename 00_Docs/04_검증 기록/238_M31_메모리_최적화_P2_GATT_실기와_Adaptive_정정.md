# 238 — M31 메모리 최적화 P2: GATT 512 B 실기와 adaptive 정정

## 판정

고정 NCS v3.4.0, board submodule `fe65f2f0`, `M31-MEM-OPT`의 P1 기준
`8f5f7cf8`에서 시작한 P2 국소 시험이다. 두 NU54DK의 generic GATT
Peripheral/Central에 **512 B write→read 검증과 20회 연결 해제·재연결**을
수행했다. 선언만 사용하는 adaptive 최종 image는 20/20, 수신 20/20,
bounded 재시도 0, STOP 20으로 **PASS**다. 별도 진단 image도 20/20이지만
연결 성립 실패 3건을 제한된 재시도로 복구했다. 이것은 GATT 역할의 실기
증거이지 P2 전체 역할의 완료 판정이 아니다.

| 항목 | 최종 확인 |
| --- | --- |
| 프로파일·선언 | `adaptive`, server/client 방향별 1 service·1 characteristic·1 link, event/TX/inline 각 512 B |
| 사용자 수동 BLE 설정 | 없음. 시험 `prj.conf`는 thread/heap 계측만 활성화 |
| 생성·최종 설정 | `BT_L2CAP_TX_MTU=512`, `BT_BUF_ACL_RX_SIZE=251`, `BT_BUF_ACL_TX_SIZE=251`, `BT_ATT_PREPARE_COUNT=6` 일치 |
| 이미지 | Peripheral HEX SHA-256 `30d877f8d47214483f0769ec8ca409b82229da44cd8c941f472367e22eec206c`, Central `30da3b2427b3bcef733539b05dc7fcb04aecb7d5e88bdd9bb0c17f78838afa6b` |
| 실기 | 2개의 exact CMSIS-DAP/COM mapping 확인, `auto_unlock=false`, sector erase, reset-halt-drain-resume; mass erase·unlock 없음 |
| 최종 결과 | [raw transcript·image/probe hash](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-adaptive.json): 20 cycle, 20 full write/read, Peripheral `P2_STOP writes=20`, 오류·재시도 0 |

## 실기에서 찾은 두 경계

첫째, adaptive overlay의 loaderless code partition include가 빠져 초기 image가
`0x10000`에 링크됐다. 기존 flash의 `0x0` image와 섞인 상태의 BUS FAULT는
메모리 high-water나 새 GATT 코드의 성공/실패로 세지 않았다. overlay에
`nu54dk-arduino-storage.dtsi`를 포함해 code partition을 `slot0_partition`
`[0x0, 0x16c000)`로 고정했다. builder는 loaderless 최종 DTS·linker map이
이 영역과 다르면 `[NU54:E_MEMORY_LAYOUT]`로 거부하며 Host/Arduino smoke
불변식을 추가했다. 같은 검사로 발견한 `fabric`·`ble_audio_io` overlay의
누락도 정정하고 다섯 loaderless profile 모두를 Host 계약에 포함했다.
기존 잘못된 image의 재사용을 막는 P0 정정이다.

UART를 사용하지 않는 공개 Blink 예제로 추가 두 profile을 실제 Arduino CLI
pristine 빌드했다. `fabric`은 FLASH 119,972 B/RAM 90,327 B,
`ble_audio_io`는 FLASH 41,836 B/RAM 23,707 B였고, 각각의 최종
resource audit에서 FLASH origin `0x0`, end `0x16c000`을 확인했다.
처음에 `fabric`에 적용한 Serial 계측 스케치는 이 profile이 DAP UART를
의도적으로 끄므로 미정의 `Serial` 링크 오류로 끝났다. 따라서 그 시도는
partition 실패나 실기 high-water로 세지 않는다. 두 Blink 빌드는 배치
검증이며 `fabric`·외장 Audio I/O의 실제 동작 HIL은 아니다.

둘째, 내부 GATT 배열에 512 B를 선언해도 ATT MTU 23·prepare buffer 0이면
512 B 전송 계약이 성립하지 않았다. resolver가 245~512 B GATT payload에
필요한 MTU 512·ACL 251·prepare count 6을 함께 생성하도록 정정했다.
명시적 `ble.att-mtu`가 512보다 작으면 충돌로 거부한다. 이 변경은 **245 B 이상
고용량 경로에만** 적용하며, 다른 역할·작은 payload의 transport 최적 용량을
입증했다고 해석하지 않는다.

실패 진단 원본은 [첫 실패](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20.json),
[수동 transport 진단](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-transport.json),
[연결 무효화 알림](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-invalidation.json),
[recycle 대기](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-recycled.json),
[안정화 간격](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-settle.json)에
`FAIL`로 보존했다. 정상적인 `handles_invalidated` 알림은 시험 코드에서
이전 link의 실패로 오분류하지 않는다. 연결 객체 반환 알림을 기다린 뒤 scan을
재개한다. HCI reason `0x3e`와 driver `-14`가 함께 나온 연결 성립 실패만
최대 3회 재시도하고, payload 오류·다른 해제·timeout은 실패로 남긴다.
[수동 transport 복구 PASS](evidence/m31-p2-gatt-8f5f7cf8/gatt-512-20-retry.json)는
20/20이지만 재시도 3건이 있어 무오류 결과로 표기하지 않는다.

## 실행 중 관찰값과 비판정 범위

최종 adaptive PASS image에 thread analyzer와 heap runtime stats를 켠 채
관찰한 high-water다. `used`는 관찰된 최고 사용량이지 예약 RAM에 다시 더할
별도 할당량이 아니다. 단위는 byte다.

| Thread/ISR | Peripheral used/reserved | Central used/reserved |
| --- | ---: | ---: |
| BT RX WQ | 1080/2048 | 960/2048 |
| BT TX processor | 372/904 | 516/904 |
| BT LW WQ | 188/2104 | 1068/2104 |
| BT GATT DM WQ | 해당 없음 | 204/1304 |
| sysworkq | 272/2048 | 792/2048 |
| MPSL Work | 364/1024 | 356/1024 |
| main | 1272/8192 | 1784/8192 |
| ISR0 | 432/2048 | 448/2048 |

양쪽의 libc malloc·관찰된 Zephyr `k_heap` peak는 0 B였고 계측 시점의
free는 각각 8108 B·4100 B였다. 이 통계는 controller 내부 pool, 모든
할당 실패·fragmentation, 미실행 보안/복구 경로를 포괄하지 않는다. 따라서
main/workqueue/BT stack, malloc arena, Zephyr heap, SDC controller pool은
이번 값만으로 축소하지 않았다. 계측 자체의 메모리·타이밍 비용도 제품
image와 다르다. `0 B peak`를 해당 pool 제거 승인으로 해석하지 않는다.

세 번째 probe는 별도 초기 진단 뒤 debug attach에서 core를 발견하지 못해
이 시험에 사용하지 않았다. 자동 unlock/recover/mass erase는 시도하지 않았다.
두 보드 GATT 결과를 세 보드 역할 재배치 검증으로 확대하지 않는다.

## P2 전체의 남은 판정

GATT 이외 역할은 이 기록의 판정 밖이다. 후속 [239번](239_M31_메모리_최적화_P2_CoC_CS_계측.md)에서
CoC 512 B 두 채널은 PASS했고 CS raw 100개는 계측했지만 counter 연속성은
HOLD로 남겼다. ISO/Audio·DF와 역할별 controller high-water도 **HOLD**다.
역할별 계측과 동일 기능 native 비교가 부족하므로 P2 전체 체크리스트는
열어 둔다. W04/W05 잔여 기능과 W06 수명주기·M19~M30 회귀, 외장 장치와
상용 peer의 `NOT RUN`, Windows 공개 승인도 별개다.
