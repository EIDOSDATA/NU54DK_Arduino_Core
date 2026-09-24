# 247 — M31 P2 connectionless DF 수신 재진단과 보류

## 판정

고정 NCS v3.4.0·Zephyr 4.4.0의 `bt-ll-sw-split` 단일 안테나
connectionless 수신 후보와 Arduino `CteBeacon` 송신을 exact 두 NU54DK에서
다시 대조했다. 기존 [172번 진단](172_M31_W04_DF_기본안테나_IQ_수신_진단.md)의
periodic sync 실패를 재현했다. **IQ report 0건이므로 connectionless RX와
해당 역할의 P2 high-water는 HOLD**다. 연결형 내부 IQ 20건의
[246번 계측](246_M31_P2_DF_연결_IQ_메모리_계측.md)을 이 결과에 합치지 않는다.

| 시도 | 관찰·정리 | 원본 |
| --- | --- | --- |
| 2초마다 재시작하는 P2 beacon | extended 광고와 periodic interval 960을 수신했지만 sync 미수립. 당시 수신 앱은 sync 실패 후 명시적 STOP 없이 반환했고, 송신 측만 STOP. 이후 수신 보드를 수정 진단 image로 안전하게 다시 기록·시작해 STOP을 확인했다. 기능 FAIL 원인으로 송신 주기를 단정하지 않는다. | [1차 실기](evidence/m31-p2-df-memory-53e8bbad/connectionless-rx-memory-01.json) |
| 광고를 유지하는 P2 beacon | 광고 RSSI 약 -57 dBm과 `SYNC_CREATE code=0` 뒤에도 `SYNC_LOST`·`SYNC_TIMEOUT`. IQ 0. 양측 STOP과 수신 stack/malloc 출력은 확인했지만 수신 부하 high-water는 아니다. | [연속 송신 재시험](evidence/m31-p2-df-memory-53e8bbad/connectionless-rx-memory-02.json) |
| sync 종료 사유 추가 관찰 | 광고 RSSI 약 -56 dBm, `SYNC_CREATE code=0`, `SYNC_TIMEOUT` 뒤 cleanup의 sync delete가 `-134`를 반환했고 `sys_dlist_remove`/`z_abort_thread_timeout`에서 usage fault가 발생했다. 이 실행은 수신 STOP이 없어 **FAIL**로 보존한다. 송신 STOP은 확인했다. | [cleanup fault](evidence/m31-p2-df-memory-53e8bbad/connectionless-rx-memory-03.json) |

마지막 fault의 PC `0x135ce`와 LR `0x1361d`는 해당 image ELF에서 각각
`sys_dlist_remove`(`dlist.h:530`)와 `z_abort_thread_timeout`
(`timeout_q.h:87`)으로 해석했다. 이는 [172번의 같은 종류 실패](172_M31_W04_DF_기본안테나_IQ_수신_진단.md)와
일치하지만, controller와 Host 사이의 단일 근본 원인을 새로 확정한 것은
아니다. `-134` 반환과 동기화 실패를 명령 수락 또는 IQ 성공으로 승격하지 않는다.

fault 뒤 수신 보드에는 이미 검증된 연결형 DF 수신 image를 자동 unlock 없는
sector flash로 다시 기록했다. 정확한 probe/COM을 재확인한 뒤
reset-halt-drain-resume, `DF_CONN|SCANNING|code=0`, `s`,
`DF_CONN|STOPPED`, `P2_PHASE name=stopped`를 순서대로 확인했다.
송신 보드는 같은 실행에서 `P2_STOP role=df-beacon`을 확인했다.
1차 실패 뒤에는 수정 진단 image에서 `P2_READY`, `s`,
`P2_STOP role=df-connectionless-receiver`를 확인했다. 이후 실패한
connectionless image로 추가 시험을 이어가지 않았다.

재진단을 위한 `m31_df_receiver` 변경과 전용 러너는 fault 경로가 확인된 뒤
저장소에서 되돌렸다. P2 beacon 시험 sketch에는 진단 시 광고를 유지하는
`NUCODE_P2_DF_CONTINUOUS` guard만 남겼으며 기본 20회 동작은 바꾸지 않았다.
실패 JSON과 image hash는 삭제하지 않았다.
따라서 이 기록은 저장소의 현재 fixture로 재현 가능한 PASS가 아니며,
`source_clean=false`인 진단 snapshot이다. 고정 SDK source·board pin이나
공개 Arduino API를 수정하지 않았고, mass erase·자동 unlock·recover는
사용하지 않았다.

## 잔여

Zephyr LL의 connectionless sync 실패·종료 경로를 별도 원인 조사하고,
지원 가능한 구성이라면 controller IQ event→Host callback→양수 sample과
정상 STOP을 함께 입증해야 한다. 안테나 배열·각도 계산·외장 RF의
사용자 후속 실물 범위와 기본 안테나 raw IQ 수신 적용성은 구별한다.
이 HOLD는 P2 전체 또는 M31-W04 완료로 승격하지 않는다.
