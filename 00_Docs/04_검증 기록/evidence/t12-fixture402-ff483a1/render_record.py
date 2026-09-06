"""! @brief 현재 402 실기와 부분 coverage 증거에서 검증 기록을 생성합니다. """
import json
import re

def make_record(work):
    audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
    coverage = json.loads((work / 'analog-coverage-audit.json').read_text(encoding='utf-8'))
    post = json.loads((work / 'postflight.json').read_text(encoding='utf-8'))
    assert audit['status'] == coverage['status'] == 'passed'
    build = (work / 'build.log').read_text(encoding='utf-8-sig')
    seconds = re.search(r'with no warnings in ([0-9.]+) seconds', build).group(1)
    states = '·'.join(f"{'A' if row['role'] == 1 else 'B'} {row['state']}" for row in post['devices'])
    base = 'evidence/t12-fixture402-ff483a1'
    return f'''# T12 Fixture 402 current-source PWM→AIN1 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | Fixture 402 단독 한 cycle; T12 전체는 부분 완료 |
| Exact Core | `{audit['source']}` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3i` DUT/peer 2/2 build-only PASS, failed/error/warning 0, {seconds}초 |
| SWD | flash·mailbox·종료 read-only 확인 모두 **10,000,000 Hz** |
| 결과 | 첫 실행 **48개 기능 PASS**, 연속 {audit['continuous_elapsed_seconds']}초 |
| 다음 | Fixture 403: A 입력을 P1.05에서 P1.06/AIN2로 이동, 전원 OFF 결선과 새 확인 필요 |

## 결선 확인과 exact 입력

[74번 Fixture 401](74_T12_Fixture_401_current_source_PWM_ADC_검증.md) 완료 뒤 사용자의 요청에 따라
402 결선을 GPIO 번호로 안내했다. 사용자는 “결선 완료 402 테스트 시작해.”라고 확인했다.
[체크포인트]({base}/checkpoint.json)와 [확인서]({base}/confirmation.json)에 원래 시각
11:52:52 UTC, catalog revision 2·두 UID SHA·role·exact source·HEX hash와 조건을 연결했다.
확인 시각을 갱신하지 않고 30분 안에 실행했다. 전기적 결선과 스위치는 사용자 확인이며
USB 열거 또는 소프트웨어가 직접 계측한 사실로 확대하지 않는다.

| 연결 | A/DUT, role 1 | B/peer, role 2 |
| --- | --- | --- |
| B PWM → A AIN1 | **P1.05**, P2-11 | **P1.14**, P4-12 |
| 공통 GND | GND, P2-30 | GND, P2-30 |

양쪽 USB 전원 OFF 상태에서 A 쪽만 P1.04에서 P1.05로 옮긴 조건이다. B와 GND를 유지하고
DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·각자 USB 전원, 외부 저항/전원 rail/다른 출력 없음
조건을 확인했다. Controller는 B/role 2만 사용한다. [USB 재식별]({base}/usb-inventory.json)에서
A D/COM5·COM6, B E/COM7·COM8과 기존 exact UID 두 개를 확인했다.

[build evidence]({base}/target-build-evidence.json), [artifact 색인]({base}/target-artifact-index.json),
[exact image]({base}/exact-images.json)에 두 역할의 새 HEX/ELF·빌드 기록·설정·hash를 보존했다.
NCS v3.4.0·bundle dcbdc366a1·GNU Arm 14.3·bundled Python·pyOCD 0.42.0을 사용했다.
[401 대비 입력 대조]({base}/build-input-comparison.json)는 두 역할의 컴파일 소스·설정·소속·메모리가
같음을 확인했다. 이번에도 제품·시험 앱·canonical runner는 변경하지 않았으며 embedded commit
identity는 이전 a12e444와 별도다.

## 실기 결과와 독립 감사

PWM20·21·22 × channel slot 0~3 × 32/256 samples × 단일/이중 DMA buffer = **48개**를 검사했다.
출력은 B P1.14로 순차 route하며 top 1021·compare 512·individual load를 사용한다.
A의 SAADC는 AIN1·12-bit·gain 1/4이며 수동 SAMPLE로 수집한다. 준비·시작·완료·오류 0,
DMA 반환 pointer/길이·완료 mask, 요청/수집 sample 수와 HIGH 관측을 판정했다.

전체 **{audit['samples_read']:,} samples**를 읽고 vector별 sample hash·min/max를 보존했다.
LOW(raw <256)는 {audit['vectors_observing_low_below_256']}개, HIGH(raw >256)는
{audit['vectors_observing_high_above_256']}개 vector에서 관측했으며 raw 범위는
{audit['raw_minimum']}~{audit['raw_maximum']}이다. 이는 교정 전압·ADC 정확도나 PWM 주기·듀티 측정값이 아니다.

각 vector 뒤 두 역할 모두 disarm `[0]`을 확인했다. Cleanup 48개와 campaign 2개는 기능 PASS에서
제외하고 journal 총 98개로 보존했다. 동일 cleanup 논리 ID는 바로 앞 기능 record와 순서로 대응한다.
[독립 감사]({base}/results-audit.json)는 별도 48개 계획·고유 기능 ID·전체 순서·상태·길이·해제,
JSON/journal 일치·두 image/UID·10 MHz를 대조했다.

| 원본 | SHA-256 |
| --- | --- |
| [결과 JSON]({base}/fixture402-attempt1.json) | `{audit['hashes']['fixture402-attempt1.json']}` |
| [journal]({base}/fixture402-attempt1.json.jsonl) | `{audit['hashes']['fixture402-attempt1.json.jsonl']}` |

두 flash와 전체 cycle은 첫 실행에서 통과했다. Sector erase·`auto_unlock=false`를 사용했고
mass erase/recover·속도 하향·재시도는 없었다. [종료 read-only 확인]({base}/postflight.json)에서
reset/flash 없이 CPUID `0x411fd210`, full 40-byte commit·role을 2/2 검증했다.
CPU snapshot은 {states}이다.

[부분 coverage 감사]({base}/analog-coverage-audit.json)는 이전 401의 원본 gzip을 복원하고
원래 SHA를 검사한 뒤 현재 402와 각각 48개 고유 계획을 대조했다. 두 fixture의 합계는 기능
**96개**, cleanup **96개**, samples **{coverage['samples_total']:,}개**다. 각 exact source는 별도 유지한다.
T11의 61,423개 결과와 역사 실패도 보존하며 합계가 하나의 frozen-source 캠페인이라는 뜻은 아니다.

## T12의 남은 범위

401·402는 PWM route와 외부 AIN0·AIN1의 수집/DMA/정지 근거다. 현재 oracle의 필수 판정은
HIGH와 sample 수이고 LOW는 min/max의 추가 관측이다. PWM period/duty capture, ADC
calibration/채널 순서, timer/event 등 T12 전체 요구는 별도 검증해야 한다.
후속 403·404·408·420·430·440과 T13 동시성·600/7,200초 soak, T14~T15 판정,
최종 통합·RC·공개는 미완료다. M24/M25 전체와 readiness gate를 승격하지 않았다.
GitHub Actions는 미확인이며 SDK·board·제품 source·과거 evidence·공개 자산은 보존했다.

## 다음: Fixture 403 PWM→AIN2

양쪽 USB를 분리하고 **A 쪽만 P1.05 → P1.06/AIN2**로 이동한다(P2-11 → P2-10).
**B P1.14와 공통 GND는 그대로** 유지한다. DAP UART 양쪽 분리·SWD 연결,
동일 I/O 전압·각자 USB 전원·다른 출력/전원선 없음 조건을 유지하고 USB 재연결 완료를 확인한다.
[다음 핀맵 감사]({base}/next-wiring-audit.json)에 GPIO/connector 대응을 보존했다.
403은 이번에 실행하지 않았으며 새 확인과 exact HEAD 이미지가 필요하다.
'''
