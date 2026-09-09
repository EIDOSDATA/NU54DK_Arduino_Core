# T12 Fixture 440 — PDM 연속 전체 검증

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 상태는 [v0.4.0 TODO](../TODO_v0.4.0.md)를 따릅니다.

**Exact f02734d에서 연속 96 개 조합·모노 밀도 비교 16 개·cleanup 96 개를 한 campaign으로 모두 통과했다. 같은 결선을 유지했으며 추가 결선 확인은 필요 없다. 440 기본·연속 기능 검증은 완료했지만 전체 Host와 나머지 T12 요구는 미완료다.**

기록일: 2026-09-07. 시각은 UTC다. [91번](91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md)의 기본 기능 통과·연속 65 개 부분 실행·Host 차단 원본은 변경하지 않았다.

## 결선·실행 조건

사용자 “결선돼있는데, 더 할 이유가 있어?”를 **02:36:38Z**에 동일 결선 유지 확인으로 기록했다. A P1.04↔B P1.05(clock), A P1.05↔B P1.04(gate), A P1.06↔B P1.07(data), 공통 GND다. A P1.07·B P1.06은 미연결, DAP UART 분리·SWD 연결, SB/PMIC 설정 유지다. 확인 유효시간 안에 전체 campaign을 완료했으며 유효시간 설정은 바꾸지 않았다. [확인 원본](evidence/t12-fixture440-f02734d/checkpoint.json).

Source **f02734d69d9722085771fc1a34d5ed0cf756bc4e**, build **C:/u4m**, exact 두 probe와 **SWD 10 MHz**, auto_unlock=false, sector flash·controlled start 조건이다. NCS 99553055607b2e9885fbc80ccd11fa9da81c2df0, Zephyr bf801e4e3d19e1ffa76164346480cb7734dd2800, board gitlink fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3은 유지했다. [Image 식별](evidence/t12-fixture440-f02734d/exact-images.json).

## 결과와 판정

| 검사 | 실제 결과 |
| --- | --- |
| Pair target build | 역할 1/2 모두 PASS |
| 연속 조합 | PDM20/21 × 256/1024 samples × 25/50/75 selector × mono/stereo × 좌우 sampling edge × 신호원 역할 1/2 = 96/96 PASS |
| DMA 반환 | 조합마다 4 개 안정화 + 100 개 측정, 총 9,984 개 반환과 6,389,760 samples의 장치 통계 대조 PASS |
| 경계·순환 | 네 slot의 반환 순서·포인터·길이·재사용 상태·전후 canary·미사용 tail 검사 PASS |
| 모노 밀도 | 평균 기준 16 개 비교 PASS, 측정 버퍼 각각의 25<50<75 순서 1,600 개도 PASS |
| 스테레오 | 측정 버퍼 각각의 좌우 반대 부호 4,800 개 PASS |
| Cleanup | 모든 조합에서 두 보드 정리 응답, 96/96 PASS |
| 전체 campaign | 359.532 초, 1 회 전체 완료, 미실행 0. 이전 부분 campaign과 합산하지 않음 |
| 종료 상태 | 두 exact identity/CPUID, CONSTLAT/PDM20/PDM21/SPIS/GPIOTE/DPPI off, 신호 핀 8 개 입력 복귀 PASS |

[정식 결과](evidence/t12-fixture440-f02734d/fixture440-continuous.json), [journal](evidence/t12-fixture440-f02734d/fixture440-continuous.json.jsonl), [opcode 39 원본 통계](evidence/t12-fixture440-f02734d/continuous-statistics.jsonl), [계획·통계 독립 감사](evidence/t12-fixture440-f02734d/continuous-audit.json), [측정 버퍼별 감사](evidence/t12-fixture440-f02734d/measured-buffers-audit.json), [postflight](evidence/t12-fixture440-f02734d/postflight.json)에 근거를 분리했다.

측정 버퍼 100 개 각각을 비교했으므로 평균값만으로 채널 오류를 가리지 않는다. 연속 증거는 장치에서 계산한 합계·최솟값/최댓값·FNV 등 통계이며 전체 PCM export는 아니다. Stereo 신호원은 edge 동기 0/100% 반대 레벨을 사용하며 75 selector에서 반전한다. 실제 stereo 25/50/75% 밀도 생성, 외부 마이크의 음질 교정, T13 장시간·동시성 시험까지 통과한 결과는 아니다.

기본 1/2-buffer 기능 **192 개·모노 밀도 32 개·184,320 raw samples PASS**는 917dc02의 [91번 결과](91_T12_Fixture_440_PDM_밀도와_연속_DMA_검증.md)로 유지한다. 이번에는 기본 모드를 다시 실행하지 않았다. 두 역할의 저장소 translation unit 42 개 Git blob·membership·config·DTS와 연속 helper/runner/test가 동일함을 대조했다. 이전 main.cpp raw 줄바꿈 차이는 정규화 byte가 같고 이번 추가 코드 변경은 없다. [입력 비교](evidence/t12-fixture440-f02734d/build-input-comparison.json).

## Software·증거·인계

이번 exact pair build 2/2 PASS와 이전 source의 정렬 362 개·신호 Host 17 개 PASS를 구분한다. **전체 Host는 여전히 미통과**다. 이전 canonical 전체 실행과 나머지 그룹의 WinError 4551은 91번에 보존했다. 이번에는 읽기 전용 Windows CodeIntegrity 로그를 조회해 CMake가 기존 WinLibs ninja.exe를 실행할 때 정책 차단된 3077/3033 기록을 확인했다. 이는 이전 Ninja `unknown error`의 환경 근거다. 보안 정책·예외·도구 binary를 변경하지 않았고 차단된 동일 검사를 반복 실행하지 않았다. [조회 결과](evidence/t12-fixture440-f02734d/host-code-integrity-readonly.json), [software 요약](evidence/t12-fixture440-f02734d/software-summary.json).

새 원본 41 개는 [manifest](evidence/t12-fixture440-f02734d/raw-files.json)에 UTF-8/LF 사본·원본 byte gzip·SHA-256으로 보존한다. 문서 201 개의 UTF-8·내부 링크, JSON/JSONL·Python 문법, gzip roundtrip·원본 hash·UID 비공개·Git stage 93 개 byte 대조를 모두 통과했다. 활성 문서 8 개와 이 기록을 갱신하며 91번 이하 역사 증거는 유지한다. 실제 사용 중인 HIL helper·재현 자료는 보존했고 이번 작업에서 삭제할 저장소 임시 파일은 만들지 않았다.

현재 두 보드는 f02734d이며 신호 출력 해제 상태다. 실행 중 시험과 결선 확인 질문은 없다. 다음에는 Host 실행 환경 정상화 뒤 전체 회귀와 PWM 주기·듀티 capture, ADC 정량 검증 등 남은 T12 요구를 처리해야 한다. T14 공용 PWM 미시작 STOP, T13 이후와 readiness 미해결 8 개는 유지한다. 원격 CI는 확인하지 않았다.
