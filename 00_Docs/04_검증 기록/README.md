# 검증 기록

시험 당시의 source·환경·조건·결과와 원본 증거를 찾는 색인입니다. **정식 지원은 v0.4.1,
공개 후보는 v0.5.0-rc.1**이며 M28~M31과 메모리 최적화 P0~P2를 완료했습니다.
현재 작업과 후속 범위는 [HANDOFF](../HANDOFF.md)와 [v0.5.0 TODO](../TODO_v0.5.0.md)가 관리합니다.

과거 기록의 진행률·HOLD·다음 작업은 작성 당시 상태입니다. 아래 최종 기록부터 읽고,
필요한 경우 번호별 원본과 [evidence](evidence/)로 내려가세요.

<a id="최근-완료재개-기록"></a>

## 최종 결과부터 확인하기

| 확인할 내용 | 최종 근거 |
| --- | --- |
| RC 브랜치 이력 정리·문서 전수 정비 | [269번](269_공개_RC_이력_Squash와_문서_전수_정비.md) |
| 정식 지원 v0.4.1 · 설치 예제 30개 | [129번](<129_v0.4.1_설치기_유지보수_릴리스.md>) · [지원 문서](<../05_릴리스/v0.4.1/README.md>) |
| 공개 v0.5.0-rc.1 · 다운로드·설치 smoke | [268번](<268_v0.5.0-rc.1_공개와_다운로드_smoke.md>) · [RC 설치 안내](<../05_릴리스/v0.5.0-rc.1/README.md>) |
| M31-W08 · Windows RC 준비 · M31 8/8 | [267번](<267_M31_W08_Windows_RC_준비와_M31_완료.md>) — 설치 예제 113/113, 수명주기·대표 upload/UART/debug |
| M31-W07 · 설치 예제·3보드 역할 HIL | [266번](<266_M31_W07_설치_예제와_3보드_역할_HIL_완료.md>) — 설치 예제 49/49, 공개 예제 감사 113개, 역할 43개 |
| M31-W06 · 자원·수명주기·영향 회귀 | [265번](<265_M31_W06_자원_수명주기와_영향_회귀_완료.md>) — 독립 image와 M19~M30 회귀; 당시 debug protection HOLD 원본 보존 |
| M31-W05 · Channel Sounding | [264번](<264_M31_W05_Channel_Sounding_완료.md>) — secure RAS·256-step·peer-loss 복구·negative |
| M31-W04 · Direction Finding | [263번](<263_M31_W04_Direction_Finding_완료.md>) — 지원 CTE 송신·별도 LL 연결 응답과 제품 SDC IQ RX/AoD 미지원 |
| 메모리 최적화 P0·P1·P2 | [222번](<222_M31_메모리_최적화_P0_완료.md>) · [237번](<237_M31_메모리_최적화_P1_정적_저장소_완료.md>) · [262번](<262_M31_메모리_최적화_P2_세_축_완료.md>) — 오류·최악 부하, 최종 크기 유지, 동등 native 비교 |
| M31-W02 ISO · W03 LE Audio | [199번](<199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) · [214번](<214_M31_W03_LE_Audio_Profile_완료.md>) — ISO 11개 예제, Audio 11/11 |
| M28 · M29 · M30 | [140번](<140_M28_W07_3보드_HIL과_W08_완료.md>) · [149번](<149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>) · [161번](<161_M30_W08_실제_전원_HIL과_M30_완료.md>) — 각 W01~W08 완료 |
| v0.4.0 기능 기준선·QDEC 지원 경계 | [124번](<124_T22전_QDEC_지원_범위_재확정.md>) · [125번](<125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>) |

공개 RC는 Windows 10/11 x64 후보입니다. 정식 v0.5.0 stable 승격은 별도 후속입니다.
M32·M33은 미착수이며 HOST-W04~W08은 사용자 보류 상태입니다. 개발 결과를 v0.4.1 ZIP의
기능으로 해석하지 않습니다.

## 기록 읽는 방법

- PASS는 명시한 source·image·역할·입력·시간에만 적용합니다. Host/mock/build와 물리 HIL,
  비공개 package 준비와 실제 공개 다운로드 결과를 구분합니다.
- FAIL·HOLD·NOT RUN·UNSUPPORTED와 후속 수정·재검증을 함께 보존합니다.
  후속 성공이 과거 실패 원본을 대체하지 않습니다.
