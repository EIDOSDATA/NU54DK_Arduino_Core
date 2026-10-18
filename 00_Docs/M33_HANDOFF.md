# M33 개발 인계 — W06 재설계 구현

최종 갱신: **2026-10-19**. 현재는 사용자 연속 진행 지시에 따라 실패별 집중 수정을 진행한다.
실패 수정은
**한 항목 수정 → 로컬 해당 항목 재검증 → 실제 PASS 확인 → 다음 실패** 순서다.
전수조사 완료·대규모 일괄 수정·전체 49개·Actions를 개별 수정의 선행조건으로 삼지 않는다.
W06은 미완료이며, 이전 자동 재개 지시보다 최신 사용자 범위를 우선한다.
구체적인 설계·수락 조건은 [W06 재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>)가 소유한다.

## 최신 재개 지점 — 2026-10-19

- #37 `resources:df_cs`의 clean `8b1b132a9942bdac4a5f47eef4e5f6c6145e8028`에서 DF 설정 1개·
  회귀 89개·skip 0은 PASS했다. 이어 직접 attestation 기능 검사 9개·skip 0도 모두 PASS했지만
  Host registry가 과거 5개여서 집계는 FAIL했다. 원본은
  `D:\w06\resource37-df-attestation-host-8b1b132a\result.json`, SHA-256은
  `6e736945842ad8693583715aa4ee49ab6c275a55b86cdb1d6f610c484bda5d44`다.
  이 등록 한 항목의 count/hash만 실제 9개 verbose ID에 맞춰 정정하고 직접 회귀 뒤 새 clean
  후보에서 DF→CS RAS→CS ACL 위험을 순차 검증한다. #37 build·flash·실기는 아직 시작하지 않았다.
  과거 d909의 DF 20회 PASS·CS 재연결 FAIL과 아래 c1의 #36 PASS는 각 source로 보존한다.
  수정 전 commit의 dirty 직접 검사 99개·skip 0·각 suite의 독립 등록 count/hash 일치도 PASS했다.

- #36 `resources:iso_audio`는 clean `c1f7e8ce1c0217b0fe529da7ecbf349398bcb957`에서
  combined ISO·BAP duplex·CIS ACL 위험 세 캠페인을 각각 20회 순차 실제 PASS했다.
  combined의 CIS 수신·BIS 전달·BIS 수신은 각각 2,000건이다. BAP는 매 회차 양쪽 송수신
  각 100 frame 이상·energy 양수·drop 0·stream STOP·ACL disconnect를 확인했다.
  CIS 위험은 양쪽 NSE 최소 2·load tick 최소 29·active payload 25 이상에서 ACL을 먼저 종료했다.
- 세 캠페인의 등록 raw/schema/semantic·정규화·exact image/readback을 독립 재검증했다.
  combined 실제 UART 3개, BAP flash 준비와 본 시험 각각 실제 UART 2개, CIS 실제 UART 2개의
  종료를 따로 확인했다. 캠페인별 최종 HALTED readback 3+2+2개와 세 보드 STOP/idle도 PASS다.
  마감 때 새 읽기 전용 identity·HALTED·RADIO0·DPPI 차단·WDT30/31 정지를 다시 확인했다.
- 직접 관련 검사는 등록 Host 127개·skip 0·독립 count/hash 일치와 별도 CIS parser 4개 PASS다.
  외부 실행 경계 3+3+4개는 별도이며 전체 최종 Host나 물리 PASS 분모에 합산하지 않는다.
  필요한 combined 3·BAP 공개 Arduino 2·일반 CIS 2역할만 빌드했고 SDK patch context 원복을 검증했다.
  아래 registry 두 항목만 실제 ID에 맞춰 정정했다. firmware·runner·oracle·SDK pin은 바꾸지 않았다.
  과거 CIS 8회차의 reason 62·7/20·cleanup FAIL도 보존하며 하위 원인이 해결됐다고 추정하지 않는다.
  현재의 엄격한 20회 실제 PASS와 과거 원인 미확정 기록은 구분한다. CLEAR·자동 재시도는 하지 않았다.
- 통합 원본 검증은 `D:\w06\focused-resource36-final-replay-c1f7e8ce.json`, SHA-256은
  `5a2d94156806a4edb76d093d47220bc0d3422a2ba8eb4cd5b11bbf651c90afa3`다.
  진행은 `D:\w06\targeted-resource36-c1f7e8ce-progress.json`, 세 캠페인 원본은
  `D:\w06\targeted-c1f7e8ce-resource36-combined`, `targeted-c1f7e8ce-resource36-bap`,
  `targeted-c1f7e8ce-resource36-cis-risk`에 보존한다. 이전 8096cc7f의 combined PASS는 합치지 않았다.
  다음은 #37 `resources:df_cs`다. 개발 집중 집계는 36/49이며 최종 동일 후보의 공식 49/49·
  별도 resource measurement closure·141/9/150·R3 전달/재개·1,800초 soak·전체 Host·risk 7·
  qualification 3·strict closure·최종 문서 마감은 미완료다.

### #36의 이전 source와 최초 실패 — 원본 보존

