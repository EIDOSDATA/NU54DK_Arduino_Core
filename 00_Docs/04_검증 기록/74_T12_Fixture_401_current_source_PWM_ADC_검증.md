# T12 Fixture 401 current-source PWM→AIN0 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | T12의 Fixture 401 단독 한 cycle; T12 전체는 부분 완료 |
| Exact Core | `a12e444cfb5ef47471c0e0d436f082acfd200c19` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3h` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 118.09초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz** |
| 결과 | 첫 실행 **48개 기능 PASS**, 실기 연속 26.5초 |
| 다음 | Fixture 402 PWM→AIN1 전원 OFF 결선 변경과 새 사용자 확인 |

## 사용자 지시와 exact 입력

[73번](73_T11_Fixture_301_current_source_TWI_회귀.md)에서 current-source T11 단독 회귀를 완료했다.
이후 Fixture 401의 두 선과 스위치·전원 조건을 안내했고, 사용자가 T12임을 확인한 뒤
“T12가 맞다면 이제 시작하도록 해.”라고 지시했다. 이를 직전 결선 안내에 따른 시작 지시로 해석한
근거와 11:37:59 UTC의 기록 시각을 [체크포인트](evidence/t12-fixture401-a12e444/checkpoint.json)에 보존했다.
[확인서](evidence/t12-fixture401-a12e444/confirmation.json)는 catalog revision 2, 두 UID SHA·role·exact source·HEX와
조건을 결합한다. 원래 시각을 갱신하지 않고 30분 이내 실행했다. 사용자 지시의 문맥에 따른
결선 확인이며 소프트웨어가 스위치·전기적 연결을 직접 계측했다는 뜻은 아니다.

| 신호 | A/DUT, role 1 | B/peer, role 2 |
| --- | --- | --- |
| B PWM → A AIN0 | P2-12 / P1.04 | P4-12 / P1.14 |
| 공통 GND | P2-30 | P2-30 |

이전 TWI SCL은 양쪽에서 제거하고 위 두 선만 사용하는 조건이다. 양쪽 DAP UART 분리·SWD 연결,
동일 I/O 전압·각자 USB 전원을 유지하며 외부 저항·보드 사이 전원 rail·다른 신호 출력은 없다.
[USB 재식별](evidence/t12-fixture401-a12e444/usb-inventory.json)은 A D/COM5·COM6, B E/COM7·COM8과 정확한 두 UID를 확인했다.
Controller는 B/role 2만 사용했고 역할을 반전하지 않았다.

[build evidence](evidence/t12-fixture401-a12e444/target-build-evidence.json), [산출물 색인](evidence/t12-fixture401-a12e444/target-artifact-index.json),
[exact image](evidence/t12-fixture401-a12e444/exact-images.json)에 clean source의 두 역할·HEX/ELF·설정·빌드 기록 hash를 보존했다.
NCS v3.4.0, bundle dcbdc366a1, GNU Arm 14.3, bundled Python과 pyOCD 0.42.0을 사용했다.
[직전 T11 입력 대조](evidence/t12-fixture401-a12e444/build-input-comparison.json)에서 두 역할의 저장소 컴파일 소스,
설정·source membership·메모리가 직전 9a63251과 동일하다. Embedded commit identity는 별도 유지한다.
이번에는 제품 코드·시험 앱·canonical runner를 변경하지 않았다.

## 실제 실행과 독립 대조

| 조합 | 범위 |
| --- | --- |
| PWM instance | 20, 21, 22 |
| 출력 channel slot | 0, 1, 2, 3을 P1.14로 순차 route |
| PWM sequence 입력 | top 1021, compare 512, individual load |
| SAADC | AIN0, 12-bit, gain 1/4, 수동 SAMPLE |
| 버퍼 | 32/256 samples × 단일/이중 DMA buffer |
| 전체 조합 | 3 × 4 × 2 × 2 = 48 |

각 vector는 generator/receiver 준비, PWM 시작, SAADC SAMPLE, DMA 완료와 전체 샘플 읽기를
수행한다. 준비·시작·완료 상태와 오류 0, 요청 길이·완료 sample 수, HIGH 관측을 판정한다.
버퍼 반환 이벤트에서 buffer pointer/길이를 확인하고 완료 mask로 단일·이중 버퍼를 구분한다.
전체 **10,368 samples**를 읽어 vector별 SHA-256와 최솟값·최댓값을 기록했다.
48개 모두 LOW 영역(raw <256)과 HIGH 영역(raw >256)을 관측했으며 전체 raw 범위는
-220~3768이었다. 이 값은 교정 전압이나 ADC 정확도 보증이 아니다.

매 vector 뒤 두 역할 모두 signal disarm `[0]`을 확인했다. **Cleanup 48개·campaign 2개**를
기능 PASS와 분리했으며 journal은 총 98개다. Cleanup의 동일 논리 ID는 바로 앞 기능 record와
순서로 대응한다. [독립 감사](evidence/t12-fixture401-a12e444/results-audit.json)는 별도 작성한 48개 조합과 고유 기능 ID,
전체 순서·길이·상태·해제 결과, final JSON과 journal 일치, exact image/UID·10 MHz를 확인했다.

| 원본 | SHA-256 |
| --- | --- |
| [결과 JSON](evidence/t12-fixture401-a12e444/fixture401-attempt1.json) | `41d4244d954666f9912668dd2c9f27f58426d8b9f342c83e64eaf4216cd0de3a` |
| [journal](evidence/t12-fixture401-a12e444/fixture401-attempt1.json.jsonl) | `173375caa50152429388af63e6b84262cbd87630f563c38ad8bab3ed973c7725` |

두 보드 flash는 첫 시도에 통과했다. Sector erase·`auto_unlock=false`이며 mass erase/recover,
SWD 속도 하향과 재시도는 없었다. [종료 read-only 확인](evidence/t12-fixture401-a12e444/postflight.json)은 reset/flash 없이
CPUID `0x411fd210`, 전체 40-byte commit과 role을 2/2 검증했다. CPU snapshot은 A SLEEPING·B SLEEPING이다.

사후 감사 초안은 flash metadata의 필드명을 잘못 읽어 `KeyError`가 났다. 실제 schema의
`frequency_hz`로 바로잡아 감사만 다시 수행했다. [초안](evidence/t12-fixture401-a12e444/audit_results_initial.py)과
[작성 교정 기록](evidence/t12-fixture401-a12e444/authoring-correction.json)을 보존했으며 firmware·HIL 결과 수정이나
실기 재실행은 없었다.

## 판정 범위와 남은 검증

401 PASS는 PWM 출력 route와 외부 AIN0 수집·DMA 완료·정지를 확인한다. 현재 oracle은 HIGH와
sample 수를 필수 판정하며 LOW 관측은 저장된 min/max에서 추가 확인한 사실이다. PWM 주기·듀티를
peer capture로 측정한 결과는 아니다. 별도 timer/event/capture, ADC calibration·채널 순서 등
T12 전체 요구와 아직 연결하지 않은 경로를 이 48개로 완료 처리하지 않는다.

다음 analog 402·403·404·408과 QDEC 420·I2S 430·PDM 440, T13 동시성·600/7,200초 soak,
T14~T15 판정, T16~T18 통합과 R14/RC·공개가 남아 있다. M25 physical gate와 readiness는
미완료 상태를 유지한다. GitHub Actions는 미확인이며 이전 local full software 근거를
새 frozen RC의 PASS로 바꾸지 않는다. 기존 실패·SDK·board·공개 자산과 과거 기록은 보존한다.

## 문서와 증거 검증

활성 문서 9개에 결과와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 183개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는 필수 16개 중
blocker 8개를 유지한다. [software 검사 기록](evidence/t12-fixture401-a12e444/software-verification.json)에
canonical 명령과 log hash를 보존했다. 제품 코드 변경이 없어 이전 full Host·package·전체 target
결과는 해당 source의 역사 증거로 유지한다.

이번 실행·준비 입력 32개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·
UID 비공개를 검사했다. 실제 시험 source와 최종 문서 commit을 구분하며 commit·main push와
checkout·board·SDK·작업 프로세스 종료 점검은 최종 작업 산출물에 기록한다.

## 다음: Fixture 402 PWM→AIN1

양쪽 USB를 먼저 분리한다. **A 쪽 신호 끝만 P2-12에서 P2-11/P1.05/AIN1로 이동**한다.
B P4-12/P1.14와 양쪽 P2-30 GND는 유지한다. DAP UART 양쪽 분리·SWD 연결 상태,
동일 I/O 전압·각자 USB 전원·다른 신호/전원선 없음 조건은 같다.
재연결 완료 확인 뒤 새 exact source/확인서를 준비하며 이번 실행에서는 402를 시작하지 않았다.
[다음 핀맵 대조](evidence/t12-fixture401-a12e444/next-wiring-audit.json)에 catalog와 커넥터 원본의 대응을 보존한다.
