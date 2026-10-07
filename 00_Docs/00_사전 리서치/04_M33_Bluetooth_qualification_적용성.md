# M33 Bluetooth Qualification 적용성

검토일: **2026-10-04** · 대상: **nRF54L15 + nRF Connect SDK 3.4.0 LTS**

## 결론

M33의 Host·SoftDevice Controller·Bluetooth Mesh는 모두 제품 기능에 사용되므로 qualification
적용성을 조사해야 한다. 그러나 Nordic의 nRF54L15 공식 DN 표에서 NCS 3.4.0 LTS의 Host와
SoftDevice Controller는 **`Planned`**이고, Bluetooth Mesh DN은 **기재되어 있지 않다**. 따라서
현재 저장소에는 NCS 3.4.0 조합을 `QUALIFIED`로 표시할 근거가 없다.

이 문서는 component 공개 상태를 기록한 조사 결과일 뿐이다. NU54DK Arduino Core, 예제 또는 이를
사용한 최종 제품의 Bluetooth Qualification 완료를 뜻하지 않는다. 제품 자격 상태는 계속
**`NOT_ASSESSED`**이며, 출시 주체가 자기 회사의 Bluetooth SIG 회원 계정과 Qualification
Workspace에서 제품별 절차를 완료해야 한다.

## 1. 고정 SDK component 상태

Nordic의 [nRF54L15 Bluetooth DN 표](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54l15/page/comp/nrf54l15/nrf54l15_ble_qdid_qual_matrix.html)는
nRF54L15과 호환 Bluetooth stack 조합의 Design Number를 SDK 버전별로 제시한다. 2026-10-04에
NCS 3.4.0 LTS 행을 확인한 결과는 다음과 같다.

| Component | 프로젝트 적용성 | NCS 3.4.0 공식 표 | 기록용 식별자 | 판정 |
| --- | --- | --- | --- | --- |
| Zephyr Bluetooth Host | 적용 | `Planned` | `PLANNED_NO_DN` | 근거 기록 완료, component 자격 완료 아님 |
| SoftDevice Controller | 적용 | `Planned` | `PLANNED_NO_DN` | 근거 기록 완료, component 자격 완료 아님 |
| Bluetooth Mesh | 적용 | NCS 3.4.0 행에 DN 미기재 | `NOT_LISTED_NO_DN` | 근거 기록 완료, component 자격 완료 아님 |

표의 `Planned`는 DN이 발급되었다는 뜻이 아니다. 이전 NCS 버전의 DN을 3.4.0에 임의로 복사하지
않으며, 문서 갱신 뒤에도 실제 사용 조합·수정 범위와 Qualification Workspace 판정을 다시 확인한다.
이 상태를 이유로 NCS 3.4.1로 전환하지 않는다. v0.6.0은 계획대로 NCS 3.4.0을 유지하고 SDK
전환은 v0.7.0의 별도 작업이다.

## 2. Component와 제품 절차의 경계

Bluetooth SIG의 [제품 qualification 안내](https://www.bluetooth.com/develop-with-bluetooth/qualify/)에
따르면 Bluetooth 제품은 시장 출시 전까지 Qualification Process를 완료해야 하고, 공급자나 다른
회원사가 제품 소유자를 대신해 제품을 qualify할 수 없다. 출시 주체가 자기 회원 계정으로 제품을
등록해야 한다.

[Qualification Process 빠른 시작 안내](https://www.bluetooth.com/bluetooth-qualification-process-quick-start-guide/)는
Qualification Workspace가 입력한 design을 바탕으로 다음 경로를 결정한다고 설명한다.

- 단일 기존 Design을 사용하는 Option 1
- 여러 기존 Design을 결합하는 Option 2a
- 그 밖의 새 Design을 만드는 Option 2b

어느 경로가 적용되는지는 이 저장소가 임의로 확정하지 않는다. 현재 NCS 3.4.0 행에는 사용할 수
있는 Host·Controller DN이 없고 Mesh DN도 확인되지 않았으므로, 제품 소유자는 Nordic 표의 갱신
여부와 실제 component/design 조합을 다시 확인한 뒤 Qualification Workspace 또는 Bluetooth SIG
지원 절차에서 필요한 시험과 제출 범위를 결정해야 한다. 새 design에 시험이 요구되면 최신 TCRL과
[공식 qualification 시험 도구 안내](https://www.bluetooth.com/develop-with-bluetooth/qualify/qualification-test-tools/)를
따른다.

## 3. 저장소 기록 계약

W06 증거의 qualification 세 행은 다음 의미로만 기록한다.

| 필드 | Host | Controller | Mesh |
| --- | --- | --- | --- |
| `applicability` | `applicable` | `applicable` | `applicable` |
| `component_status` | `EVIDENCE_RECORDED` | `EVIDENCE_RECORDED` | `EVIDENCE_RECORDED` |
| `component_version` | `NCS 3.4.0 LTS` | `NCS 3.4.0 LTS` | `NCS 3.4.0 LTS` |
| `design_identifier` | `PLANNED_NO_DN` | `PLANNED_NO_DN` | `NOT_LISTED_NO_DN` |
| `product_status` | `NOT_ASSESSED` | `NOT_ASSESSED` | `NOT_ASSESSED` |
| `example_status_implied` | `false` | `false` | `false` |

`EVIDENCE_RECORDED`는 공식 페이지의 현재 상태를 증거로 남겼다는 뜻이며 `QUALIFIED`의 동의어가
아니다. 예제의 compile/runtime PASS, scripted peer PASS, component DN, 제품 qualification은 서로
승격하지 않는다. 공식 표가 바뀌면 조회일과 정확한 DN을 새 evidence에 기록하되 과거 evidence를
소급 변경하지 않는다.

제품 공개 전에 남는 소유자 절차는 다음과 같다.

1. 제품명·모델·출시 주체와 Bluetooth SIG 회원 계정을 확정한다.
2. 출시 시점의 Nordic DN 표와 실제 NCS/component 변경 범위를 다시 확인한다.
3. Qualification Workspace에서 design을 지정하고 생성된 시험·서류·수수료 요구를 이행한다.
4. 제출·검증 완료 결과를 Qualified Product Database에서 확인한다.

이 네 단계는 M33-W06 기능 회귀의 PASS 조건이 아니며 자동으로 완료 처리하지 않는다. 최종 공개
승인과 제품 qualification은 각각 별도 사용자·제품 소유자 절차다.

## 4. 기준 문서

- Bluetooth SIG, [Qualify your product](https://www.bluetooth.com/develop-with-bluetooth/qualify/)
- Bluetooth SIG, [Bluetooth Qualification Process quick start guide](https://www.bluetooth.com/bluetooth-qualification-process-quick-start-guide/)
- Bluetooth SIG, [QPRD v5, 2026-04-21](https://www.bluetooth.com/download/qprd-document/)
- Nordic Semiconductor, [nRF54L15 Bluetooth DNs](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54l15/page/comp/nrf54l15/nrf54l15_ble_qdid_qual_matrix.html)
