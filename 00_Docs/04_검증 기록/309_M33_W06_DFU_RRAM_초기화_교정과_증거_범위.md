# M33-W06 DFU RRAM 초기화 교정과 증거 범위

기록일: **2026-11-03**. W06은 미완료다. 이 기록의 교정 진단은 정식 #18 PASS가 아니다.
현재 실행 정본은 `D:/w06/control/continuation.json`의 `active_workflow`다.

## S16에서 실제 완료한 범위

S16 `398dcc1752d62094b1ed9fddab8fd40a90368c3d`의 exact CI
[41498594841/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41498594841),
Host652/64 suite·skip0, Actions141, ecosystem2, runtime9, stage/validate150은 PASS다.
Actions 원본은 [41498436685/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41498436685)다.

`D:/w06/final398d/attempt-001`의 독립 #1~#17은 원형 `GROUP_COMPLETED` PASS다.
#1에는 실제 선두 동일 READY 반복이 포함됐으며, [308번 교정](308_M33_W06_READY_판정_불일치_교정과_독립_마감_재개.md)이
수집기/최종 파서의 경계를 일치시켰음을 확인했다. S15 최초 FAIL과 원본 누락은 소급 변경하지 않는다.

#18 `families:secure_dfu`는 native **52523/exit1/final20c275**로 FAIL 종료했다.
원본 `campaign.m30_dfu.log`의 오류는 `peripheral-secondary-initial-erase RRAM sector erase timeout`이며,
실패 cleanup도 `FAIL:BlePairHilFailure`다. DFU 본시험·서명/rollback 판정 및 bootloader/primary의
4개 flash 이전에 발생했다. #19 이후는 실행하지 않았다. 실패 bundle은 봉인했고 이어 쓰지 않는다.

## 원인 분석과 최소 교정

secondary 범위는 `[0xC2000,0x174000)`, **729,088byte**다. 기존 코드는 256byte 쓰기 2,848회와
4KiB readback 178회를 하나의 120초 예산 안에서 수행한다. 현재 raw CoreSight J-Link 경로는
AP word별 DLL 호출을 사용하므로 데이터 전송만 write182,272회와 read182,272회가 필요하다.
과거 다른 source·전송 경로의 DFU PASS만으로 이 경로가 같은 제한 시간 안에 끝난다고 판단할 수 없다.

최초 오류 로그에는 실패 주소와 쓰기/readback 단계가 없다. 따라서 그 정확한 중단 지점은 확정하지 않는다.
reset 미동작이나 앞선 시험의 잔류 설정을 원인으로 단정하지도 않는다. 이번에 교정한 문제는
**대용량 초기화에서 반복 데이터까지 느린 전송 경로로 매번 보내던 준비 구현**이다.

DFU의 초기 준비·성공 cleanup·실패 cleanup 세 호출만 `prepare_for_program=True`를 명시한다.
고정 nRF54L flash 알고리즘의 RAM buffer0에 0xff 한 page를 적재하고, 정확한 178개 page에 순차 재사용한다.
알고리즘은 입력 buffer를 변경하지 않고 각 목적지의 1,024개 word를 기록한다.
buffer 데이터의 host 쓰기는182,272word에서1,024word로 줄며, 알고리즘 적재41word와 제어 호출은 별도다.

- page 정렬·RRAM region·RAM buffer·전체 범위를 program 전에 확인한다. 범위 밖 쓰기와 자동 fallback은 거부한다.
- **120초 공동 예산·전범위 byte 비교·SHA 검증·기존 retry 분류/횟수**를 유지한다. init/uninit과 page wait도 잔여 시간에 묶는다.
- flash 알고리즘이 앱의 RAM/PC/SP를 복원하지 않으므로 이 경로는 성공·실패 모두 HALTED로 남긴다.
  다음 기존 flash가 정상 reset/program을 수행한다. 알고리즘 위치에서 임의 `resume()`하지 않는다.
- 기존 settings 초기화 등 기본 경로의 동작과 256byte 범위 계약은 유지한다.
- cleanup·timeout 설정 복원·최종 halt가 추가로 실패해도 최초 오류를 보존한다. 실패 cleanup을 무한 재시도하지 않는다.

timeout 확대나 부분 readback은 사용하지 않았다. 설치 SDK·pyOCD·pylink·J-Link firmware도 변경하지 않았다.
단순 FlashEraser sector 호출은 이 설치 알고리즘에서 각 sector의 첫 word만 초기화하므로 대체 수단으로 쓰지 않았다.
mass erase·unlock·recover와 Defender 변경은 하지 않았다.

## 검증과 실제 종료

관련 회귀 **157개 PASS**: regression96, DFU16, 공통 두 보드15, Mesh DFU19, Mesh update11.
신규2개는 실제 secondary 크기의 buffer 재사용·전범위 검증, 범위/부분 readback/오류/deadline 거부를 다룬다.
기존 기본 경로·최초 오류 보존·최종 HALTED·resume 금지도 확인했다. 공식 Host 계약은 **654개/64 suite**이며,
이 관련 회귀를 새 source의 전체 Host654 실행으로 표시하지 않는다.

고정한 수정 byte의 별도 실기 진단은 native **32137/exit0/final867aa3**로 완료했다.
729,088byte 초기화·전범위 readback은 **87.130178초**였고 expected/observed SHA는
`544a5483c2e7d091f149870d14450065ead8877cee954536e7eabe1594c2fe85`로 일치했다.
기존 primary 이미지 보존, 세 보드 HALTED·strict RF isolation, debug4·OS·6COM·공통3lock 종료까지 확인했다.
application STOP 성공으로 바꾸어 기록하지 않는다.

종료 증거는 `D:/w06/control/s17-rram-diagnostic-001-close.json`, SHA
`e6f5c96cb75ac2b59bef2835cc3666b434c1d54b8337953aacfd12a7c738799d`다.
원형 #18 FAIL·디버거 FAIL2개는 보존했고, 이 진단의 **정식 #18 실적은0**이다.
전체 DFU 보안 시험을 이 진단으로 대체하지 않는다.

## 이후 1~7과 소스 경계

[현행 1~7](../M33_HANDOFF.md#다음-작업-17)을 계속 수행한다. 수정/관련 회귀/문서 → commit/push·exact CI·source 고정 →
Host654 → 같은 source의 Actions141/ecosystem2/runtime9/stage150 → 독립49 → soak1800/risk7/qualification3 →
원형 strict closure/export → 기록 commit C/push/exact CI·최종 기록 순서다.

같은 source의 유효한 개별 PASS는 실패한 번호 때문에 버리지 않는다. 다만 이번 구현 수정으로 source가 바뀌면
S16의 #1~#17과 준비 PASS는 S16 실적으로 보존하며 새 source의 strict 증거로 합산할 수 없다.
이는 동일 소스·원본 증거 계약이며, 전체49를 끊김 없이 연속 통과해야 한다는 요구가 아니다.
별도 선행 #29 focused20은 추가하지 않고 공식 #29의20회/40구간과 #30~#49를 유지한다.

실패 cycle 이어쓰기·FAIL 재분류·출처 변경을 금지한다. 자동점검 w06은 PAUSED 유지다.
단일 writer·공통3lock·단일 heavy job, 출력/TMP `D:/w06`, 최소4GiB 조건을 유지한다.
