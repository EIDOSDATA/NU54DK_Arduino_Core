# T12 Fixture 407 — Host 재개와 software 검증

| 항목 | 값 |
| --- | --- |
| 작성일 | 2026-09-06 |
| 재개 source | `393e419f4c855037d4e6221c315f9be808a7d274` |
| 상태 | **software gate 완료, 407 flash/reset/HIL NOT RUN** |
| 작업 연결 | T09/T12, R13 Host 도구 유지보수, C++ 형 변환 교정 |
| 원래 407 준비·실행 차단 | [80번 기록](<80_T12_Fixture_407_준비와_Host_실행_차단.md>) — exact 076685a, 원본 불변 |
| 새 raw 증거 | [원본·정규화 hash 목록](<evidence/t12-fixture407-resume-393e419/raw-files.json>) — 46개 원본, gzip byte roundtrip 확인 |

사용자의 “ㅇㅇ 다시 진행해” 지시에 따라 기존 개발 환경을 다시 확인했다. 기존 `g++.exe`는
14:16 UTC 재시도에서도 Windows Application Control에 차단됐다. 같은 PC에 이미 설치된
LLVM 22.1.8의 `clang.exe`·`clang++.exe`·`ld.lld.exe`는 실제 compile/link/run에 성공했다.
보안 정책·허용 목록·파일 차단 속성은 변경하지 않았다. 차단된 실행 파일을 복사하거나 이름을
바꾸지도 않았다. GCC 차단 자체의 원인이 해소됐다고 주장하지 않으며, 정상 실행되는 별도
Host 컴파일러를 명시적으로 선택해 필수 native 검사를 완료했다.

## 변경 범위와 처음 실패

- `host_compiler.py`로 직접 compile하는 22개 시험군과 CMake 구성 1개 시험군의 CC/CXX 선택을
  통일했다. 추가 인자는 JSON 배열이고, 명시한 도구가 없으면 실패한다. 기본은 GCC 우선이다.
- 경로 공백·C/C++ 인자 분리·잘못된 JSON·명시적 도구 부재를 검사하는 6개 시험을 추가했다.
- File 자기 복사 대입은 같은 객체의 별칭을 사용한다. 기존 참조 수 검사를 유지한다.
- SPI Host 시험의 Arduino weak main 선언을 모든 번역 단위에서 Host entrypoint와 구분했다.
- `GapScanning.cpp`의 scan type 0/1을 `std::uint8_t`로 명시 변환했다. SDK 원본 enum으로도
  Clang의 narrowing 오류를 재현했다. SDK·board·ArduinoCore-API 원본은 수정하지 않았다.
- CMake Host 시험에도 GNU target·sysroot·LLD 인자를 전달했다. 경고 오류 판정과 시험의
  기능·실패 assertion을 완화하지 않았다.

초기 canonical Host는 File 자기 대입 경고에서 실패했다. 별도 관련 Host 113개 실행에서는
자기 대입, weak main, scan enum narrowing, CMake의 MSVC 기본 target 선택에 따른 실패
12건(7개 CMake 구성 포함)을 기록했다. 수정 후 같은 관련 113개가 모두 통과했다.
[초기 log](<evidence/t12-fixture407-resume-393e419/native-clang-initial.log>)와
[수정 후 log](<evidence/t12-fixture407-resume-393e419/native-clang-corrected.log>)를 별도로 보존했다.

## 검증 결과

| 검사 | 실제 결과 |
| --- | --- |
| canonical Host | **656개 중 655 PASS·1 조건부 SKIP**, 81개 group, 필수 native compiler SKIP 0 |
| 관련 Host | 113/113 PASS — signal 14·lifecycle 3 포함 |
| 계약 | 45/45 PASS |
| Package | 20/20 PASS, 공개 자산 불변·재현성 검사 포함 |
| 예제 | 현재 source 격리 staging의 Arduino CLI 발견 PASS; compile 결과와 구분 |
| Inventory·생성 계약 | 75 instance·23 serial identity·16 capability, 75 test identity·19 family PASS |
| 정렬 | 직접 관리 C/C++/ino 358개, clang-format 22.1.8, FAILED=0 |
| 문서 | 증거 등록 전 Markdown 189개 PASS; 새 기록 등록 후 최종 검사는 아래에 별도 기록 |
| Target | **8/8 build-only PASS**, failed/error/warning 0, 519.63초 |
| USB | 지정 DUT/peer 2/2 열거 PASS; SWD runtime 확인으로 간주하지 않음 |
| 준비 image | DUT/peer 2/2 clean source·board·ELF mailbox metadata 검증 PASS |
| 407 flash/reset/HIL | **NOT RUN — 결선 확인의 30분 유효시간 경과, 유지 여부 답변 대기** |

Host의 조건부 SKIP은 `NUCODE_M13_CLI_DISCOVERY=1`을 요구하는 설치된 package의 예제 발견
검사 1개다. 별도의 canonical examples gate는 현재 source를 격리 staging해 통과했다.
이를 Host 656개 전부 PASS로 바꾸지 않는다. 환경·명령·compiler hash는
[전체 Host 실행 기록](<evidence/t12-fixture407-resume-393e419/gate-host-final.json>), 집계는
[software 검증 결과](<evidence/t12-fixture407-resume-393e419/software-validation.json>)에 있다.

