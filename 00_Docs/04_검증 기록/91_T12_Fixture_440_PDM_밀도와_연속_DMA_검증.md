# T12 Fixture 440 — PDM 밀도와 연속 DMA 검증

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 진행 상태는 [v0.5.0 TODO](../TODO_v0.5.0.md)를 따릅니다.

현재 문제 상태: PDM 위상·모노 준비 순서 오류는 **해결 완료**입니다. 이 기록의 기본 192개·밀도 32개와 [92번](92_T12_Fixture_440_PDM_연속_전체_검증.md)의 연속 96/96이 근거입니다. Host 실행 환경 차단도 [93번](93_Host_재검증과_T12_이후_남은_작업.md)의 전체 재검증으로 **해결 완료**이며 아래 중간 결과는 보존합니다.

**당시 결과:** Exact 917dc02의 기본 기능 192개와 모노 밀도 비교 32개는 모두 통과했다. 연속 4+100 버퍼 시험은 65개 조합을 통과하고 결선 확인 만료로 31개를 실행하지 않았다. 전체 Host 검사는 실행 환경 차단으로 미통과였으며 이 기록만으로 PDM/T12 전체를 완료 처리하지 않았다.

기록일: 2026-09-07. 아래 시각은 UTC다. [90번 이전 진단](90_T12_Fixture_440_재결선과_PDM_위상_진단.md) 이하 역사 기록과 공개 자산은 변경하지 않았다.

## 확인·source·결선

사용자 “ㅇㅇ 그대로 유지하고 있어.”를 **01:53:36Z**에 기록했다. A P1.04↔B P1.05(clock), A P1.05↔B P1.04(gate), A P1.06↔B P1.07(data), 공통 GND, A P1.07·B P1.06 미연결이다. DAP UART 분리·SWD 연결, SB/PMIC 유지 조건이다. [확인 원본](evidence/t12-fixture440-917dc02/checkpoint.json).

모든 hardware 접근은 **SWD 10 MHz**, exact 두 probe, auto_unlock=false, sector flash와 controlled start를 사용했다. Mass erase/recover·보안 설정 변경은 없었다. NCS 99553055607b2e9885fbc80ccd11fa9da81c2df0, Zephyr bf801e4e3d19e1ffa76164346480cb7734dd2800, board gitlink fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3은 유지했다.

| Source / build | 결과 |
| --- | --- |
| 4a8dbafe74e251bbc2897775dae15688ab950823 / C:/u4k | Pair 2/2 PASS. 이전 CONSTLAT 보완과 같은 컴파일 입력. 기능 192·cleanup 192·A 신호원 밀도 16 PASS, B 신호원 밀도 FAIL |
| 같은 4a8dbaf image, 준비 순서 비교 | B→A 모노 25/50/75% 6 개 capture·1,536 samples. 기존 순서는 모두 +17261.2617, 수신기 먼저 준비하면 −12968.9336 / −2.2891 / +12962.4414 |
| 917dc0284b1185d23eeef3f8df31bd3498f78408 / C:/u4l | 수신기 gate 우선과 연속 DMA HIL 추가. Pair 2/2, 기본 기능 192·밀도 32·cleanup 192 PASS. 연속 65·cleanup 65·밀도 8 PASS, 31 개 NOT RUN |

## 원인과 변경 — 해결 완료

B 신호원의 SPIS를 먼저 준비하면 수신기가 gate를 HIGH로 정하기 전의 상태에 노출됐다. 같은 target image에서 명령 순서만 바꿔 세 밀도가 구별됨을 확인했다. 기존 생성 순서에서는 밀도와 무관하게 같은 양의 포화 수신값이 나왔다. [준비 단계 SPIS/GPIO와 raw PCM](evidence/t12-fixture440-4a8dbaf/mono-order-diagnostic.json), [독립 비교](evidence/t12-fixture440-4a8dbaf/diagnostic-audit.json).

현재 runner는 PDM 수신기 준비·ready(gate HIGH) → 생성기 준비·ready → 수신 시작 순서를 사용한다. Mono oracle의 25<50<75 기준과 기존 stereo 좌우 부호 기준은 유지했다. 이전 CONSTLAT 보완의 stereo 96 개도 이번 기본 sweep에서 통과했다. 이 결과는 보완 효과의 실기 근거이며 과거 위상 반전 원인을 전원 지연 하나로 확정하는 파형 계측은 아니다.

연속 HIL은 네 DMA slot을 순환하고 104 개 반환을 기록한다. 매 반환에서 기대 포인터·순서·길이·재사용 상태와 payload 전후 canary 및 미사용 tail을 검사한다. 첫 4 개를 제외한 100 개에서 좌우 합계·extrema·FNV를 계산한다. `--pdm-continuous`와 opcode 39는 HIL 전용 확장이며 제품 core/public API·SDK·board 변경은 없다.

## 실제 검증 범위

