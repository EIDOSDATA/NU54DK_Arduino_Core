# v0.5.0-rc.2 Release notes

2026-09-27 Windows 시험 후보. 기능 기반은 [RC1 변경점](../v0.5.0-rc.1/RELEASE_NOTES.md)과 같으며
M28~M31·P0~P2의 완료 및 지원/미지원 경계를 유지한다. M32/M33이나 Ubuntu/macOS 지원을 추가하지 않는다.

## RC1 이후 교정

- 공개 예제 113개에 Feature set·역할·보드 수·Serial·sidecar metadata와 한국어 `.ino` 안내를 제공한다.
- CMSIS-DAP/J-Link 메뉴를 실제 연결 조건에 맞추고 한 probe 자동 선택, 다중 probe 명시 선택,
  UID 환경 변수·자리표시자 거부·로그 마스킹을 적용한다.
- UTF-8 출력, 단계별 Verify 진행/heartbeat, upload 오류 분류와 비파괴 SWD 진단을 보강한다.
- Sketch 본문·임시 build 경로 변화에서 CMake/Ninja 재사용과 cache identity를 교정한다.
- CI 변경 영향 분류, package 준비/설치 예제 검증/자산 재사용 단계를 분리한다.
  113개 예제를 가중 분할하고 worker·중첩 병렬도·실패 로그를 제어한다.
- Windows post-configure 무출력 종료는 좁게 식별하여 **최대 한 번** 재시도한다.
  실패 원본과 재시도 횟수를 보존하며 일반 오류를 무한 재시도하지 않는다.

## 판정

최종 b2e7 소스의 M12는 9/9 job, Full RC는 11/11 job, 설치 예제는 113/113 PASS다.
최종 package를 사용한 sector upload/UART HIL도 PASS다.
대표 CI 20분·Full RC 40분 목표는 달성하지 못했고 SDK 설치 정체와 compile 재시도 이력이 남는다.
사용자가 현재 결과를 수용하고 GUI 시험을 직접 진행하기로 하여 시험 후보로 공개한다.
성능 FAIL과 GUI NOT RUN을 PASS로 바꾸지 않으며 stable 승격도 하지 않는다.

정확한 source·재시도·시간·후속 항목은 [Testing](TESTING.md),
결정 원본은 [272번 기록](<../../04_검증 기록/272_RC2_사용자_수용과_main_통합_및_시험배포.md>)을 따른다.