- 원시 transcript·JSON·archive manifest는 해당 번호 문서의 링크로 찾습니다.
  원본 SHA-256과 Git 줄바꿈 정규화본 SHA-256을 구분합니다.
- 당시 “다음 작업”을 자동 재개하지 않습니다. 최신 사용자 요청과 현행 TODO를 우선합니다.
- 파일 번호와 경로는 인용·증거 추적을 위해 유지합니다. 목차의 접힌 구간은 보관 범위이지
  삭제 목록이 아닙니다.

## P2 기록의 현행 판정 경계

P2의 세 기술 축은 [262번](<262_M31_메모리_최적화_P2_세_축_완료.md>)에서 완료했습니다. 이전 기록의 당시 미완료 조건을
현재 gate로 다시 적용하지 않습니다.

| 경계 | 적용 기준과 원본 |
| --- | --- |
| 고정 SDK/controller | NCS v3.4.0·제품 SDC 유지. nRF54L15 제품 IQ RX·AoD는 UNSUPPORTED. LL 연결형 성공·connectionless fault는 내부 진단 이력. [259번](<259_M31_P2_DF_고정_SDK_지원_경계.md>) |
| CS counter gap | 간헐 RF/controller loss·gap은 observe_only. 유효 raw·step·목표 수·양측 STOP·fault·중복/역행 검사는 유지. [260번](<260_M31_P2_CS_누락_분류와_256_step_장시간.md>) |
| Pool·stack·heap | SDC 역할/count 요구량·8-byte 정렬 준수. 내부 high-water API 부재는 추가 gate가 아니며 축소 근거가 없으면 크기 유지. [248번](<248_M31_P2_SDC_pool_정적_경계_감사.md>) · [262번](<262_M31_메모리_최적화_P2_세_축_완료.md>) |
| CoC credit | 로컬 net_buf 포화([257번](<257_M31_P2_CoC_송신_버퍼_부하와_복구.md>))와 상대 credit 직접 고갈·복구([262번](<262_M31_메모리_최적화_P2_세_축_완료.md>))는 다른 시험 |
| Native 비교 | [250번](<250_M31_P2_native_CS_비교와_DF_재진단.md>)의 RAS 진단은 설정이 다른 비교. 동등 조건 CoC·암호화 Audio FLASH/RAM 비용 판정은 [262번](<262_M31_메모리_최적화_P2_세_축_완료.md>) |

## 주제별 찾아가기

| 주제 | 시작점 |
| --- | --- |
| 메모리 설계·측정·최종 판단 | [통합 설계](<../01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>) · [219번](<219_M31_W06_메모리_점유_감사와_최적화_계약.md>) · [262번](<262_M31_메모리_최적화_P2_세_축_완료.md>) |
| GATT·cache·CoC · Signed Write/EATT | [141번](<141_M29_W01_ATT_GATT_L2CAP_capability.md>)~[149번](<149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>); 최종 범위는 [149번](<149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>) |
| T13 정상·오류 복구·UART00 종료 | [113번](<113_T13_S_범위_종료와_U_준비.md>) · [115번](<115_T13_U_UART00_완료와_T13_종료.md>) · [116번](<116_T14_자원_충돌_판정과_PWM_식별_교정.md>) |
| 공개 이력·원본 복원 | [106번](<106_Git_이력_정리와_구버전_패키지_공급_종료.md>) · [215번](<215_M31_W03_이력과_문서_정비.md>) · [221번](<221_main_마일스톤별_이력_정리.md>) |
| 문서 전수 감사 | [문서 관리 원장](../document-review.json) |
| 최신 재개 지점 | [HANDOFF](../HANDOFF.md) · [M31 TODO](../TODO_M31.md) |

## 전체 기록 목차

번호순으로 모든 기록을 포함합니다. 206·207번 파일은 현재 저장소에 없으며,
기존 번호를 다시 매기지 않습니다.

<details>
<summary>P2 실측·최종 기능 완료·RC 공개·문서 정비 — 238~269</summary>

