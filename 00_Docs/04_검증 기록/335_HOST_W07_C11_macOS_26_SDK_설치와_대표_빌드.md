# HOST-W07 C11 — macOS 26 설치와 대표 빌드

2026-11-23, 실제 macOS 26.7.3 (25G342) Apple Silicon ARM64의 `mac26-a002`에서 제품 `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa`를 사용했다. 인수 후 문서 checkout은 `1936d494571b89250c2efb69aed008b3679dddde`이고 [exact 문서 CI 45179753406/1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/45179753406)은 8 PASS·범위 SKIP 1이다. kit는 [334번](334_HOST_W07_C11_macOS_26_실기_시작과_Gatekeeper_차단.md)의 원본과 동일하다.

## 실행 결과

- macOS에서 실기 kit 내장 Python의 파일별 승인을 확인했다. 승인 후 Gatekeeper와 SIP가 활성화된 상태에서 원본 `START.sh`의 `plan`을 통과했다. 이전 SIGKILL과 승인 대기 종료 기록은 로컬 원장에 보존했다.
- `/opt/nordic/ncs`에서 NCS 3.4.0 설치·별도 verify를 통과했다. `ccc010f809`, Nordic Python 3.12.4, Zephyr SDK 1.0.1·GCC 14.3.0을 확인했다. BOOTSTRAP Python 3.12.16과 SDK Python의 역할은 각각 초기 설치와 SDK 빌드·장치 작업이다.
- `0.6.0-host.1`에서 `0.6.0-rc.1` 갱신, 동일 버전 byte 검사, 제거·재설치, 사용자 데이터·공유 SDK 보존을 통과했다. 설치본에서 24개 라이브러리의 예제 204개를 발견했다.
- Blink, SerialEcho, NUS Peripheral, NUS Central의 cold 4회와 warm 4회를 통과했다. 로컬 BIN·HEX 8개의 byte가 같은 제품 C11의 Mac26 software CI artifact 14180863023과 일치했다. 전체 204개 빌드는 이 Mac에서 실행 범위에 포함하지 않았다.
- 새 Mac inventory에서 NU54DK CMSIS-DAP 두 개와 VCOM 네 개의 해시를 대조했다. 두 장치가 USB 허브 아래에서 열거됐으며 실기 연결 구성을 확인한 뒤 새 inventory로 보드·포트를 지정한다.
- IDE 2.3.11 검증용 고립 데이터·설정 경로와 비공개 후보 loopback index의 해시를 확인했다. GUI 설치·발견·Verify는 후속 실기다.

## 증거 해시

| 로컬 원본 | SHA-256 |
| --- | --- |
| 고정 SDK 새 설치 | `9b577a06dc2827f271fd270ca6b489817af2dda0da00123b0ec12e88eab3ba84` |
| 별도 SDK verify | `ea78df5b78f0c26fb52fe59d3c64b8ec6ff6228816d469546d088fd4b4df90de` |
| 설치 수명주기 | `bb401610a8850a6751aa3794ad37324b5b121f2ac653f50efefeddf8f04e6fc4` |
| 대표 빌드 | `16f09604993f15b6d913f1329774ff4f18ae679a2d4699994e152207e58170a9` |
| 읽기 전용 장치 inventory | `30ae71fc439df52b3d68ddeebd65cc8f4a7781edde3934cccdee45367f4a2b0c` |
| Mac26 CI 산출물 byte 비교 | `b73204219c6b0ffb52c512d190fe96711744b0a2b236f97cbb908d82bc16b398` |
| IDE용 비공개 loopback index 확인 | `7fb68f936696934e371857c5df374a66b6d7269d52f96a372cc3cc3f672e0ddf` |

각 단계의 stdout·stderr·exit code, build manifest, 보드 익명 inventory와 자식 프로세스 종료 증거는 Mac 작업 원장 및 새 work root에 보존한다. 보드 flash·reset·halt 및 UART open은 아직 시작 전이다. Mac26·27 물리 gate는 `NOT_RUN`, Host 6/8·지원3/5·M33 수락6/8·기술5/8을 유지한다.