- 기본: PDM20/21 × 256/1024 samples × 25/50/75 selector × mono/stereo × 좌우 sampling edge × 1/2 buffer × 양방향, **192 개 기능·184,320 raw samples·32 개 밀도 비교·192 개 cleanup**. [원본](evidence/t12-fixture440-917dc02/fixture440-attempt1.json), [독립 audit](evidence/t12-fixture440-917dc02/results-audit.json).
- 연속: instance·길이·selector·mono/stereo·edge × 양방향의 96 개 계획 중 **65 개 기능·6,760 개 DMA 반환·4,046,848 samples의 장치 통계·65 개 cleanup·8 개 밀도 비교**. [원본](evidence/t12-fixture440-917dc02/fixture440-continuous.json), [raw 통계](evidence/t12-fixture440-917dc02/continuous-statistics.jsonl), [독립 audit](evidence/t12-fixture440-917dc02/continuous-audit.json).
- **02:23:36Z** confirmation 만료 뒤 다음 조합 진입이 거부됐다. 관측한 65 개 중 기능 오류는 없으며, campaign status는 실패/미완료로 유지한다. 남은 31 개를 통과로 간주하거나 다른 실행에 이어 붙여 전체 연속 PASS로 만들지 않는다.
- 종료 후 두 role의 exact identity·CPUID와 CONSTLAT/PDM20/PDM21/SPIS/GPIOTE/DPPI 해제, GPIO 입력 복귀를 읽기 전용으로 확인했다. [Postflight](evidence/t12-fixture440-917dc02/postflight.json).

연속 결과는 buffer별 실제 통계이며 전체 PCM 원본 export는 아니다. Stereo 신호원은 edge 동기 0/100% 반대 레벨을 사용하고 75 selector에서 반전한다. Stereo 25/50/75% 각각의 물리 밀도 발생·외부 마이크·교정 음질·T13 soak 결과로 확대하지 않는다. 100 개 평균의 부호·밀도 비교와 시간에 따른 buffer 통계는 원본에서 구분한다.

## Software·정렬·실행 환경

Pair target는 두 source에서 각각 2/2 통과했다. 917dc02는 HIL main/signal translation unit과 새 helper/runner/test가 변경됐고 config·membership·DTS는 동일하다. [Build 입력 비교](evidence/t12-fixture440-917dc02/build-input-comparison.json), [정리](evidence/t12-fixture440-917dc02/software-summary.json).

전체 C/C++/ino **362 개 정렬 PASS**. 첫 검사에서 main.cpp 한 줄의 혼합 LF/CRLF를 발견해 줄바꿈만 교정했다. 정규화 byte·Git blob은 동일하며 index refresh 전 clean 검사가 거부한 preflight는 flash 없이 끝났다. 원본은 `preflight.log`, `preflight-rejected-fixture440-attempt1.log`에 보존했다.

새 Host 4 개(준비 순서·oracle negative·fixture 조건·실제 native 104-buffer 순환)는 구현 직후 precommit 실행에서 통과했다. 해당 helper/test를 그대로 917dc02에 커밋했다. 이후 exact 재실행에서는 Python 3 개가 통과했으나 native 실행 파일은 두 차례 WinError 4551로 차단됐다. 기존 신호 Host 17 개와 R02 별도 재실행은 통과했다.

**전체 Host PASS 아님:** canonical 전체 실행 2 회는 R02 native 파일 실행에서 Windows 애플리케이션 제어 차단을 기록했다. 미실행 나머지 35 그룹도 별도로 시도했다. R09 SPI, R12 BLE/EEPROM/LittleFS, QDEC, serial lifecycle 일부 native 실행에서도 같은 차단이 발생했다. CMake source 검사는 기존 WinLibs Ninja `--version` 실행이 `unknown error`로 실패했다. 이를 코드 동작 FAIL로 단정하거나 SKIP/PASS로 바꾸지 않았다. 보안 정책·예외·SDK/도구 binary는 변경하지 않았다. [전체 첫 실행](evidence/t12-fixture440-917dc02/host-all.log), [전체 재실행](evidence/t12-fixture440-917dc02/host-retry.log), [나머지 그룹](evidence/t12-fixture440-917dc02/host-remaining.json).

## 증거·인계

두 source의 원본 **124 개**를 UTF-8/LF 사본과 원본 byte gzip으로 보존했다. [4a8dbaf manifest](evidence/t12-fixture440-4a8dbaf/raw-files.json), [917dc02 manifest](evidence/t12-fixture440-917dc02/raw-files.json). SHA-256·gzip roundtrip·JSON/JSONL·Python 문법·UID 평문 누출과 **Markdown 200 개·Git stage 261 개 byte 대조를 통과했다**. 한 실행 script 사본의 끝 빈 줄만 정리했으며 원본 gzip은 그대로이고 manifest에 정규화 방식을 기록했다. 과거 실패 원본과 사용 중인 HIL helper는 보존했으며 삭제할 저장소 내 불용 파일은 확인되지 않았다.

당시 다음 작업이던 연속 96개 전체 campaign은 [92번](92_T12_Fixture_440_PDM_연속_전체_검증.md)에서 완료했다. Host 실행 환경 문제는 **해결 완료([93번](93_Host_재검증과_T12_이후_남은_작업.md))**, 공용 PWM 미시작 STOP 결함도 **해결 완료([94번](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md))**다. 이 기록 종료 당시 보드는 917dc02 출력 해제 상태였고 실행 중 시험은 없었으며 원격 CI는 확인하지 않았다. 현재 잔여 작업은 활성 TODO를 따른다.
