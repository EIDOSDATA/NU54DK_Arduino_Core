# 250 — M31 P2 native RAS 비교·connectionless DF 재진단

## 범위와 판정

고정 NCS `v3.4.0`·Zephyr `4.4.0`, 동일 NU54DK board definition과 두 exact
보드를 사용했다. 세 번째 감지 보드에는 접근하지 않았다. HIL 직전 probe UID와
app/aux COM mapping을 확인하고 자동 unlock 없이 sector flash,
reset-halt-drain-resume으로 시작했다. 원시 UID는 JSON에 저장하지 않았다.
고정 SDK 원본은 변경하지 않았다.

Nordic `ras_initiator`·`ras_reflector` **원본은 둘 다 target build PASS**다.
실기에는 reboot를 제거하고 UART `s` 종료, callback·RAS 분모만 추가한
[계측 복사본](../../tests/hil/nu54dk/fixtures/NordicRasComparison/README.md)을 썼다.
따라서 아래 HIL은 원본과 byte-identical하다는 주장이 아니라 원본의 무선/RAS
경로를 보존한 진단이다. 각 역할이 종료할 때 CS disable·ACL disconnect·광고
중단과 `NATIVE_CS_STOP`을 확인했다.

| 실행 | 유효 RAS | controller callback | abort | local busy | peer counter mismatch | counter gap | 종료 | 근거 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 최초 짧은 검증 | 100 | 100 | 0 | 0 | 0 | 0 | 양측 STOP | 작업용 원본 `native-ras-100.json`, SHA-256 `3ad349b7fcaeb82a049fa2d4c80a75afe874aee540f9a7b350cb6fcf8759814e` |
| DF fault 뒤 복구 확인 | 100 | 102 | 2 | 0 | 0 | 2 | 양측 STOP | [복구 원본](evidence/m31-p2-native-comparison-2cf92933/native-ras-recovery-100.json) |
| 최초 장기 비교 | 1,000 | 1,007 | 4 | 3 | 3 | 7 | 양측 STOP | 작업용 원본 `native-ras-1000.json`, SHA-256 `ca015ad26fae8321ccfaf1fec0e9903f0ab9178160caee772e6f9a1bb8f53c14` |
| 저장소 증거 장기 비교 | 1,000 | 1,004 | 2 | 2 | 2 | 4 | 양측 STOP | [1,000건 원본](evidence/m31-p2-native-comparison-2cf92933/native-ras-1000.json) |

각 장기 실행에서 abort된 procedure의 RAS 데이터가 비어 있고, 다음 local
callback 때 단일 버퍼가 바빠 peer counter가 현재 counter와 달라진 경로가
계측됐다. 두 종류의 합은 해당 실행의 gap 7건/4건과 일치한다. 하지만 이
동등 횟수만으로 모든 gap과 각 callback 사이의 일대일 인과관계를 증명하지
않으며, RF 조건도 실행마다 달랐다. 가장 중요한 결론은 **고정 Nordic sample
경로도 1,000건에서 gap 0을 보장하지 않는다**는 것이다. 따라서
[Arduino 1,000건 실행의 gap 2건](245_M31_P2_CS_장기_연속성_진단.md)을
코어 고유 누락으로 즉시 판정하거나, 절대적인 0-gap을 P2의 유일한 통과
조건으로 삼지 않는다. 반대로 native 누락을 근거로 Arduino의 정상 callback
뒤 누락 4건·불완전 raw를 해결된 것으로 처리하지도 않는다.

## 정적 자원 비교의 한계

계측 native initiator/reflector의 FLASH/RAM 예약은 각각
`290,176/67,408 B`, `247,384/53,590 B`다. 원본 native build는
`290,180/67,352 B`, `247,840/53,574 B`였다. 같은 board의 현재
Arduino raw RAS 계측 image는 initiator `243,716/80,458 B`,
reflector `225,148/63,380 B`다. native 계측 initiator와 Arduino의
표면 RAM 차이는 `13,050 B`지만 **Arduino API 비용이 아니다**.

native initiator는 `CONFIG_BT_CS_DE=y`로 FFT/phase/RTT 거리 추정과
sliding window를 포함하고 main stack `3,584 B`, malloc arena `-1`을
쓴다. Arduino image는 비보정 RTT raw parser·메모리 계측을 쓰고 main stack
`8,192 B`, malloc arena `8,192 B`다. RAS data path·로그·stack·heap
조건이 일치하지 않는다. native initiator의 `sdc_mempool` 정적 예약은
`7,672 B`로 Arduino initiator와 같지만 이는 controller 내부 peak가
아니다. 두 reflector의 controller/역할 설정도 동일하지 않아 차감을
보류한다. native 계측 HEX SHA-256은 initiator
`85049aca219cebec3c1c4f5d0be667d05df4bfa031097c833c5451037e0b06f8`,
reflector `f08aaa4eb512e019971d9f057c5a423d887dc511705dc8fc922eba3dfe16c83a`다.
Arduino clean-source와의 **동일 기능·동일 설정 비용 비교는 여전히 HOLD**다.

ELF symbol 대조는 혼합된 차이가 어디에 있는지 더 분명히 보여준다. 아래는
서로 다른 설정의 **예약량**이며 같은 역할의 조정 목표나 동적 peak가 아니다.