Target은 `C:/u3o`에서 pair DUT/peer 2개와 M19 GAP·M20 GATT·M21 Security 양쪽 역할 6개를
고정 NCS v3.4.0·bundle dcbdc366a1로 새로 빌드했다. Host Clang은 target 컴파일러를 바꾸지 않는다.
Board gitlink는 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`다.
[target index](<evidence/t12-fixture407-resume-393e419/target-artifact-index.json>)와
[canonical build 증거](<evidence/t12-fixture407-resume-393e419/target-build-evidence.json>)가 source·설정·ELF/HEX를 연결한다.

| 역할 | 준비 HEX SHA-256 | 준비 ELF SHA-256 |
| --- | --- | --- |
| 1 | `920c604313dd33443dd3b567d2fa652dfa1d296f7d72352e38d6489478b2ddc7` | `6f3830347a160a05712e40690e6d437378ab2665972300b6fcaeb0f42721e1fe` |
| 2 | `caeb1a3b597e73faefdeae4b041d665a12cb8964dd197a3094ba01566a86334d` | `9d3b370533243961490c1f3ab44320a27d611a495cfaf25ec9f32bd3315542ac` |

407 pair의 repository translation unit 42개와 설정은 기존 준비 exact 076685a와 동일하다.
BLE 6개 구성의 `GapScanning.cpp.obj`를 기존 actual BLE HIL source 18a7cbe의 `C:/u2a`와
`objdump -dr`로 비교했다. Object 파일명 줄만 정규화한 **명령어·재배치 출력이 6/6 동일**하다.
[변경 입력·기계어 대조](<evidence/t12-fixture407-resume-393e419/build-input-comparison.json>)에 두 object와 출력 hash를 남겼다.
이 비교를 새 BLE 실기 PASS나 전체 ELF byte 동일성으로 확대하지 않는다.

## 결선·재개 경계

마지막 사용자의 물리 결선 완료 확인은 2026-09-06T13:47:49Z다. A P1.13/AIN6(P4-11)↔
B P1.14(P4-12), 공통 GND(P2-30), 이전 A P1.12 신호선 제거, DAP UART 분리/SWD 연결,
기존 SB/PMIC 유지, 버튼 미누름 조건이었다. USB 분리 후 변경·재연결도 당시 확인했다.
`v04_fixture.py`는 확인 timestamp가 1,800초를 넘으면 거부한다. 재개 지시만으로 timestamp를
현재 시각으로 바꾸지 않았으며, 현재 동일 결선·버튼 조건 유지 여부를 사용자에게 요청했다.
유지한 상태면 USB를 다시 분리할 필요는 없다.

이번에는 flash·reset·fixture 명령을 실행하지 않았다. 마지막 업로드는 406 exact
`96f38e9486c69cda2c76b48029bc0dc9404d9709`이며 재연결 후 runtime identity는 미검사다.
확인 답변 후 실제 clean checkout과 새 pair image의 source를 대조하고 **SWD 10 MHz**, sector
erase·auto_unlock=false·지정 두 UID로 407 첫 실행을 한다. 문서 commit으로 HEAD가 바뀌면
그 HEAD의 pair image를 다시 준비하며 문자열 치환으로 오래된 image의 provenance를 바꾸지 않는다.

계획은 INPUT pull-down/up/down·25ms settle, 12 vector·2,592 ADC samples·12 cleanup,
source INPUT readback 24개와 해제 12개다. 실기 PASS는 아직 없다. **408도 필수**이며 별도
결선 확인 전 실행하지 않는다. 401~406 누계 216개 기능·46,656 samples와 T12 나머지·T13 이후,
readiness blocker 8개는 유지한다.

## 저장·정리

기존 407 차단 checkpoint 세 commit과 새 Host 지원 source commit을 보존했다. 전체 software
회귀 후 새 문서·원본 증거를 검증해 main으로 push한다. Tag·Release·Boards Manager index는
변경하지 않는다. 일회성 `clang-shared-probe.exe` 1개(62,976 bytes)는 canonical native 시험으로
대체되어 정확한 workspace 경로 확인 후 제거했다. 삭제 전 hash는
[정리 기록](<evidence/t12-fixture407-resume-393e419/diagnostic-cleanup.json>)에 보존했다. 준비 ELF/HEX·실패 log·이전 증거는 유지한다.

최종 등록 후 Markdown **190개 PASS**를 확인했다. [문서 검증 결과](<evidence/t12-fixture407-resume-393e419/docs-verification.json>)와 [BLE 비교 양쪽 source identity](<evidence/t12-fixture407-resume-393e419/ble-comparison-source-identities.json>)도 보존한다. 실행 중 시험 프로세스는 남기지 않으며 407은 결선 유지 답변 대기 상태다.
