# R05 — Core 소스와 패키지 identity

2026-09-06, 시작 source `1145e72`. 종료 commit은 이 문서의 최초 commit으로 식별한다.
다음은 R06 nu54-builder 모듈화와 설치 경로 검증이다.

## 원본과 수명주기

| 의미 | 원본·소비자 |
| --- | --- |
| Core 소스 버전 | internal/CoreIdentity.h의 NUCODE_CORE_SOURCE_VERSION, 현재 0.4.0-dev |
| 런타임 BoardSystem::coreVersion | 위 소스 원본, BoardInfo 예제는 Core source로 표시 |
| 설치 배포 버전 | platform.txt version, 기존 packager가 선택한 배포 번호로 stamp |
| checkout platform 표시 | 소스 버전에서 동기화, verify_product_identity.py로 drift 검사 |
| 빌드 식별 | 기존 core revision·source hash와 별도의 source_version/package_version |
| adapter·cache·manifest schema | 기존 상수와 수명주기 유지 |

기존 runtime 고정 문자열 0.2.0-dev와 checkout platform 0.3.0을 교정했다. 소스 원본이
0.4.0-dev인 상태를 정식 공개로 표시하지 않는다. 설치 archive의 0.0.90/0.4.0-rc.1 같은
배포 label은 소스 revision과 함께 별도로 해석한다. RC/정식 소스 버전 승격은 R14 이후
해당 source를 고정할 때 수행하며 현재 published stable/tag/index에는 변화가 없다.

CMake configure와 live build record, builder context/artifact의 product_identity가 같은
원본을 읽는다. CMake는 두 파일의 변경에 재configure하며 원본 누락·중복·잘못된 버전을
거부한다. source/package metadata는 기존 JSON에 추가되는 항목이며 schema 번호는 유지한다.

```powershell
python tools/ci/verify_product_identity.py
python tools/ci/verify_product_identity.py --write
```

두 번째 명령은 소스 원본에서 checkout platform 표시를 동기화한다. inventory gate에 drift
검사를 연결했다. package version만 바뀌는 기존 runtime fingerprint 정규화는 유지하며
CoreIdentity 소스가 바뀌면 fingerprint도 바뀐다. 이를 위해 package version을 runtime
coreVersion에 주입하지 않는다. release-manifest의 version/core_revision 계약도 유지한다.

## 검증과 영향

| 검사 | 결과 |
| --- | --- |
| identity Host | 6개 PASS, CMake/Python parser 일치·invalid 거부·live record·drift 재생성·package stamping/fingerprint |
| Host 전체 | 611개 중 609 PASS·2 조건부 SKIP |
| CI contract / inventory | 45/45 PASS / identity drift 포함 PASS, readiness blocker 8 유지 |
| target | M3 runtime·M15 board 2/2 build-only PASS |
| C/C++/ino style | clang-format 22.1.8, 260개 dry-run PASS |
| 설치 archive 전체 build·예제 | R06 설치 -I 경로 및 R13 최종 전체 gate에서 검증 |
| BoardInfo 실기·flash | NOT RUN |

M15 ELF의 실제 coreVersion 함수를 검사했다. pinned compiler의 ldr/bx와 literal pointer가
0.4.0-dev 문자열을 반환하는 코드이고 live build record도 두 버전을 0.4.0-dev로 기록한다.
이는 ELF 검사이며 CPU에서 함수를 실행한 결과는 아니다. [source·gate·ELF 관측](evidence/r05-1145e72/software-and-source.json)과
[target artifact](evidence/r05-1145e72/target-build.json)에 연결한다.

기존 API/ABI·호출 signature·CLI arguments·exit·package stamping·schema·저장 형식·partition을
유지한다. runtime 문자열과 BoardInfo 표시 label은 의도한 수정이며 최종 실기에서 확인한다.
SDK·board·공개 자산·역사 evidence를 변경하지 않았다. 되돌림 단위는 소스 identity 원본과
runtime 연결, CMake/builder metadata, drift 검사 및 관련 회귀다.