- #36 clean `8096cc7f29922d5f6354c8a761dfaf74cc857351`의 combined ISO 20회는 CIS 수신·BIS 전달·
  BIS 수신 각각 2,000건, 실제 UART 3개 종료·exact image/readback·세 보드 STOP/idle과 독립 원본
  재검증까지 PASS했다. 증거는 `D:\w06\focused-resource36-combined-final-replay-8096cc7f.json`이다.
  이어 BAP 직접 기능 9개·skip 0은 PASS했으나 flat 증거 검사 등록부 7개와 실제 8개가 불일치해
  집계 FAIL했다. 원본 `D:\w06\resource36-bap-host-8096cc7f\result.json`, SHA-256
  `275b1a71e7cc8a272c227a73464926a7a2e3b7fe5dbbdadb949be96d3ef06282`를 보존한다.
  이 등록 한 항목의 count/hash만 실제 ID에 맞춰 수정한다. BAP build·flash·실기는 시작하지 않았으며,
  새 clean 후보에서 combined부터 다시 순차 검증한다. 8096cc7f의 combined PASS를 새 후보에 합치지 않는다.
  수정 전 commit의 dirty 직접 검사 108개·skip 0·각 suite의 등록 count/hash 일치는 PASS했다.

- #36 `resources:iso_audio` 첫 combined ISO의 clean `4948cec95f01b9b96c54f06446d87da3697c340f`에서
  parser 5개·build provenance 5개·skip 0은 모두 PASS했지만 Host registry가 과거 parser 4개여서
  집계가 FAIL했다. 원본은 `D:\w06\resource36-combined-host-4948cec9\result.json`이며 SHA-256은
  `1409ef01c979f5e88fe35566e103529d69262e54cc2d79cb891cbd73e04c29c1`이다.
  이 등록 한 항목의 count/hash만 실제 5개 verbose ID에 맞춰 정정하고 직접 회귀 뒤 새 clean
  후보에서 #36 세 캠페인을 순차 검증한다. #36 build·flash·실기는 이 실패 전에 시작하지 않았다.
  수정 전 commit의 dirty 직접 검사는 parser 5·provenance 5·회귀 89, 합계 99개·skip 0·등록 일치 PASS다.
  과거 d909 combined의 software reset 증적을 hardware reset으로 오판한 원인은 `e8b5be12`에서
  이미 수정됐다. 새 speculative firmware/SDK 수정이나 과거 PASS 승계는 하지 않는다.

### #35 집중 검증 완료 — 당시 증거

- #35 `resources:security_dfu`는 clean `64ec9a874c265e05a19b4c4e3d10239c91418773`에서
  M30 multi 20회·cleanup 60건과 signed DFU 10회·negative 5종별 20회·unconfirmed rollback을
  순차 실제 PASS했다. multi 실제 UART 3개와 DFU 실제 UART 2개 종료를 검증했다.
  두 캠페인의 등록 raw/schema/semantic·정규화·exact image/readback·종료 증거를 독립 재검증했고,
  DFU 5개 program phase와 9개 typed 분모도 그대로 검증했다. 최종 현재 세 보드의 읽기 전용
  identity·HALTED·RADIO0·DPPI 차단·WDT30/31 정지도 PASS다. bond CLEAR·물리 전원 차단은 하지 않았다.
- 직접 관련 Host 고유 113개·skip 0·registry count/hash 일치와 선택한 입력 recipe 검사 1개를
  PASS했다. 외부 실행 경계 multi 3개·DFU 3개는 별도이며 전체 최종 Host나 물리 PASS에 합산하지 않는다.
  필요 multi 3역할과 DFU confirmed/unconfirmed/central 3개 sysbuild만 수행했다. 동일 MCUboot·
  canonical signed image·trust public key 입력을 검증했고 공식 SDK patch context 원복도 확인했다.
  아래 최초 registry FAIL만 실제 16개 ID/count/hash에 맞춰 수정했으며 firmware·runner·oracle은 그대로다.
- 통합 원본 검증은 `D:\w06\focused-resource35-final-replay-64ec9a87.json`, SHA-256은
  `3bd5da224ff4599995ab1318d9f4e232b35c4aada1d18ec4185db1e7d9ae363d`다.
  진행은 `D:\w06\targeted-resource35-64ec9a87-progress.json`, 캠페인 증거는
  `D:\w06\targeted-64ec9a87-resource35-multi`와 `targeted-64ec9a87-resource35-dfu`에 보존한다.
  이전 fe84a247 multi PASS는 합치지 않았다. 당시 다음은 #36 `resources:iso_audio`였다.
  이는 개발 집중 캠페인 집계 35/49이며 최종 동일 후보의 공식 49/49·별도 resource measurement closure·
  141/9/150·R3 전달/재개·1,800초 soak·전체 Host·risk 7·qualification 3·strict closure는 미완료다.

### #35의 이전 source와 최초 실패 — 원본 보존

- #35 `resources:security_dfu`의 clean `fe84a2478436bfb22d80823e2fced0e3f2beb08f`에서
  M30 multi 20회·cleanup 60건·UART 3개 종료·exact readback·세 보드 STOP/idle과 독립 원본
  재검증은 PASS했다. 다음 DFU 기능 검사 16개·skip 0도 PASS했지만 Host registry는 과거
  11개여서 집계가 FAIL했다. 원본은 `D:\w06\resource35-dfu-host-fe84a247\result.json`에 보존한다.
  이 등록 한 항목의 count/hash만 실제 16개 ID에 맞춰 정정하고 직접 회귀 뒤 새 clean 후보로
  #35 두 캠페인을 위와 같이 새 clean 후보에서 순차 검증했다. fe84a247의 multi PASS는 합치지 않았다.
  DFU build·flash·runtime은 이 registry 실패 전에 시작하지 않았다. 과거 d909의 원본 실패는
  power용 unconfirmed 입력과 unsigned direct image 선택이었으며 관련 수정은 이미 현재 코드에 있다.

