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

### R13-B 기계적 분리 결과

Kconfig는 기존 symbol/menu 순서를 유지해 core·serial·analog fabric·event·stream·system·
buses·analog·BLE·scheduler의 10개 파일을 `zephyr/config`에서 포함한다. Windows의
대소문자 구분 없는 filesystem 때문에 기존 `Kconfig`와 충돌하는 `kconfig/` 이름은 쓰지 않는다.
최상위 CORE 조건과 malloc default는 원래 위치에 남겼고, include를 펼친 UTF-8 내용은
기준선과 byte 동일하다. Storage는 기존 library conf/SDK symbol을 그대로 사용한다.

CMake source_selection은 명시적 source 목록, source_provenance는 Git·내용 hash와
build_info, build_record_target는 기존 sidecar target를 소유한다. product_identity와
write_build_record의 기존 구현은 보존했다. include를 펼친 token이 동일하며 추가 함수 scope는
없다. script 상대 경로는 include 디렉터리에 맞춰 같은 실제 write_build_record를 가리킨다.

| 검사 | 결과 |
| --- | --- |
| application resolved config | 대표 12개 전체 CONFIG value/disabled symbol 동일 |
| 실제 compile_commands source | 대표 12개 source multiset·중복 수 동일 |
| flash/RAM | 대표 12개 모두 동일; pair DUT 184,000/161,496 B |
| 실제 CMake Host | Serial 7개 선택/비선택 조합·단일 target 소속 PASS |
| canonical 목록 | 독립 testcase YAML의 NU54DK 60개 전체와 일치; QEMU 1개는 별도 runner |
| 전체 Host | 634개 중 632 PASS·2 조건부 SKIP |
| contract / style / docs | 45/45 / 356개 / 173개 PASS |

비교 도구의 초기 `.config` 탐색이 sysbuild의 빈 설정을 선택한 것을 발견해 ELF와 같은
application 디렉터리의 `.config`로 고정하고 최소 symbol 개수도 검증했다. 최종 비교는 실제
application 설정 전체를 사용한다. M21에서 발견한 SPI driver 누락은 위 B0의 별도 수정과
재시험에 연결한다. 최초 16개 전체를 PASS로 바꾸지 않고 실패 report를 보존한다.

[gate](evidence/r13b-a1b19aa/software.json),
[본문·파일 대응](evidence/r13b-a1b19aa/module-comparison.json),
[12개 설정·source·메모리](evidence/r13b-a1b19aa/target-comparison.json),
[기준선 target](evidence/r13b-a1b19aa/target-baseline.json),
[CMake Host](evidence/r13b-a1b19aa/cmake-host.txt),
[목록 검사](evidence/r13b-a1b19aa/matrix-host.txt)를 보존한다.
R13-C 정책·증거 구조와 최종 전체 gate를 계속한다.

## R13-C 정책·예제 gate·문서 역할

[정책 원본 지도](../../tools/peripheral/README.md)는 기존 JSON/schema와 M23/M24/M26/시험
계획 생성기의 소유 관계를 연결한다. 공개 singleton·silicon/IRQ·지원 상태의 `EXPECTED_*`
상수는 JSON 원본 오류를 잡는 독립 oracle이므로 JSON에서 다시 생성하지 않는다.
기존 schema를 합치거나 profile·readiness 지원 상태를 바꾸지 않았다.

새 `verify_generated.py`는 기존 validator를 통과한 5개 생성물을 hash seed 17/101의
독립 Python process에서 메모리로 생성한다. 두 결과와 저장된 UTF-8/LF 내용을 대조하며
원본·생성물 파일을 쓰지 않는다. M12 inventory는 이 검사와 기존 개별 계약 검사를 함께
수행한다. 독립 Host 3개는 비결정성·생성 누락·저장물 변조·읽기 실패·경로 이탈과 Windows
CRLF 정규화를 검증한다. 실제 고정 SDK DTS와 M23 75개·M24 23개 계약 대조도 PASS다.

기존 29개 설치 예제 runner에는 선택적인 `--package-version 0.0.90`을 추가했다. 기존
기본값·M27 RC 계약은 유지한다. software preview는 release_version `0.0.90`, milestone
`R13`, `staged-software-package-examples`로 기록하여 RC 판정과 구분한다. Host 5개는
두 모드의 실제 gate orchestration과 저장 JSON identity를 fake compiler로 검증한다.
이 Host의 예제 PASS marker는 실제 compile 증거가 아니며 최종 실제 29개 compile은 별도다.

| 결정 / 역할 | 유지하는 원본과 검증 기록 |
| --- | --- |
| Loader 없는 전체 Zephyr image | [Arduino CLI 통합](<../02_빌드 설계/03_Arduino_CLI_통합.md>)과 기존 build template |
| 고정 메모리·lease·generation | [R02](53_R02_Serial_완료와_DMA_수명주기.md), [R08](59_R08_자원과_경로_수명주기.md) |
| ISR/thread·STOP·오류 소유권 | [검증 기록 index](README.md)의 R02/R03/R08/R10/R11 기록 |
| DTS 사실 / 제품 정책 | [정책 지도](../../tools/peripheral/README.md)·기존 schema·고정 SDK/board |
| 제품 identity / protocol·schema 수명주기 | [R05](56_R05_Core_소스와_패키지_identity.md), [R06](57_R06_builder_모듈과_설치_경로.md) |
| Fabric private 경계 / 공개 API 보존 | [R07](58_R07_EventFabric_책임_분할.md)~[R12](63_R12_BLE_Storage_수명주기.md)의 책임·본문·target 증거 |
| 설계·계약 | 01_아두이노 코어 설계와 code의 기존 공개 header·schema |
| 실기 runbook / 활성 계획 | [HIL README](../../tests/hil/nu54dk/README.md)와 [TODO](../TODO_v0.4.0.md) |
| 생성 문서 / 실행·release 증거 | 생성기는 정책 지도, 실제 판정은 04_검증 기록, 불변 공개 자료는 05_릴리스 |

