# M31-W04 Direction Finding 완료

## 1. 결론

M31-W04를 **PASS·완료**로 판정했다. 고정 NCS v3.4.0·nRF54L15에서
제품 SDC connectionless AoA CTE 송신과 별도 opt-in Zephyr LL의 연결형 AoA CTE
응답을 현재 공개 Arduino API·예제로 재빌드하고 실기 재검증했다. 제품 SDC
IQ RX와 AoD는 고정 SDK의 `UNSUPPORTED`로 유지했다.

이 완료로 M31은 **W01~W04 4/8**이다. W05는 진행 중, W06~W08은 미착수이며
v0.5.0 공개·tag·catalog를 승인한 것은 아니다.

## 2. 고정 조건

| 항목 | 고정값 |
| --- | --- |
| 소스 | `6e646fcf4c6f578f8cb29cfcd4dbf43f701fed32`, clean |
| SDK / Zephyr | NCS `v3.4.0` / Zephyr `4.4.0` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Arduino 구성 | `nucode:zephyr:nu54dk:feature_set=adaptive` |
| 제품 controller | connectionless CTE beacon: SDC |
| 별도 controller | connected responder·내부 receiver: opt-in Zephyr LL |
| 플래시 안전 | exact sector flash, `auto_unlock=false`, mass erase/recover 없음 |

probe SHA-256 identity·COM·역할·image hash를 실행 직전 재결합했고,
배타 probe lock과 reset-halt-drain-resume 절차를 사용했다. 원시 probe UID와 Bluetooth
주소는 증거에 남기지 않았다.

## 3. build·HIL 결과

| 경로 | build | 실기 | 판정 경계 |
| --- | --- | --- | --- |
| 공개 `CteBeacon` / 제품 SDC | FLASH 114,540 B, RAM 38,314 B | start/stop 20/20, invalid CTE length 거부 20/20 | controller가 수용한 connectionless AoA CTE TX. IQ 수신·각도 PASS 아님 |
| 공개 `ConnectedCteResponder` / Zephyr LL | FLASH 134,700 B, RAM 44,578 B | 연결 CTE report 20건, IQ sample 1,640개, cleanup PASS | 응답 송신 경로의 실제 무선 재검증. 내부 receiver는 제품 API 아님 |
| 제품 SDC IQ RX | build/HIL 필수 분모 없음 | `UNSUPPORTED` | [259번](259_M31_P2_DF_고정_SDK_지원_경계.md)의 공식 지원 경계 유지 |
| 제품 SDC AoD | build/HIL 필수 분모 없음 | `UNSUPPORTED` | HCI capability·SDK 근거 유지 |

첫 연결형 시도는 연결·CTE 명령 수용 후 IQ report 0건인 채 연결이 종료돼
`FAIL` 원본으로 보존했다. 계약에서 허용한 단 한 번의 진단 재시도는 11.547초에
유효 report 20건·1,640 sample·Host gate drop 0·중복 event 0건으로 PASS했고 양쪽
연결·수신 상태를 정리했다. 첫 실패를 재시도 PASS로 덮어쓰지 않았다.

## 4. 증거

- [완료 audit](evidence/m31-w04-close-20260925/closure-audit.json)
- [build manifest](evidence/m31-w04-close-20260925/build-manifest.json)
- [제품 SDC beacon 20회](evidence/m31-w04-close-20260925/cte-beacon-public-20.json)
- [연결형 재시도 PASS](evidence/m31-w04-close-20260925/connected-responder-iq20-retry.json)
- [연결형 첫 시도 FAIL 원본](evidence/m31-w04-close-20260925/connected-responder-iq20.json)

과거 Zephyr LL 연결형 20 report·1,640 sample, connectionless sync 실패·LL fault,
제품 SDC periodic TX Power option 거부 원본은 기존 기록에 그대로 보존했다.

## 5. 영향 회귀와 완료 판정

공개 beacon·responder를 현재 adaptive 구성에서 직접 빌드했고, DF parser·periodic
option·예제 공개 경계·M31 계약 검사를 다시 실행했다. readiness 계약 9개, DF 국소 6개,
예제 공개 경계·negative matrix 26개로 합계 41개 Host test가 PASS했다. 시스템 Python
3.12의 `pyserial` 미설치와 NCS bundled Python의 `ctypes` 불일치 실행은 환경 실패로 분리했고,
`pyserial` 3.5가 설치된 로컬 Python에서 DF 6개를 재실행해 PASS했다. 같은 환경의 전체
M31 Host 회귀도 **152개 PASS**했다. 코드·pool·stack 크기는
변경하지 않았다. `standard`/full 기본값과 adaptive 실험 선택지도 유지했다.

W04 분모는 지원되는 두 CTE TX 경로, 공개 예제, 오류 거부, 정지·자원 반환,
제품 SDC 미지원 경계의 정합이다. 이 분모를 충족했으므로 W04를 완료한다.
정밀 각도, 안테나 전환·외장 RF, 상용 peer 상호운용, Bluetooth qualification은 별도
범위다. 다음 기능 작업은 W05이며 이 기록에서 자동 착수하지 않는다.
