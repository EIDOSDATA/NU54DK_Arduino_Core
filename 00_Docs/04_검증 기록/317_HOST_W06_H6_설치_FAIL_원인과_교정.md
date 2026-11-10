# HOST-W06 H6 설치 FAIL 원인과 교정

기록일: 2026-11-10. Host 완료5/8, HOST-W06 진행 중이다.
Exact H6 source는 `2f656943318f66a33627cd1905d4488d2d78bc0b`이며
[316번](316_HOST_W06_native_package_구현과_검증_착수.md) 이후의 실제 실행이다.

## 실제 결과와 원본 보존

[Package CI42774982286](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42774982286)는
producer 성공·세 OS smoke 실패로 종료했다. 전체204개 예제와 artifact 비교는 실행되지 않았다.
Producer의 같은 source package·sidecar 두 번 동일 및 검증은 통과했지만 설치 gate 성공으로 세지 않는다.

| Host | 실제 최초 실패 | 원인 구분·교정 |
| --- | --- | --- |
| Ubuntu | Python tool 압축 해제 중 `terminfo/1/1178` symlink placeholder의 부모 없음 | 공식 tar의 symlink-only 부모와 고정 CLI 1.5.1 압축 해제기의 호환 문제. 부모 directory 우선 파생 archive 생성 |
| macOS | `/usr/sbin/weakpass_edit` 조회의 Permission denied | CI 검증 코드 문제. 관련 없는 보호된 OS 관리 파일 조회 실패는 건너뛰고 Python/Git fallback 금지는 유지 |
| Windows | 설치 뒤 재검증이 `C:/Users/runneradmin/ncs/toolchains/…`를 선택 | CI 검증 코드 문제. 설치는 `D:/n6/ncs`에서 진행됐으므로 재검증에도 같은 `--install-root`를 명시 |

Windows의 초기 Python은 실제3.12.16·isolated1로 실행됐고 설치 상태의 SDK·도구 정보가 기록됐다.
재검증 호출에서 실패했으므로 전체 consumer PASS로 올리지 않았다. 이 세 실패는 target firmware나
기존 #29의 원인 판정이 아니다. #29 분석·새 HIL은 계속 유예한다.

원본 ZIP 전체 size·원격 digest·source binding을 검증해 `D:/w06/control/host-ci-artifact-ID`에 보존했다.

| Artifact | ID | 원형 ZIP SHA-256 |
| --- | --- | --- |
| Windows FAIL | 13743672753 | `6eba6fb4097758b217bdd6160f79d131c66269657d8320158d400bf649f835c0` |
| Ubuntu FAIL | 13743432599 | `9da08b90161d992074f547ef8eea25539e2960748bae7e0bf156e26a733fb13b` |
| macOS FAIL | 13743781162 | `574723eca97e3a68a7e1969dfcec154565fb9442213b4c1e5c8c94acbbaf1c7b` |
| Producer PASS | 13743113469 | `b20f851298e9070b92e23903501bead5b33bc41ba3a08bd1d2fc534193f06a5f` |

원문 job log도 별도 raw/clean hash와 함께 보존했다. 감사 정본은
`D:/w06/control/host-w06-h6-source-audit-20261110.json`(`2c206d/exit0`)이다.

별도 [H6 prerequisite CI42774982248](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42774982248)는
세 OS의 실제 SDK 설치·저장 상태 재검증 모두 통과했다. Source·platform pin·backend hash·SDK/Zephyr
revision·bundle·실제 도구 출력을 원문과 대조했다. Unit은 OS별67개씩, 총201개 중195 PASS·조건부 SKIP6이다.
이 성공을 package smoke의 실패 칸에 합성하지 않는다. H6 software/build-only는 별도 추적한다.

## 교정 개발 검증

Python 원형 tar의 parent directory entry 부재와 symlink 의미를 실제 확인했다.
CLI의 [고정 dependency](https://github.com/arduino/arduino-cli/blob/v1.5.1/go.mod) 및
[placeholder 구현](https://github.com/codeclysm/extract/blob/v4.0.0/extractor.go)을 대조했다.
SDK·Python 실행 파일 byte·mode·symlink 대상을 바꾸지 않고 부모 directory, 원문 notice와
provenance만 추가하는 `USTAR_PARENTS_FIRST_BZIP2_9_V1` 파생 archive를 실제 생성했다.

| 파생 runtime | 보존한 원형 file/link | 추가 notice | 실제 archive SHA-256 |
| --- | --- | --- | --- |
| Linux x86-64 | 4536 | 20 | `8afcd33bc77a094b678905eae791bce1a5b7672a3ba03e40c1eb9771b6279595` |
| macOS ARM64 | 1665 | 20 | `a671849578714176940ffcac2de852474c20301f6a5cc3d53e4f12d1ff9b902e` |
| Windows x86-64 | 3348 | 20 | `d6e1a280b2a743ca03323c603ed7ed2612941318c4b36bddb2a7f0bb913d38a4` |

각 OS 두 번 생성한 archive가 byte 동일했다(`a712fc/exit0`). Linux archive는 별도 CPython 3.12에서도
동일 hash를 재확인했다(`6fa8b9/exit0`). 최초 archive와 파생 byte·receipt는
`host-w06-arduino-bootstrap-a001`, `host-w06-arduino-bootstrap-python312-a002`에 보존한다.
파생 tool의 원본/파생 pin과 license·notice를 구분하고 별도 미게시 asset으로 추적한다.
공개 tag·Release·asset을 생성하지 않았으며 법무 검토를 자동 승인하지 않는다.

교정한 archive·보호된 파일 조회·source/attempt/target artifact 계약 단위 검사는
`d3b81c/exit0`, 보고30개 중29 PASS·조건부 POSIX SKIP1이다. 후속 notice 메타데이터와 설치 root
호출까지 포함한 최종 source는 fresh CI에서 다시 판정한다. 로컬 단위 검사를 실제 설치 PASS로 세지 않는다.

기존 W06 S19의 실제 PASS46 + 명시 수락 #29·40·44, 원형 FAIL·soak·private11831개·public3개와
완료 TODO6개는 보존한다. 자동점검 w06 PAUSED 요청 유지·예약작업 생성/재활성화 없음.
Ubuntu/macOS 물리 USB·Serial·debug·lifecycle은 RC1 최종 사용자 gate `NOT_RUN`이다.

## H7 fresh 실행 후속

교정 source H7 `64b488bfcbe979375ff2c5e2b93e251636a6cf54`의
[native package CI42777568938](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42777568938)는
Ubuntu 단위30개 모두 통과한 뒤 producer의 exact-source 진입 guard에서 실패했다.
실제 세 OS 설치·전체 예제는 아직 재실행되지 않았다. 허용 version·HEAD·작업본 상태를 묶은
기존 메시지만으로 어느 조건이 거부됐는지는 미확정이다. Guard를 완화하지 않고 실제 version·HEAD·
변경 파일 상태를 출력하도록 진단을 보강해 fresh source에서 확인한다.
Job129699560066의 원형 log SHA-256은
`bfd159811bc0f11d2d2adf7e656c4727df2c069fd570095a502267ca3ceaa621`이다.
이 실행에는 producer artifact가 생성되지 않았으며 이를 다운로드 성공으로 만들지 않는다.
