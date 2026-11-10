# HOST-W06 H8 설치 통과와 SDK Git 전달 교정

기록일: 2026-11-10. Host 완료5/8, 현재 HOST-W06 진행 중이다.
Exact H8 source는 `80e11169b19e0d634fbec447cbd4233fbf50523e`이다.
[317번](317_HOST_W06_H6_설치_FAIL_원인과_교정.md)의 H6 설치 FAIL과 H7 guard FAIL을 보존한 fresh 실행이다.

## 실제 결과

[Native package CI42778400841](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42778400841)의
producer는 Ubuntu 단위30개와 package·sidecar 및 초기 runtime 파생 archive의 독립 재현 검사를 통과했다.
H7의 exact-source guard 실패는 H8에서 재현되지 않았다. H7의 세부 원인을 확정하거나 원형 FAIL을 지우지 않는다.

| 실제 Host | 초기 Python·SDK 설치·저장 상태 재검증 | 원형 ZIP 대조 | 예제 발견 | Blink build |
| --- | --- | --- | --- | --- |
| Windows x86-64 | PASS | 955파일 PASS | 24 library·204예제 | FAIL, SDK patch Git 실행 전 |
| Ubuntu AMD64 | PASS | 955파일 PASS | 24 library·204예제 | FAIL, system Git trap |
| macOS Apple Silicon | PASS | 955파일 PASS | 24 library·204예제 | FAIL, system Git trap |

같은 H8 source의 실제 CLI 설치·initial Python 3.12.16 isolated1·고정 SDK/Zephyr·bundle·도구와
CI signing fixture 준비를 기록과 대조했다. Compile 실패 뒤에도 원형 설치955파일이 같았다.
설치 PASS를 Blink·전체204예제 compile·cross-Host 비교의 PASS로 합산하지 않는다. 전체 예제·비교는 `NOT_RUN`이다.

Producer package SHA-256은 `11f5e5a56369333776549ab3a8d765782910784eeb175099f4880295bb9d757c`이다.
Producer 원형 ZIP ID13744602736의 SHA-256은
`93e6b499a416ef9b5d88dd53d7f7ab9038956ec0f60a5c64bc5f09e359e2b922`이며 크기75,663,053바이트를
원격 digest와 검증했다. Package/sidecar6파일의 두 번 생성 byte 및 파생 tool3개도 원문 ZIP에서 대조했다
(`62acf4/exit0`, download `616eab/exit0`).

| FAIL artifact | ID | 보존한 원형 ZIP SHA-256 |
| --- | --- | --- |
| Windows | 13745286911 | `7d5533fcece1a31caf0a699af4a03352b5735650294e73bdc21396b0f0239d86` |
| Ubuntu | 13745517239 | `dd0dfef474b9b507114282e59af5a475ba81a1450808d3d37fdf86d5f7183c50` |
| macOS | 13745073163 | `55513ac5dc743463681cca21d018a9b323d77c9803e7088f7f8530ecf77877ec` |

로그·context·ready·설치 byte·발견 분모·실패 원문을 대조한 정본은
`D:/w06/control/host-w06-h8-smoke-audit-20261110.json`(`df0309/exit0`)이다.

## 확정 원인과 교정

실제 공통 builder의 SDK patch manager가 `subprocess.run(['git', …])`를 호출하면서 준비된 SDK 환경을
전달하지 않았다. 시스템 Git이 없는 초기 환경에서 Windows는 WinError2, Ubuntu/macOS는
의도한 system Git trap으로 실패했다. Compiler·target firmware 실행 전 Host 의존성 전달 문제다.

교정은 `tool_environment()`가 실제 선택한 SDK Git 절대 경로를 `NUCODE_SDK_GIT`으로 전달하고
patch revision·clean 검사·적용·역적용·최종 복구 검사에 같은 환경을 명시하는 것이다.
명시한 Git이 없거나 상대 경로이면 system PATH로 대체하지 않고 실패한다. 별도 CI harness의
기존 환경 미지정 API는 유지한다. SDK version·revision·승인 patch byte·파일 목록은 바꾸지 않는다.

독립 임시 Git fixture에서 PATH를 비우고 명시한 Git만으로 실제 적용·정상 복원·예외 후 복원 및
잘못된 명시 경로 거부를 검사했다. 제품 SDK에는 로컬 patch를 적용하지 않았다.
관련 focused 최초 실행(`180b75/exit1`)은34개 중33 PASS·1 ERROR였으며 ERROR는 기존 R06 시험의
인접 module import를 지원하지 않는 호출 방식 때문이었다. 올바른 import 경로로 실패한 그1개만
fresh 실행한 결과 `a7758a/exit0`이었다. 이를 전체34개 fresh PASS로 합산하지 않는다.
최종 교정 source의 native package CI·공통 software 회귀에서 다시 판정한다.

기존 W06 S19 실제 PASS46·명시 수락 #29·40·44·원형 FAIL·soak와 완료 TODO6개를 보존한다.
#29 원인 분석은 유예하고 새 HIL은 수행하지 않았다. 자동점검 w06 PAUSED 요청 유지·예약 생성/재활성화 없음.
Ubuntu/macOS 실제 USB·Serial·debug·lifecycle은 RC1 최종 사용자 gate `NOT_RUN`이다.
