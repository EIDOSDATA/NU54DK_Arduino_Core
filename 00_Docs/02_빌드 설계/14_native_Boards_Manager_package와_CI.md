# Native Boards Manager package와 CI

기준일: 2026-11-10. HOST-W05까지 완료5/8, HOST-W06의 H6 실제 설치 FAIL을 교정 중이다.
현행 순서는 [Host 계약](10_v0.5.0_다중_Host_지원_착수_계약.md)과
[v0.6.0 TODO](../TODO_v0.6.0.md)를 따른다. 이 문서는 private CI package의 계약이며 공개 승인이 아니다.

## 초기 실행 환경

기존 Windows stable 0.5.0의 package·index·설치 계약은 유지한다. Native 0.6.0 시험 package는
Python이 없는 초기 설치를 위해 Boards Manager tool dependency `nu54-python`을 사용한다.
공식 [python-build-standalone 20261026](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026)의
CPython 3.12.16을 사용하며 Windows x86-64·Linux x86-64·macOS ARM64 자산의 URL·size·SHA-256은
[bootstrap-pins.json](../../tools/nu54-prerequisites/bootstrap-pins.json)에 고정한다.
Arduino host flavour는 각각 `x86_64-mingw32`, `x86_64-linux-gnu`, `arm64-apple-darwin`이다.

초기 runtime은 post-install과 네 가지 builder recipe에서 동일 공통 backend를 `-I -B`로 실행한다.
SDK 설치 후의 실제 build·Git·west·compiler는 [고정 Nordic 환경](12_Host별_고정_Nordic_환경_설치.md)의
SDK 자체 도구를 선택한다. 시스템 Python/Git으로 조용히 대체하지 않는다.
`NUCODE_PREREQUISITE_STATE_ROOT`는 post-install과 이후 build가 같은 준비 상태를 읽도록
공통 backend에서 처리하며 빈 값·상대 경로는 거부하고 명시 CLI 인자를 우선한다.

각 배포 자산을 실제 내려받아 size·SHA-256·실행 파일을 확인했다. Windows에서는 고정 runtime의
독립 실행·한글 파일 I/O·인증서 검증을 켠 HTTPS를 실제 확인했다. 이것은 세 OS의 Boards Manager
설치 완료 증거가 아니다. Stripped archive에 생략된 upstream notice는 같은 release의 full archive에서
원문60개를 보관하고 [license 원장](../../tools/nu54-prerequisites/bootstrap-license-inventory.json)에
출처·원형 hash를 기록한다. Git 개행 변환으로 원형 notice byte를 바꾸지 않는다.
SPDX의 법무 검토 상태는 자동으로 승인 상태로 올리지 않는다.

## Private package 생성

[producer](../../tools/ci/host_native_package.py)는 clean exact Git source의 archive와 sidecar를 두 번
독립 생성해 byte를 비교한다. `0.6.0-host.1` 또는 `0.6.0-rc.1`은 해당 프로세스의 private candidate로만
허용한다. 공개 allowlist·root index·tag·Release는 수정하지 않는다. Package 검증은 Git blob에서
선택한 bootstrap pin·notice·platform pin·backend·OS별 recipe와 bundle map을 결합한다.
Native index 검증은 실제 package archive도 요구하며 tool version에 서로 다른 자산을 붙이면 실패한다.

실제 설치 시험은 검증된 동일 archive를 loopback index로 제공한다. Core와 초기 runtime의 미게시
자산 URL을 `127.0.0.1`로 바꾸고 실제 생성한 archive의 고정 SHA-256·size는 유지한다. 게시 예정 URL을
가진 index와 loopback index의 hash를 각각 보관하며 실제 공개한 index로 주장하지 않는다.
CLI 1.5.1 역시 OS별 고정 archive의 hash·size와 실제 실행 version을 확인한다.