- #34 `resources:gap_gatt`는 clean `d19a02d674d724eb823138906f5068a905542398`에서
  multi 20회·PAST 20회·signed 재부팅 20회/replay 거부/EATT를 순차 실제 PASS했다.
  multi cleanup 60건·UART 3개 종료, PAST 1,000/1,000 수신·손실 0·실제 UART 3개 종료,
  signed counter 21·replay accept 0·EATT 두 bearer별 1,000회·실제 UART 2개 종료를 검증했다.
  각 캠페인의 raw/schema/semantic·exact image/readback과 세 보드 STOP/idle을 독립 재검증했고,
  최종 현재 세 보드의 읽기 전용 identity·HALTED·RADIO0·DPPI 차단·WDT30/31 정지도 확인했다.
- 직접 관련 Host는 고유 166개·skip 0·registry count/hash 일치다. 외부 실행 경계 검사는
  multi 3개·PAST 3개·signed 5개이며 물리 PASS나 전체 최종 Host 분모에 합산하지 않는다.
  필요 역할만 3+3+2개 빌드했고 공식 SDK patch context 원복을 확인했다. Firmware·runner·
  oracle은 그대로이며, 아래 최초 parser registry FAIL만 실제 18개 ID/count/hash에 맞춰 정정했다.
- 사용자가 위임한 초기화 선택은 signed 시험 두 보드의 기본 identity CLEAR 각 1회로 실행됐다.
  실제 전달 시도 각 1회와 원본 CLEAR ACK를 검증했으며 세 번째 보드·다른 identity·자동 재시도로
  확대하지 않았다. 이 사용된 범위를 후속 반복 CLEAR의 포괄적 권한으로 재사용하지 않는다.
- 통합 원본 검증은 `D:\w06\focused-resource34-final-replay-d19a02d6.json`, SHA-256은
  `d559895b55af58af5e13460f2d8f67b549c295ee47abf59a6b4c757ed7d4d1bc`다.
  진행은 `D:\w06\targeted-resource34-d19a02d6-progress.json`이며 세 캠페인의 원본·정규화·
  readback·실제 UART 종료·정지 증거는 `D:\w06\targeted-d19a02d6-resource34-*`에 보존한다.
  이전 fb8832 PASS는 합치지 않았다. 당시 다음은 #35 `resources:security_dfu`였다. 이는 개발 집중
  캠페인 집계 34/49이며 최종 동일 후보의 공식 49/49·별도 resource measurement closure·
  141/9/150·R3 전달/재개·1,800초 soak·전체 Host·risk 7·qualification 3·strict closure는 미완료다.

### #34의 이전 source와 최초 실패 — 원본 보존

- #34 `resources:gap_gatt`의 clean `fb8832a21ba5f326b2d9c5239078c2ffcf6a2987`에서
  multi-link 20회와 PAST 20회를 실제 PASS했다. 두 캠페인 모두 원본·정규화·exact image/readback·
  실제 serial 종료·세 보드 STOP/idle을 재검증했다. PAST는 1,000/1,000 수신·손실 0이다.
  multi의 수동적 PHYEND→DISABLE SHORTS를 외부 helper가 잘못 거부한 원본 FAIL은 보존했고,
  기존 수동 bit 계약만 재사용해 모든 다른 정지 조건을 유지했다. 펌웨어·SDK는 바꾸지 않았다.
- signed/EATT의 기존 runner가 시험 두 보드에서 기본 identity 전체 bond 초기화를 요구하여
  먼저 승인 경계를 알렸다. 사용자는 제시한 초기화와 무삭제 최소 수정 중 편한 방법을 선택해
  W06을 계속 마무리하도록 지시했다. 기존 runner 유지와 시험 두 보드의 시작 초기화 각 1회를
  선택했으며 세 번째 보드·다른 identity·금지된 erase/unlock/recover로 확대하지 않는다.
- signed/EATT 직접 기능 테스트 17+18개는 PASS했으나 parser Host 등록부가 과거 16개여서
  집계는 FAIL했다. 원본은 `D:\w06\resource34-signed-host-fb8832a2`에 보존한다.
  실제 verbose ID에 맞춰 그 등록 수와 hash 한 항목만 정정했다. 빌드·실기·bond 삭제는
  이 실패 전에 시작하지 않았다. 이후 직접 검사와 새 clean source의 #34 세 캠페인을 위와 같이
  완료했다. 위 fb8832의 PASS는 별도 개발 증거이며 새 source의 #34 PASS에 합치지 않았다.
  이전 진행 `D:\w06\targeted-resource34-progress.json`은 현재 source 진행을 가리키며 원본은 보존한다.

