# R06 — builder 모듈과 설치 경로

상태: R06-A 순수 모듈 추출 완료, R06-B 설치 공백 경로 교정 진행. 시작 source `feaccc7`.
R06 전체 완료 체크와 새 physical PASS는 아직 없다. 각 종료 commit은 해당 변경의 최초 commit으로 식별한다.

## 추출 전 책임과 의존성

| 모듈 | 책임 | 상위 의존성 |
| --- | --- | --- |
| common | schema·오류, 원자 파일 I/O·JSON·hash·revision | 표준 라이브러리 |
| configuration | source/package identity·profile·allowlisted feature | common |
| paths | session·cache 경로 검증 | common |
| locking | OS lock·process 확인·build/probe 배타성 | common |
| environment | 고정 SDK·toolchain·설치 prerequisites | common, paths |
| source_graph | Arduino record·include·sources.cmake·provenance | common, paths |
| cache | key·generation·회복·LRU·제한된 삭제 | configuration, environment, locking, paths |
| artifacts | partition·export transaction·manifest 검증 | cache, common, paths |
| build | configure·feature migration·link·context 생성·clean | 위 하위 모듈 |
| frontend | preprocessing·record·archive recipe | build, environment, paths |
| upload | runner·probe 선택·flash command/실행 경계 | artifacts, build, environment, locking, paths |
| cli | 기존 argparse·진단·exit dispatch | action 모듈 |

내부 모델은 BuildContext, ToolEnvironment, ArtifactManifest의 필수 필드를 정의한다.
기존 `.cmd`와 Python entry, CLI argument/diagnostic/exit, schema 및 파일 형식은 보존한다.
entry는 신뢰된 자기 설치 경로에서만 package를 로드하고 `-I`를 유지한다.

## 검증 계획

분할 전 CLI help/invalid argument 7개를 외부 CWD에서 고정했다. 함수 AST와 출력 대조,
기존 Host·contract·inventory·package 검사, 한국어·공백 경로와 압축 해제 설치본 `-I`,
Arduino frontend부터 ELF/HEX/manifest까지의 대표 전체 compile을 수행한다.
중간 결과는 완료 또는 실기 PASS로 사용하지 않는다.

## R06-A 추출 결과

106개 기존 함수/class는 타입 표기를 제외한 AST가 동일하다. 내부 모듈은 단방향 의존성을
가지며 `BuildContext`, `ToolEnvironment`, `ArtifactManifest`의 필수 필드를 TypedDict로 고정했다.
기존 Python entry는 자기 설치 위치에서 내부 package를 명시적으로 로드하며 sys.path에
외부 CWD/PYTHONPATH를 추가하지 않는다. 기존 `.cmd`의 `-I`와 CLI 진단/exit를 유지했다.
테스트의 patch 대상은 각 함수를 실제 소비하는 모듈로 옮기고 원래 assertions를 유지했다.

| 검사 | 결과 |
| --- | --- |
| Host 전체 | 613개 중 611 PASS·2 조건부 SKIP |
| CLI 전후 | 외부 CWD의 help/invalid argument 7개 stdout·stderr·exit 동일 |
| 압축 해제 격리 | 한국어·공백 경로, 오염된 CWD/PYTHONPATH에서 `-I` 4개 일치 |
| CI contract / package | 45/45 / 20/20 PASS |
| Inventory / style | PASS / C/C++/ino 260개 PASS |
| 설치 ZIP 이중 생성 | 0.0.90 검증 label, 두 archive SHA-256 동일 |
| 실제 설치 compile | Blink·library 내용/헤더/경로 증분·config/overlay·원래 ino 오류 행 PASS |
| flash·HIL·Boards Manager lifecycle·공개 | NOT RUN |

검증 ZIP은 모듈 소스만 stage한 별도 Git index에서 만든 로컬 snapshot
`55ec8e0ad6b75b77dbf97d13ac1bbea9f13c3e06`을 사용했다. branch/tag/ref와 main index는
변경하지 않았다. 배포 번호 0.0.90은 로컬 검증 label이며 stable index 또는 RC를 생성하지 않았다.
실제 설치본은 Git 없는 `C:/r6base/user/hardware/nucode/zephyr`, CWD는 checkout 외부이고
Blink build 경로에는 한국어와 공백이 있다. SDK는 기존 prerequisite marker가 소유한
사용자 NCS 경로이며 R00과 동일한 NCS/Zephyr/bundle revision을 검증했다.

[소스·gate](evidence/r06-feaccc7/software-and-source.json),
[snapshot](evidence/r06-feaccc7/validation-snapshot.json),
[설치 compile](evidence/r06-feaccc7/installed-smoke.json),
[ELF/HEX/manifest](evidence/r06-feaccc7/installed-artifacts.json)에 증거를 보존했다.

초기 Host 실패는 분할 후 test patch/static source 위치를 옮기지 않은 항목을 교정했다.
이어 Windows Code Integrity가 R02 SPIM Host 실행 파일을 WinError 4551로 한 번 차단했다.
보안 정책 변경 없이 동일 시험 재실행 24개와 전체 Host 재실행이 통과했으며 일시 차단의
근본 원인을 해결했다고 주장하지 않는다. [실패 요약](evidence/r06-feaccc7/attempts.json)과
[Serial 재시험](evidence/r06-feaccc7/serial-retry.txt)을 보존했다.

설치 compile의 의도적 오류 시험은 원본 11행을 올바르게 보고했지만 smoke 검사가 바로 앞
Doxygen 주석의 marker 10행을 기대했다. 기대 행을 실제 의도적 오류 문장으로 선택하도록
교정하고 같은 설치 image/toolchain의 진단 회귀를 다시 통과했다. 제품 컴파일 동작은
변경하지 않았다. [재시험](evidence/r06-feaccc7/error-retry.txt)에 결과를 연결한다.

## R06-B 발견한 설치 경로 결함과 다음 수정

`C:/r6pkg/설치 공백/hardware/nucode/zephyr`에서 실제 Arduino CLI 1.5.1 compile은
recipe 실행 시 첫 공백에서 launcher 경로가 잘려 실패했다. 기존 builder/launcher를 복사한
최소 재현에서도 동일하며 모듈 추출과 독립적인 Windows command 인용부호 문제다.
[원래 설치 실패](evidence/r06-feaccc7/installed-smoke.txt)와
[기존 entry의 최소 재현](evidence/r06-feaccc7/recipe-probe.json)을 보존한다.
다음 변경은 Windows recipe에서 명시적인 `cmd /d /c call` 경계로 launcher를 호출하고,
같은 한국어·공백 설치 경로에서 actual CLI compile과 오류 전달을 재검증한다.
Python CLI·schema·공개 API·저장 format·partition은 유지한다.