- [238 — — M31 메모리 최적화 P2: GATT 512 B 실기와 adaptive 정정](<238_M31_메모리_최적화_P2_GATT_실기와_Adaptive_정정.md>)
- [239 — — M31 메모리 최적화 P2: CoC PASS, CS 당시 연속성 HOLD 기록](<239_M31_메모리_최적화_P2_CoC_CS_계측.md>)
- [240 — — M31 메모리 최적화 P2: CIS·BIS 100 SDU × 20세션 실기 계측](<240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md>)
- [241 — — M31 메모리 최적화 P2: LE Audio unicast LC3 실기 계측](<241_M31_메모리_최적화_P2_Audio_unicast_실기_계측.md>)
- [242 — — M31 메모리 최적화 P2: AoA CTE beacon TX 계측](<242_M31_메모리_최적화_P2_DF_beacon_TX_계측.md>)
- [243 — — M31 메모리 최적화 P2: 암호화 Audio broadcast 실기 계측](<243_M31_메모리_최적화_P2_Audio_broadcast_실기_계측.md>)
- [244 — — M31 P2 연결형 DF IQ 수신 내부 진단](<244_M31_P2_DF_연결_IQ_진단.md>)
- [245 — — M31 P2 CS 장기 연속성·중단 상태 진단](<245_M31_P2_CS_장기_연속성_진단.md>)
- [246 — — M31 P2 연결형 DF IQ 수신의 내부 LL 메모리 계측](<246_M31_P2_DF_연결_IQ_메모리_계측.md>)
- [247 — — M31 P2 connectionless DF 수신 재진단과 보류](<247_M31_P2_DF_connectionless_재진단과_보류.md>)
- [248 — — M31 P2 SDC controller pool 정적 경계 감사](<248_M31_P2_SDC_pool_정적_경계_감사.md>)
- [249 — — M31 P2 문서 정합성·가독성 감사](<249_M31_P2_문서_정합성_감사.md>)
- [250 — — M31 P2 native RAS 비교·connectionless DF 재진단](<250_M31_P2_native_CS_비교와_DF_재진단.md>)
- [251 — — M31 P2 두 채널 CoC 재연결 메모리 계측](<251_M31_P2_CoC_재연결_메모리_계측.md>)
- [252 — — M31 P2 CS 장절차·반복 계수 경계 진단](<252_M31_P2_CS_장절차_반복계수_경계_진단.md>)
- [253 — — M31 P2 Audio broadcast source 재시작·sink 재가입 메모리 계측](<253_M31_P2_Audio_broadcast_재가입_메모리_계측.md>)
- [254 — — M31 P2 Audio unicast source 재시작·sink 재연결 메모리 계측](<254_M31_P2_Audio_unicast_재연결_메모리_계측.md>)
- [255 — — M31 P2 CS 256-step·분할 RAS 실기 진단](<255_M31_P2_CS_256_step_분할_RAS_진단.md>)
- [256 — — M31 P2 DF connectionless sync 대기 취소 진단](<256_M31_P2_DF_sync_대기_취소_진단.md>)
- [257 — — M31 P2 CoC 송신 버퍼 포화·재연결 부하](<257_M31_P2_CoC_송신_버퍼_부하와_복구.md>)
- [258 — — M31 P2 Audio/ISO 양방향 장시간·종료 경합](<258_M31_P2_Audio_양방향_장시간과_종료_복구.md>)
- [259 — — M31 P2 DF 고정 SDK 지원 경계](<259_M31_P2_DF_고정_SDK_지원_경계.md>)
- [260 — — M31 P2 CS 누락 원인 계수·256-step 장시간](<260_M31_P2_CS_누락_분류와_256_step_장시간.md>)
- [261 — — P2 잔여 세 축 확정과 문서 전수 정비](<261_P2_잔여_세_축_확정과_문서_전수_정비.md>)
- [262 — — M31 메모리 최적화 P2 세 축 완료](<262_M31_메모리_최적화_P2_세_축_완료.md>)
- [263 — M31-W04 Direction Finding 완료](<263_M31_W04_Direction_Finding_완료.md>)
- [264 — M31-W05 connected Channel Sounding 완료](<264_M31_W05_Channel_Sounding_완료.md>)
- [265 — M31-W06 자원·수명주기와 영향 회귀 완료](<265_M31_W06_자원_수명주기와_영향_회귀_완료.md>)
- [266 — — M31-W07 설치 예제와 3보드 역할 HIL 완료](<266_M31_W07_설치_예제와_3보드_역할_HIL_완료.md>)
- [267 — — M31-W08 Windows RC 준비와 M31 완료](<267_M31_W08_Windows_RC_준비와_M31_완료.md>)
- [268 — v0.5.0-rc.1 공개와 다운로드 smoke](<268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)
- [269 — 공개 RC 이력 Squash와 문서 전수 정비](<269_공개_RC_이력_Squash와_문서_전수_정비.md>)

