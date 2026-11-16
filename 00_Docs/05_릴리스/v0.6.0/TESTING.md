# v0.6.0 검증 근거와 재실행 범위

기준일: 2026-11-16. **새 제품 검증을 실행하지 않은 HOST-W08 문서 정리**다.
전체204·기존 HIL은 반복하지 않았으며 Mac 실기 두 행은 `NOT_RUN`이다.

| 증거 단위 | exact source | 범위·색인 |
| --- | --- | --- |
| HOST-W06 H12 | `6364a1d9955f79fef0ac1f3219883a9d77e24f32` | 당시 세 native OS 전체 빌드와 image 비교, [322번](<../../04_검증 기록/322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md>) |
| C5 최신 전체 기준선 | `5ee7c10368b554ca23d68f8f82e39308b91df6de` | NUS 교정 후 전체204/OS·profile 거부9/OS, [328번](<../../04_검증 기록/328_HOST_W07_C5_필수_자동검증과_사용자_OS_gate.md>); Windows11 후속 실기는 [329번](<../../04_검증 기록/329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md>) |
| C10 WSL2 | `4890f697ab80dfed3cff62bd42acc42b0f3e1a34` | Ubuntu24 기준선·변경 영향,26 버전 호환성, [330번](<../../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>) |
| C11 Mac software | `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa` | [CI43760678488 attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43760678488),5/5SUCCESS, [331번](<../../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>) |
| C11 문서 후속 | `4d7dff44666b0ab1c01311bf6350dd675d6f8e9e` | [CI43763189943 attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43763189943),8PASS+범위SKIP1; 제품 검증 source와 분리 |

C11 Mac26·27 각각 설치960파일·204예제 발견, 대표4cold/4warm, 관련 unit67PASS·조건부SKIP3이다.
204예제 발견을204개 compile로 세지 않는다. 같은 C11의 두 Mac 대표 BIN·HEX 실제 byte는 일치했다.
각 OS·source·run·attempt와 원본 artifact를 유지하며 서로 다른 실행을 단일 동일-source 결과로 합성하지 않는다.

## release gate 연결

| 계약 case | 지금 연결할 수 있는 근거 | 최종 잔여 |
| --- | --- | --- |
| `M33-PACKAGE-01` | C5 package 재현·설치 발견·전체 기준선, C11 kit/producer 원본과222파일 hash 감사 | 정식 배포 source·version·plan·archive hash와 재현 결과 고정 |
| `M33-INSTALL-01` | Windows11 C5, WSL2 C10, Mac software C11을 [지원표](SUPPORT_MATRIX.md) 범위로 연결 | Mac 실제 장치·IDE와 최종 package의 설치 전이 영향 확인 |
| `M33-RELEASE-01` | [공개 전 체크리스트](RELEASE_CHECKLIST.md) 준비 | exact plan 승인·게시·공개 URL 설치 모두 미실행 |

[m33-release-readiness.json](../../../variants/nu54dk/m33-release-readiness.json)은 생성된 strict 기능/원형 case 원장이다.
그 안의 W07 미착수·package/install `NOT_RUN`을 현재 Host 준비가 없다는 뜻으로 읽지 않는다.
현행 진행은 [host-readiness.json](../../../variants/nu54dk/host-readiness.json)이 소유하며, 최종 case 판정은
실제 종료 근거를 갖춘 뒤 생성원본과 함께 갱신한다. 이번 문서 작업은 strict 원장을 소급 승격하지 않는다.

## 필요한 때에만 확대

OS 버전이나 문서 SHA만 달라졌다는 이유로 전체 빌드를 반복하지 않는다.
SDK/compiler·firmware·compile 설정이 바뀌거나 실패 분석에서 영향이 확인되면 해당 범위만 재검증한다.
전체 영향이 확인된 경우에만 전체 시험을 배정한다. 기존 FAIL과 중단 기록은 새 PASS로 덮어쓰지 않는다.
