# v0.5.0 알려진 제한

| 항목 | 상태와 사용 지침 |
| --- | --- |
| Host OS | Windows 10/11 x64만 지원. Ubuntu/macOS는 후속 릴리스 범위 |
| 첫 빌드 | 고정 NCS/toolchain 설치와 Zephyr configure 때문에 증분 빌드보다 오래 걸림 |
| CI 시간 | RC2에서 일반 20분·Full RC 40분 목표 미달을 수용. 기능/패키지 PASS와 혼동하지 않음 |
| Windows 경로 | sysbuild/Ninja 긴 경로 제약 가능. 짧은 Arduino data/cache 경로 권장 |
| Adaptive/EATT | Experimental opt-in이며 기본 stable 구성 아님 |
| Signed Write | Deprecated legacy opt-in |
| Direction Finding | 제품 SDC의 IQ RX·AoD 미지원. CTE 송신과 별도 LL 진단 경계를 구분 |
| Audio/peer | 외장 마이크·스피커·상용 peer의 실제 운용과 정밀 음질은 검증 보증 밖 |
| Channel Sounding | raw/거리 결과 경로를 제공하지만 정밀 거리·각도 보정을 보증하지 않음 |
| 조합 | ISO·Audio·DF·CS와 모든 주변장치의 단일 image 동시 조합을 보증하지 않음 |

QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event를 지원하지만 반복 manual `read()/clear`의
무손실 누산은 보증하지 않습니다. `Serial`은 DAP UART이며 native USB CDC가 아닙니다.

RC2에서 확인된 Standard Blink 연속 Upload의 runtime PM 문제는 v0.5.0에서 해결했습니다.
`E_SWD_NO_ACK`가 다시 발생하면 [문제 해결](TROUBLESHOOTING.md)의 전원·VTref·GND·점유·저속 SWD·
under-reset 진단 순서를 따르고 자동 recover·unlock·mass erase는 사용하지 않습니다.
