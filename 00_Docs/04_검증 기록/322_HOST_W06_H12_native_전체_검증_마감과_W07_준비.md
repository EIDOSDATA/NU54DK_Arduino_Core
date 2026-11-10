# HOST-W06 H12 native 전체 검증 마감과 W07 준비

기록일: 2026-11-10. HOST-W01~W06 완료 **6/8**, HOST-W07 준비 중이다.
Exact 기술 source는 `6364a1d9955f79fef0ac1f3219883a9d77e24f32`(H12)다.
문서 마감 commit과 후속 W07 source에 H12 실적을 이월하지 않는다.

## 같은 H12 source의 실제 종료 결과

| gate | run | 실제 결과 |
| --- | --- | --- |
| native Boards Manager | [42797342852](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42797342852) | 30성공·0skip, producer·smoke3OS·전체24worker·최종 비교 |
| native prerequisite | [42797342944](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42797342944) | 3OS 성공·0OS skip, unit222 reported·216PASS·조건부6skip |
| software | [42797950721](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42797950721) | 9성공·0skip |
| build-only | [42797342920](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42797342920) | 6성공·0skip |

Windows x86-64·Ubuntu AMD64·macOS Apple Silicon 각각 실제 고정 SDK 설치, package 설치,
955개 Core 파일·24개 library·204예제 발견, **204개 positive compile·9개 잘못된 profile 거부**를
통과했다. 합계612compile·27negative이며 SDK당 compile1·Ninja2·8shard/OS 조건을 유지했다.

세 OS의 **204개 실제 image 비교**는 ELF의 ARM load·할당 section·정규화 HEX·memory/budget·
금지 symbol을 검사했다. DFU 서명·인증 payload·version도 검증하며 알려진 정확한 public key
범위만 비교에서 정규화했다. 임의 차이를 가리거나 build PASS를 runtime PASS로 확대하지 않았다.

## 원형 보존과 독립 로컬 감사

native 원형 ZIP **57/57**을 전체 다운로드해 GitHub source·size·digest와 대조했다.
native30개 job의 raw/clean log, software9개 raw log와 81개 clean source checkpoint도 보존했다.
24worker의 실제 ELF·HEX·manifest·compile log·negative marker를 로컬 재검증했다.

- 최종 비교 원형 artifact: `13766983440`, ZIP SHA-256
  `228da6313af42bb43a0c570eb9a48aa854d96124f29f2947f1d6889e2b893b11`.
- 로컬 전체 재집계: `D:/w06/control/host-w06-h12-full-local-aggregate-20261110.json`,
  실제 `37b006/exit0`. 204비교 PASS, 관측 시각을 제외한 JSON이 원격 최종 집계와 동일하다.
- 기술 마감 감사: `D:/w06/control/host-w06-h12-technical-closure-20261110.json`,
  실제 `4480d7/exit0`. 57개 ZIP 목록·hash, terminal4run, frozen TODO6과 보존 경계를 고정한다.
- private Core package SHA-256:
  `2556d00a1bb7435c1c47d72ce750a4973fc3a84b2354158bf9b48981fd5241d6`.

버전 `0.6.0-host.1`은 **UNPUBLISHED_PRIVATE_CI_ONLY**다. 공개 package·tag·Release를 만들지 않았다.
CI Windows Server2025는 사용자 Windows10/11 물리 지원 증거가 아니다.

## 과거 실패와 W06 보존

[321번](321_HOST_W06_H11_Windows_macOS_통과와_Linux_source_진단.md)의 H11 Linux와
H7 producer source guard 실패의 세부 조건은 여전히 **미확정**이다. H12는 판정 조건을 유지하고
진단을 추가했으며 strict guard가 통과했다. H12 성공으로 과거 원인을 확정하거나 FAIL을 고치지 않는다.
H6~H11 source별 실적·실패 원형은 해당 기록과 readiness의 attempts에 그대로 남긴다.

원래 M33-W06 S19 `b46ce5708a17da788644d3e87021b5ab54a6e4c6`는 실제 PASS46개와
명시 수락 #29·40·44를 구분한다. strict49PASS를 주장하지 않는다. private11831·public3·soak·
FAIL·완료 TODO6을 보존하며 firmware/library/template/HIL 영역은 S19 대비 변경0이다.
신규 HIL은0이며 #29 원인 분석은 사용자 지시로 유예한다.
w06 PAUSED 요청 유지·예약 생성/재활성화 없음. 실행 중인 자동점검 상태를 새로 확인했다는 뜻은 아니다.

## 다음 순서와 미완료 gate

1. HOST-W07: upload의 유한 timeout·소유 process tree 정리, probe identity/lock,
   serial·ELF debug·lifecycle 도구와 명령·실패 수집 절차를 통합한다.
2. 별도 고정 SDK 작업본에서 Windows 회귀를 수행하고 비공개 M33-W07 RC1 kit를 준비한다.
3. RC1의 exact source/package에 사용자 Ubuntu/macOS 실물 설치·USB upload·serial·debug·
   갱신/재설치/제거 결과를 결합한다. 현재 이 gate는 **NOT_RUN**이다.
4. HOST-W08 지원표·문서와 M33-W07을 마감하고 M33-W08 공개 승인 단계로 진행한다.

도구·Windows·RC1 준비를 먼저 완성한다. 사용자 실기 전 Host8/8 또는 정식 다중 OS 지원 완료로
표시하지 않는다. 공개·tag·Release·main 승격은 별도 사용자 승인 단계다.
