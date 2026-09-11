# NU54DK Arduino Core v0.4.1 Release Notes

## v0.4.0 대비 변경

- prerequisite 설치 도중 복구 가능한 초기 검사가 실패했더라도, 설치와 최종 검증이 성공하면
  마지막에 실패처럼 다시 표시하지 않도록 로그 수집·종료 판정을 분리했습니다.
- 긴 Windows 경로와 8.3 short path가 같은 경로를 가리키는 경우 설치 검증 test가 이를 서로
  다른 경로로 오판하지 않도록 filesystem identity로 비교합니다.
- source identity를 `0.4.1-dev`, 배포 package identity를 `0.4.1`로 갱신했습니다.
- stable Boards Manager index는 지원 버전 `0.4.1` 하나만 제공합니다.
- 이전 모든 stable·RC·preview의 지원을 종료했습니다. 과거 공개 byte와 기록은 삭제하지 않습니다.

## 변경하지 않은 것

- nRF54L15 peripheral 구현, public Arduino API, profile, pin route, library 9개와 예제 30개
- NCS v3.4.0, Zephyr 4.4.0, Toolchain `dcbdc366a1`, 보드 DTS revision
- QDEC20/21 지원 경계와 기존 비보증 항목

따라서 v0.4.0에서 정상 동작한 Sketch의 소스 변경은 필요하지 않습니다.
