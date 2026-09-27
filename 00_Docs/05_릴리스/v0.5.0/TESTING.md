# v0.5.0 Testing

## 릴리스 판정 범위

- M31 W01~W08 8/8과 채택 기능의 Host·build·HIL 증거
- Windows package 두 번 독립 생성과 archive/sidecar byte 재현성
- 격리 설치, library 16개·공개 예제 113/113 Arduino recipe compile
- 설치·업그레이드·제거·재설치와 cache 경계
- 대표 Blink/NUS/Channel Sounding 역할 build·upload·runtime
- probe 0/1/2대, UID placeholder·형식·불일치, J-Link 미설치 negative
- UTF-8 stdout/stderr와 Verify 단계·heartbeat
- 문서 UTF-8·로컬 링크·생성 계약과 package inventory

RC2의 M12 9/9 job, Full RC 11/11 job, 113/113 예제와 실제 sector upload/UART HIL은 PASS였습니다.
정식 source에서는 RC2 이후 runtime PM 교정과 영향 Host 회귀를 다시 실행했고 stable package를 두 번
생성해 byte 일치를 확인했습니다. package source, tag target, manifest의 source revision은
`0999b6a721b4579faa6a7a4d91d04da5e4960c07`로 일치합니다. 공개 자산 11개 재다운로드·hash 비교와
공개 index의 격리 설치·Blink cold compile도 PASS했습니다.
[274번 공개 기록](<../../04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)을 따릅니다.

공개 후 main `ed5fb745`의 6개 대표 build 단계는 PASS했지만 cache 저장 중 25분 제한으로 job은
취소됐습니다. 제한을 45분으로 보정한 `7a343b4f`의
[M12 실행](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36313276335)은
8개 job 성공·대표 build 1개 생략으로 전체 성공했습니다. 같은 실행에서 9개 모두 성공하거나
6개 대표 build를 다시 수행한 것으로 집계하지 않습니다.

## Arduino IDE 사용자 확인

사용자는 runtime PM 교정을 적용한 RC2 설치본과 실제 Arduino IDE에서 Standard Blink 250 ms를
Upload한 뒤 100 ms로 수정해 USB 재연결 없이 다시 Upload했고 성공을 확인했습니다.
같은 교정은 정식 source에 포함됐습니다. 이 결과는 연속 Upload 교정에 대한 실제 GUI·보드 PASS이며,
NUS·Channel Sounding 전체 GUI 동작을 새로 수행했다는 뜻은 아닙니다.

## 결과 해석

Host/mock PASS, Arduino CLI Verify, Upload와 기능 HIL은 서로 대체하지 않습니다. 외장 audio 장치,
상용 mobile/desktop peer, Ubuntu/macOS Host, 정밀 RF·음질·거리·각도 보정은 NOT RUN 또는 지원 범위
밖으로 유지합니다. RC2에서 기록한 CI 20분·Full RC 40분 목표 FAIL도 역사 결과로 보존합니다.
