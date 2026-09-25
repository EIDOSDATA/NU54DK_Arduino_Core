# 256 — M31 P2 DF connectionless sync 대기 취소 진단

> 판정 갱신: 아래 CS 복구 100건의 `연속성 HOLD`는 당시 0-gap 기준이다.
> 현행 P2에서 간헐 CS loss는 비차단 관찰값이다. [260번](260_M31_P2_CS_누락_분류와_256_step_장시간.md)
> DF IQ 0·수신 fault는 LL 진단 실패로 보존하되, 제품 SDC IQ RX는 `UNSUPPORTED`·P2 비차단이다.
> 이 실패 실험의 재시도는 P2 필수가 아니다. [259번 지원 경계](259_M31_P2_DF_고정_SDK_지원_경계.md)

## 범위와 결과

고정 NCS `v3.4.0`·Zephyr `4.4.0`, Core 기준 commit
`e1e8e0952f750b60f0d57959c2e77f021677c77a`, board submodule
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`의 두 exact NU54DK에서
저장소 소유 Zephyr LL connectionless receiver fixture를 단일 진단했다.
세 번째 보드는 접근하지 않았다. 실기 전 probe UID·app/aux COM·HEX hash를
대조하고, 이전 CS 실행의 양측 STOP을 확인한 뒤 지정한 두 보드에만
자동 unlock 없는 sector flash를 했다.

[250번 실패](250_M31_P2_native_CS_비교와_DF_재진단.md)의 receiver는
`SYNC_TIMEOUT` 뒤 sync 객체가 아직 **동기화 대기 중**이면 종료 경로에서
`bt_le_per_adv_sync_delete()`를 호출하지 않았다. 고정 Zephyr API는 대기
상태에서도 이 함수로 취소하도록 명시한다. fixture의 종료 분기에만
`periodic_sync != NULL`이면 delete를 호출하고, 수립된 경우에만 CTE RX를
먼저 disable하도록 일시 변경했다. 제품 Arduino API·SDK·board 정의는
변경하지 않았다. 해당 진단 image는 `source_clean=false`이며 실패 뒤
fixture 소스를 기준 commit과 byte 동일하게 되돌렸다.

처음 `bt-ll-sw-split` snippet 없이 시작한 build는 DF RX Kconfig가 `n`으로
해결돼 `bt_df_per_adv_sync_cte_rx_*` 링크 오류가 났다. 이 잘못된 build는
**플래시하지 않았다**. 이전 실기와 동일한 `-S bt-ll-sw-split`으로
다시 빌드하자 receiver의 최종 `.config` SHA-256이 이전 image와 같은
`ff439044638814513a9e06fc9761cd120e305fc7762e5e2c260ddbd58eff7a7b`였다.
이 진단 receiver는 FLASH/RAM `89,804/47,100 B`, HEX SHA-256
`135b00187c127cc6fc200891410c979ffb22e752fe122eea1c8df60c41f35459`다.
상대는 [250번](250_M31_P2_native_CS_비교와_DF_재진단.md)과 같은 연속
Arduino beacon HEX
`ca510a5af52bc8d614fa939f3dff643413e137951a2b2ed5033425f3f05c66ac`다.

단일 실기에서 광고 interval 960·RSSI -61 dBm, `SYNC_CREATE code=0`,
8.4초 뒤 `SYNC_TIMEOUT`, **IQ 0**이었다. cleanup 도중 receiver는
`P2_STOP` 없이 precise data **bus fault**를 냈고 beacon만 STOP했다.
[실패 원본](evidence/m31-p2-native-comparison-2cf92933/df-connectionless-pending-cancel-01.json)은
image/probe hash·UART·종료 여부를 보존한다. PC `0x13416`은
`sys_dlist_remove`, LR `0x13465`는 `z_abort_thread_timeout`으로 해석됐다.
앞선 usage fault와 같은 함수 경로이지만 fault 유형·주소가 달라
**대기 객체 취소가 원인을 해결했다고 볼 수 없다**. 이 로그만으로
controller/Host 내부의 정확한 결함 위치를 단정하지 않는다. 실패 image를
다시 실행하지 않았고 이 fixture 변경을 제품 소스에 채택하지 않았다.

## 보드 복구와 P2 판정

두 보드를 이미 검증된 기본 CS initiator/reflector image로 자동 unlock·
mass erase 없이 sector 복구했다. 복구 [첫 100 raw](evidence/m31-p2-native-comparison-2cf92933/cs-recovery-after-df-pending-cancel-100.json)는
100건·양측 STOP을 확인했지만 counter 64→66 gap 1로 당시에는 **연속성 HOLD**였다.
이는 board fault가 지속됐다는 근거도, CS 연속성 PASS도 아니다.
후속 [10 raw](evidence/m31-p2-native-comparison-2cf92933/cs-recovery-after-df-pending-cancel-10.json)는
gap 0·양측 STOP으로 국소 PASS했다. 두 복구 원본을 모두 보존한다.

이 진단의 고정 SDK·NU54DK·Zephyr LL connectionless IQ RX는 **FAIL/HOLD**다.
연결형 내부 Zephyr LL IQ 수신 20 report·1,640 sample은 별개이고,
공개 Arduino/SDC RX 성공으로 옮기지 않는다. 동일 실패 image의 반복
플래시는 하지 않으며, P2 전체·DF RX 완료나 메모리 축소를 선언하지 않는다.

진단 fixture 원복 후 저장소 C/C++의 Git blob은 기준 commit과 같다.
Markdown 412개 strict UTF-8·로컬 링크 검사는 오류 0건이다. 직전
[255번 검증](255_M31_P2_CS_256_step_분할_RAS_진단.md)의 같은 제품 source
전체 Host 1,495건(2 skip) PASS를 재사용할 수 있지만, 이번 실패한 DF image의
HIL 결과를 PASS로 바꾸거나 P2 완료로 합치지 않는다.