</details>

<details>
<summary>P0·P1 메모리 최적화 — 222~237</summary>

- [222 — — M31 메모리 최적화 P0 완료](<222_M31_메모리_최적화_P0_완료.md>)
- [223 — — M31 메모리 최적화 P1 GPIO 상태 절감](<223_M31_메모리_최적화_P1_GPIO_상태_절감.md>)
- [224 — — M31 메모리 최적화 P1 UART20 lease 절감](<224_M31_메모리_최적화_P1_UART20_lease_절감.md>)
- [225 — — M31 메모리 최적화 P1 Runtime Route 절감](<225_M31_메모리_최적화_P1_Runtime_Route_절감.md>)
- [226 — — M31 메모리 최적화 P1 Resource Table 정렬](<226_M31_메모리_최적화_P1_Resource_Table_정렬.md>)
- [227 — — M31 메모리 최적화 P1 CoC/GATT 분리](<227_M31_메모리_최적화_P1_CoC_GATT_분리.md>)
- [228 — — M31 메모리 최적화 P1 GATT Schema Capacity](<228_M31_메모리_최적화_P1_GATT_Schema_Capacity.md>)
- [229 — — M31 메모리 최적화 P1 GATT Client Context](<229_M31_메모리_최적화_P1_GATT_Client_Context.md>)
- [230 — — M31 메모리 최적화 P1 GATT Event Payload](<230_M31_메모리_최적화_P1_GATT_Event_Payload.md>)
- [231 — — M31 메모리 최적화 P1 GATT TX Payload](<231_M31_메모리_최적화_P1_GATT_TX_Payload.md>)
- [232 — — M31 메모리 최적화 P1 GATT Inline Value](<232_M31_메모리_최적화_P1_GATT_Inline_Value.md>)
- [233 — — M31 메모리 최적화 P1 GATT 방향 분리](<233_M31_메모리_최적화_P1_GATT_방향_분리.md>)
- [234 — — M31 메모리 최적화 P1 GATT shared TX pool](<234_M31_메모리_최적화_P1_GATT_Shared_TX_Pool.md>)
- [235 — — M31 메모리 최적화 P1 GATT client payload buffer](<235_M31_메모리_최적화_P1_GATT_Client_Payload_Buffer.md>)
- [236 — — M31 메모리 최적화 P1 역할별 잔여 pool 감사](<236_M31_메모리_최적화_P1_역할별_잔여_Pool_감사.md>)
- [237 — — M31 메모리 최적화 P1 정적 저장소 구현 완료](<237_M31_메모리_최적화_P1_정적_저장소_완료.md>)

</details>

<details>
<summary>M31 ISO·LE Audio·DF/CS 초기 검증 — 165~221</summary>

