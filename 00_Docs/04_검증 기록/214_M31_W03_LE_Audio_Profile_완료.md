# M31-W03 LE Audio profile 완료

M31-W03의 LE Audio 11개 subcase를 고정 NCS v3.4.0과 NU54DK 세 보드 범위에서
모두 닫았다. 실행할 때마다 CMSIS-DAP V2 probe identity를 원문 UID 대신
SHA-256으로 선택하고 target COM·role·image revision을 다시 결합했다. 공개
`.ino`는 사용자가 읽고 수정할 수 있는 C++/NUCODE API 흐름을 두었으며 Zephyr
직접 호출이나 개발 milestone 표식을 노출하지 않는다.

기계 판정은 [`w03-subcase-index.json`](evidence/m31-w03-close-dc312cce/w03-subcase-index.json),
M31 work package 종료 판정은
[`closure-audit.json`](evidence/m31-w03-close-dc312cce/closure-audit.json), 파일 크기·SHA-256은
[`manifest.json`](evidence/m31-w03-close-dc312cce/manifest.json)이 소유한다.

## 1. 고정 source·SDK

| 항목 | 값 |
| --- | --- |
| W03 종료 source | `dc312cce5d56bf50a5acc0ed3e7788b8ada804c6` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| NCS nRF | `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Windows toolchain | `dcbdc366a1` |

종료 source와 각 실기의 clean source, 실제 flash image revision은 서로 다를 수
있다. 따라서 각 subcase index에 source/image/evidence revision을 각각 유지했고,
후속 clean source를 이전 image의 build revision으로 잘못 바꿔 기록하지 않았다.

## 2. M31-AUDIO-01 11/11

| subcase | 최종 판정 근거 | 결과 |
| --- | --- | --- |
| W03-01 LC3·stream data | native 양방향 LC3과 공개 Arduino source→sink 1,000 frame encode·ISO·decode, drop 0, sink 재시작 복구 20/20 | PASS |
| W03-02 BAP unicast·PACS/ASCS | 양방향 각 1,000 frame, stop/release·재연결 20/20, invalid state 40/40, codec·QoS·idle ASE 원격 거부 | PASS |
| W03-03 BAP broadcast | 암호화 LC3, stop/restart 20/20, wrong code 거부·정상 code 복구 20/20, sync loss 재가입 20/20 | PASS |
| W03-04 BASS | source·Assistant·Delegator 100/100, invalid/duplicate 각 20/20 거부, peer loss 20/20, 180초 17,500 frame·drop 0 | PASS |
| W03-05 CAP | broadcast 102/102·negative·peer loss, 185초 18,000 frame·drop 0; unicast start/stop 23, cancel 22, reconnect 48, remote failure 20/20·정상 image 복구 | PASS |
| W03-06 CSIP | 7/7 scenario, valid state/operation 101건, member loss 재가입·lock/release 20/20 | PASS |
| W03-07 PBP | 180초 stream·drop 0, stop/restart·wrong code·quality·sync loss 5/5 campaign | PASS |
| W03-08 VCP·VOCS·AICS·MICP | valid report 273건 + invalid range 거부 3건 = 276 report, peer loss 복구 20/20 | PASS |
| W03-09 MCP/MCS·CCP/TBS | Media·Call 각 normal 100, negative 2 class×20, recovery 40, reconnect 20, 180초 soak | PASS |
| W03-10 TMAP·GMAP | TMAP/GMAP unicast·broadcast 4/4, 각 180초 LC3·drop 0, stop/restart 20/20, 적용 role·quality·feature negative | PASS |
| W03-11 HAP/HAS | preset operation 100/100, invalid index 20/20, synchronized request 20/20 거부, reconnect 20/20 | PASS |

W03-01·02의 단계별 기록은 [181번](<181_M31_W03_native_BAP_LC3_실제_무선_전송.md>)~
[190번](<190_M31_W03_Arduino_BAP_양방향_클라이언트_및_회귀.md>), W03-03~05는
[202번](<202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>)·
[203번](<203_M31_W03_Arduino_BASS_3역할과_복구.md>)·
[204번](<204_M31_W03_Arduino_CAP_3역할과_broadcast_복구.md>)·
[205번](<205_M31_W03_Arduino_CAP_unicast_반복_실기.md>), W03-06~08은
[209번](<209_M31_W03_Arduino_CSIP_완료.md>)·
[210번](<210_M31_W03_Arduino_PBP_완료.md>)·
[208번](<208_M31_W03_Arduino_Audio_Control_완료.md>)에 보존했다. 마지막 profile 세
항목은 [211번](<211_M31_W03_Arduino_Media_Call_Control_완료.md>)·
[212번](<212_M31_W03_Arduino_TMAP_GMAP_완료.md>)·
[213번](<213_M31_W03_Arduino_HAP_HAS_완료.md>)이 소유한다.

## 3. 진단 이력과 지원 경계

각 실기의 앞선 FAIL·HOLD·부분 PASS는 원본 transcript와 diagnostic history로
보존했고 최종 PASS 분모에 합산하지 않았다. 특히 W03-09의 probe register
query·negative submission 오류, W03-10의 역할 dependency·boot 순서, W03-11의
synchronized rejection timeout은 원인·수정·동일 조건 재검증을 분리했다.

외부 PDM microphone·I2S speaker/codec의 실제 음향 입출력, 상용 phone·headset·
hearing aid·gaming 제품 상호운용은 **사용자 후속 `NOT RUN`**이며 M31-W03
개발·릴리스 비차단이다. 합성 PCM·encoded payload의 실제 RF data path PASS를
물리 음질, 의료 성능, 상용 상호운용, Bluetooth qualification으로 확대하지 않는다.

## 4. 종료 판정과 잔여

M31-AUDIO-01 W03-01~W03-11은 **11/11 PASS**이고 **M31-W03은 완료**다. 따라서
M31 work package 진도는 W01·W02·W03 **3/8**이다. M31 전체는 완료가 아니며
W04 Direction Finding과 W05 Channel Sounding은 진행 중, W06·W07·W08은
미착수로 남는다. W02 설치본 ISO 11예제·11역할 증거는 변경하지 않았고
CI/CD는 조회하지 않았다. 이 종료는 v0.5.0 공개, Bluetooth qualification,
M31-W04~W08 완료를 뜻하지 않는다.
