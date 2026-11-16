# v0.6.0 제한·수락 예외·미검증 범위

공개 전 후보 문서다. 해결된 실패와 남은 미검증을 구분한다.

| 구분 | 현재 판정 | 처리·근거 |
| --- | --- | --- |
| C10 macOS process 정리 FAIL | C11 fresh software 검증으로 교정 확인 | [331번](<../../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>). 원형 실패 순간의 zombie-only 상태까지 입증한 것은 아님 |
| macOS26·27 USB·serial·debug·재연결·IDE | `NOT_RUN`, 장비 없음 | software PASS로 대체하지 않음. [지원표](SUPPORT_MATRIX.md)의 후속 실기 |
| Ubuntu native 사용자 실기 | `NOT_RUN` | 완료한 환경은 WSL2; native CI와 사용자 실기는 별도 |
| W06 #29·40·44 | 사용자 명시 수락, 기술 PASS 아님 | 실제46PASS와 구분. #29 분석 유예. [310번 집계 원형](<../../04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>)·[311번 별도 명시 수락·정정](<../../04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>) |
| Apple/Google·외부 제품·외장 장치 interop | 사용자 후속 `NOT_RUN` | scripted peer와 실제 제품 인증/interop 구분; 이 후속 실기만으로 개발·릴리스 차단하지 않음 |
| 실험 profile·미검증 template 조합 | opt-in·예제별 조건 적용 | 일반 지원으로 확대하지 않음. [Migration](MIGRATION.md) 참조 |

COM5·6 초기화 FAIL, C8 BLE FAIL, C9 재연결 UART FAIL, 이전 CI·실행 환경 실패와 중단 기록은
[329번](<../../04_검증 기록/329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md>)·
[330번](<../../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>)·331번에 그대로 보존한다.
후속 성공을 원형 실패의 원인 확정이나 당시 PASS로 바꾸지 않는다.

제품 SDC의 DF IQ RX·AoD 미지원, 정밀 RF·음질·거리/각도 보정과 외장 결선의 제한은 기존 계약을 유지한다.
미실행과 범위 밖을 새 제품 결함으로 세지 않으며, 반대로 사용자 수락을 기술 PASS로 세지 않는다.
