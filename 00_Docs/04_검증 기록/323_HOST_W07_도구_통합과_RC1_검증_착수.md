# HOST-W07 도구 통합과 RC1 검증 착수

기록일: 2026-11-10. Host6/8, HOST-W07 준비 중이며 완료 판정은 아니다.
앞선 [322번](322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md)의 H12 기술 마감과 구분한다.

## W06 문서 마감

문서 전용 source `b6169b9af6d3b23d9afd530cc6d4ffc849ec86e5`는 현행 문서·원장34개를 갱신했다.
전체528Markdown UTF-8/local-link(`32954d/exit0`)·CI 계약46(`bba641/exit0`)을 통과했다.
해당 exact source의 [software CI42826873833](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42826873833)는
실제9/9 성공·skip0으로 종료했다(`98d825/exit0`).

중첩 README·Host readiness 경로가 자동 native workflow를 요청해 문서 source의 중복 실행3개를
취소했다(`103f09/exit0`). H12 원형 run은 취소하지 않았다. 취소된 build-only의 aggregate는
upstream 미완료 거부로 failure1을 남겼으며 compile 실패나 PASS로 바꾸지 않는다.
원형 terminal·취소 요청은 `D:/w06/control/host-w06-closure-*.json`에 보존한다.
W07에서는 문서 경로의 과도한 재build 분류와 workflow 경로 제외 순서를 교정한다.

## W07 제품 통합

- Windows는 atomic Job List, POSIX는 새 session group으로 실행한 child를 유한 소유한다.
  timeout·중단의 부분 출력과 실제 exit를 보존하고 cleanup 미확인 상태를 PASS로 만들지 않는다.
- Build Adapter upload는 기본180초·최대1800초 제한, `--probe-sha256`, 기존 manifest·SDK identity·
  공통 lock·sector program·no recover/unlock 정책을 유지한다.
- 새 `host-check.py`는 비식별 inventory·SerialEcho 두 번 open/close·ELF halt/resume·Blink GPIO 읽기·
  두 NUS 역할의 양방향 nonce를 검증한다. 실제 cable 재연결과 광학 LED 검증은 구분한다.
- native lifecycle·RC kit 도구는 source별 archive를 대조하고 고정 관리 Python/CLI로 단계별 실행한다.
  모든 예제용 선택은204cold·대표4warm·profile 거부9개이며 대표4만 수행한 결과와 구분한다.
- native push의 private version을 RC1으로 맞춰 같은 source를 host.1과 rc.1로 불필요하게 중복
  검증하지 않는다. 초기 source의 기존 FAIL과 actual PASS는 보존한다.

실행·OS7행·실패 수집 계약은 [Host RC1 절차](<../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)를 따른다.

## 현재 개발 단계의 실제 검사

| 범위 | 실제 결과 | tool |
| --- | --- | --- |
| 제품 소유 process | 8PASS — 실제 child/grandchild7·정리 실패 수집 주입1 | `d36f3a/exit0` |
| upload process·선택·실패 log | 6PASS | `d422a5/exit0` |
| Serial 선택/재열거·NUS 모델·debug resume | 6PASS, 물리 PASS 아님 | `6db5d9/exit0` |
| 기존 flash 안전 계약 | 20PASS, 후속 전체 회귀는 별도 | `0639fd/exit0` |
| 기존 lock·실패 처리 | 17PASS, 후속 전체 회귀는 별도 | `93415c/exit0` |
| 문서/build 분류 | 5PASS | `989259/exit0` |
| 새 readonly 장치 inventory | probe3·serial6, flash/reset/halt0 | `102c82/exit0` |

위 실적은 통합 중인 작업본의 해당 byte 범위다. RC exact source의 최종 CI 실적으로 합성하지 않는다.
Native 세 OS·전체204예제·실제 image 비교와 Windows physical 회귀·kit 실행은 fresh source에서
별도로 검증해야 한다. RC kit 생성·사용자 실물 gate·M33-W07 완료는 아직 `NOT_RUN`이다.

## SDK 준비 시도 보존

별도 `D:/w06/host-w07/sdk`에 같은 고정 SDK를 설치한다. 기존 `D:/w06/ncs`와
`C:/ncs/toolchains/dcbdc366a1`은 입력 전용이다. SDK version·bundle은 바꾸지 않는다.
첫 설치 시도의 다운로드를 agent가 중단했다(`f608c9/exit-1`). 중단 직전 실제 부분 파일은
708,837,376B였으므로 앞선 0B 정체 판단은 잘못됐으며 이를 정정했다. SDK 결함으로 분류하지 않는다.
원형 부분 파일과 hash·중단 기록을 보존하고 같은 공식 byte를 이어받았다.
Windows toolchain 전체 size/SHA-256은 통과했으며 NCS 원형은 계속 수집 중이다.
정본은 `D:/w06/control/host-w07-prefetch-pinned-a002-20261110.json`이며 입력 검증을 설치 PASS로 세지 않는다.

원래 W06 S19 actual46PASS·명시 수락 #29·40·44·FAIL·soak·private11831/public3·완료 TODO6은
동결한다. #29 분석은 유예한다. w06 PAUSED 요청 유지·예약 생성/재활성화 없음. 단일 writer를 유지한다.

## 후보 고정 전 추가 검사

고정 A001 작업본의 전체 Host gate는 실제 `c7bb51/exit0`으로 종료했다. 278개 unittest suite의
reported2470개·조건부 skip9개이며 device-free fixture marker를 물리 HIL PASS로 세지 않는다.
변경29개 파일의 검사 전후 byte가 같았고 전체 원형을 별도 보존했다(`0e78a3/exit0`). 정본은
`D:/w06/control/host-w07-full-host-completion-a001.json`이다.

그 뒤 kit의 검증 전 import를 제거하고 최초 진입점 hash 확인·필수 원형 목록을 보강했다.
source archive는 같은 exact Git source의 tooling·현행 안내만 포함하며 제품 예제는 검증한 Core에
포함된다. Serial의 명시적 DTR/RTS 값과 전체 child 제한도 분명히 했다.
이 후속 범위의 원형 변조·누락 거부2개(`09488a/exit0`)와 Serial/debug/NUS 계약6개
(`19e9a9/exit0`)를 fresh 검사했다. 앞선 전체 gate를 후속 변경의 exact 최종 CI로 표시하지 않는다.

시스템 Git 없는 전이 입력 검사 A001은 진단용 JSON 폴더에 원형 ZIP이 없어 실패했다
(`b612eb/exit1`). 검사 입력 경로 오류이며 target/SDK 실패가 아니다. 원형 FAIL을 보존하고,
이미 보존·검증한 H12 artifact13754777154에서 완전한8개 입력을 새 폴더에 만들었다.
fresh A002의 연속2회 원형 검증은 `f75caf/exit0`이다. H12는 전이 입력일 뿐 새 RC 실적이 아니다.

세 OS CLI1.5.1 원형은 공식 pin의 size/SHA-256을 통과했다(`2da55b/exit0`). Windows toolchain은
전체 원형 검증 완료, NCS 원형 다운로드는 별도로 진행 중이다. RC exact source의 native CI·
Windows regression·kit end-to-end 실행·사용자 OS7행의 실물 gate는 여전히 별도 미완료다.
