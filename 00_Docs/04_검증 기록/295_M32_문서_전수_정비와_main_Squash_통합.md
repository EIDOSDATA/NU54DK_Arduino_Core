# 295. M32 문서 전수 정비와 main Squash 통합

작성: 2026-10-03. 사용자는 M32 완료 후 전체 문서 검토·불필요한 내용 정리·가독성 개선,
커밋·푸시, 이력 squash와 main 갱신을 요청했다. 이 기록은 문서 정비 범위와 통합 방식을 고정한다.

## 기준선과 최종 상태

| 항목 | 기준 |
| --- | --- |
| 시작 branch / source | `Dev-0.6.0-M32` / `49099e74fec60566f8708e8398d6c1def86dd6d6`, clean |
| 통합 전 main | `1049caf77a997338373f8a98a57a4888cd33693b` |
| 시작 시 main 이후 개발 이력 | 118 commit; 이번 문서 마감 commit은 별도로 추가 |
| M32 | W01~W12 12/12 완료; 시험군 23 PASS + `M32-ACL-01` 1 HOLD / 24 |
| ACL 제한 | 고정 SDK에 Host TX 경로가 없어 unsupported/HOLD; 기능 PASS 아님 |
| 다음 작업 | M33-W01, M33은 0/8 미착수; HOST-W04~W08 사용자 보류 |
| 제품·SDK | stable/source version 0.5.0, NCS 3.4.0; v0.6.0 미공개 |

최종 구현 `49099e74…`의 [Software Gates 37099299097](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37099299097)는
exact SHA에서 9/9 성공했고 이번 정비에서도 조회해 확인했다. W11 `94f02544…`의 HIL·signed MDFU·
1,800초 soak는 [286번](286_M32_W11_software_회귀와_HIL_soak_blocker.md), W12 감사와 adaptive BLE clock 교정은
[287번](287_M32_W12_정합성_감사와_후속_인계.md)이 소유한다. 새 문서/squash SHA의 CI와 구분한다.

## 문서 정비 범위

시작 시 본 저장소 Markdown 477개를 목록화했다. 이 기록 추가 후 478개와 고정 board submodule의
Markdown 6개, 총 484개를 감사 원장에서 추적한다. 경로·UTF-8·내용 hash·분류를 전수 확인하고,
현행 설명과 변경 문맥은 작업별 담당 검토로 대조한다. 과거 원시 실기 결과·외부 URL·하드웨어를
다시 시험한 것은 아니다. 파일별 방법과 보존 사유는 [문서 감사 원장](../document-review.json)에 남긴다.

- M32가 8/12·중단·실기 잔여라고 적힌 현행 표·본문을 12/12 완료와 M33 인계로 맞췄다.
- README는 stable 설치와 미공개 개발 소스를 구분하고, HANDOFF는 다음 작업과 완료 증거를 먼저 보여 준다.
- AGENTS·기여 안내·문서 목차에 반복된 과거 통합 경과와 실패 설명은 원본 링크로 줄였다.
- 검증 기록의 제목·색인·최신 안내를 보완하되 과거 source와 PASS/FAIL/HOLD/NOT RUN 원문은 보존했다.
- 감사 원장의 오래된 M32 상태·검토 날짜·파일 목록·hash를 갱신했다.

독립 문서 파일은 삭제하지 않았다. 완료 TODO·번호별 기록·이전 릴리스 문서는 고유한 결정 또는
재현 근거를 갖는다. 불필요한 중복 문단과 완료된 작업의 재개 지시는 본문에서 제거했고 변경 전
내용은 Git으로 복구할 수 있다. 원시 evidence·공개 자산·board submodule·서드파티 원본은 보존한다.

## Squash 범위와 보존

문서 정비를 `Dev-0.6.0-M32`에 commit·push한 다음, 기존 main을 parent로 전체 완료 상태를
**한 개의 squash commit**에 담는다. Squash 결과와 문서 마감 branch의 Git tree가 같아야 한다.
기존 main 이력은 유지하므로 원격 main 갱신은 일반 fast-forward push다.

`Dev-0.6.0-M32`에는 원본 단계별 커밋과 문서 마감 이력을 남긴다. 그 branch를 다시 main에
일반 merge하지 않으며 후속 개발은 새 main에서 분기한다. 기존 공개 tag·Release·asset,
`Release-0.5.0`과 stable catalog는 유지한다. 원본 SHA 목록·통합 parent·불변 파일은
[이력 보존 원장](evidence/m32-main-squash-20261003/history-manifest.json)에 고정한다.
기존 checkout 갱신은 [기여 안내](../../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)를 따른다.

## 검사와 결과 확인

문서 링크·heading·hash, 생성 문서, CI 계약, M31/M32 원장과 변경 범위를 검사한다.
실행 결과는 [감사 원장 checks](../document-review.json)에 기록한다.
이번 문서 작업으로 firmware·SDK·board를 변경하거나 새로운 HIL을 실행하지 않는다.

이 문서를 포함하는 commit 자체의 SHA는 본문에 자기 참조로 고정할 수 없으므로 Git ref와
Actions의 `head_sha`로 확인한다. 문서 commit 수동 Software Gates와 main push 후 Software Gates는
각각 완료 상태를 확인하며, 실행 전·진행 중인 검사를 성공으로 기록하지 않는다.
최종 SHA·원격 일치·Git tree 동일성과 실제 CI 결과는 작업 완료 보고에서 함께 확인한다.
