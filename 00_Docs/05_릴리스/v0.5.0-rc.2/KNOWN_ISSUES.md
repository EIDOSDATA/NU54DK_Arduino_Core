# v0.5.0-rc.2 알려진 제한

## 수용한 잔여 항목

| 항목 | 실제 상태 | 이번 시험 배포의 처리 |
| --- | --- | --- |
| Arduino IDE 2.x 실제 GUI | 자동화 환경에 native GUI 조작 표면이 없어 NOT RUN(기존 HOLD) | 사용자 직접 시험; CLI 통과로 대체하지 않음 |
| 대표 CI 시간 | 최종 성공 job 24분 20초로 20분 초과 | 목표 FAIL 보존, 사용자가 수용 |
| Full RC 시간 | 성공 shard 최장 54분으로 40분 초과; 최초 SDK 설치 정체 후 실패 job 재실행 | 목표 FAIL·원본 이력 보존, 사용자가 수용 |
| Windows 일시적 compile 종료 | 최종 전체 예제 중 bounded retry 1회 | 재시도 뒤 PASS; 무재시도 PASS가 아님 |
| 긴 Windows 경로 | sysbuild/Ninja의 긴 경로 제약 가능 | 짧은 cache/build root 사용, 실패 원본 보존 |

기능 추가를 중단하고 현재 RC2로 GUI 시험을 이어간다는 2026-09-27 사용자 결정에 따른다.
이 결정은 모든 기술 gate PASS 선언이나 stable 공개 승인이 아니다.

## 공개 후 확인된 연속 Upload 문제

공개 RC2의 `Standard peripherals`는 `PM_DEVICE_RUNTIME`을 사용하는 주변장치를 모두 포함하며,
최종 구성에서 `CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=y`가 되어 사용하지 않은 장치까지 부팅 직후
자동 suspend한다. 실제 Arduino GUI에서 250 ms Blink의 첫 Upload는 성공했지만, 실행 중 100 ms로
수정한 두 번째 pyOCD Upload가 `E_SWD_NO_ACK`로 실패했고 USB 재연결 뒤에만 일시적으로 성공했다.

main 후속 교정은 Standard profile에 `CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=n`을 명시한다.
Wire·SPI·PWM의 runtime route는 `begin()` 시 필요한 장치에만 runtime PM을 명시적으로 적용하므로
기능은 유지된다. 수정 설치본에서 250 ms → 100 ms 연속 Upload를 USB 재연결 없이 통과했다.
공개 RC2 tag·archive·index는 재작성하지 않으며, 이 수정은 main과 다음 배포 후보에 포함한다.

## 계속 유지되는 지원 경계

[RC1 Known issues](../v0.5.0-rc.1/KNOWN_ISSUES.md)의 제한을 승계한다.
Windows 10/11 x64만 사용자 설치 범위이며, adaptive/EATT는 experimental, Signed Write는 legacy opt-in이다.
제품 SDC의 DF IQ RX·AoD는 UNSUPPORTED이며 별도 Zephyr LL 진단 성공을 제품 지원으로 표시하지 않는다.
외장 audio 장치·상용 BLE peer·정밀 RF/음질/거리/각도 보정·모든 기능 동시 조합은 검증 보증 범위 밖이다.
`coreVersion()`의 개발 문자열과 Boards Manager 설치 버전은 다르다.

문제 보고에는 설치 버전, IDE/CLI/Windows 버전, Feature set, 최소 예제와 첫 오류를 포함한다.
인증 정보와 원시 probe UID는 제거한다. [문제 해결](TROUBLESHOOTING.md)을 먼저 확인한다.