| 예약 symbol | Nordic 계측 initiator | Arduino raw initiator | 차이의 성격 |
| --- | ---: | ---: | --- |
| `z_main_stack` | 3,584 B | 8,192 B | 설정 차이 4,608 B |
| `malloc_arena` | 없음 | 8,192 B | C library 설정 차이 |
| `bt_tx_processor_stack` | 904 B | 3,200 B | Bluetooth 설정 차이 2,296 B |
| `sys_work_q_stack` | 2,048 B | 4,096 B | workqueue 설정 차이 2,048 B |
| `sdc_mempool` | 7,672 B | 7,672 B | 같은 정적 controller 예약 |
| native DSP `m_iq_scratch_mem`·`m_cs_de_report` | 4,096 B·1,232 B | 없음 | native의 추가 거리 추정 기능 |
| Arduino `scan_result_queue`·`gap_event_queue` | 없음 | 2,496 B·960 B | 공개 API의 비동기 event 보존 |

`malloc_arena`가 해당 정상 수명에서 peak 0이었다고 해서 일반 Arduino sketch의
`malloc` 사용까지 불가능하게 만들 수는 없다. stack 또한 정상 단일 stream의
high-water만으로 줄이지 않는다. `sdc_mempool` 동일성은 **예약 상한**만의
일치다. Native의 DSP 비용과 Arduino의 공개 API 상태·여유 stack을 한 숫자로
상쇄해 최소 API 비용을 주장하지 않는다.

## DF connectionless 재진단과 보드 복구

고정 Nordic locator sample의 `BT_LE_PER_ADV_SYNC_OPT_SYNC_ONLY_CONST_TONE_EXT`
옵션과 timeout 10 ms 단위 변환을 저장소 소유 Zephyr LL 수신 fixture에
반영하고, UART STOP과 stack/heap 계측을 추가해 build PASS했다. 상대는
연속 송신 Arduino beacon image다. 첫 실행은 광고 interval 960,
RSSI 약 -57 dBm, sync create `0` 뒤 8.4초 timeout·IQ 0이었으나 양측
STOP이었다. 둘째 실행은 동일 timeout 뒤 수신기에 **usage fault**가
발생해 수신 STOP이 없었다. fault 원본을 삭제하지 않고
[실패 JSON](evidence/m31-p2-native-comparison-2cf92933/df-connectionless-cte-only-01.json)에
image/probe hash, UART, 송신 STOP·수신 STOP 실패를 남겼다. 이 구성은
**FAIL**이고 단일 옵션 누락이 원인이었다는 가설은 기각된다. 해당 ELF의
PC `0x13412`는 `sys_dlist_remove`, LR `0x13461`은
`z_abort_thread_timeout`으로 해석돼 이전 cleanup fault와 같은 경로다.
동일 함수 경로라는 사실만으로 controller 내부 원인까지 확정하지 않는다. fault 뒤 수신
보드와 송신 보드를 검증된 native CS 계측 이미지로 sector flash해 위 100건
복구 실행에서 양측 STOP을 확인했다. 자동 unlock·mass erase·recover는
사용하지 않았다.

Zephyr upstream connectionless locator와 beacon의 `sample.yaml`은 둘 다 nRF54L15DK를
허용 플랫폼에 포함하지 않는다. 이 사실과 실패 HIL은 **현재 고정 SDK·이 보드
조합의 지원 근거가 없다**는 뜻이지 칩 전체의 CTE RX 불가능 증명은 아니다.
내부 Zephyr LL 연결형 IQ 20 report·1,640 sample의 [246번 PASS](246_M31_P2_DF_연결_IQ_메모리_계측.md)는
별도이고, 이를 connectionless 또는 공개 Arduino/SDC RX PASS로 옮기지 않는다.

후속으로 locator 원본의 **active scan** 설정까지 맞춘 별도 image를 빌드했다.
고정 SDK·같은 보드의 target build는 `FLASH 89,788/RAM 47,100 B`로 PASS했고,
receiver HEX SHA-256은
`729e3be98337aed5188600a85bc3f688a1707a46ce83d59a8bdd18081755b357`다.
연속 Arduino CTE beacon을 상대에 두고 **한 번** 실행했으나 광고 interval 960,
RSSI -54 dBm, `SYNC_CREATE code=0` 다음 8.4초 timeout·IQ 0이었다.
수신기에서 같은 `sys_dlist_remove` PC `0x13412` usage fault가 다시 발생해
receiver STOP은 없었고 beacon STOP만 확인했다.
[active-scan 실패 원본](evidence/m31-p2-native-comparison-2cf92933/df-connectionless-active-scan-01.json)은
**FAIL**이며 active/passive scan 차이만으로 해결된다는 가설은 기각된다.
실패한 image는 반복 실행하지 않았다. 두 보드를 이미 검증된 native CS
image로 sector 복구한 뒤 [RAS 100건·gap 0·양측 STOP](evidence/m31-p2-native-comparison-2cf92933/native-ras-recovery-after-active-scan-100.json)을
다시 확인했다. 이 복구 PASS는 DF 수신 성공을 의미하지 않는다.

## P2 잔여 판정

CS의 native 비교로 0-gap 문턱의 오류는 바로잡았지만 최대 procedure·step,
fragmented RAS, RF abort/peer loss 후 복구의 peak와 Arduino 정상 callback
뒤 누락은 남았다. DF connectionless는 재실패·fault로 계속 HOLD/FAIL 경계를
유지한다. Audio/ISO 다중 역할·오류/재가입·최악 부하와 동일 설정 native 비용
비교가 끝나지 않았고 SDC 내부 실행 중 high-water는 노출되지 않는다.
따라서 **P2 전체 완료와 stack/heap/controller pool 축소를 선언하지 않는다**.
후속 [252번 장절차·반복 계수 진단](252_M31_P2_CS_장절차_반복계수_경계_진단.md)도
실제 93~98 step에 머물러 최대 256-step·분할 RAS를 닫지 못했다.