- [165 — — M31-W01 완료와 W02 CIS/BIS 진행](<165_M31_W01_착수와_W02_CIS_개발_후보.md>)
- [166 — M31-W02 세 보드 CIS→BIS 기능 실기](<166_M31_W02_3보드_CIS_BIS_통합_실기.md>)
- [167 — M31-W02 설치 Arduino ISO 예제 완료](<167_M31_W02_설치_Arduino_ISO_예제_완료.md>)
- [168 — M31-W03 LC3 공개 Arduino API 실기 진행](<168_M31_W03_LC3_공개_API_실기_진행.md>)
- [169 — M31-W03 고정 NCS LE Audio 샘플의 NU54DK native 빌드](<169_M31_W03_NCS_Audio_샘플_NU54DK_빌드.md>)
- [170 — M31-W04 기본 안테나 CTE 송신 진행](<170_M31_W04_DF_CTE_송신_진행.md>)
- [171 — M31-W05 connected Channel Sounding native 2보드 착수](<171_M31_W05_CS_native_2보드_착수.md>)
- [172 — M31-W04 기본 안테나 IQ 수신 진단](<172_M31_W04_DF_기본안테나_IQ_수신_진단.md>)
- [173 — M31-W05 RAS native 100회 진단](<173_M31_W05_RAS_native_100회_진단.md>)
- [174 — M31-W04 연결 기반 AoA CTE 응답 실기](<174_M31_W04_연결_CTE_응답_실기.md>)
- [175 — M31-W05 Arduino RAS reflector 100회 진단](<175_M31_W05_Arduino_RAS_reflector_100회_진단.md>)
- [176 — M31-W05 Arduino RAS initiator 100회와 재시작 진단](<176_M31_W05_Arduino_RAS_initiator_100회와_재시작_진단.md>)
- [177 — M31-W05 RAS 재연결과 3보드 peer 분리 진단](<177_M31_W05_RAS_재연결과_3보드_peer_분리_진단.md>)
- [178 — M31-W04 연결 AoA 수신의 Host·controller 경계](<178_M31_W04_연결_AoA_수신_Host_Controller_경계.md>)
- [179 — M31-W05 Ranging UUID 위장 peer 거부 20회](<179_M31_W05_RAS_UUID_위장_peer_거부_20회.md>)
- [180 — M31-W05 미암호화 RAS Features 읽기 거부 20회](<180_M31_W05_미암호화_RAS_Features_읽기_거부_20회.md>)
- [181 — M31-W03 native BAP unicast LC3 실제 무선 전송](<181_M31_W03_native_BAP_LC3_실제_무선_전송.md>)
- [182 — M31-W03 Arduino BAP unicast LC3 sink 실기](<182_M31_W03_Arduino_BAP_unicast_LC3_sink_실기.md>)
- [183 — M31-W03 Arduino BAP unicast LC3 두 역할 실기](<183_M31_W03_Arduino_BAP_unicast_LC3_두_역할_실기.md>)
- [184 — M31-W03 Arduino BAP unicast LC3 재시작 복구 20회](<184_M31_W03_Arduino_BAP_unicast_재시작_복구_20회.md>)
- [185 — M31-W03 Arduino BAP stop/release 20회](<185_M31_W03_Arduino_BAP_stop_release_20회.md>)
- [186 — M31-W03 Arduino BAP 잘못된 상태 전이 거부 40회](<186_M31_W03_Arduino_BAP_잘못된_상태_거부_40회.md>)
- [187 — M31-W03 Arduino BAP 원격 codec·QoS 거부 각 20회](<187_M31_W03_Arduino_BAP_원격_codec_QoS_거부_각_20회.md>)
- [188 — M31-W03 Arduino BAP 원격 잘못된 ASE 상태 거부 20회](<188_M31_W03_Arduino_BAP_원격_잘못된_ASE_상태_거부_20회.md>)
- [189 — M31-W03 Arduino BAP 양방향 서버 실기](<189_M31_W03_Arduino_BAP_양방향_서버_실기.md>)
- [190 — M31-W03 Arduino BAP 양방향 client/server와 단방향 회귀](<190_M31_W03_Arduino_BAP_양방향_클라이언트_및_회귀.md>)
- [191 — M31-W02 공개 ISO 예제 재점검과 완료 판정 정정](<191_M31_W02_공개_ISO_예제_재점검.md>)
- [192 — M31-W02 공개 CIS 사용자 SDU 두 역할 실기](<192_M31_W02_공개_CIS_사용자_SDU_실기.md>)
- [193 — M31-W02 공개 BIS 사용자 SDU 두 역할 실기](<193_M31_W02_공개_BIS_사용자_SDU_실기.md>)
- [194 — M31-W02 공개 암호화 BIS 사용자 SDU와 잘못된 Code 거부](<194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md>)
- [195 — M31-W02 공개 BIS 시각 동기 사용자 SDU 실기](<195_M31_W02_공개_BIS_시각동기_사용자_SDU_실기.md>)
- [196 — M31-W02 공개 CIS→BIS 세 보드 사용자 SDU 실기](<196_M31_W02_공개_CIS_BIS_세_보드_사용자_SDU_실기.md>)
- [197 — M31-W02 공개 API 암호화 BIS 오류 후 복구](<197_M31_W02_공개_API_암호화_BIS_오류_후_복구.md>)
- [198 — M31-W02 공개 BIS sync loss·재시작 복구](<198_M31_W02_공개_BIS_sync_loss_재시작_복구.md>)
- [199 — M31-W02 격리 설치본 ISO 11예제·실기 완료](<199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)
- [200 — M31 다른 PC 작업 인계 — 2026-09-17](<200_M31_다른_PC_작업_인계.md>)
- [201 — M31-W03 Arduino BAP broadcast 비암호화와 재가입](<201_M31_W03_Arduino_BAP_broadcast_비암호화와_재가입.md>)
- [202 — M31-W03 Arduino BAP broadcast 암호화와 negative 완료](<202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>)
- [203 — M31-W03 Arduino BASS 3역할과 복구 완료](<203_M31_W03_Arduino_BASS_3역할과_복구.md>)
- [204 — M31-W03 Arduino CAP 3역할과 broadcast 복구](<204_M31_W03_Arduino_CAP_3역할과_broadcast_복구.md>)
- [205 — M31-W03 Arduino CAP unicast 반복 실기](<205_M31_W03_Arduino_CAP_unicast_반복_실기.md>)
- [208 — M31-W03 Arduino Audio Control 완료](<208_M31_W03_Arduino_Audio_Control_완료.md>)
- [209 — M31-W03 Arduino CSIP 완료](<209_M31_W03_Arduino_CSIP_완료.md>)
- [210 — M31-W03 Arduino PBP 완료](<210_M31_W03_Arduino_PBP_완료.md>)
- [211 — M31-W03 Arduino Media·Call Control 완료](<211_M31_W03_Arduino_Media_Call_Control_완료.md>)
- [212 — M31-W03 Arduino TMAP·GMAP 완료](<212_M31_W03_Arduino_TMAP_GMAP_완료.md>)
- [213 — M31-W03 Arduino HAP·HAS 완료](<213_M31_W03_Arduino_HAP_HAS_완료.md>)
- [214 — M31-W03 LE Audio profile 완료](<214_M31_W03_LE_Audio_Profile_완료.md>)
- [215 — M31 W03 이력 squash와 문서 전수 정비](<215_M31_W03_이력과_문서_정비.md>)
- [216 — M31-W04 연결 AoA controller IQ event 진단](<216_M31_W04_연결_AoA_Controller_IQ_Event_진단.md>)
- [217 — M31-W05 비암호화 RAS ATT 오류 진단](<217_M31_W05_비암호화_RAS_ATT_오류_진단.md>)
- [218 — M31-W05 flash 직후 RAS 복구 재검증](<218_M31_W05_flash_직후_RAS_복구_재검증.md>)
- [219 — — M31-W06 메모리 점유 감사와 최적화 계약](<219_M31_W06_메모리_점유_감사와_최적화_계약.md>)
- [220 — — M31 릴리스 전환과 문서 전수 정비](<220_M31_릴리스_전환과_문서_전수_정비.md>)
- [221 — — main 마일스톤별 이력 정리](<221_main_마일스톤별_이력_정리.md>)