H6 실제 Ubuntu 설치에서 공식 stripped tar의 symlink-only 디렉터리가 없어 CLI 1.5.1의 압축 해제가
실패했다. CLI가 사용하는 [extract v4.0.0](https://github.com/codeclysm/extract/blob/v4.0.0/extractor.go)의
symlink placeholder 생성은 부모를 생성하지 않는다. 교정은 원형 실행 파일·mode·link를 보존하면서
모든 부모 디렉터리를 먼저 넣는 USTAR/bzip2 archive를 실제 생성하는 것이다. 별도 tool version은
`3.12.16-20261026.nu54.1`이며 각 OS의 원문 고지20개와 upstream provenance도 동봉한다.
원본 upstream pin과 파생 archive pin을 구분하고 두 번 생성한 실제 byte를 검사한다.
`tools-nu54-python-…` URL은 미게시 후보이며 tag·Release·asset을 아직 공개하지 않았다.

## Native CI 단계

[workflow](../../.github/workflows/host-native-package.yml)는 push 또는 명시 dispatch로 실행한다.
예약 실행은 없으며 다른 source의 실행을 취소하지 않는다.

1. Ubuntu producer에서 package·evidence 단위 검사와 두 번 생성한 archive·sidecar의 byte 동일성을 확인한다.
2. Windows 2025 x86-64·Ubuntu 24.04 AMD64·macOS 26 Apple Silicon에서 실제 CLI로 package를 설치한다.
   부모 Python/Git 경로를 제거한 자식 환경에서 post-install을 실행하고 저장된 SDK 상태를 재검증한다.
3. 공백·한글 data/user 경로의 설치 파일 전체를 원본 ZIP과 대조하고 24개 library의 예제204개를 발견한다.
   각 OS에서 설치된 Blink를 compile하고 세 OS의 실제 ARM load image·HEX·메모리 값을 비교한다.
4. Smoke 비교가 모두 성공하면 OS별8개 shard, 총24개 worker로 전체 예제204개와 잘못된 profile9개를 검사한다.
   Shard 배정은 정렬된 예제 identity의 index modulo8이며 권장 profile을 그대로 사용한다.
5. 집계는 같은 source·version·workflow run·attempt의 세 OS 전체 결과와 실제 파일을 다시 검증한다.
   전체 실행을 생략한 smoke-only 결과를 HOST-W06 완료로 세지 않는다.

Worker마다 설치 상태와 SDK를 새로 준비한다. 공유 cache는 공식 pin으로 매번 검사하는 download byte에
한정하며 ready marker·SDK 설치 디렉터리·build 결과를 다른 worker의 설치 성공으로 재사용하지 않는다.
CI signing fixture의 private key는 worker의 별도 private 경로에만 생성하며 artifact에 업로드하지 않는다.
원형 compile/negative/설치 로그·ELF·HEX·manifest와 실패 시 부분 진단은 같은 attempt에 보존한다.

## Artifact 비교와 실패 판정

[consumer](../../tools/ci/host_native_package_consumer.py)는 실제 compile exit0뿐 아니라 manifest의
Core·board·SDK/Zephyr·bundle·Host·FQBN·profile과 artifact hash·size·경계를 확인한다.
[집계기](../../tools/ci/host_native_package_aggregate.py)는 전달된 실제 파일을 다시 분석한다.

ELF 전체 원형 hash와 debug 정보를 보존하면서 ARM ELF32의 실제 PT_LOAD byte·주소·entry와
할당 section을 비교한다. HEX는 checksum·주소·중복·EOF를 검증하고 line 분할·순서만 정규화한다.
FLASH/RAM·영역·budget·금지 symbol도 같아야 한다. 실제 명령·데이터·메모리 차이는 FAIL이다.

DFU 예제의 worker별 CI signing key는 다르므로 전체 서명 HEX가 byte 동일하다고 주장하지 않는다.
고정 SDK의 MCUboot imgtool로 서명된 application을 실제 검증하고 인증된 payload digest·version이 같아야 한다.
Boot HEX에서는 그 worker에서 생성한 public DER key가 정확히 한 번 들어간 범위만 따로 표시한다.
그 밖의 실제 load byte 차이나 알 수 없는 차이는 FAIL이며 임의 마스킹·자동 PASS·무한 재시도를 허용하지 않는다.
실패는 원형을 보존하고 원인을 교정한 fresh source/attempt에서 확인한다.

## 완료 경계

H6의 실제 package CI는 producer PASS·세 OS smoke FAIL로 종료했다. Ubuntu archive 호환성,
macOS 검증 코드의 보호된 파일 조회와 Windows 검증 코드의 설치 root 누락을 각각 교정한다.
전체 예제·cross-Host artifact 비교는 `NOT_RUN`이며 fresh 교정 source의 실제 CI가 필요하다.
로컬 통과는 이 gate의 대체 증거가 아니다. 최초 구현은
[316번 기록](<../04_검증 기록/316_HOST_W06_native_package_구현과_검증_착수.md>), 실제 FAIL·교정은
[317번 기록](<../04_검증 기록/317_HOST_W06_H6_설치_FAIL_원인과_교정.md>)을 따른다.

CI에는 물리 upload·Serial·debug·USB lifecycle이 없다. Ubuntu/macOS 실물 검증은 RC1 최종 사용자
gate `NOT_RUN`으로 남긴다. 기존 W06 S19의 PASS46과 명시 수락 #29·40·44, 원형 FAIL·soak는
보존하며 Host 실적과 합산하지 않는다. #29 원인 분석은 사용자 지시로 유예한다.
