# Host 경로·권한·cache·lock — HOST-W05

현재 개발 상태와 실제 판정은 [Host 원장](../../variants/nu54dk/host-readiness.json),
[현행 인계](../HANDOFF.md)와 [314번 기록](<../04_검증 기록/314_HOST_W05_경로_cache_lock_교정과_native_검증.md>)을 따른다.
Windows stable v0.5.0의 공개 지원 경계는 그대로다. 이 계약의 구현·unit PASS로 Ubuntu/macOS의
실제 USB 지원을 선언하지 않는다.

## 경로 입력과 cache

명시한 SDK·toolchain·prerequisite 상태·build cache 경로는 현재 OS의 절대 경로여야 한다.
상대 경로와 빈 명시 override를 작업 directory 기준으로 조용히 바꾸지 않는다. POSIX에서
`C:/ncs` 같은 Windows drive 입력도 거부한다. `XDG_CACHE_HOME`의 빈 값만 XDG 규약에 따라
사용자 기본값으로 처리한다. command argument는 argv로 전달하며 shell 문자열로 재해석하지 않는다.

| Host | 기본 build cache | 기본 SDK 후보 |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%/NU54/c` | `C:/ncs`, 사용자 `ncs`; 설치 package에서는 사용자 경로 우선 |
| Ubuntu | `${XDG_CACHE_HOME:-$HOME/.cache}/NU54/c` | 사용자 `ncs` |
| macOS | `~/Library/Caches/NU54/c` | `/opt/nordic/ncs` |

cache는 단일 Host의 local filesystem에 둔다. filesystem root와 Windows UNC/network cache는
허용하지 않는다. 실제 쓰기·prune·clear 전에 directory 생성과 임시 파일 쓰기를 확인한다.
POSIX에서는 현재 UID 소유와 다른 사용자의 쓰기 금지, 쓰기·탐색 권한도 확인한다. 기존 directory의
mode나 ACL을 자동 완화하지 않으며 권한 오류는 `E_CACHE_PERMISSION`으로 보고한다.

cache key는 기존 SDK·compiler·Core·board 입력에 OS·architecture·distribution·version·native
identity를 함께 포함한다. 다른 Host의 cache를 재사용하지 않고 기존 cache와 FAIL 원본도 삭제하지 않는다.
cache key가 달라지는 것은 firmware 기능 HIL의 source 실적을 승계하는 근거가 아니다.

## 실제 파일 이름과 경계

symlink는 실제 대상 경로로 정규화한다. 파일 이름을 일괄 소문자나 Unicode casefold로 바꾸지 않는다.
실제 case-sensitive filesystem의 `A`와 `a`, `straße`와 `strasse`는 서로 다른 객체로 유지한다.
macOS에서는 `F_GETPATH`로 실제 filesystem spelling과 Unicode alias를 확인하고, 아직 없는 끝부분은
그 이름대로 유지한다. 이 과정에서 device나 FIFO는 열지 않는다. containment와 상대 경로 계산은
같은 정규화 경계를 사용하며 SDK bundle 밖으로 나가는 선언·symlink는 거부한다.

공백·한글·260자를 넘는 경로의 Python 파일 쓰기·atomic replace·lock을 실제로 검사한다.
이는 모든 SDK compiler가 모든 Unicode·긴 경로를 지원한다는 의미가 아니다. Windows의 짧은 기본
cache와 고정 SDK용 설치 package ASCII build 복사 경로는 유지한다. 전체 target compile의 실제
설치 경로 조건과 산출물 비교는 HOST-W06에서 별도 검증한다.

## 배타 lock과 복구

Windows는 기존 전역 kernel mutex 이름을 유지해 이전 worker와 직렬화한다. POSIX는 native
`flock`을 사용하며 cache/session lock은 `/tmp/n54-<UID>/adapter-locks`, 명시 logical probe lock은
`/tmp/n54/adapter-locks`를 사용한다. `TMPDIR`·`TMP`·`TEMP`가 다른 두 process도 같은 대상에
동시에 진입하지 못해야 한다. POSIX의 `/tmp` 실제 OS alias는 경로 정규화로 일치시킨다.

POSIX lock directory·file은 현재 UID와 안전한 mode를 요구하며 symlink·다른 사용자 소유·
공유 쓰기·여러 hard link를 거부한다. 다른 사용자 소유의 probe lock 경로가 이미 있으면 안전하게
실패하며 잠금 없이 진행하거나 권한을 변경하지 않는다. process 종료로 native lock은 회수되고
stale JSON은 진단 정보로만 취급한다. timeout을 성공으로 바꾸지 않는다.

기존 M9 시험의 두 process 직렬화·강제 종료 후 회수·stale metadata·quota prune·부분 산출물 복구와
atomic 공개 회귀를 함께 유지한다. probe 검사는 SHA-256 logical identity만 사용하며 이 시험에서는
실제 장치를 열거나 flash·reset·halt하지 않는다.

## 검증 범위

`test_host_paths_locks.py`, `test_m9_cache.py`, `test_m9_safety.py` 및 prerequisite·Host portability
시험을 사용한다. Windows에서 POSIX 권한·FIFO 검사를 PASS로 계산하지 않는다. case-sensitive
이름 두 개를 생성할 수 없는 filesystem의 해당 검사는 SKIP으로 남긴다. native 세 OS CI의 실제
source·조건·결과를 따로 기록하고 전체 Host 완료와 사용자 USB gate를 구분한다.

macOS API 근거는 [Python 3.12 fcntl](https://docs.python.org/3.12/library/fcntl.html)과
[Apple Libc의 실제 경로 구현](https://github.com/apple-oss-distributions/Libc/blob/main/libdarwin/stdlib.c)을
따른다. 문서 근거가 native 실행 결과를 대신하지 않는다.