</details>

<details>
<summary>M28·M29·M30 완료와 후속 계약 — 130~164</summary>

- [130 — 개발문서 전수 감사와 M28 착수 준비](<130_개발문서_전수감사와_M28_착수_준비.md>)
- [131 — M28-W01 Capability image와 Host·target 준비](<131_M28_W01_Capability_image와_Host_target_준비.md>)
- [132 — M28-W01 실제 HCI capability 완료](<132_M28_W01_실제_HCI_capability_완료.md>)
- [133 — M28-W01 CI container revision 교정](<133_M28_W01_CI_container_revision_교정.md>)
- [134 — — M28-W02 고정 2-slot·generation link 기반](<134_M28_W02_2-slot_generation_link_기반.md>)
- [135 — — M28-W03 확장 광고와 스캔](<135_M28_W03_확장_광고와_스캔.md>)
- [136 — — M28-W04 periodic sync·PAST](<136_M28_W04_periodic_sync_PAST.md>)
- [137 — — M28-W05 PAwR advertiser·scanner](<137_M28_W05_PAwR_advertiser_scanner.md>)
- [138 — — M28-W06 privacy·RPA·link control](<138_M28_W06_privacy_RPA_link_control.md>)
- [139 — — M28-W07 2보드 HIL 자동화 준비](<139_M28_W07_2보드_HIL_자동화_준비.md>)
- [140 — M28-W07 2·3보드 HIL과 W08 완료](<140_M28_W07_3보드_HIL과_W08_완료.md>)
- [141 — M29-W01 ATT/GATT·L2CAP capability 완료](<141_M29_W01_ATT_GATT_L2CAP_capability.md>)
- [142 — M29-W02 link별 GATT client와 long read 완료](<142_M29_W02_link별_GATT_long_read.md>)
- [143 — M29-W03 long/reliable write 완료](<143_M29_W03_long_reliable_write.md>)
- [144 — M29-W04 descriptor·authorization·read multiple 완료](<144_M29_W04_descriptor_authorization_read_multiple.md>)
- [145 — M29-W05 robust GATT cache migration 완료](<145_M29_W05_robust_GATT_cache_migration.md>)
- [146 — M29-W06 LE CoC·credit·고정 buffer 완료](<146_M29_W06_LE_CoC_credit_buffers.md>)
- [147 — M29-W07 Signed Write·EATT HIL 준비와 2보드 완료](<147_M29_W07_Signed_Write_EATT_HIL_준비.md>)
- [148 — 개발문서 전수 검토와 README 개선](<148_개발문서_전수검토와_README_개선.md>)
- [149 — M29-W07 3보드 통합·회귀·Windows 상호운용과 W08 완료](<149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)
- [150 — — v0.5.0 다중 Host 지원 계획 정비](<150_v0.5.0_다중_Host_지원_계획_정비.md>)
- [151 — M30-W01 계약과 HOST-W01~W03 기반](<151_M30_W01_계약과_HOST_W01_W03_기반.md>)
- [152 — M30-W01 capability 실기 완료](<152_M30_W01_capability_실기_완료.md>)
- [153 — M30-W02 link별 security와 IO capability 5종 완료](<153_M30_W02_link별_security와_IO_5종_완료.md>)
- [154 — M30-W03 유선 OOB·bond/privacy·NFC adapter 완료](<154_M30_W03_유선_OOB_bond_privacy_NFC_adapter_완료.md>)
- [155 — M30-W04 일곱 BLE profile 완료](<155_M30_W04_7개_BLE_profile_완료.md>)
- [156 — M30-W05 MCUboot layout·서명 완료](<156_M30_W05_MCUboot_layout_signing_완료.md>)
- [157 — M30-W06 secure BLE DFU·negative·rollback 완료](<157_M30_W06_secure_BLE_DFU_negative_rollback_완료.md>)
- [158 — M30-W07 3보드 secure multi-link 완료](<158_M30_W07_3보드_secure_multi_link_완료.md>)
- [159 — M30-W08 전원 HIL 주입 직전 준비](<159_M30_W08_전원_HIL_주입_직전_준비.md>)
- [160 — 전체 문서 검토와 마일스톤 개정](<160_전체_문서_검토와_마일스톤_개정.md>)
- [161 — M30-W08 실제 전원 HIL과 M30 완료](<161_M30_W08_실제_전원_HIL과_M30_완료.md>)
- [162 — 전체 문서 정비와 M31 TODO 확정](<162_전체_문서_정비와_M31_TODO.md>)
- [163 — Bluetooth 전체 기능·예제와 마일스톤 재배치](<163_Bluetooth_전체_기능_예제와_마일스톤_재배치.md>)
- [164 — 사용자 후속 검증 범위와 DF IQ 인계](<164_사용자_후속_검증_범위와_DF_IQ_인계.md>)

