# v0.5.0-rc.1 Known issues

이 RC의 완료 판정은 아래 지원 경계를 포함합니다. RC 공개가 모든 Bluetooth 기능의 지원이나
정식 stable·Bluetooth qualification 완료를 의미하지 않습니다.

| 영역 | 경계 |
| --- | --- |
| Host·보드 | Windows 10/11 x64의 NU54DK nRF54L15 CPUAPP만 대상. Ubuntu/macOS는 후속 제품선 |
| Direction Finding | 고정 NCS v3.4.0 제품 SDC의 IQ RX·AoD는 `UNSUPPORTED`. 지원 CTE TX/response와 구분 |
| Audio·외부 상호운용 | 보드 간 합성 PCM/LC3·프로토콜 경로와 실제 외장 마이크·스피커·상용 peer 검증은 다름. 후자는 미검증 |
| Angle·distance | 정밀 각도·거리 보정과 외부 안테나 조건의 정확도는 보증하지 않음 |
| Channel Sounding | 간헐 RF/controller loss와 counter gap은 비차단 관찰값. 유효 raw·step·완료·양측 STOP·fault·중복/역행 counter 검사는 유지 |
| 동시 구성 | ISO·Audio·DF·CS 전체를 하나의 image에서 동시에 사용하는 구성과 모든 주변장치 조합은 보증하지 않음 |
| 실험·호환 기능 | adaptive와 EATT는 experimental opt-in, Signed Write는 deprecated legacy opt-in |
| QDEC20/21 | 기본 정·역회전·SAMPLE/REPORT event 지원. 반복 manual `read()/clear`의 무손실 누산은 보증하지 않음 |

`standard/full`은 기본 설정입니다. 메모리 최적화 완료가 모든 pool·stack을 줄였다는 뜻은 아니며,
SDC 내부 high-water API 비노출도 별도의 미완료 gate가 아닙니다.

Secure BLE DFU는 전용 profile·MCUboot layout·외부 signing key가 필요합니다.
[DFU 예제 계약](../../../libraries/NUCODE_BLE_DFU/examples/README.md)을 따르고 private key를 공개하지 않습니다.
Native USB·Wi-Fi·Ethernet·Thread·Matter·Mesh는 이 RC의 지원 범위가 아닙니다.

시험하지 않은 조합은 PASS로 추정하지 않습니다. 정확한 조건·분모는
[M31 완료 범위](../../TODO_M31.md)와 [Testing](TESTING.md)을 확인하십시오.