- #33 `families:diagnostic_templates`는 clean source
  `a8de62883831398deb5bc68ef629006934cf920b`에서 two-wire 12개·H4 12개 실기와 두 등록
  캠페인의 독립 원본 재검증을 PASS했다. DTM 두 경로·동일 source idle 준비 세 역할과
  controller/scan-request 두 역할만 빌드했으며 SDK 원복도 확인했다. 뒤의 두 역할은
  build-semantic 2개이며 물리 runtime·외부 상호운용 PASS로 세지 않는다.
- DTM runtime의 WDT31 `RUNSTATUS=1`, `CONFIG=65`와 3초 RF lease를 유지했다.
  최종 Test End 뒤 별도 terminal handover에서만 정상 watchdog 해제·ACK·명령 종료를 수행한다.
  양쪽 STOP·WDT30/31 정지·CPU halt·RADIO idle·DPPI/timeout·serial close 및 세 번째 보드
  연속 guard를 원본에서 재검증했다. 고정 nrfx가 정상 해제 event를 소비하므로 ACK 뒤
  STOPPED event는 정확히 0이다. 두 transport × 두 역할의 program/readback은 4건이고,
  최종 H4 상태의 campaign identity는 2개다. 두 분모를 각각 검증했으며 기준은 완화하지 않았다.
- 직접 영향 Host는 진단 12·campaign 7·prepare 40·회귀 89, 합계 148/148·skip 0이며
  등록 suite의 독립 test ID count/hash도 일치한다. 원본·정규화·semantic·exact image/readback·
  cleanup 재검증은 `D:\w06\focused-diagnostic33-final-replay-a8de6288.json`에 있다.
  SHA-256은 `c0fdb0eafc4e1578b20d24e7de7df39291a7cbc30b10199d2672971f86ec8556`이다.
  진행은 `D:\w06\targeted-diagnostics33-progress.json`, 두 캠페인은
  `targeted-a8de6288-diagnostic33-dtm`과 `targeted-a8de6288-diagnostic33-build`에 보존한다.
- 2026-10-18 #33의 two-wire→H4 전환에서 실행 중인 WDT31이 software reset 뒤에도 남는
  원인을 좁혔다. 사용자 승인으로 현재 RX에 정상 STOP을 한 번만 수행했으며
  `RUNSTATUS=0`, `STOPPED=1`, `TSEN=0` readback을 확인했다. TX·세 번째 보드는 변경하지 않았다.
  원본 FAIL·두 bounded 진단은 보존하며 이 복구를 #33 PASS로 세지 않는다.
  정상 STOP 영수증은 `D:\w06\diagnostic33-rx-approved-wdt31-stop-20261018\result.json`이다.
  이 정지 상태의 미소비 event=1과 위 firmware 정상 API 뒤의 event=0은 다른 관측이다.
  수동 STOP을 반복하지 않았다. 잘못 선택한 Windows PowerShell의 사전 launch 실패와 외부
  집계 helper의 최종 identity/phase 분모 혼동도 별도 원본에 보존했다. 실행 정책·실기 source·
  원본 byte는 변경하지 않았으며, 기존 허용 PowerShell 7과 수정된 오프라인 helper로 검증했다.

- 개발 집중 검증의 #27 `families:mesh`는 실기 source
  `3168868b6077cf5a24c7ce113ca0a952d17be313`에서 base 20회, management 10회×두 target,
  BLOB update 10회×두 target, signed DFU 5회×두 target을 실제 PASS했다.
  DFU rollback 9회와 세 역할 cleanup·serial close도 PASS다.
- 네 native/child 영수증의 원본 로그·semantic·image·build-record·readback을 공통 판정기로
  재검증했다. DFU UART raw의 `0x1c` 14개와 `0x1e` 2개를 `splitlines()`가 LF 기록 경계로
  잘못 나누는 소비자 오류를 수정했다. 저장된 원본 byte·hash·실기 source는 변경하지 않았다.
  이 소비자 수정 뒤의 재검증을 새 source에서 수행한 HIL로 표시하지 않는다.
- 직접 관련 Host 세 suite는 회귀 89, Mesh 21, Mesh DFU 14, 합계 124/124·skip 0이다.
  세 suite의 독립 test ID count/hash 목록도 실제 verbose 결과와 일치시켰다.
  전체 최종 Host 검사를 대신하지 않는다.
- 로컬 진행·증거 위치는 `D:\w06\targeted-3168868b-mesh27-progress.json`, 네
  `targeted-3168868b-mesh27-*` 디렉터리, `D:\w06\mesh27-native-transcript-fix-checks`다.
  네 역할의 DFU bound build는 `D:\w06\dfu316`이다. 첫 DFU 호출의 출력 폴더 누락은
  플래시 전에 실패했으며 원본 launch failure와 새 attempt-2를 분리 보존했다.
- #28 `families:radio_coexistence`는 clean source
  `f62d311dc64276474e9304a99cf95fc8b1d42855`에서 두 캠페인 모두 실제 PASS했다.
  독립 IEEE 802.15.4·ESB는 각각 20회·2,000 packet의 ACK/고유 수신 2,000개, 최종 손실 0개다.
  BLE+802.15.4·BLE+ESB·BLE+Mesh 공존은 각각 20회, 두 transport 수신 4,000개씩,
  손실·corrupt·starvation 0이며 아홉 scenario-role의 STOP·serial close와 exact readback을
  원본에서 재검증했다. 증거는 `D:\w06\focused-radio28-final-replay-f62d311d.json`과
  `D:\w06\targeted-f62d311d-radio28-progress.json`에 있다. 과거 d909 실패는 보존했다.