</details>

<details>
<summary>v0.4.0 실기 마감·정식 공개·v0.4.1 — 104~129</summary>

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
- [115 — T13 U UART00 완료와 T13 종료](<115_T13_U_UART00_완료와_T13_종료.md>)
- [116 — T14 자원 충돌 판정과 PWM 식별 교정](<116_T14_자원_충돌_판정과_PWM_식별_교정.md>)
- [117 — T15 지원 범위와 Physical Gate 확정](<117_T15_지원_범위와_Physical_Gate_확정.md>)
- [118 — T16 Peripheral Fabric 설치 통합](<118_T16_Peripheral_Fabric_설치_통합.md>)
- [119 — T17 문서와 지원 매트릭스 정리](<119_T17_문서와_지원_매트릭스_정리.md>)
- [120 — T18 stable 공개 절차와 승인 차단](<120_T18_stable_공개_절차와_승인_차단.md>)
- [121 — T19 RC 소스 고정과 전체 회귀](<121_T19_RC_소스_고정과_전체_회귀.md>)
- [122 — T20 RC 설치 수명주기와 실제 Upload](<122_T20_RC_설치_수명주기와_실제_Upload.md>)
- [123 — T21 stable 패키지와 최종 검사](<123_T21_stable_패키지와_최종_검사.md>)
- [124 — T22 전 QDEC20/21 지원 범위 재확정](<124_T22전_QDEC_지원_범위_재확정.md>)
- [125 — v0.4.0 정식 릴리스 공개와 T24/T25 마감](<125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)
- [126 — 정식 공개 후 문서 전수 정비](<126_정식_공개_후_문서_전수_정비.md>)
- [127 — 후속 마일스톤 지원 경계와 착수 계획 정비](<127_후속_마일스톤_지원_경계와_착수_계획_정비.md>)
- [128 — Nordic 설치 복구 검증 로그 교정](<128_Nordic_설치_복구_검증_로그_교정.md>)
- [129 — v0.4.1 설치기 유지보수 릴리스](<129_v0.4.1_설치기_유지보수_릴리스.md>)

