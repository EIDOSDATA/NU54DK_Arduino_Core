# HOST-W07 C3 전체 빌드와 C4 NUS 소유권 교정

2026-11-14 현재 Host6/8, HOST-W07 진행 중이다. C3의 빌드·CI PASS와 실기 FAIL,
C4 개발 교정, 새 source의 최종 미실행을 구분한다. W06 S19의 실제 PASS46·승인 수락3과
FAIL 원형은 보존한다. #29 원인 분석은 사용자 지시로 유예하며 이번 결과로 소급 확정하지 않는다.

| 실행 범위 | source와 실제 결과 |
| --- | --- |
| Windows 전체 빌드 | C3 `9e48de4ced1bc223e99880bbbbc2166a36304099`, `058fc3/exit0`:204 cold·대표4 warm·negative9 PASS |
| 전체 산출물 독립 검사 | 같은 C3, `fc57f5/exit0`:826 산출물·208 manifest 실제 byte/source/조건 대조 PASS |
| 설치 수명주기 | C3 `fa9775/exit0`, 독립 검사 `a2c66c/exit0` PASS |
| C3 CI | software43372824463 9개, prerequisite43372821296 3개, build-only43372821311 6개, native43372821379 30개 성공. 총48 job 원형 log·57 ZIP 보존. native reported612 positive·27 negative·204 image 비교. 로컬24 worker byte 독립 검사는 미실행 |
| 실기 a001 | C3 `1429e9/exit1`:전체204 빌드 뒤 LRU로 대표 cache가 정리되어 hash 거부 검사 이전 E_FLASH_CACHE. 실행 순서 결함, FAIL 보존 |
| 대표 cache 새 생성 | 같은 C3의 별도 attempt `2ea3fe/exit0`:4 cold·4 warm; 제품 flash validator4종·16 산출물 독립 검사 `90584b/exit0`. 전체204 attempt와 합산하지 않음 |
| 실기 a002 | C3 `adb4bc/exit1`:잘못된 probe hash 거부·Blink upload PASS 후 부모 검증기의 존재하지 않는 `tools['python']` 조회로 worker 실행 전 FAIL. SDK Python locator로 교정 |
| C4 SDK 실행 경로 개발 검사 | 미커밋 도구·C3 firmware. 단위10 `8f3bae/exit0`, Blink `98a08b/exit0`, Serial nonce6·2 open/close PASS. BLE pair는 `1b92c1/exit1`의 E_HOST_NUS_TIMEOUT |
| NUS 원인 관측 | C3 firmware a003. 선택한 A/B peer·NUS UUID 확인. Generic GAP 연결 콜백의 local disconnect(19) → ATT ECONNRESET(-104) → disconnected 순서를 HW breakpoint로 확보. 관측기 종료 응답은 잘려 native exit 미확보; 자식 종료·resume·breakpoint 제거·probe close·양쪽 Blink 반환은 결과 원형으로 확인 |
| 원인 재현과 교정 | 비활성 GAP callback이 NUS facade 소유 연결에 개입. 새 Host 회귀는 수정 전 `e868a7/exit1` FAIL, lifecycle lock 안의 비활성 guard 추가 후 `83cb39/exit0` PASS(19 scenario). 활성 GAP role·중복·stale/session 검사는 유지 |
| 교정 영향 검사 | GATT·Security·L2CAP·부모 실행 경로13 tests `3427d1/exit0`, CI contract46 `b79232/exit0`, Markdown533 UTF-8·local-link `2b6524/exit0` PASS |
| 정렬 검사 범위 | 전체 두 파일 정렬은 기존 위반으로 `ce4f92/exit1`. C3 원형과 줄 이동을 대조한 `237b38/exit0`에서 추가25줄의 새 위반0을 확인했으며 전체 파일 PASS로 바꾸지 않음 |
| C4 최종 검증 | source 고정·새 RC kit·실기·전체204·최종 CI 미완료. C3 또는 개발 진단 PASS를 C4 실적으로 이월하지 않음 |

첫 관측기 a001은 SDK project_dir의 CWD 변경과 TemporaryDirectory 정리 순서를 잘못 처리했고,
a002는 예약된 HW breakpoint의 명시 flush가 빠졌다. 두 진단 FAIL과 source도 보존했다.
a003은 초기 halt 없이 FPB 적용 확인·제거 flush·resume·probe close를 확인했다. 관측용 halt 자체가
HCI reason에 줄 수 있는 영향은 원인 판정에 사용하지 않는다. 원인 근거는 선행 local disconnect
호출자와 조건을 실제 Host 코드에서 동일하게 재현한 결과다. SDK·보안 수준·판정·nonce timeout을
바꾸지 않았으며 probe firmware 변경·mass erase·unlock·recover는 수행하지 않았다.

다음 순서는 교정 영향 Host 검사 → 새 exact C4 source·private producer·RC kit → 대표 빌드와
실기를 전체204보다 먼저 실행 → 같은 source의 최종 native/Windows 검증과 독립 검사 → private kit
반출·필수 OS별 실기 → HOST-W08 지원표·문서 마감이다. 대표 cache가 소실된 뒤 실기를 실행하지 않는다.
사용자 OS7행·IDE·물리 USB 재연결·기본 CMSIS-DAP 실기는 미실행이며 조건부 J-Link 실적과 구분한다.
공개 tag·Release·main 통합은 별도 승인 범위다. 자동점검 w06은 PAUSED이며 새 예약은 없다.

비공개 원형은 `D:/w06/control/host-w07-c4-NUS-cause-confirmation-20261114.json`,
`host-w07-c4-gatt-observation-a003/`, 기존 각 source/attempt의 result·log에 보관한다.
현재 절차는 [RC1 실기 절차](<../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>),
마지막 완료 Host 기술 기준선은 [322번](322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md),
직전 C3 보호 교정은 [325번](325_HOST_W07_C2_Windows_통과와_C3_probe_FW_보호.md)을 따른다.