폴더·과거 raw evidence를 이동하지 않고 원본으로 연결했다. 각 새 evidence 디렉터리는
시작 commit·물리 실행 여부·log hash·artifact identity와 실패/재시험의 별도 파일을 갖는다.
큰 원시 build log는 고정 로컬 경로와 SHA-256을 함께 기록하고 기존 공개 증거를 덮어쓰지 않는다.

[gate](evidence/r13c-3ab31b1/software.json),
[생성물 hash](evidence/r13c-3ab31b1/generated.json),
[독립 생성 Host](evidence/r13c-3ab31b1/generated-host.txt),
[예제 identity Host](evidence/r13c-3ab31b1/example-identity-host.txt),
[추가 SPI-on AC02B target](evidence/r13c-3ab31b1/additional-spi-on-target.json)를 보존한다.
R13 구현을 마쳤으며 전체 60개 target·실제 설치 예제·package·Host 최종 검증이 남았다.
최종 게이트를 통과한 뒤에만 R13을 완료 체크하고 current-source T11 직전에서 멈춘다.

## R13-D 최종 설치 smoke의 provenance fixture 보완 범위

최종 exact 499fde3에서 전체 target 60개와 실제 설치 예제 29개는 통과했다. Arduino smoke의
M7 마지막 live provenance 검사에서 test helper가 이동 전 CMakeLists.txt의 입력 목록을
찾아 실패했다. 옮긴 source_provenance.cmake와 이전 monolithic package 경로를 구분해
검사하고, R05 이후 writer가 요구하는 identity 입력을 독립 fixture에도 포함한다.
제품 runtime·package·SDK는 바꾸지 않는다. 같은 설치 package의 실제 CMake writer로
baseline·공개 header/library metadata/DTS 변경·dirty 표식·복원 회귀를 확인한 뒤
실패한 M7 경계와 아직 실행하지 않은 smoke부터 재개한다. 기존 통과 결과와 실패 원본은 보존한다.


### R13-D 보완 결과

현재 package는 source_provenance.cmake를, 이전 단일 CMake 배치는 CMakeLists.txt를 읽는다.
독립 fixture에는 존재하는 CoreIdentity.h·platform.txt·product_identity.cmake를 함께 복사하고
fixture 전용 Git 저장소의 전체 입력을 stage한다. 실제 설치 package에서 현재/이전 배치 모두
baseline·공개 header/library metadata/DTS 변경·dirty와 복원을 통과했다. identity Host 6개와
contract 45개도 통과했다. 제품 runtime·builder·CMake producer·package 입력은 변경하지 않았다.

원래 smoke는 Blink/library/config/error/parallel/M6의 6개 routine을 PASS했다. M7의 4개 예제
compile·설정 검사는 끝났고, 그 loop 뒤의 provenance helper에서 실패했다. 이때 canonical
runner가 자신의 임시 디렉터리를 정리했다. 이미 성공한 compile을 전부 반복하지 않고 같은
package의 helper를 별도 실행해 실패 부분을 완료했다. 아직 실행하지 않은 M9 이후 9개와
M8 두 선택값의 compile만 이어간다. 이 분리 실행은 하나의 무실패 smoke 실행으로 표시하지 않는다.
[원본 실패와 재시험](evidence/r13d-499fde3/software.json)에 각 단계 log hash를 보존한다.

## R13-E 설치 package의 Git-less revision 복원 교정

최종 설치 artifact를 추적하며 exact `499fde3` package의 release manifest에는 올바른 Core·board
SHA가 있지만 configure의 `build_info.yml`과 매 build의 live YAML은 `unknown`인 결함을 발견했다.
실제 CMake에서 `^[0-9a-fA-F]{40}$`가 유효한 40자리 SHA를 거부하는 것을 재현했다.
두 production reader를 길이 40자 검사와 anchored 16진수 문자 검사로 교정했다.
공개 API·CLI·schema·저장 형식·partition·package producer는 바꾸지 않는다.
설치 artifact의 누락된 revision을 복원하는 metadata 동작 변경이며 이전 unknown을 정상으로
승격하지 않는다. SDK·board·기존 공개 archive도 변경하지 않는다.

새 Host 2개는 두 실제 CMake 함수의 소문자·대문자 SHA, 39/41자리, 비16진수·공백·null·
누락·잘못된 JSON·파일 없음과 실제 live writer의 Core/board YAML을 검사한다.
수정 전 5개 subcase 실패를 보존했으며 Host와 고정 SDK의 실제 CMake 모두 2/2 PASS다.
기존 R05 identity 6/6와 contract 45/45도 PASS다.
[실패·수정·입력 증거](evidence/r13e-b9c3004/software.json)에 raw 압축본과 preview를 구분했다.

기존 `499fde3` package의 60 target·29 compile·smoke는 해당 source의 결과로 보존한다.
진행 중인 설치 smoke는 이미 압축 해제한 불변 `499fde3` package와 변경 없는 smoke helper를
사용한다. R13-E commit 뒤 새 source로 전체 target·Host·package·설치 29개를 검증하고,
각 설치 compile 직후 configure/live SHA를 둘 다 확인해 cache 정리 전에 원본 YAML을 보존한다.
영향받는 M7 provenance와 M8 compile도 새 package로 재시험한다. R13은 아직 완료 체크하지 않는다.
current-source T11과 모든 flash/HIL은 NOT RUN이다.
