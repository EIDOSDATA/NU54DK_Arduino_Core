# v0.6.0 제한·수락 예외·미검증 범위

공개 전 후보 문서다. 해결된 실패와 남은 미검증을 구분한다.

| 구분 | 현재 판정 | 처리·근거 |
| --- | --- | --- |
| C10 macOS process 정리 FAIL | C11 fresh software 검증으로 교정 확인 | [331번](<../../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>). 원형 실패 순간의 zombie-only 상태까지 입증한 것은 아님 |
| macOS26 USB 재연결 첫 UART timeout | 기본 옵션 FAIL 보존, 명시적 줄 동기화 옵션으로 실제 재연결 재검증 PASS | 원인 byte는 확정하지 않았다. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>) |
| macOS27 첫 물리 재연결 관찰 | 분리 미감지로 관찰 타임아웃. 사용자 준비 후 새 관찰에서 분리·복원, 첫 UART 6/6 확인 | [337번](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>) |
| C11 RC1 macOS27 Arduino IDE Upload | `E_RUNNER_UNAVAILABLE`, `No module named 'yaml'`. 보드 선택 전에 중단 | C12 비공개 패키지에서 고정 SDK Python으로 검사하고 Arduino IDE의 일반 Upload와 Blink 동작을 확인했다. [337번](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>) · [338번](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>) |
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