</details>

<details>
<summary>v0.4.0 준비·리팩토링·주변장치 실기 — 43~103</summary>

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
- [86 — T12 Fixture 430 — I2S 짧은 버퍼 실패 이력과 후속 해결 완료](<86_T12_Fixture_430_current_source_I2S_검증.md>)
- [87 — T12 Fixture 430 — DMA 자원 처리 지연 해결 완료와 I2S 전체 PASS](<87_T12_Fixture_430_current_source_I2S_재검증.md>)
- [88 — T12 Fixture 440 — PDM DMA·스테레오 실패 이력과 후속 해결 완료](<88_T12_Fixture_440_current_source_PDM_검증.md>)
- [89 — T10/T12 Fixture 440 — clock·gate 네 핀의 전기적 연결 관측](<89_T12_Fixture_440_clock_gate_분리_진단.md>)
- [90 — T10/T12 Fixture 440 — 재결선과 PDM 위상 진단](<90_T12_Fixture_440_재결선과_PDM_위상_진단.md>)
- [91 — T12 Fixture 440 — PDM 밀도와 연속 DMA 검증](<91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md>)
- [92 — T12 Fixture 440 — PDM 연속 전체 검증](<92_T12_Fixture_440_PDM_연속_전체_검증.md>)
- [93 — Host 재검증과 T12 이후 남은 작업](<93_Host_재검증과_T12_이후_남은_작업.md>)
- [94 — T14 PWM 지연 시작 취소와 무점퍼 검증](<94_T14_PWM_지연_시작_취소와_무점퍼_검증.md>)
- [95 — T12 내부 ADC·TIMER·이벤트 무점퍼 검증](<95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md>)
- [96 — 새 PC 인수 확인과 T12 PWM peer capture 첫 경로 준비](<96_새_PC_인수와_T12_PWM_peer_capture_준비.md>)
- [97 — T12 PWM peer capture 첫 240 조건 검증](<97_T12_PWM_peer_capture_첫_240조건_검증.md>)
- [98 — T13 단독 안정성 3 분 기준 조정](<98_T13_단독_안정성_3분_기준_조정.md>)
- [99 — 공통 결선 검사와 승인 전 자동 진행 계획](<99_공통_결선_검사와_승인_전_자동_진행_계획.md>)
- [100 — T12 공통 기능 묶음과 T13 시험 조합 확정](<100_T12_공통_기능_묶음과_T13_조합_확정.md>)
- [101 — T12 QDEC 누산 누락 원인 분리](<101_T12_QDEC_누산_누락_원인_분리.md>)
- [102 — 개발 문서 전수 검토와 v0.4.0 마일스톤 체크포인트](<102_개발_문서_전수_검토와_마일스톤_체크포인트.md>)
- [103 — TIMER 기능 완료 정리와 T13 자동 진행 경계](<103_TIMER_기능_완료와_T13_진행_경계.md>)

</details>

<details>
<summary>초기 기반·v0.1~v0.3 공개·v0.4.0 범위 — 01~42</summary>

- [1 — M1 도구 환경과 NU54DK 보드 실기 기준선](<01_M1_도구와_보드_기준선.md>)
- [2 — M2 Zephyr module과 Arduino runtime 기준선](<02_M2_Zephyr_Module과_Runtime_기준선.md>)
- [3 — M3 GPIO, 시간과 Scheduler 기준선](<03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [4 — M4 ArduinoCore-API 계약 기준선](<04_M4_ArduinoCore_API_계약_기준선.md>)
- [5 — M5 Arduino CLI Build Adapter 기준선](<05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [6 — M6 기본 Arduino API, Serial과 인터럽트 기준선](<06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [7 — M7 Wire·SPI·ADC·PWM 기준선](<07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [8 — M8 업로드와 디버그 기준선](<08_M8_업로드와_디버그_기준선.md>)
- [9 — M9 증분 빌드, 캐시와 재현성 기준선](<09_M9_증분_빌드_캐시와_재현성_기준선.md>)
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

</details>