- #29 표준 프로필 준비 시 Host C++ compiler PATH 누락을 실제 설치된 MSYS2 UCRT compiler로
  바로잡았다. 관련 HIL oracle 26개와 campaign 6개, 합계 32/32·skip 0을 통과했다.
  기존 clean 초기 연결 실패 한 번 재시도 검사의 두 test ID를 독립 registry에 반영했다.
  최초 환경 실패 원본과 별도 attempt-2를 `D:\w06\profile29-host-*`에 보존한다.
  준비 당시 단위검사만으로 실기 PASS를 주장하지 않았으며, 아래는 이후 실제 완료 결과다.
- #29~#32는 clean source `8185c55d1c915446765980df62a0fcd53cc2e241`에서 완료했다.
  #29 표준 20개 fresh/restored chain과 네이티브 20개 fresh/restored/second-peer chain,
  #30 비콘 20 cycle·두 session, #31 합성 ANCS 20·AMS 20·access denied 1·malformed 4개를
  실제 PASS했다. 세 그룹 모두 raw·semantic·exact image·readback·STOP·serial close와
  해당 runner-owned bond 정리를 원본에서 독립 재검증했다. 실제 Apple/Google 상호운용은 `NOT_RUN`이다.
- #32 Fast Pair input/locator·EnOcean·MDS 네 template의 실제 build와 credential negative 4개,
  manifest·log·ELF/HEX/config·exact command 재검증이 PASS다. 계약상 build-semantic이며
  보드 runtime·외부 peer PASS가 아니다. 실패 시에도 private 원본 build 자료를 보존하도록
  외부 실행 helper의 임시 폴더 자동 삭제만 해제했으며, 등록 runner의 source·명령·판정은 바꾸지 않았다.
  네 그룹의 증거는 `D:\w06\focused-profile29-final-replay-8185c55d.json`,
  `D:\w06\focused-beacon30-final-replay-8185c55d.json`,
  `D:\w06\focused-ecosystem31-final-replay-8185c55d.json`,
  `D:\w06\focused-template32-final-replay-8185c55d.json`이다.
- #33 최초 준비의 직접 테스트는 진단 11·campaign 6·prepare 40개가 모두 성공했지만 독립 Host registry가
  campaign을 과거 3개로 등록해 집계 검사는 FAIL했다. 실제 verbose ID 6개와 hash에 맞춰
  그 registry 한 항목을 수정했다. 최초 FAIL은 `D:\w06\diagnostic33-host-8185c55d`에 보존한다.
  이후 terminal handover 검사 추가에 따른 현재 12·7개도 실제 verbose ID로 검증했다.
- 개발 집중 집계는 36/49이며 다음 항목은 #37 `resources:df_cs`다. 이 집계는 서로 다른 개발
  수정 단계의 누적이며 최종 동일 source의 공식 49/49나 W06 전체 완료율이 아니다.
  40~49번을 포함한 후속 범위와 정본의 최종 gate를 계속 수행한다.
- 아래 d909의 40개 판정·17 PASS/23 FAIL은 2026-10-11 원본 조사 기록으로 보존한다.
  현재 HEAD·실행·결과를 그 원본 source로 되돌리거나 과거 FAIL을 덮어쓰지 않는다.

## 1. 지금의 정본

