# R06 — builder 모듈과 설치 경로

상태: R06-A/B 완료. 시작 source `feaccc7`. R06-A는 `f1b3fa4`, R06-B 종료는
Windows 설치 build 복사본 구현 commit으로 식별한다. 다음은 R07 EventFabric이다. 실기 NOT RUN.

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

### R06-B 추가 원인과 구현 범위

launcher 인용부호 교정 뒤 고정 CMake 4.2.1의 `cmake_path(SET ...)`가 한국어 경로에서
0xC0000409로 종료하는 것을 한 줄 script로 재현했다. ASCII 공백 설치 경로도 Zephyr의
Kconfig 환경 인자 처리에서 실패했다. SDK와 시스템 locale은 변경하지 않는다.
Git 없는 설치 package의 bytes를 기존 cache lock 안에서 ASCII build 복사본으로 만들고
원본 설치 root·package revision·source hash와 실제 compiled path를 별도로 기록한다.
복사본 전체 입력은 cache key에 포함하고 손상·부분 복사·경로 이탈을 거부/회복하도록
검증한다. 일반 ASCII checkout와 설치본의 기존 cache 동작은 유지한다.

### R06-B 결과와 유지하는 계약

Windows recipe만 `cmd.exe /d /c call`로 `.cmd`에 진입하며 Python `-I`는 유지한다.
한국어 또는 공백이 있는 Git-less 설치 package는 전체 원본 bytes의 digest를 cache key에
추가하고 기존 cache lock 안의 `platform` 디렉터리에 복사한다. CMake·board·bundled source/
include만 이 복사본을 사용하고, 원본 설치 경로·package revision·source_path와 실제
compiled_path를 따로 남긴다. ASCII checkout와 설치 경로의 기존 key 입력은 유지한다.

추가된 context `platform_build_root`는 build 경로를 설명하는 metadata이고 기존 CLI argument,
exit, artifact 이름, schema 번호, 저장 format과 partition은 바꾸지 않는다. 손상/누락 파일은
원본 bytes로 회복하고 예상 밖 파일·경로 이탈·key 계산 이후 입력 변경은 거부한다.
설치 source 변경은 복사본에 포함되는 전체 digest를 바꾸므로 새 cache identity가 필요하다.
복사본도 기존 cache 용량/lock/삭제 경계 안에 있다. SDK, 설치 원본, 시스템 locale은 수정하지 않는다.

| 검사 | 최종 결과 |
| --- | --- |
| Windows recipe 회귀 | 교정 전 2개 subcase 실패, 교정 후 help=0·invalid=2 |
| 설치 복사본 Host | source/compiled path·byte hash·손상 회복·extra file·key 이후 변경 거부·ASCII 경로 유지 PASS |
| Host 전체 | 616개 중 614 PASS·2 조건부 SKIP |
| 추가 경로 이탈 회귀 | Windows junction이 cache 밖을 가리킬 때 거부·대상 보존 PASS; 설치 복사본 Host 4개 최종 PASS |
| CI contract / package | 45/45 / 20/20 PASS |
| Inventory | PASS, readiness 8 blocker 유지 |
| 실제 한국어·공백 설치 compile | Blink·prj.conf/overlay·원본 ino 오류 진단 3/3 PASS |
| 새 ZIP 재현성 | SHA-256 `9e3fafcf3e8f33eaeb9bbde14f00f44e2f008c1fa276d56c9aad6af9c0f08d7a`, 두 번 동일 |
| flash·HIL·공개·Boards Manager lifecycle | NOT RUN |

새 archive는 로컬 snapshot `1f933cb87f5b556ac9a63e80b6b116e5d4b068ef`의 0.0.90 검증 label이다.
원본 `C:/r6fin/설치 공백/hardware/nucode/zephyr`와 외부 CWD, 한국어·공백 build 경로를
실제 Arduino CLI 1.5.1로 사용했다. 최종 ELF/HEX/manifest integrity와 cache key 재계산,
source provenance·LFXO 검사는 canonical smoke assertion을 그대로 통과했다.
추가 파일은 기존 package 포함 범위에 자동 포함되며 공개 index/tag/Release는 변경하지 않았다.

[최종 source·gate](evidence/r06-f1b3fa4/software-and-source.json),
[설치 compile](evidence/r06-f1b3fa4/installed-smoke-d.json),
[artifact provenance](evidence/r06-f1b3fa4/installed-artifacts.json),
[SDK 최소 실패 재현](evidence/r06-f1b3fa4/sdk-path-failure.json)에 연결한다.
실패한 초기 설치본/trace는 보존했고 현재 PASS와 합산하지 않는다.
빌드 cache 자체는 고정 Windows SDK 때문에 ASCII 공백 없는 경로가 필요하다.
해당 제약을 만족하지 않는 cache에는 명시적인 진단을 내며 사용자 설치 경로를 옮기지 않는다.
Git checkout 경로 자체의 Unicode/공백 지원을 새로 선언하지 않는다.
