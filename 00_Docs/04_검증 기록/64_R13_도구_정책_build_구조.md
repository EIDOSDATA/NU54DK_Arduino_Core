# R13 도구·정책·build 구조와 최종 software 입력

상태: 진행 중. R12 `480d780` 뒤 R13-A package, R13-B Kconfig/CMake,
R13-C 정책·증거와 전체 software gate를 순서대로 기록한다. flash/HIL은 실행하지 않는다.

## R13-A package 책임 분리

기존 entrypoint에서 함수·자료형 43개를 책임별 내부 모듈로 이동했다. model/channels는
자료형과 고정 공개 계약, inputs/serialization은 exact Git 입력과 순수 byte 처리,
licenses/sbom/manifest는 배포 내용·license·SPDX·provenance, archive/validation은
생성과 실제 검증, index/build/cli는 공개 인자와 orchestration을 소유한다.
모듈 간 필요한 이름만 명시적으로 import하고 상호 순환 import는 없다.

함수 AST와 자료형은 보존했다(이동한 세 candidate tuple의 model 참조를 정규화). CLI의 상대 repository root만 파일 깊이에 따라
`parents[2]`에서 `parents[3]`으로 조정하여 실제 기본 경로를 유지했다. wrapper는 같은
설치 디렉터리 아래의 package를 고유 이름으로 로드하며 기존 Python 이름을 re-export한다.
공개 stable의 source·tooling commit 제한과 archive size/hash 상수는 그대로다.

동일 입력 `480d780`의 로컬 preview `0.0.90`으로 ZIP·checksum·manifest·SPDX·license·
notices·index 7개를 비교해 byte 동일을 확인했다. 이 preview는 소프트웨어 검증 전용이며
공개하거나 RC로 승격하지 않는다. CLI help·오류 8개도 exit/stdout/stderr byte 동일이다.
새 Host 5개는 한국어·공백 CWD의 `-I`, 외부 PYTHONPATH 동명 package 차단, 두 독립
import 소비자, repository 기본값, 오류 marker/exit 2와 실패 전 출력 미생성을 검증한다.

## R13-B 착수 범위

Kconfig의 symbol·default·depends/select·menu 순서를 보존한 기능별 include와,
CMake의 명시적 source 선택·provenance·build record target include를 분리한다.
함수/변수 scope를 추가하지 않는 include를 사용한다. Storage는 기존 library feature conf와
SDK Kconfig가 원본이므로 의미 없는 새 Core symbol을 만들지 않는다.
분리 전 대표 12개 resolved config·source membership·메모리를 같은 구성으로 비교한다.
누락된 M21 target는 canonical runner에 명시적으로 연결하고 최종 전체 목록을 검사한다.

## 증거와 실행 경계

역사적 raw evidence는 이동하거나 고치지 않는다. 새 증거는 시작 commit별 디렉터리에
판정 요약·원본 log hash·source/board identity·artifact hash를 연결한다. 큰 로컬 build 로그는
검증 기록의 경로와 hash로 추적하고, CI의 만료 artifact만을 유일한 근거로 삼지 않는다.
R13 완료는 current-source T11 physical, T12/T13, T16~T18 또는 RC/공개 완료가 아니다.

### R13-A gate와 발견한 연결 결함

Package 20/20, contract 45/45, 새 module Host 5/5, M18 25/25,
M27 8 PASS/dirty-checkout 1 SKIP와 Markdown 172개를 통과했다. 최초 CI lock 실패는
상수를 이동한 model 원본으로 연결하여 수정했다. M27의 기존 tuple 재할당은 분리된 모듈의
복사본에 전파되지 않아 candidate 판정에서 실패했다. 세 tuple은 model 한 곳을 참조하고
기존 M27 설정은 명시적 등록 함수로 연결했다. 동일 이름의 재import에서도 이전 candidate
상태를 재사용하지 않도록 module namespace를 매 load마다 독립시켰다. 공개 stable 목록은
확장하지 않으며 새 CLI 명령도 없다. M18의 생성 전후 stable 보호 snapshot에는 이동한
내부 Python 파일도 포함한다. 해당 model 변조를 거부하는 독립 Host를 추가했다.

최종 연결 보정 뒤 같은 source로 다시 생성한 7개 package 산출물도 처음 기준선과 byte
동일했다. [gate](evidence/r13a-480d780/software.json),
[함수·모듈](evidence/r13a-480d780/module-comparison.json),
[산출물·CLI](evidence/r13a-480d780/byte-comparison.json),
[새 Host](evidence/r13a-480d780/module-host.txt),
[M27](evidence/r13a-480d780/m27-host.txt), [M18](evidence/r13a-480d780/m18-host.txt),
[최초 lock 실패](evidence/r13a-480d780/initial-lock-failure.txt),
[최초 candidate 실패](evidence/r13a-480d780/initial-candidate-failure.txt)를 보존한다.

### R13-B0 선택되지 않은 SPI driver 참조 보정

M21 Board+Security를 canonical 목록에 추가하자 `CONFIG_SPI=n`인데 SPI00 DTS node가
활성인 기존 구성에서 공통 route cpp가 없는 SPI device/pinctrl symbol을 참조해 link가
실패했다. Kconfig/CMake 분리는 기존 본문과 같은 내용이며 이 결함은 선택 경계의 누락이다.
SPI binding과 pinctrl 선언에 실제 SPI driver 선택 조건을 함께 적용했다. driver가 없으면
기존 비활성 경로와 같이 빈 binding을 반환한다. 다른 route·singleton·DTS·public API는 같다.

16개 최초 build 중 15개는 build-only 성공, M21 Board+Security 1개는 실패였다. 수정 뒤
실패한 M21 구성(SPI off)과 M7(SPI on)만 새 경로에서 2/2 재빌드 PASS했다. 이 보정과
canonical M21 metadata/누락 검사는 기계적 CMake/Kconfig 파일 분리와 별도 commit이다.
[원래 16개 report](evidence/r13b0-a1b19aa/target-before.json),
[링크 실패](evidence/r13b0-a1b19aa/link-failure.txt),
[재시험](evidence/r13b0-a1b19aa/target-after.json),
[설정·artifact](evidence/r13b0-a1b19aa/software.json)를 보존한다.
