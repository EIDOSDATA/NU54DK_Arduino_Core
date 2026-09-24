# 검증 기록

시험 당시의 source·환경·조건·성공·실패와 원본 증거를 보존하는 색인입니다. 현재 설치·지원 버전은
**v0.4.1**이고, 개발 소스는 **M28·M29·M30 완료, M31 3/8**입니다. M31-W03 LE Audio
profile은 **11/11 PASS**로 닫았으며 W04~W08은 완료가 아닙니다. HOST-W01~W03은 완료했고
HOST-W04~W08은 사용자 보류 상태입니다.

지원 배포와 개발 중 기능을 구분하려면 [프로젝트 README](../../README.md)를, 다음 작업은
[v0.5.0 TODO](../TODO_v0.5.0.md)와 [인계 문서](../HANDOFF.md)를 확인하세요. 아래 기록의
진행률·미실행·다음 작업·릴리스 시점은 각 기록 작성 시점의 상태입니다. 과거의 M33 v0.5.0·
세 Host 계획을 현재 gate로 다시 적용하지 않습니다. 현행은 M31 완료 후 Windows v0.5.0입니다.

## 현재 상태

| 구분 | 상태 | 기준 문서 |
| --- | --- | --- |
| 설치·지원 | `v0.4.1`만 지원 | [v0.4.1 유지보수 기록](129_v0.4.1_설치기_유지보수_릴리스.md) |
| 개발 소스 | M28·M29·M30 완료, M31 3/8 | [v0.5.0 TODO](../TODO_v0.5.0.md) · [M31 TODO](../TODO_M31.md) |
| M31-W01·W02 | 완료 | [W01/W02 진행 기록](165_M31_W01_착수와_W02_CIS_개발_후보.md) · [W02 최종 설치본 기록](199_M31_W02_격리_설치본_ISO_11예제와_완료.md) |
| M31-W03 | LE Audio profile 11/11 PASS·완료 | [W03 종료 기록](214_M31_W03_LE_Audio_Profile_완료.md) |
| M31 메모리 최적화 P0·P1 | 완료. P2의 동적 계측·안전 판정과 구별 | [P0](222_M31_메모리_최적화_P0_완료.md) · [P1](237_M31_메모리_최적화_P1_정적_저장소_완료.md) |
| M31 메모리 최적화 P2 | GATT·CoC·ISO·Audio·DF TX·CS 단기 실행은 역할별 국소 PASS. 내부 LL 연결 IQ 20건과 정상 종료 stack을 관찰했다. CS 장기 누락·connectionless/공개 DF RX·최악 부하는 HOLD | [현재 범위·잔여 gate](../TODO_M31.md) · [최근 P2 기록](#최근-완료재개-기록) |
| M31-W04·W05 | 연결형 내부 IQ 수신 국소 PASS, W04/W05 전체는 미완료·이전 실패 보존 | [W04 102 event 진단](216_M31_W04_연결_AoA_Controller_IQ_Event_진단.md) · [W04 이전 실패 인계](220_M31_릴리스_전환과_문서_전수_정비.md) · [W04 연결 IQ 후속](244_M31_P2_DF_연결_IQ_진단.md) · [W05 동일 ACL](217_M31_W05_비암호화_RAS_ATT_오류_진단.md) · [W05 flash 직후](218_M31_W05_flash_직후_RAS_복구_재검증.md) |
| M31-W06~W08 | 미착수 | [M31 TODO](../TODO_M31.md) |
| HOST-W04~W08 | 사용자 보류·미완료 | [Host 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |

지원 중인 `v0.4.1`과 개발 브랜치의 M31 결과는 서로 다른 범위입니다. M31 PASS를 설치본의
지원 기능이나 `v0.5.0` 공개 완료로 읽지 않습니다.

## 최근 완료·재개 기록

| 기록 | 용도 |
| --- | --- |
| [249 — P2 문서 정합성 감사](249_M31_P2_문서_정합성_감사.md) | 현재 진입점·P2 기록 수치/링크/판정 분리, Markdown 404개 gate와 Host 회귀 경계 |
| [248 — P2 SDC pool 정적 경계](248_M31_P2_SDC_pool_정적_경계_감사.md) | 8개 역할 ELF의 SDK 계산·8-byte 정렬 pool 예약과 초기화 요구량 검사 확인; 내부 high-water·임의 축소는 미주장 |
| [247 — P2 DF connectionless 재진단](247_M31_P2_DF_connectionless_재진단과_보류.md) | 연속 CTE 송신에서도 LL periodic sync 미수립, IQ 0·cleanup fault 원본과 보드 복구 보존; P2 RX HOLD |
| [246 — P2 DF 연결 IQ 메모리 계측](246_M31_P2_DF_연결_IQ_메모리_계측.md) | Zephyr LL 내부 연결형 20 report·1,640 sample, cleanup과 역할별 stack high-water 국소 PASS; 공개 RX·controller pool 별도 |
| [245 — P2 CS 장기 연속성 진단](245_M31_P2_CS_장기_연속성_진단.md) | controller sync abort와 단일 로컬 버퍼 경쟁을 분리; 500건 × 2 국소 PASS, 두 수정 image의 1,000건 연속성은 HOLD |
| [244 — P2 DF 연결 IQ 내부 진단](244_M31_P2_DF_연결_IQ_진단.md) | Zephyr LL 내부 연결형 20 report·1,640 sample과 cleanup 국소 PASS; Arduino/SDC·connectionless·high-water 별도 |
| [243 — P2 Audio broadcast 실기](243_M31_메모리_최적화_P2_Audio_broadcast_실기_계측.md) | 암호화 LC3/BIS 1,000 frame 최종 image 8/8 및 연속 10,000 frame·drop 0, 최초 동기화 실패 원본 보존, 정적 예약·stack high-water |
| [242 — P2 DF beacon TX](242_M31_메모리_최적화_P2_DF_beacon_TX_계측.md) | AoA CTE beacon 20회 TX start/stop·negative·high-water; IQ RX/각도는 HOLD |
| [241 — P2 Audio unicast 실기](241_M31_메모리_최적화_P2_Audio_unicast_실기_계측.md) | 동일 image의 합성 PCM/LC3/CIS 1,000·연속 10,000 frame 송신·복호화, drop 0·양측 종료·high-water; 다른 조합은 별도 |
| [240 — P2 CIS·BIS 실기](240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md) | 두 보드에서 각 100 SDU × 20세션, BIS 누락 0, 정적 예약·stack high-water; Audio 결합은 별도 |
| [239 — P2 CoC·CS 계측](239_M31_메모리_최적화_P2_CoC_CS_계측.md) | CoC 두 채널 512 B/100 echo PASS, CS 후속 연속 100개 PASS·앞선 간헐 counter 누락 원인 HOLD, 역할별 high-water |
| [238 — P2 GATT 512 B 실기](238_M31_메모리_최적화_P2_GATT_실기와_Adaptive_정정.md) | adaptive loaderless·ATT transport 정정, 두 보드 20회 read/write·reconnect와 stack/heap 관찰; P2 다른 역할 HOLD |
| [237 — P1 정적 저장소 완료](237_M31_메모리_최적화_P1_정적_저장소_완료.md) | 역할별 source·state·pool 분리와 선언 용량 연결, 전체 Host 1,481건; P2 실측은 별도 |
| [226 — M31 메모리 최적화 P1 Resource Table 정렬](226_M31_메모리_최적화_P1_Resource_Table_정렬.md) | 48-slot·64-bit generation 유지, table 2,320→1,936 B, 누적 30,288 B 절감과 22,000 B 상한 |
| [225 — M31 메모리 최적화 P1 Runtime Route 절감](225_M31_메모리_최적화_P1_Runtime_Route_절감.md) | 단일 자원 lease, `spi_route` 4,224→624 B, P1 누적 29,864 B 절감과 전체 Host 1,475 PASS |
| [224 — M31 메모리 최적화 P1 UART20 lease 절감](224_M31_메모리_최적화_P1_UART20_lease_절감.md) | boot 등록 transaction 지역화, adaptive SPI RAM 25,405→24,613 B, 누적 26,264 B 절감과 26,000 B 상한 |
| [223 — M31 메모리 최적화 P1 GPIO 상태 절감](223_M31_메모리_최적화_P1_GPIO_상태_절감.md) | pin별 transaction lease 중복 제거, adaptive SPI RAM 50,877→25,405 B, Core RAM 상한과 ownership target 회귀 |
| [222 — M31 메모리 최적화 P0 완료](222_M31_메모리_최적화_P0_완료.md) | compiler probe·resolver·52 preset·55 image의 config/source/ELF/RAM 상한과 금지 symbol gate, P1 인계 |
| [221 — main 마일스톤별 이력 정리](221_main_마일스톤별_이력_정리.md) | 공개 v0.4.1 마감 뒤 189커밋→7묶음, 원격 archive 원본 보존·tree 동일성·새 checkout 인계 |
| [220 — M31 릴리스 전환·문서 정비](220_M31_릴리스_전환과_문서_전수_정비.md) | v0.5.0 Windows·M31 공개 준비, 최적화 우선·main/M31-MEM-OPT 인계, 기존 W04 raw IQ 실패 원본 보존 |
| [219 — M31-W06 메모리 감사·최적화 계약](219_M31_W06_메모리_점유_감사와_최적화_계약.md) | Audio·CS·DF 정적 RAM 원인, lean fragment·pool·회귀 gate. 최신 순서는 메모리 최적화→W04/W05→W06 |
| [218 — W05 flash 직후 복구 재검증](218_M31_W05_flash_직후_RAS_복구_재검증.md) | 두 exact attempt의 raw RAS·stop/restart·disconnect/reconnect PASS, 과거 간헐 중단 원인 확정 아님 |
| [217 — W05 동일 ACL ATT 오류 진단](217_M31_W05_비암호화_RAS_ATT_오류_진단.md) | 비암호화 RAS read 20/20 거부, request 재사용 경계·회귀 |
| [216 — W04 controller IQ event 진단](216_M31_W04_연결_AoA_Controller_IQ_Event_진단.md) | 당시 controller event 102건·Host gate 폐기·sample 0. 최신 내부 callback 시도는 220에 별도 보존 |
| [215 — W03 이력·문서 정비](215_M31_W03_이력과_문서_정비.md) | 개발 이력 squash, 문서 전수 검토, main 반영과 원본 이력 보존 |
| [214 — M31-W03 LE Audio profile 종료](214_M31_W03_LE_Audio_Profile_완료.md) | W03-01~W03-11 11/11 PASS, 고정 source·SDK와 비차단 후속 범위 |
| [211 — Media·Call control](211_M31_W03_Arduino_Media_Call_Control_완료.md) | MCP/MCS·CCP/TBS 정상·negative·복구·reconnect·soak 최종 PASS |
| [212 — TMAP·GMAP](212_M31_W03_Arduino_TMAP_GMAP_완료.md) | unicast·broadcast 네 역할, LC3 soak와 role·quality·feature negative PASS |
| [213 — HAP·HAS](213_M31_W03_Arduino_HAP_HAS_완료.md) | preset 100/100, invalid·synchronized request 거부, reconnect 20/20 PASS |
| [208 — Audio control](208_M31_W03_Arduino_Audio_Control_완료.md) | VCP·VOCS·AICS·MICP 완료 |
| [209 — CSIP](209_M31_W03_Arduino_CSIP_완료.md) | 일곱 scenario와 member loss·lock/release 완료 |
| [210 — PBP](210_M31_W03_Arduino_PBP_완료.md) | 180초 stream과 다섯 campaign 완료 |
| [199 — M31-W02 설치 ISO 완료](199_M31_W02_격리_설치본_ISO_11예제와_완료.md) | 설치본 ISO 11예제·11역할 build와 공개 사용자 SDU 실기 근거 |
| [200 — 다른 PC 작업 인계](200_M31_다른_PC_작업_인계.md) | 작성 당시 장치·lock·재개 경계의 역사 snapshot |

<details>
<summary>이전 주요 기록 펼치기</summary>

| 기록 | 용도 |
| --- | --- |
| [205 — M31-W03 Arduino CAP unicast 반복 실기](205_M31_W03_Arduino_CAP_unicast_반복_실기.md) | exact 공개 API start/stop 23회, cancel 22회, 재연결 48회, LC3 decode 1,800 frame·drop 0; 원격 완료 실패 20/20와 정상 image 복구 |
| [204 — M31-W03 Arduino CAP 3역할과 broadcast 복구](204_M31_W03_Arduino_CAP_3역할과_broadcast_복구.md) | CAP broadcast 제어 102/102, negative 20×2, peer loss 복구 20/20, 185초 drop 0 |
| [203 — M31-W03 Arduino BASS 3역할과 복구](203_M31_W03_Arduino_BASS_3역할과_복구.md) | BASS 제어 100/100, invalid/duplicate 20×2, peer loss 20/20, 180초 drop 0 |
| [202 — M31-W03 Arduino BAP broadcast 암호화와 negative 완료](202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md) | clean 암호화 LC3, restart 20/20, wrong code 거부·복구 20/20, hardware-reset sync loss 재가입 20/20 |
| [201 — M31-W03 Arduino BAP broadcast 비암호화와 재가입](201_M31_W03_Arduino_BAP_broadcast_비암호화와_재가입.md) | clean 공개 source/sink LC3 방송과 stop/restart 재가입 20/20, Broadcast Code·강제 sync loss 잔여 |
| [196 — M31-W02 공개 CIS→BIS 세 보드 사용자 SDU 실기](196_M31_W02_공개_CIS_BIS_세_보드_사용자_SDU_실기.md) | clean 세 역할 20/20·2,000/2,000 CIS 수신→BIS 전달·수신, 자원 반환 20/20, 공개 ISO 예제 감사 0건 |
| [195 — M31-W02 공개 BIS 시각 동기 사용자 SDU 실기](195_M31_W02_공개_BIS_시각동기_사용자_SDU_실기.md) | clean 시간 동기 두 역할 20/20·2,000/2,000, HCI·수신 시각 유효·단조 0오류, W02 공개 예제 3개 진행 중 |
| [194 — M31-W02 공개 암호화 BIS 사용자 SDU 실기](194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md) | clean 암호화 두 역할 20/20·2,000/2,000, 잘못된 Code MIC 거부·유효 SDU 0, W02 공개 예제 5개 진행 중 |
| [193 — M31-W02 공개 BIS 사용자 SDU 실기](193_M31_W02_공개_BIS_사용자_SDU_실기.md) | clean 공개 `RawBis` source/receiver 20/20, 1,999/2,000 수신·회차별 최소 99, W02 공개 예제 7개 진행 중 |
| [192 — M31-W02 공개 CIS 사용자 SDU 실기](192_M31_W02_공개_CIS_사용자_SDU_실기.md) | clean 공개 `RawCis` 두 역할 20회×100 송수신·payload 오류 0, W02 나머지 9개 예제 진행 중 |
| [188 — M31-W03 Arduino BAP 원격 잘못된 ASE 상태 거부 20회](188_M31_W03_Arduino_BAP_원격_잘못된_ASE_상태_거부_20회.md) | clean 공개 Arduino server의 idle ASE 원격 Release가 20/20 `code=4 reason=0`으로 거부됨 |
| [187 — M31-W03 Arduino BAP 원격 codec·QoS 거부 각 20회](187_M31_W03_Arduino_BAP_원격_codec_QoS_거부_각_20회.md) | clean 공개 Arduino server의 원격 ASCS unsupported codec·invalid QoS 각각 20/20 거부 |
| [186 — M31-W03 Arduino BAP 잘못된 상태 거부 40회](186_M31_W03_Arduino_BAP_잘못된_상태_거부_40회.md) | clean 공개 API 중복 stop·정지 중 frame 전송 40/40 거부, LC3 2,400 frame과 재연결 20/20 |
| [185 — M31-W03 Arduino BAP stop/release 20회](185_M31_W03_Arduino_BAP_stop_release_20회.md) | clean 공개 예제의 ASE disable·release·재연결 20/20과 LC3 2,400 frame, 정상 연결 해제 오류 교정 |
| [184 — M31-W03 Arduino BAP 재시작 복구 20회](184_M31_W03_Arduino_BAP_unicast_재시작_복구_20회.md) | clean source/sink 1,000 LC3 frame과 sink reset 복구 20/20 |
| [191 — M31-W02 공개 ISO 예제 재점검](191_M31_W02_공개_ISO_예제_재점검.md) | 이전 무선 HIL 보존, 공개 payload API 부재로 W02 완료 판정 취소·재작업 |
| [167 — M31-W02 설치 Arduino ISO 예제 당시 기록](167_M31_W02_설치_Arduino_ISO_예제_완료.md) | package sketch 11/11 build, CIS·BIS·암호화·negative·time·combined 실제 보드 PASS; 완료 판정은 191에서 정정 |
| [166 — M31-W02 세 보드 CIS→BIS 기능 실기](166_M31_W02_3보드_CIS_BIS_통합_실기.md) | native 세 역할 build와 20회×100 CIS 수신→BIS 전달 PASS, 설치 예제 전 단계 |
| [165 — M31-W01 완료와 W02 CIS/BIS 진행](165_M31_W01_착수와_W02_CIS_개발_후보.md) | W01 1/8 완료, CIS·BIS·time sync 개발·exact 시도와 실패 보존 |
| [164 — 사용자 후속 검증 범위와 DF IQ 인계](164_사용자_후속_검증_범위와_DF_IQ_인계.md) | 구현·자동 검증 의무와 사용자 실물 검증 분리, DF raw IQ 후보 경계, 기존 m31-w01 재개·CI/CD 생략 |
| [163 — Bluetooth 전체 기능·예제와 마일스톤 재배치](163_Bluetooth_전체_기능_예제와_마일스톤_재배치.md) | M31 8·M32 12·M33 8 작업, 전체 NCS 예제·기능 소유권, 보드 기반 자동화와 별도 Host 계약 |
| [162 — 전체 문서 정비와 M31 TODO 확정](162_전체_문서_정비와_M31_TODO.md) | 308개 Markdown 전수 감사, 현재 계약·Host 표기 교정, M31-W01~W08 TODO와 재개 순서 |
| [161 — M30-W08 실제 전원 HIL과 M30 완료](161_M30_W08_실제_전원_HIL과_M30_완료.md) | 네 지점 × 3회 실제 차단 12/12, recovery failure·invalid boot 0, M30 8/8·10/10 완료 |
| [160 — 전체 문서 검토와 마일스톤 개정](160_전체_문서_검토와_마일스톤_개정.md) | 현황 모순 교정, 과거 준비/현재 재개 조건 분리, W08 내부 gate·M33 예제·후속 ARF 배치 |
| [159 — M30-W08 전원 HIL 주입 직전 준비](159_M30_W08_전원_HIL_주입_직전_준비.md) | 세 role build·두 보드 preflight PASS, 네 지점 × 3회 계획, 실제 전원 차단 0회 |
| [158 — M30-W07 3보드 secure multi-link 완료](158_M30_W07_3보드_secure_multi_link_완료.md) | 동시 두 link·handle별 보안 연산 총 400회·cross-link/security/key-size 오류 0 |
| [157 — M30-W06 secure BLE DFU·negative·rollback 완료](157_M30_W06_secure_BLE_DFU_negative_rollback_완료.md) | 인증 BLE update 10/10·negative 5×20·invalid/rollback accept 0 |
| [156 — M30-W05 MCUboot layout·서명 완료](156_M30_W05_MCUboot_layout_signing_완료.md) | 별도 secure profile·외부 ECDSA P-256, signed boot 20/20·unsigned/wrong-key accept 0 |
| [155 — M30-W04 일곱 BLE profile 완료](155_M30_W04_7개_BLE_profile_완료.md) | BAS·DIS·HID 3종·HRS·ESS, 두 보드 서비스별 100회·오류 0 PASS |
| [152 — M30-W01 capability 실기 완료](152_M30_W01_capability_실기_완료.md) | Host parser·target build·1보드 보안/OOB/profile/DFU capability 7/7 PASS |
| [153 — M30-W02 link별 security와 IO 5종 완료](153_M30_W02_link별_security와_IO_5종_완료.md) | generation별 보안 상태·IO 5종 target 10/10·실제 pairing 50/50 PASS |
| [154 — M30-W03 유선 OOB·bond/privacy·NFC adapter 완료](154_M30_W03_유선_OOB_bond_privacy_NFC_adapter_완료.md) | 유선 OOB 20/20·bond reconnect 20/20·RPA 3·migration 1, NFC RF NOT RUN |
| [151 — M30-W01 계약과 HOST-W01~W03 기반](151_M30_W01_계약과_HOST_W01_W03_기반.md) | 유선 OOB/NFC 비검증·secure DFU 계약, Host inventory·resolver·launcher와 Windows 회귀 |
| [150 — v0.5.0 다중 Host 지원 계획 정비](150_v0.5.0_다중_Host_지원_계획_정비.md) | 당시 M30 시작·M33 완료의 세 Host 계획. 현행 릴리스 범위는 v0.5.0 TODO 참조 |
| [149 — M29-W07 3보드·회귀·상호운용과 W08 완료](149_M29_W07_3보드_회귀_상호운용과_W08_완료.md) | MULTI/REG, Windows/Intel GATT, 예제·리팩터링·M30 인계 |
| [148 — 개발문서 전수 검토와 README 개선](148_개발문서_전수검토와_README_개선.md) | 지원 범위·개발 현황 안내, 중복 설명 정리와 문서 검사 |
| [147 — M29-W07 Signed Write·EATT 2보드 완료](147_M29_W07_Signed_Write_EATT_HIL_준비.md) | exact `c71ef4a2…` SIGN/EATT PASS, MULTI/REG NOT RUN, 실패 진단부터 최종 증거까지 |
| [146 — M29-W06 LE CoC·credit](146_M29_W06_LE_CoC_credit_buffers.md) | 2-channel·512-byte·각 방향 1,000 SDU와 5 negative class PASS |
| [140 — M28-W07 2·3보드 HIL과 W08 완료](140_M28_W07_3보드_HIL과_W08_완료.md) | M28 8/8 완료·9개 test ID PASS, 시험별 보드 수·범위·증거 |
| [129 — v0.4.1 설치기 유지보수 릴리스](129_v0.4.1_설치기_유지보수_릴리스.md) | 현재 지원 배포의 공개·설치 수명주기·30/30 예제 build PASS |
| [125 — v0.4.0 정식 릴리스 공개와 T24/T25 마감](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md) | v0.4.1이 유지하는 기능 기준선의 최종 공개·설치 결과 |

</details>

## 주제별 찾아가기

| 확인할 내용 | 기록 |
| --- | --- |
| M29 GATT·cache·CoC 구현과 단일 link 실기 | [141 capability](141_M29_W01_ATT_GATT_L2CAP_capability.md) · [142 long read](142_M29_W02_link별_GATT_long_read.md) · [143 reliable write](143_M29_W03_long_reliable_write.md) · [144 descriptor](144_M29_W04_descriptor_authorization_read_multiple.md) · [145 cache](145_M29_W05_robust_GATT_cache_migration.md) · [146 CoC](146_M29_W06_LE_CoC_credit_buffers.md) |
| M29 Signed/EATT·3보드·상호운용 완료 | [147 두 보드 Signed/EATT](147_M29_W07_Signed_Write_EATT_HIL_준비.md) · [149 세 보드 MULTI/REG·Windows](149_M29_W07_3보드_회귀_상호운용과_W08_완료.md) |
| M28 보드 수와 RF 검증 범위 | [140번 시험별 결과표](140_M28_W07_3보드_HIL과_W08_완료.md) — PAwR은 2보드, periodic/PAST는 3보드 |
| QDEC20/21 지원·비보증 경계 | [124번 지원 계약](124_T22전_QDEC_지원_범위_재확정.md) |
| v0.4.0 주변장치 실기 종료·결함 해결 | [115 T13 종료](115_T13_U_UART00_완료와_T13_종료.md) · [116 T14 자원 충돌](116_T14_자원_충돌_판정과_PWM_식별_교정.md) |
| 이전 버전 공급 종료·원본 복원 | [106번 이력 보존](106_Git_이력_정리와_구버전_패키지_공급_종료.md) · [129번 v0.4.1 단독 지원](129_v0.4.1_설치기_유지보수_릴리스.md) |

## 기록 읽는 방법

- PASS는 기록에 명시된 exact source·역할·핀·속도·시간·조건에만 적용합니다.
- Host·target build·실제 HIL·설치·공개 결과를 구분합니다. 준비 결과를 실기 PASS로 세지 않습니다.
- 실패·부분 완료·시험 제외·사용자 수용은 각각 별도로 남깁니다. 후속 결과로 원본을 덮어쓰지 않습니다.
- [`evidence/`](evidence/)에는 원시 transcript, 구조화 JSON과 일부 archive manifest가 있습니다.
  해당 번호 기록에서 source·조건·결과를 먼저 읽고 증거 링크를 따라가세요. Manifest의 원본 SHA-256과
  Git 줄바꿈 정규화본의 SHA-256은 구분합니다.
- 과거 문서의 “다음 작업”은 당시 계획입니다. 현재 지시는 TODO와 최신 사용자 요청이 우선입니다.

## 전체 기록 목차

<details>
<summary>v0.4.0 실기·공개, v0.4.1 유지보수, M28·M29·M30 완료와 M31 진행 — 94~167</summary>

- [94 — T14 PWM 지연 시작 취소와 무점퍼 검증](<94_T14_PWM_지연_시작_취소와_무점퍼_검증.md>) — **PWM 미시작 STOP 문제 해결 완료**
- [95 — T12 내부 ADC·TIMER·이벤트 무점퍼 검증](<95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md>)
- [96 — 새 PC 인수 확인과 T12 PWM peer capture 첫 경로 준비](<96_새_PC_인수와_T12_PWM_peer_capture_준비.md>)
- [97 — T12 PWM peer capture 첫 240조건 검증](<97_T12_PWM_peer_capture_첫_240조건_검증.md>)
- [98 — T13 단독 안정성 3분 기준 조정](<98_T13_단독_안정성_3분_기준_조정.md>)
- [99 — 공통 결선 검사와 승인 전 자동 진행 계획](<99_공통_결선_검사와_승인_전_자동_진행_계획.md>)
- [100 — T12 공통 기능 묶음과 T13 시험 조합 확정](<100_T12_공통_기능_묶음과_T13_조합_확정.md>)
- [101 — T12 QDEC 누산 누락 원인 분리](<101_T12_QDEC_누산_누락_원인_분리.md>)
- [102 — 개발 문서 전수 검토와 v0.4.0 마일스톤 체크포인트](<102_개발_문서_전수_검토와_마일스톤_체크포인트.md>)
- [103 — TIMER 기능 완료 정리와 T13 자동 진행 경계](<103_TIMER_기능_완료와_T13_진행_경계.md>)
- [104 — T13 S 결선의 복구·동시·안정성 검증](<104_T13_S_복구_동시_안정성_검증.md>)
- [105 — T13 S GPIO 전수 결선 진단](<105_T13_S_GPIO_전수_결선_진단.md>)
- [106 — Git 이력 정리와 구버전 패키지 공급 종료](<106_Git_이력_정리와_구버전_패키지_공급_종료.md>)
- [107 — T13 S 자동 진행과 peer 제어 System OFF 검증 계획](<107_T13_S_자동_진행과_System_OFF_계획.md>)
- [108 — T13 S 자동 실행 종료와 재개 항목](<108_T13_S_자동_실행_종료와_재개_항목.md>)
- [109 — T13 S 자원 충돌 수용과 세 복구 묶음 재검증](<109_T13_S_세_복구_묶음_재검증.md>)
- [110 — 전체 문서 정리와 T13 S 잔여 재개](<110_문서_정리와_T13_S_잔여_재개.md>)
- [111 — T13 S I2S 완료와 SPIS 연속 버퍼 교정](<111_T13_S_I2S_완료와_SPIS_연속_버퍼_교정.md>)
- [112 — T13 S SPI·TWI 완료와 System OFF 원인](<112_T13_S_SPI_TWI_완료와_System_OFF_원인.md>)
- [113 — T13 S 범위 종료와 U 준비](<113_T13_S_범위_종료와_U_준비.md>)
- [114 — 전체 문서 정비와 남은 마일스톤](<114_전체_문서_정비와_남은_마일스톤.md>)
- [115 — T13 U UART00 완료와 T13 종료](<115_T13_U_UART00_완료와_T13_종료.md>) — **U 실기 완료·T13 합의 범위 종료**
- [116 — T14 자원 충돌 판정과 PWM 식별 교정](<116_T14_자원_충돌_판정과_PWM_식별_교정.md>) — **T14 완료·결함 1건 해결·미해결 0건**
- [117 — T15 지원 범위와 Physical Gate 확정](<117_T15_지원_범위와_Physical_Gate_확정.md>) — **T15 완료·M24/M25 fixture gate PASS**
- [118 — T16 Peripheral Fabric 설치 통합](<118_T16_Peripheral_Fabric_설치_통합.md>) — **T16 완료·설치 profile/예제 통합**
- [119 — T17 문서와 지원 매트릭스 정리](<119_T17_문서와_지원_매트릭스_정리.md>) — **당시 T17 완료·public 62/75·사용자 문서 확정**
- [120 — T18 stable 공개 절차와 승인 차단](<120_T18_stable_공개_절차와_승인_차단.md>) — **T18 완료·T22 승인 전 공개 차단**
- [121 — T19 RC 소스 고정과 전체 회귀](<121_T19_RC_소스_고정과_전체_회귀.md>) — **R14·T19 완료·35/35 target·RC 이중 재현 PASS**
- [122 — T20 RC 설치 수명주기와 실제 Upload](<122_T20_RC_설치_수명주기와_실제_Upload.md>) — **T20 완료·설치본 30/30·Upload·수명주기 PASS**
- [123 — T21 stable 패키지와 최종 검사](<123_T21_stable_패키지와_최종_검사.md>) — **T21 완료·stable 30/30·Upload·RC/runtime 동등성 PASS**
- [124 — T22 전 QDEC20/21 지원 범위 재확정](<124_T22전_QDEC_지원_범위_재확정.md>) — **QDEC 지원 계약·T19~T21 영향 재검증 PASS**
- [125 — v0.4.0 정식 릴리스 공개와 T24/T25 마감](<125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>) — **T22~T25 완료·정식 공개·공개 URL 수명주기 PASS**
- [126 — 정식 공개 후 문서 전수 정비](<126_정식_공개_후_문서_전수_정비.md>) — 문서 검토·가독성 개선·현행/역사 구분
- [127 — 후속 마일스톤 지원 경계와 착수 계획 정비](<127_후속_마일스톤_지원_경계와_착수_계획_정비.md>) — 지원성 판정·선행 작업·v0.5.0 착수 체크
- [128 — Nordic 설치 복구 검증 로그 교정](<128_Nordic_설치_복구_검증_로그_교정.md>) — 복구 안내·최종 실패 구분과 단계별 진단 로그
- [129 — v0.4.1 설치기 유지보수 릴리스](<129_v0.4.1_설치기_유지보수_릴리스.md>) — **v0.4.1 공개·설치·30/30 예제 build PASS**
- [130 — 개발문서 전수 감사와 M28 착수 준비](<130_개발문서_전수감사와_M28_착수_준비.md>) — 현행 문서 교정·정적 capability 원장·착수 계약
- [131 — M28-W01 Capability image와 Host·target 준비](<131_M28_W01_Capability_image와_Host_target_준비.md>) — **고정 protocol·Host parser·target 1/1 PASS, 당시 실제 HCI NOT RUN**
- [132 — M28-W01 실제 HCI capability 완료](<132_M28_W01_실제_HCI_capability_완료.md>) — **exact target 1/1·실제 HCI 6/6 PASS, W01 완료**
- [133 — M28-W01 CI container revision 교정](<133_M28_W01_CI_container_revision_교정.md>) — **Linux Git 소유권 수정·3보드 실기 직전 정지 경계**
- [134 — M28-W02 고정 2-slot·generation link 기반](<134_M28_W02_2-slot_generation_link_기반.md>) — **Host·target 2-slot/generation PASS, W02 완료**
- [135 — M28-W03 확장 광고와 스캔](<135_M28_W03_확장_광고와_스캔.md>) — **Host·target 확장 GAP PASS, W03 완료**
- [136 — M28-W04 periodic sync·PAST](<136_M28_W04_periodic_sync_PAST.md>) — **Host·target periodic/PAST PASS, W04 완료**
- [137 — M28-W05 PAwR advertiser·scanner](<137_M28_W05_PAwR_advertiser_scanner.md>) — **Host·target PAwR PASS, W05 완료**
- [138 — M28-W06 privacy·RPA·link control](<138_M28_W06_privacy_RPA_link_control.md>) — **Host·target privacy/control PASS, W06 완료**
- [139 — M28-W07 2보드 HIL 자동화 준비](<139_M28_W07_2보드_HIL_자동화_준비.md>) — **Host parser 10/10·target 2/2 PASS, 실제 HIL NOT RUN**
- [140 — M28-W07 2·3보드 HIL과 W08 완료](<140_M28_W07_3보드_HIL과_W08_완료.md>) — **9개 test ID·M28 8/8 PASS, LINK 재연결 진단·수정·M29 인계**
- [141 — M29-W01 ATT/GATT·L2CAP capability](<141_M29_W01_ATT_GATT_L2CAP_capability.md>) — **M29-CAP-01·W01 완료, M29 1/8**
- [142 — M29-W02 link별 GATT client와 long read](<142_M29_W02_link별_GATT_long_read.md>) — **Host·target·2보드 512-byte read PASS, M29 2/8**
- [143 — M29-W03 long/reliable write](<143_M29_W03_long_reliable_write.md>) — **Host·target·2보드 512-byte write/read-back PASS, M29 3/8**
- [144 — M29-W04 descriptor·authorization·read multiple](<144_M29_W04_descriptor_authorization_read_multiple.md>) — **Host·target·2보드 descriptor 4개와 read multiple PASS, M29 4/8**
- [145 — M29-W05 robust GATT cache](<145_M29_W05_robust_GATT_cache_migration.md>) — **Host·target·2보드 cache migration PASS, M29 5/8**
- [146 — M29-W06 LE CoC·credit](<146_M29_W06_LE_CoC_credit_buffers.md>) — **Host·target·2보드 COC/NEG PASS, M29 6/8**
- [147 — M29-W07 Signed Write·EATT HIL 준비와 2보드 완료](<147_M29_W07_Signed_Write_EATT_HIL_준비.md>) — **Host/parser·target과 실제 SIGN/EATT PASS, MULTI/REG NOT RUN**
- [148 — 개발문서 전수 검토와 README 개선](<148_개발문서_전수검토와_README_개선.md>) — 지원 배포·개발 상태 구분, 문서 가독성과 탐색 경로 정비
- [149 — M29-W07 3보드·회귀·Windows 상호운용과 W08 완료](<149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>) — **M29 8/8·test ID 10/10 PASS, M30 인계**
- [150 — v0.5.0 다중 Host 지원 계획 정비](<150_v0.5.0_다중_Host_지원_계획_정비.md>) — **M30 시작·M33 완료의 세 Host 구현·검증 계약**
- [151 — M30-W01 계약과 HOST-W01~W03 기반](<151_M30_W01_계약과_HOST_W01_W03_기반.md>) — **유선 OOB·NFC 비검증·secure DFU·Host 공통 기반 계약**
- [152 — M30-W01 capability 실기 완료](<152_M30_W01_capability_실기_완료.md>) — **parser 13/13·target 1/1·실제 capability 7/7 PASS, M30 1/8**
- [153 — M30-W02 link별 security와 IO 5종 완료](<153_M30_W02_link별_security와_IO_5종_완료.md>) — **target 10/10·실제 pairing 50/50 PASS, M30 2/8**
- [154 — M30-W03 유선 OOB·bond/privacy·NFC adapter 완료](<154_M30_W03_유선_OOB_bond_privacy_NFC_adapter_완료.md>) — **OOB·BOND 실기 PASS, NFC RF NOT RUN, M30 3/8**
- [155 — M30-W04 일곱 BLE profile 완료](<155_M30_W04_7개_BLE_profile_완료.md>) — **catalog 7/7·서비스별 100회·오류 0, M30 4/8**
- [156 — M30-W05 MCUboot layout·서명 완료](<156_M30_W05_MCUboot_layout_signing_완료.md>) — **signed boot 20/20·unsigned/wrong-key accept 0, M30 5/8**
- [157 — M30-W06 secure BLE DFU·negative·rollback 완료](<157_M30_W06_secure_BLE_DFU_negative_rollback_완료.md>) — **update 10/10·negative 5×20·invalid/rollback accept 0, M30 6/8**
- [158 — M30-W07 3보드 secure multi-link 완료](<158_M30_W07_3보드_secure_multi_link_완료.md>) — **동시 2-link·handle별 보안 연산 총 400회·오류 0, M30 7/8**
- [159 — M30-W08 전원 HIL 주입 직전 준비](<159_M30_W08_전원_HIL_주입_직전_준비.md>) — **세 role build·두 보드 preflight PASS, 실제 전원 차단 0회, M30 7/8 유지**
- [160 — 전체 문서 검토와 마일스톤 개정](<160_전체_문서_검토와_마일스톤_개정.md>) — **현황 모순 교정과 W08·M33·후속 ARF 배치 확정**
- [161 — M30-W08 실제 전원 HIL과 M30 완료](<161_M30_W08_실제_전원_HIL과_M30_완료.md>) — **네 지점 × 3회 실제 차단 12/12 PASS, M30 8/8·10/10 완료**
- [162 — 전체 문서 정비와 M31 TODO 확정](<162_전체_문서_정비와_M31_TODO.md>) — **308개 Markdown 전수 감사·Host 표기 교정·M31 재개 순서 확정**
- [163 — Bluetooth 전체 기능·예제와 마일스톤 재배치](<163_Bluetooth_전체_기능_예제와_마일스톤_재배치.md>) — **M31 8·M32 12·M33 8 작업·기능별 예제·보드 기반 자동화 계약**
- [164 — 사용자 후속 검증 범위와 DF IQ 인계](<164_사용자_후속_검증_범위와_DF_IQ_인계.md>) — **실물 검증 책임·비차단/최종 Host gate·raw IQ 후보 경계·다른 PC 재개**
- [165 — M31-W01 완료와 W02 CIS/BIS 진행](<165_M31_W01_착수와_W02_CIS_개발_후보.md>) — **W01 완료, CIS·BIS·time sync 단계별 exact와 실패 원본 보존**
- [166 — M31-W02 세 보드 CIS→BIS 기능 실기](<166_M31_W02_3보드_CIS_BIS_통합_실기.md>) — **20회×100 CIS→BIS 2,000/2,000 PASS, 설치 예제 잔여**
- [167 — M31-W02 설치 Arduino ISO 예제 당시 기록](<167_M31_W02_설치_Arduino_ISO_예제_완료.md>) — **설치 sketch 11/11 build·7개 실제 보드 case PASS; 191에서 W02 완료 판정 정정**
- [191 — M31-W02 공개 ISO 예제 재점검](<191_M31_W02_공개_ISO_예제_재점검.md>) — **사용자 payload API 없는 11개 예제 재작업, M31 1/8**

</details>

<details>
<summary>M31 작업 기록 — 168~214</summary>

작성 시점의 진행·FAIL·HOLD는 그대로 보존합니다. W02의 최종 판정은 199번, W03의 최종 판정은
214번이 소유하며 W04·W05의 부분 결과를 전체 완료로 승격하지 않습니다.

- [168 — W03 LC3 공개 API 실기 진행](<168_M31_W03_LC3_공개_API_실기_진행.md>)
- [169 — W03 NCS Audio sample NU54DK build](<169_M31_W03_NCS_Audio_샘플_NU54DK_빌드.md>)
- [170 — W04 DF CTE 송신 진행](<170_M31_W04_DF_CTE_송신_진행.md>)
- [171 — W05 CS native 두 보드 착수](<171_M31_W05_CS_native_2보드_착수.md>)
- [172 — W04 기본 안테나 IQ 수신 진단](<172_M31_W04_DF_기본안테나_IQ_수신_진단.md>) — **기능 HIL FAIL·미완료 보존**
- [173 — W05 RAS native 100회 진단](<173_M31_W05_RAS_native_100회_진단.md>)
- [174 — W04 연결 CTE 응답 실기](<174_M31_W04_연결_CTE_응답_실기.md>)
- [175 — W05 Arduino RAS reflector 100회 진단](<175_M31_W05_Arduino_RAS_reflector_100회_진단.md>)
- [176 — W05 Arduino RAS initiator 100회와 재시작 진단](<176_M31_W05_Arduino_RAS_initiator_100회와_재시작_진단.md>)
- [177 — W05 RAS 재연결과 세 보드 peer 분리 진단](<177_M31_W05_RAS_재연결과_3보드_peer_분리_진단.md>)
- [178 — W04 연결 AoA 수신 Host/controller 경계](<178_M31_W04_연결_AoA_수신_Host_Controller_경계.md>) — **IQ report 0건·미완료 보존**
- [179 — W05 RAS UUID 위장 peer 거부 20회](<179_M31_W05_RAS_UUID_위장_peer_거부_20회.md>)
- [180 — W05 미암호화 RAS Features 읽기 거부 20회](<180_M31_W05_미암호화_RAS_Features_읽기_거부_20회.md>)
- [181 — W03 native BAP LC3 실제 무선 전송](<181_M31_W03_native_BAP_LC3_실제_무선_전송.md>)
- [182 — W03 Arduino BAP unicast LC3 sink 실기](<182_M31_W03_Arduino_BAP_unicast_LC3_sink_실기.md>)
- [183 — W03 Arduino BAP unicast LC3 두 역할 실기](<183_M31_W03_Arduino_BAP_unicast_LC3_두_역할_실기.md>)
- [184 — W03 Arduino BAP unicast 재시작 복구 20회](<184_M31_W03_Arduino_BAP_unicast_재시작_복구_20회.md>)
- [185 — W03 Arduino BAP stop/release 20회](<185_M31_W03_Arduino_BAP_stop_release_20회.md>)
- [186 — W03 Arduino BAP 잘못된 상태 거부 40회](<186_M31_W03_Arduino_BAP_잘못된_상태_거부_40회.md>)
- [187 — W03 Arduino BAP 원격 codec·QoS 거부 각 20회](<187_M31_W03_Arduino_BAP_원격_codec_QoS_거부_각_20회.md>)
- [188 — W03 Arduino BAP 원격 잘못된 ASE 상태 거부 20회](<188_M31_W03_Arduino_BAP_원격_잘못된_ASE_상태_거부_20회.md>)
- [189 — W03 Arduino BAP 양방향 서버 실기](<189_M31_W03_Arduino_BAP_양방향_서버_실기.md>)
- [190 — W03 Arduino BAP 양방향 클라이언트와 회귀](<190_M31_W03_Arduino_BAP_양방향_클라이언트_및_회귀.md>)
- [191 — W02 공개 ISO 예제 재점검](<191_M31_W02_공개_ISO_예제_재점검.md>) — **당시 완료 판정 취소·재작업 시작**
- [192 — W02 공개 CIS 사용자 SDU 실기](<192_M31_W02_공개_CIS_사용자_SDU_실기.md>)
- [193 — W02 공개 BIS 사용자 SDU 실기](<193_M31_W02_공개_BIS_사용자_SDU_실기.md>)
- [194 — W02 공개 암호화 BIS 사용자 SDU 실기](<194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md>)
- [195 — W02 공개 BIS 시각 동기 사용자 SDU 실기](<195_M31_W02_공개_BIS_시각동기_사용자_SDU_실기.md>)
- [196 — W02 공개 CIS·BIS 세 보드 사용자 SDU 실기](<196_M31_W02_공개_CIS_BIS_세_보드_사용자_SDU_실기.md>)
- [197 — W02 공개 API 암호화 BIS 오류 후 복구](<197_M31_W02_공개_API_암호화_BIS_오류_후_복구.md>)
- [198 — W02 공개 BIS sync loss 재시작 복구](<198_M31_W02_공개_BIS_sync_loss_재시작_복구.md>)
- [199 — W02 격리 설치본 ISO 11예제 완료](<199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) — **W02 최종 완료**
- [200 — M31 다른 PC 작업 인계](<200_M31_다른_PC_작업_인계.md>) — **작성 당시 snapshot**
- [201 — W03 Arduino BAP broadcast 비암호화와 재가입](<201_M31_W03_Arduino_BAP_broadcast_비암호화와_재가입.md>)
- [202 — W03 Arduino BAP broadcast 암호화와 negative 완료](<202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>)
- [203 — W03 Arduino BASS 세 역할과 복구](<203_M31_W03_Arduino_BASS_3역할과_복구.md>)
- [204 — W03 Arduino CAP 세 역할과 broadcast 복구](<204_M31_W03_Arduino_CAP_3역할과_broadcast_복구.md>)
- [205 — W03 Arduino CAP unicast 반복 실기](<205_M31_W03_Arduino_CAP_unicast_반복_실기.md>)
- [208 — W03 Arduino Audio Control 완료](<208_M31_W03_Arduino_Audio_Control_완료.md>)
- [209 — W03 Arduino CSIP 완료](<209_M31_W03_Arduino_CSIP_완료.md>)
- [210 — W03 Arduino PBP 완료](<210_M31_W03_Arduino_PBP_완료.md>)
- [211 — W03 Arduino Media·Call Control 완료](<211_M31_W03_Arduino_Media_Call_Control_완료.md>)
- [212 — W03 Arduino TMAP·GMAP 완료](<212_M31_W03_Arduino_TMAP_GMAP_완료.md>)
- [213 — W03 Arduino HAP·HAS 완료](<213_M31_W03_Arduino_HAP_HAS_완료.md>)
- [214 — W03 LE Audio profile 완료](<214_M31_W03_LE_Audio_Profile_완료.md>) — **W03-01~11 11/11 PASS·M31 3/8**

</details>

<details>
<summary>v0.4.0 기능 회귀 — 67~93</summary>

- [67 — T11 Fixture 101 current-source UART 회귀](<67_T11_Fixture_101_current_source_UART_회귀.md>)
- [68 — T11 Fixture 102 current-source UART 회귀](<68_T11_Fixture_102_current_source_UART_회귀.md>)
- [69 — T11 Fixture 103 current-source UART 회귀](<69_T11_Fixture_103_current_source_UART_회귀.md>)
- [70 — T11 Fixture 201 current-source SPI 회귀](<70_T11_Fixture_201_current_source_SPI_회귀.md>)
- [71 — T11 Fixture 202 current-source SPI 회귀](<71_T11_Fixture_202_current_source_SPI_회귀.md>)
- [72 — T11 Fixture 203 current-source SPI 회귀](<72_T11_Fixture_203_current_source_SPI_회귀.md>)
- [73 — T11 Fixture 301 current-source TWI 회귀와 통신 단독 검증 완료](<73_T11_Fixture_301_current_source_TWI_회귀.md>)
- [74 — T12 Fixture 401 current-source PWM→AIN0 실기 검증](<74_T12_Fixture_401_current_source_PWM_ADC_검증.md>)
- [75 — T12 Fixture 402 current-source PWM→AIN1 실기 검증](<75_T12_Fixture_402_current_source_PWM_ADC_검증.md>)
- [76 — T12 Fixture 403 current-source PWM→AIN2 실기 검증](<76_T12_Fixture_403_current_source_PWM_ADC_검증.md>)
- [77 — T12 Fixture 404 current-source PWM→AIN3 실기 검증](<77_T12_Fixture_404_current_source_PWM_ADC_검증.md>)
- [78 — T12 Fixture 405 — 공유 AIN4 오픈드레인 실기 검증](<78_T12_Fixture_405_current_source_공유_AIN4_검증.md>)
- [79 — T12 Fixture 406 — current-source 공유 AIN5 검증](<79_T12_Fixture_406_current_source_공유_AIN5_검증.md>)
- [80 — T12 Fixture 407 준비와 Host 실행 차단](<80_T12_Fixture_407_준비와_Host_실행_차단.md>)
- [81 — T12 Fixture 407 — Host 재개와 software 검증](<81_T12_Fixture_407_Host_재개와_검증.md>)
- [82 — T12 Fixture 407 — current-source 공유 AIN6 검증](<82_T12_Fixture_407_current_source_공유_AIN6_검증.md>)
- [83 — T12 Fixture 408 — current-source PWM→AIN7 검증](<83_T12_Fixture_408_current_source_PWM_ADC_검증.md>)
- [84 — T12 Fixture 420 — QDEC 기능 검증과 준비 취소 교정](<84_T12_Fixture_420_current_source_QDEC_검증.md>)
- [85 — T12 Fixture 420 — QDEC 수정본 재검증 완료](<85_T12_Fixture_420_current_source_QDEC_재검증.md>)
- [86 — T12 Fixture 430 — I2S 짧은 버퍼 실패 이력](<86_T12_Fixture_430_current_source_I2S_검증.md>) — **후속 해결 완료(87번)**
- [87 — T12 Fixture 430 — DMA 자원 처리 지연 교정과 I2S 전체 PASS](<87_T12_Fixture_430_current_source_I2S_재검증.md>) — **해결 완료**
- [88 — T12 Fixture 440 — PDM DMA·스테레오 진단 이력](<88_T12_Fixture_440_current_source_PDM_검증.md>) — **후속 해결 완료(91~92번)**
- [89 — T10/T12 Fixture 440 — clock·gate 네 핀의 전기적 연결 관측](<89_T12_Fixture_440_clock_gate_분리_진단.md>)
- [90 — T10/T12 Fixture 440 — 재결선과 PDM 위상 진단](<90_T12_Fixture_440_재결선과_PDM_위상_진단.md>)
- [91 — T12 Fixture 440 — PDM 밀도와 연속 DMA 검증](<91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md>) — **위상·gate 준비 문제 해결 완료**
- [92 — T12 Fixture 440 — PDM 연속 전체 검증](<92_T12_Fixture_440_PDM_연속_전체_검증.md>) — **연속 검증 완료(96/96)**
- [93 — Host 재검증과 T12 이후 남은 작업](<93_Host_재검증과_T12_이후_남은_작업.md>)

</details>

<details>
<summary>v0.4.0 구현·리팩토링 — 33~66</summary>

- [33 — M23 Peripheral inventory와 공통 소유권 기준선](<33_M23_Peripheral_Inventory와_공통_소유권_기준선.md>)
- [34 — M24 Serial Fabric 경로와 API 계약 기준선](<34_M24_Serial_Fabric_경로와_API_계약_기준선.md>)
- [35 — M24 Serial Fabric 공통 backend 기준선](<35_M24_Serial_Fabric_공통_backend_기준선.md>)
- [36 — M24 Serial Fabric adapter와 온보드 HIL 준비 기록](<36_M24_Serial_Fabric_adapter와_온보드_HIL_준비.md>)
- [37 — M25 Analog·Event·Stream Fabric과 온보드 HIL 준비 기록](<37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>)
- [38 — M26 System Peripheral 판정과 온보드 HIL 준비 기록](<38_M26_System_Peripheral_판정과_온보드_HIL_준비.md>)
- [39 — M27 v0.4.0-rc.1 자동 준비와 HOLD 기록](<39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)
- [40 — M24~M26 온보드 재개와 USB·UART 진단](<40_M24_M26_온보드_재개와_USB_UART_진단.md>)
- [41 — M24~M26 온보드 protocol 교정과 실기 재검증](<41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)
- [42 — v0.4.0 코어 기능 검증 범위 합의](<42_v0.4.0_코어_기능_검증_범위_합의.md>)
- [43 — v0.4.0 T01~T09 시험 준비와 구현 대조](<43_v0.4.0_시험_준비와_구현_대조.md>)
- [44 — M24 Fixture 101 UART 실기 검증](<44_M24_Fixture_101_UART_실기_검증.md>)
- [45 — M24 Fixture 102 UART 실기 검증](<45_M24_Fixture_102_UART_실기_검증.md>)
- [46 — M24 Fixture 103 UART 실기 검증](<46_M24_Fixture_103_UART_실기_검증.md>)
- [47 — M24 Fixture 201 SPI 실기 검증](<47_M24_Fixture_201_SPI_실기_검증.md>)
- [48 — M24 Fixture 202 SPI 실기 검증](<48_M24_Fixture_202_SPI_실기_검증.md>)
- [49 — M24 Fixture 203 SPI 실기 검증](<49_M24_Fixture_203_SPI_실기_검증.md>)
- [50 — M24 Fixture 301 TWI 실기 검증](<50_M24_Fixture_301_TWI_실기_검증.md>)
- [51 — R00 — 리팩토링 기준선과 characterization 계약](<51_R00_리팩토링_기준선.md>)
- [52 — R01 — Serial adapter의 Core target 소속 교정](<52_R01_CMake_source_소속_교정.md>)
- [53 — R02 — Serial 완료·timeout·DMA 수명주기](<53_R02_Serial_완료와_DMA_수명주기.md>)
- [54 — R03 — Analog/Stream ISR·정지 동기화](<54_R03_Analog_Stream_ISR_정지_동기화.md>)
- [55 — R04 — LittleFS File 공유 slot 수명주기](<55_R04_File_공유_slot_수명주기.md>)
- [56 — R05 — Core 소스와 패키지 identity](<56_R05_Core_소스와_패키지_identity.md>)
- [57 — R06 — builder 모듈과 설치 경로](<57_R06_builder_모듈과_설치_경로.md>)
- [58 — R07 — EventFabric 책임 분할](<58_R07_EventFabric_책임_분할.md>)
- [59 — R08 자원 관리자와 runtime route 책임 분리](<59_R08_자원과_경로_수명주기.md>)
- [60 — R09 Arduino SPI facade/backend 경계](<60_R09_Arduino_SPI_경계.md>)
- [61 — R10 Serial Fabric 동시 호출과 orchestration 분리](<61_R10_Serial_Fabric_동시_호출.md>)
- [62 — R11 Analog/Stream peripheral 분리](<62_R11_Analog_Stream_peripheral_분리.md>)
- [63 — R12 BLE·Storage 수명주기 구조 확대](<63_R12_BLE_Storage_수명주기.md>)
- [64 — R13 도구·정책·build 구조와 최종 software 입력](<64_R13_도구_정책_build_구조.md>)
- [65 — R13 후속 USB 무배선 실기와 작업 파일 정리](<65_R13_후속_USB_무배선_실기와_정리.md>)
- [66 — T09 UART 유휴 bias 교정과 BLE 무배선 회귀](<66_T09_UART_유휴_bias와_BLE_회귀.md>)

</details>

<details>
<summary>v0.1.0~v0.3.0 역사 기록 — 1~32</summary>

- [01 — M1 도구 환경과 NU54DK 보드 실기 기준선](<01_M1_도구와_보드_기준선.md>)
- [02 — M2 Zephyr module과 Arduino runtime 기준선](<02_M2_Zephyr_Module과_Runtime_기준선.md>)
- [03 — M3 GPIO, 시간과 Scheduler 기준선](<03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [04 — M4 ArduinoCore-API 계약 기준선](<04_M4_ArduinoCore_API_계약_기준선.md>)
- [05 — M5 Arduino CLI Build Adapter 기준선](<05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [06 — M6 기본 Arduino API, Serial과 인터럽트 기준선](<06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [07 — M7 Wire·SPI·ADC·PWM 기준선](<07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [08 — M8 업로드와 디버그 기준선](<08_M8_업로드와_디버그_기준선.md>)
- [09 — M9 증분 빌드, 캐시와 재현성 기준선](<09_M9_증분_빌드_캐시와_재현성_기준선.md>)
- [10 — M10 Boards Manager 패키징과 Clean Windows 기준선](<10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>)
- [11 — M11 v0.1.0-rc.1 릴리스 후보 기준선](<11_M11_v0.1.0_rc1_릴리스_후보_기준선.md>)
- [12 — M11 v0.1.0-rc.2 공개 후 수동 검증 기록](<12_M11_v0.1.0_rc2_공개_후_수동_검증.md>)
- [13 — v0.1.0 정식 릴리스 공개 기록](<13_v0.1.0_정식_릴리스_공개_기록.md>)
- [14 — M12 CI/CD와 재현 빌드 기준선](<14_M12_CI_CD_기준선.md>)
- [15 — M13 구성 프로필 및 예제 배포 검증](<15_M13_구성_프로필_검증.md>)
- [16 — M14 Core API와 Variant 기준선](<16_M14_Core_API와_Variant_기준선.md>)
- [17 — M15 NU54DK Board/System 기준선](<17_M15_NU54DK_Board_System_기준선.md>)
- [18 — M16 BLE NUS 기준선](<18_M16_BLE_NUS_기준선.md>)
- [19 — M17 NCS 기능과 예제 Coverage 기준선](<19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [20 — M18 v0.2.0 RC1·RC2 공개 검증 기록](<20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- [21 — v0.2.0 정식 릴리스 공개 기록](<21_v0.2.0_정식_릴리스_공개_기록.md>)
- [22 — AC-01 connector GPIO와 Arduino 호환 API 검증](<22_AC-01_GPIO_호환성_검증.md>)
- [23 — M19 BLE Core/GAP 검증](<23_M19_BLE_Core_GAP_검증.md>)
- [24 — M20 범용 GATT server/client 검증](<24_M20_범용_GATT_검증.md>)
- [25 — M21 BLE 보안과 표준 Profile 검증](<25_M21_BLE_보안과_표준_Profile_검증.md>)
- [26 — AC-02A 핀과 주변장치 소유권 기준선](<26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [27 — AC-02B Peripheral/Analog runtime 기준선](<27_AC-02B_Peripheral_Analog_runtime_기준선.md>)
- [28 — AC-03 Storage와 Library 호환성 기준선](<28_AC-03_Storage와_Library_호환성_기준선.md>)
- [29 — M22 v0.3.0-rc.1 통합 릴리스 기준선](<29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)
- [30 — M22 v0.3.0-rc.2 통합 릴리스 기준선](<30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)
- [31 — M22 v0.3.0-rc.3 검증과 v0.3.0 stable 인계 기록](<31_M22_v0.3.0_rc3_검증과_stable_인계.md>)
- [32 — M22 v0.3.0 정식 릴리스 공개 기록](<32_M22_v0.3.0_정식_릴리스_공개_기록.md>)

</details>
