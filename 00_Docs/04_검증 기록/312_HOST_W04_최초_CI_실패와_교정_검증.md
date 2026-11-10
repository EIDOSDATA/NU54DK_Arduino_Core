# HOST-W04 최초 CI 실패와 교정 검증

기록일: 2026-11-10 · 진행: HOST-W04 · Host 완료3/8.

최초 구현 source는 `85a87b5901ae923222a42bbe36387cbde1def4d2`(H1)다.
W06의 S19 source·실제 PASS46·명시 수락 #29·40·44 및 기존 FAIL은 별도로 보존한다.
이번 Host 시험은 W06 HIL 실적에 포함하지 않으며 #29 원인 분석을 재개하지 않는다.

| 실행 | 실제 결과 | 원인과 처리 |
| --- | --- | --- |
| [native prerequisite CI 42742780994](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42742780994) | 세 OS 전체 설치 FAIL, bootstrap 세 구성요소는 성공 | 새 설치기의 `sdk install --tarball` 경로가 고정 SDK의 다중 행 `VERSION`을 version 문자열로 해석했다. 원문과 세 artifact를 hash 검증해 보존했다. |
| [software CI 42742796093](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42742796093) | 8성공/1실패, 6종 대표 build 성공 | installer logging 시험 fixture가 새 `platform-pins.json`을 누락했다. 실제 설치기의 고정 core archive 환경 변수도 fixture에서 검사하도록 교정했다. |
| 로컬 전체 Host A001, native69452 | exit1, EEPROM Host 시험에서 중단 | MSYS2 GCC16.2로 만든 바이너리가 PATH 앞의 NCS MinGW C++ 런타임 DLL을 읽었다. 동일 바이너리에서 PATH만 맞추자 예상 `-ENOENT`와 `EEPROM.begin()` 성공을 확인했다. EEPROM 제품 코드 변경은 없다. |

원본은 `D:/w06/control/host-w04-native-a001-preservation-20261110.json`,
`host-w04-job-<job-id>.raw.log`, `host-w04-full-host-a001.log`에 보존한다.
로컬 원인 구분은 `host-w04-eeprom-diagnostic-a001/receipt.json`과
`host-w04-local-runtime-diagnosis-20261110.json`을 따른다. 서로 다른 source의 성공을 합성하지 않는다.

교정 작업본은 SHA-256을 검증한 SDK archive를 안전하게 추출한 뒤 명시 version과 toolchain 경로로
등록한다. SDK `VERSION`·revision·보안 설정은 변경하지 않는다. 기존 SDK를 덮어쓰지 않으며
경로 탈출 archive를 거부한다. 추출·부정 검사를 포함한 신규 시험13개는 통과했다.
logging fixture 교정 검사는 실제6 PASS와 Windows8.3 alias 미충족1 SKIP이며 이를 7 PASS로 세지 않는다.
원형 EEPROM 시험은 일치 런타임에서 1 PASS다. 교정 후 전체 Host A002는 native24343/exit0으로 종료했다(2389개 실행 중 조건 SKIP3). 도중 추가한 진단·portability10개는 별도 exit0으로 검사했다. fresh 세 OS CI는 아직 미실행이다.

자동 push 규칙으로 시작한 H1 [build-only shard CI42742780285](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42742780285)도
별도 관찰한다. 이 실행의 결과는 동결한 S19 W06 결과를 대체하지 않는다.

현행 상태는 [Host 원장](../../variants/nu54dk/host-readiness.json)과
[설치 안내](<../02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)를 따른다.
순서는 HOST-W04 확정 → W05 → W06 package/native CI → W07 도구 → M33-W07 RC1 →
사용자 Ubuntu/macOS 최종 실기 → HOST-W08이다. 실제 USB·serial·debug·lifecycle은 `NOT_RUN`이며 공개는 별도 승인이다.

Windows 읽기 전용 실제 진단은 serial6개와 CMSIS-DAP identity hash3개를 열거하여 exit0이었다. flash·reset·halt는 0이며 Ubuntu/macOS 사용자 실기 PASS가 아니다.

## H2 실제 결과와 후속 교정

교정 source `beb69193140eba95d2b7b2af333da7df908b751d`(H2)의
[native CI42747429243](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42747429243)도 세 OS FAIL이다.
Windows·Ubuntu는 새 `sdk register`의 `--toolchain-path`와 `--install-dir` 조합이 CLI에서 충돌했다.
macOS는 SDK 추출·등록 후 revision 검사를 지나 Python 파일 탐색에서 실패했다.
전체 설치 PASS로 올리지 않으며 원문3개와 artifact3개를 SHA-256 검증해 별도 보존했다.
H2 [software CI42747433635](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42747433635)의 Host 전체 작업은 실제 성공했다.
최종 전체 결과는 남은 대표 build 종료 후 별도 확정한다.

후속 작업본에서는 등록 명령의 충돌 인자를 제거했다. 고정 nRF Util의 실제 CLI로 잘못된 SDK 경로를
입력하여 인자 충돌 대신 예상 경로 거부까지 진행됨을 확인했다. 이는 설치 PASS가 아닌 negative 진단이다.
macOS 공식 고정 archive의 부분 header에서 `environment.json`의 내부 PATH 선언을 확인했다.
resolver는 기존 고정 후보에 더해 이 선언 안의 실행 파일을 찾으며 bundle 밖의 상대 경로·symlink는 거부한다.
Python·west·compiler·size는 실제 `--version` 실행과 출력까지 ready 검증에 기록한다.
부분 archive 검사는 전체 archive SHA-256 검증 실적이 아니며 새 native CI가 필요하다.

H1 자동 build shard3은 두 번째 Twister가 PLY의 불완전한 `parsetab`을 읽고 `_tabversion` 오류로
build 전에 종료했다. 원본 실패 JSON의 stderr SHA-256과 실제 추출 byte가 일치했다.
큰 ZIP의 전체 다운로드는 600초 timeout으로 부분 파일을 보존했고, 필요한 원문 entry만 HTTPS Range로
추출했다. 전체 ZIP digest를 검증했다고 주장하지 않는다. 동시 실행과 공유 parser 파일 쓰기 경쟁을
고정 SDK parser 복사본으로 구분했다. 고정 SDK가 제공하는 `PARSETAB_DIR`를 실행별 새 경로로 설정해
SDK 공유 파일에 쓰지 않도록 교정했다. SDK·grammar 원본을 수정하지 않았다.
첫 진단의 `1 == 1` 입력은 SDK 문법에 맞지 않아 실패했으며 이를 보존했다.
올바른 `CONFIG_BT` positive·negative 입력의 fresh A002에서는 두 동시 process가 exit0으로 끝나고
같은 table hash를 만들었으며 공유 parser 폴더에 생성물을 남기지 않았다.
이는 parser 교정 진단이며 펌웨어 build·W06 HIL PASS가 아니다.

후속 교정의 관련36개·CI 계약46개는 로컬 exit0이었다. 세 OS 실제 설치와 build는 새 source의 fresh CI로
계속 검증한다. H1·H2 FAIL 및 기존 S19 W06 실적을 합성하지 않는다.
