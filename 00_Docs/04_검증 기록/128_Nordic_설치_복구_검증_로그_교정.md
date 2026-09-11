# Nordic 설치 복구 검증 로그 교정

## 1. 요청과 범위

- 날짜: 2026-09-12. 공개 후 설치 도구 유지보수이며 새 마일스톤 구현이 아니다.
- 시작 source: `e9ef9139bdd94c84cc678a5d8902d2b458d5a68b`, branch `main`, 미커밋 변경 없음.
- Board gitlink: `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` 유지.
- 요청: 복구 가능한 초기 검증 실패와 최종 설치 실패의 로그를 구분하고, 검사·문서 갱신 후 커밋·푸시한다.
- 사용자 설치본·SDK·보드·COM 설정과 공개 v0.4.0 tag·Release·index·자산은 변경하지 않는다.
  저장소 수정은 차기 패키지용이며 이미 배포한 v0.4.0에 자동 적용되지 않는다.

## 2. 확인한 원인

기존 `ready.json`이 남아 있으나 SDK의 `nrf/west.yml`이 없는 상태에서 초기 재사용 검증이
실패했다. 이후 복구 설치와 최종 검증은 성공했지만 초기 오류가 stderr로 그대로 흘러나갔다.
[Arduino CLI 출력 처리](https://github.com/arduino/arduino-cli/blob/master/internal/arduino/cores/packagemanager/install_uninstall.go)
는 설치 hook의 stdout과 stderr를 따로 모아 stdout 다음에 stderr를 표시한다.
따라서 앞서 발생한 초기 오류가 마지막 PASS 뒤에 표시되어 최종 설치 실패처럼 보였다.

당시 실제 설치본의 읽기 전용 재검증은 `status: ready`, 종료 코드 0이었다.
SDK 심볼릭 링크·CMake 전역 등록 경고는 이 로그 순서 문제와 별개이며 이번 수정 범위에 포함하지 않는다.

## 3. 수정 결과

**설치 로그 문제: 해결 완료.**

- 세 검증 호출을 공통 함수로 묶고 `reuse`, `installed-bytes`, `ready-marker`별
  `verification=<단계> exit_code=<종료 코드>`와 검증기 출력을 UTF-8 log에 보존한다.
- 초기 재사용 검증 실패는 stdout의 복구 안내로 표시한다. 원래 오류는 log에 남기며
  복구 성공 뒤 부모 stderr에 초기 실패 문구가 나타나지 않는다.
- 최종 byte/revision 또는 marker 검증 실패는 기존대로 stderr·종료 코드 1·`incomplete.json`을
  남기며 PASS를 출력하지 않는다. 독립 실행 `verify-nordic.ps1`의 실패 계약도 변경하지 않았다.
- PowerShell 5.1 native stderr 캡처 구간에서만 오류 정책을 조정하고 즉시 복원한다.
  종료 코드는 global scope에서 받으며 실행 시작 실패에 대비한 초기값은 nonzero다.
- 설치 pin, SHA-256·revision 검증 기준, 재개 명령과 완료 marker 구조는 유지한다.

## 4. 검사와 적용 경계

새 [격리 회귀 검사](../../tests/host/test_m10_installer_logging.py)는 production 설치기 복사본을
Windows PowerShell 5.1에서 실행한다. nRF Util·검증기는 임시 대역이며 사용자 경로·환경·출력을
격리한다. 실제 SDK 다운로드·설치나 보드 기능 시험을 대신하는 PASS가 아니다.

| 검사 | 결과 |
| --- | --- |
| `python -B -m unittest discover -v -s tests/host -p test_m10_installer_logging.py` | **6/6 PASS**. 아래 성공·실패 경로를 분리 수집 |
| `python -B -m unittest discover -v -s tests/host -p test_m10_prerequisites.py` | **24/24 PASS**. pin·marker·PowerShell·CMD 종료 코드·UTF-8 계약 |
| `python -B tools/ci/run_m12_gate.py contract` | **46/46 PASS** |
| `python -B tools/ci/run_m12_gate.py docs` | **255개 PASS**. UTF-8·로컬 링크 |
| `python -B tools/peripheral/verify_generated.py` | **PASS**. 생성기 4개·생성물 5개 일치 |
| `git diff --check` | **PASS** |
| 독립 코드 검토 | PS5.1 종료 코드 scope와 실행 시작 실패 초기값을 교정한 후 중요 잔여 문제 없음 |

격리 설치기 6조건:

| 조건 | 최종 판정 |
| --- | --- |
| 기존 marker 검사 exit 7 → 복구·최종 검증 성공 | exit 0·PASS, 부모 stderr 비어 있음, 초기 오류는 log에 보존 |
| 유효한 기존 marker 재사용 | exit 0, nRF Util 설치 명령 호출 없음 |
| marker 없는 최초 설치 | byte·marker 검증 후 exit 0·PASS |
| 최종 byte 검증 exit 9 | exit 1·incomplete, PASS 없음 |
| 최종 marker 검증 exit 11 | exit 1·incomplete, PASS 없음 |
| 검증용 PowerShell 실행 불가 | exit 1·incomplete, PASS 없음·ready 생성 없음 |

## 5. 커밋·푸시 범위

이 수정과 회귀 검사·문서를 함께 커밋하고, 앞서 로컬에 보관한 문서 커밋 `e9ef9139`도
이번 요청에 따라 `main`에 푸시한다. 현재 체크아웃의 소스 변경과 공개 package byte 변경은
별개다. 공개 v0.4.0을 재게시하지 않으며 설치본 수정·SDK 재설치·실물 시험도 수행하지 않는다.

이 기록에 적힌 PASS는 위 로컬 검사 결과다. 푸시 후 exact SHA의 GitHub CI 상태를 별도로
확인하고 사용자에게 보고한다. 실행 중인 원격 검사를 이 로컬 PASS에 포함하지 않는다.

### 첫 푸시 후 CI 대조

커밋한 `81985bde` 소스의 로컬 `test_m10_packaging.py`는 **21/21 PASS**했다.
임시 패키지 생성·검사이며 공개 자산 게시나 사용자 설치본 변경은 없다.

`81985bdeca984a9210b2af19fea676bb5f3168f0`의
[Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34624045771)는
6개 job 성공·Windows Host 1개 실패였다. 새 테스트가 CI의 짧은 사용자 경로 `RUNNER~1`과
PowerShell이 정규화한 긴 경로 `runneradmin`을 문자열로 비교해 동일 폴더를 다르게 판정했다.
6조건 중 5개가 이 비교에서 중단됐고 검증기 실행 불가 조건은 통과했다.

이는 설치기 판정 실패가 아니라 **회귀 검사의 Windows 경로 별칭 비교 결함**이다.
NCS·platform 디렉터리를 `samefile()`로 비교하도록 **교정 완료**했으며 기존 SDK 격리·종료 코드·출력 검사는 유지한다.
실제 Windows 8.3 별칭 회귀도 추가했다. 별칭을 제공하지 않는 볼륨에서는 그 추가 조건만 SKIP한다.

후속 로컬 검사에서는 새 별칭·재사용 조건 **2 PASS**, 나머지 5조건은 임시 .NET 실행 파일에 대한
Windows Application Control 차단으로 미완료였다. 앞서 통과한 6조건 결과와 구분하며 보안 정책을
해제하거나 이번 5조건을 PASS로 처리하지 않았다. 첫 CI 실패 기록도 보존하고 후속 exact SHA의
Windows CI에서 전체 7조건을 다시 확인한다.