| 항목 | 상태 |
| --- | --- |
| 작업 저장소 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core`; build·artifact·실행·log·cache·tmp는 `D:\w06` 전용 |
| 브랜치 | `Dev-0.6.0-M33`, origin의 같은 브랜치 추적; 사용자 요청으로 main 이후 87개 commit을 하나로 정리 |
| 2026-10-11 문서 정리 전 개발 source | `d9090f22c258303660c3bb6d288b7580c0d2a453`; 원본 조사 기준선이며 최종 검증 완료 source가 아님 |
| 첫 전수 조사 | `c21b2716432c5a3cc9ce98aecb4ccdeed7cf180a`: 49개 중 PASS 16 / FAIL 33, 후속 source의 PASS로 승계하지 않음 |
| squash 전 구현 source | `f9f1cd283ee39bcf0609e047473e0e8c5c9930c1`; 원본 시험의 identity, 현재 HEAD와 구분 |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| SDK·toolchain | NCS 3.4.0 / `dcbdc366a1`; C 설치본은 읽기 입력 전용 |
| 완료 상태 | M32 12/12, M33 W01~W05 **5/8**, HOST **3/8** |
| W06 | 미완료; d909 조사 40개 그룹 판정: PASS 17 / FAIL 23. 40번 하위 일부·41~49번·19/22번 누락 범위 미완료 |
| 현재 제품 | Windows stable/source version 0.5.0; v0.6.0 미공개 |

기존 결과의 source를 이번 문서 commit SHA로 바꾸지 않는다. d909 조사 당시 작업 트리는 clean이었다.
재개 시 HEAD·원격·미커밋 변경·submodule을 실제 확인한다.
이전 미커밋 idle-fixture 4개 변경은 이미 이력에 반영됐으며 현재 다시 적용할 미커밋 패치가 아니다.

### 2026-10-11 중단 지점과 개발 후보

- d909 원본 조사: 40개 판정 / 17 PASS / 23 FAIL. 40번의 ecosystem 하위 campaign,
  41~49번 9개 그룹, 19번·22번에서 건너뛴 하위 8개는 남아 있다. 49개 완료로 보고하지 않는다.
- 40번 native의 첫 cycle fresh/restored는 PASS였으나 second-peer의 `security-submit` 및
  후속 인증 실패로 종료했다. 원래 FAIL과 cleanup HOLD는 보존한다.
- 뒤의 독립 idle 복구는 2026-10-11 19:47:29 KST 종료했다. 저장된 commit 해시와 종료 journal을
  확인했고 19:52 KST 관련 실행 프로세스는 0개였다. 이는 재개 시 현재 보드 안전 상태를 대신하지 않는다.
- 자세한 로컬 상태는 `D:\w06\d909-survey-continuation.current.json`, 원본 실행은
  `D:\w06\d909-final-matrix`, 후속 원본 자료는 `D:\w06\d909-survey-*`에 보존한다.
- `D:\w06\proposals`의 수정 후보는 **저장소 미적용**이다. ORDERED51 및 추가 후보 전체를
  일괄 적용하지 말고 현재 실패에 필요한 부분만 재검토한다. 외부 후보 검사를 제품 PASS로 세지 않는다.
- 외부 ORDERED50 Host 검사 결과는 828개 시작 / 827 성공 / 환경 오류 1개다. 전체 PASS가 아니다.
  추가 후보의 74 suite / 862 ID는 등록 예정 정적 분모이며 전체 실행 결과가 아니다.
- 첫 집중 대상은 5번 `privacy`: PAwR 송신 예약 100개 대비 수신 93개로 실패했다.
  원인은 아직 확정하지 않았으며 수정 후 PASS도 없다. 기준을 낮춰 해결하지 않는다.

## 2. 정리한 실행과 남은 검증

| source/root | 실제 결과 | 사용 경계 |
| --- | --- | --- |
| `846f2993…` / e10 | build 141, Host 62/547, runtime 9, stage 150, matrix 11/49 뒤 signed-write FAIL | 과거 source의 결과; 새 source에 승계 금지 |
| dirty focused 진단 / e10 | orphan GATT 삭제·재부팅 지속성·sign/replay/EATT와 cache 재개 handshake 확인 | 개발 진단; 최종 W06 PASS 아님 |
| `f9f1cd28…` / e11 | clean Host **63 suite / 564 test / skip 0**, ecosystem 역할 build 2개, inventory·debugger 확인 | local aggregate/runtime/matrix/soak/closure 미실행 |
| Actions `37581357663` attempt 1 | 사용자 전환 요청으로 **CANCELLED**. plan·shard 1/3 성공, shard 0/2 취소, aggregate는 미완성 upstream 거부 | 전체 build PASS 아님; 취소로 인한 aggregate 실패를 제품 결함으로 단정하지 않음 |

2026-10-07 16:08 KST에 세 보드 모두 HALTED 유지·RADIO 유휴·상태 복원을 실제 확인했다.
이는 프로그램의 STOP 완료나 f9 firmware 실행 PASS가 아니다. 이후 장치 상태는 다시 확인해야 한다.
정리·자료 가용성·검사 원본은 [304번](<04_검증 기록/304_M33_W06_실행_정리와_문서_전수_검토.md>)을 따른다.

2026-10-08 exact `c21b2716…`에서 Actions build 141, runtime 9, stage 150, Host 64 suite/584 test,
R3 bundle export/import/relocation과 실물 20-cycle cleanup/resume를 통과했다. production matrix는
1~13 group PASS 후 14번 `families:pairing_security`의 round 전환 경계에서 FAIL했다. 해당 수정안은
미커밋으로 보류한 채 동일 clean source의 15~49 group을 `D:\w06\r\survey22`에 append-only로
끝까지 실행했다. 최종 group 집계는 PASS 16 / FAIL 33이다. group 내부 fail-fast 때문에
건너뛴 하위 campaign도 `D:\w06\r\survey23-skipped`에서 별도로 실행해 자료를 채웠다. 이 조사
PASS/FAIL은 새 최종 source의 완료 증거가 아니다.

당시 개발 수정본은 Host 64 suite / 597 test / skip 0을 통과했다. 수정 전 Mesh image로
`friend_clear_confirm_timeout`을 한 번 재현했고, 공식 Zephyr 수정 3564414a3b27…을 NCS 3.4.0
고정 patch로 적용한 새 세 역할 image는 build 3/3과 1-cycle 표적검증 뒤 **20/20 cycle**
Friend Clear·traffic·cleanup을 통과했다. dirty 개발 source의 `PASS_CANDIDATE`이므로 clean S의
최종 분모로 승격하지 않으며, 나머지 영향 회귀와 clean S 전체 검증은 아직 완료 전이다.

2026-10-10 native cleanup runtime 표적검증에서는 이전 실패가 남긴 비대칭 bond를 실제로
복구했다. 첫 개발 attempt는 peer 한정 stale bond 삭제 뒤 격리한 이전 link의 지연
`bond_restored_candidate`를 identity 실패로 잘못 판정했다. 이를 이전 link와 새 연결의 판정에서
분리하고 역할별 광고/scan을 유한 1회 재개하도록 수정한 두 번째 attempt는 양쪽 fresh pairing,
authenticated level 4, scoped bond 삭제, 기존 bond 불변, STOP 자원 0으로 `DEVELOPMENT_PASS`했다.
실패·성공 transcript SHA-256은 각각 `5c35654d246e137550cd327a694915a6c0283f322b2357cacd95b9ac644576cc`,
`665aa126a2dcc70e08f523161e63d7932b80b4da65f6c8dddb550ff0a8bc0455`다. 전체 bond 삭제·무한
재시도·지연 event 전역 무시는 사용하지 않았다. 이 결과도 clean S의 최종 49-group 증거는 아니다.

## 3. 현재 연속 실행 순서

1. 이번 문서 전수 검토·정리를 마치고 문서/링크·보존 범위 검사 후 같은 브랜치에 commit/push한다.
   기존 미푸시 코드 commit 2개도 함께 원격에 포함된다. `[skip ci]`로 공식 대규모 빌드는 유예하며,
   이 개발 push를 최종 source 또는 W06 완료 승인으로 해석하지 않는다.
2. 실패 수정 재개 시 한 항목만 선택하고 원본 오류·합격 기준·필요 변경 범위를 고정한다.
3. 그 항목에 필요한 코드만 수정하고 로컬 단위 검사·필요 역할 build·같은 항목 실기를 실행한다.
4. 실패하면 같은 항목에서 근거를 보강해 수정·재검증한다. 실제 PASS 확인 후 다음 실패로 이동한다.
   공통 코드의 직접 영향 회귀는 포함하되 관련 없는 실패·전체 49개를 동시에 진행하지 않는다.
5. 전체 49개·Actions·1,800초 soak·최종 Host·risk 7·qualification 3·closure는 별도 최종 단계다.
   개별 개발 PASS만으로 생략하거나 완료로 표시하지 않는다. 최종 Host 분모는 당시 registry에서 검증한다.

첫 조사 16/33, 현재 중단 조사 17/23, 앞으로의 수정 후 결과를 별도 집계한다. 새 결과로 과거 FAIL을
덮어쓰지 않으며, 알 수 없는 원인을 SDK 결함이나 상태 오염으로 단정하지 않는다.

실행 정본은 저장소의 `tests/hil/nu54dk/m33_regression_run.py`와 registry·evidence 계약이다.
[기존 artifact 안내](../tools/ci/m33_w06_artifacts.md)는 전달·복원 reference로 사용한다.

## 4. D 자료와 보존

- 새 checkout/build/artifact/log/cache/temp는 모두 `D:\w06` 아래에 둔다.
- `e1`~`e11`, `artifacts`, `archive`는 서로 다른 source·attempt의 자료다. 이름만 바꿔 합치지 않는다.
- e2/e4/e7/e10의 중복 shard extraction과 e2~e10의 재생성 가능한 clean Arduino clone은 검증 후 정리했다.
  원본 ZIP·receipt·실패 진단·local runtime은 보존했다. 삭제한 extraction의 절대경로를 바로 실행하지 않는다.
- 사용자가 추가 ZIP 삭제를 취소했으므로 이 문서 정비에서 원본 artifact ZIP을 추가 삭제하지 않는다.
- GitHub artifact는 만료될 수 있다. 재사용 시 같은 source/run/attempt의 가용성·권한·hash를 확인한다.
  기존 4-shard 계약은 byte-bearing shard를 각각 받아 aggregate-shards로 결합해야 한다.
- private RRAM backup·signing key·credential·firmware/raw bundle은 공개 문서나 GitHub에 올리지 않는다.
  closure 공개 export는 허용된 metadata만 사용한다.
- 삭제된 옛 C/D 자료는 Git/원격에 없는 local Host·runtime·cleanup까지 복구된다고 가정하지 않는다.

## M33 원본 이력 보관 — 2026-10-07 squash

사용자 요청 범위는 **현재 M33 브랜치만**이다. 분기 기준 `main`과 공개 release/tag는 바꾸지 않는다.
기존 코드·설정·board gitlink는 유지하고, 이력 정리·복구 안내만 문서에 추가한다. W06 완료나 새 구현 승인이 아니다.

| 항목 | 고정값 |
| --- | --- |
| squash parent | `314c04f2b3e342df5aafa7ba8d950643e9124fe6` — 기존 main |
| 원본 tip | `84c5f4d85c08312d7ce0ff12e2e70b31bdf6564c` — 문서 정비 commit, push 확인 |
| 원본 tree / 대상 수 | `f7013e13afb0c372c37df03b1ac257a20fcc8f02` / main 이후 87 commit |
| 독립 원본 bundle | `D:\w06\archive\git-history-20261007\M33-presquash-84c5f4d8.bundle` |
| bundle SHA-256 | `b95cbd07520c080c76c0a15bd03b480668a1ed79add8e13bbd300c7d25e7b6c5` |
| bundle 크기·검사 | 152,774,333 byte; `git bundle verify` PASS, complete history·선행 bundle 불필요 |

원격 변경은 원본 tip을 기대값으로 한 `--force-with-lease`로 현재 M33 ref에만 적용한다.
새 HEAD의 parent·변경 범위·원격 일치를 검증하며, 새 exact build/HIL은 실행하거나 PASS로 승계하지 않는다.
문서/이력 정리 commit은 `[skip ci]`로 저장하여 중단한 긴 build를 자동 재시작하지 않는다.

기존 checkout은 미커밋 작업과 별도 commit을 먼저 보존한다. squash 전 M33를 새 M33에 일반 merge하거나
그대로 `pull`해 원본 87개 이력을 다시 섞지 않는다. 원본 SHA 재현이 필요할 때는 이 bundle의 존재·hash를
확인한 뒤 별도 D 경로에 복원한다. bundle은 Git 이력만 보관하며 로컬 raw·runtime·SDK의 백업은 아니다.

## M32 원본 이력 보관

M32 브랜치는 삭제됐고 최종 내용은 M33 분기 기준 main에 남아 있다. 아래는 **과거 보관 기록**이며
현재 파일 존재 증명이 아니다. 이번 M33 squash에서 M32 branch 복원이나 추가 main 정리는 하지 않는다.

| 기록 | 당시 위치·identity |
| --- | --- |
| M32 원본 bundle | `C:\Users\eidos\Documents\Codex\2026-10-02\di-x20\outputs\M32-history-0c2af5bd.bundle` |
| 원본 tip / SHA-256 | `0c2af5bdd561c7d271dd21041e2294aba0ea6005` / `12e3f96ae50d30ac721bf43fdc217b7819ff7b388e046d622326d013ff99bdb1` |
| 문서 squash 전 bundle | `C:\Users\eidos\Documents\Codex\2026-10-03\m33-c-users-eidos-github-nu54dk\work\m33-docs-presquash-12637a30.bundle` |
| 문서 bundle SHA-256 | `cc75117047e8214fe440250891dfe95097cb56921a0f6b10e26f8885919f0e13`; 부모 6867 이력이 필요한 증분 백업 |
| 릴리스 백업 | 원격 `Release-0.5.0`의 `4790e3fa…` 기록; 공개 자산 보존 |

당시 감사는 [295번](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)과
[302번 §7](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md#7-로컬-자료-삭제-후-후속-인계--2026-10-05>)을 따른다.
실제 복구 필요 시 파일 존재·hash·bundle prerequisite를 다시 확인한다.

## 5. 변하지 않는 경계

- 실기 writer와 로컬 무거운 build/HIL은 하나씩. 이번에 승인한 병렬 문서/파일 검토는 허용하되
  다른 실패의 수정·실기를 동시에 벌이지 않는다. 후속 병렬 범위는 최신 사용자 지시를 따른다.
- NCS 3.4.0 유지. 3.4.1은 v0.7.0 전용. SDK·board·공개 API를 문서 정비로 바꾸지 않는다.
- NCS 3.4.0의 확정된 SDK 결함을 보정해야 하면 공식 upstream patch의 byte·base revision·변경 파일을
  lock에 고정하고 build 동안만 적용·원상복구한다. Windows CRLF로 stat만 바뀐 경우도 있으므로 staged·
  정규화 tracked diff·untracked 파일을 함께 검사하며 `git status` 한 줄만으로 SDK 오염을 단정하지 않는다.
- 현재 승인 patch는 NCS 3.4.1 조사에서 확인한 Zephyr
  3564414a3b27ae52718efe5244261ebd00102f56 한 건이다. 배포 자산은
  tools/nu54-builder/sdk-patches/zephyr/3564414a3b27-friend-clear-confirm.patch,
  patchset SHA-256은 0e4474e2600229354ba8a55c6529fa88217e79b63eb44684a2f6cd3bb99049bf다.
  build record나 Arduino manifest에 이 값이 없으면 W06 exact image로 승격하지 않는다.
- 승인된 정상 sector program·software reset·halt/resume는 재개 범위에서 수행할 수 있다.
  erase/unlock/recover 허용 이력은 일반 자동 retry 허가가 아니며 필요성을 먼저 진단한다.
- 현재 보드 연결·결선·firmware·STOP은 과거 기록으로 추정하지 않는다. symlink 권한 우회·임의 승격 금지.
- 완료 TODO 6개·과거 PASS/FAIL/HOLD/NOT_RUN과 공개 자산은 보존한다.
- 외부 Apple/Google·장치 실기는 사용자 후속 NOT_RUN. Linux SSH/Mac 접근을 가정하지 않는다.
  Ubuntu/macOS 실제 지원 검증은 RC 단계다.
- W06 실제 완료 후 다음 범위를 확인한다. HOST → RC/실제 OS → M33-W07 완료 → 별도 공개 승인 순서를 유지한다.

## 6. 원본을 찾는 곳

W01~W05 완료 결과는 [M33 TODO](TODO_M33.md)의 해당 절과 296·298~301번 기록에서 찾는다.
W06의 삭제 전/후 경계는 [302번](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md>),
D 재개와 개별 실패·교정은 [303번](<04_검증 기록/303_M33_W06_재실행_최소화와_checkpoint_개선_계획.md>),
이번 중단·정비는 [304번](<04_검증 기록/304_M33_W06_실행_정리와_문서_전수_검토.md>)이 소유한다.
축약 전 인계·TODO 전체 문장은 위 M33 bundle에 보존한 Git commit
`f9f1cd283ee39bcf0609e047473e0e8c5c9930c1`에서 복원할 수 있다. 새 원격 clone에 원본 중간 SHA가 있다고 가정하지 않는다.
