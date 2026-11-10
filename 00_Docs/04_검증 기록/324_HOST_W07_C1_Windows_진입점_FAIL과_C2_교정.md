# HOST-W07 C1 Windows 진입점 FAIL과 C2 교정

기록일: 2026-11-11. Host6/8, HOST-W07 준비 중이다.
[323번](323_HOST_W07_도구_통합과_RC1_검증_착수.md)의 도구를 C1
`addef962d8ce141e6c03d200b77df8dba2590402`로 고정했다(31파일, `1f33cb/exit0`).
푸시는 `40647a/exit0`, 실제 software dispatch는1회(`00cc77/exit0`)다.
그 전 푸시 진행 중 원격 source 전제검사가 거부한 요청(`58a3bf/exit1`)은 workflow를 실행하지 않았다.

## C1 실제 원형과 실패

C1의 private `0.6.0-rc.1` Core를 로컬에서 두 번 독립 생성해 모든 byte 일치를 확인했다
(`26ab63/exit0`). archive SHA-256은
`87bbc74b71229b35ed1c1334e7cc5025324d1a0970694f5833927ec7d7d51778`다.
비공개 kit 생성은 `8e23b1/exit0`,218파일·manifest SHA-256은
`4662c11b6177867ed069e7dfb817ac06f3870ba4a8685a031ae2d2628d6df81a`다.
생성 성공은 실행 PASS가 아니며, 실제 첫 `START.cmd ... plan`은 **exit2 FAIL**이었다(`2b9bf2`).

실패는 Python·SDK·target 실행 전의 `Get-FileHash` 검색이다. 직접 Windows PowerShell5.1을
실행하면 정상(`f5cc42/exit0`)이지만 PowerShell7→CMD→Windows PowerShell5.1 경로는 PS7의
모듈 경로를 그대로 상속했다. 같은 CMD 경로의 읽기 전용 probe에서 실제 모듈 경로와 검색 실패를
확인했다(`991d67`, child exit1). **생성한 Windows kit 진입점의 의존성 처리 결함**이며
target firmware 또는 SDK 결함으로 분류하지 않는다.

C1 원형 kit·START·manifest·실패 log를 고치지 않는다. 정본은
`D:/w06/control/host-w07-c1-startup-failure-a001.json`이다.

## C2 교정과 fresh 검사

Windows 진입점은 OS 기본 Windows PowerShell의 절대 경로와 .NET SHA256 stream을 사용한다.
PowerShell 모듈 검색이나 시스템 Python/Git을 요구하지 않는다. 전역 `PSModulePath`·보안 정책을
바꾸지 않으며 stream/hash handle은 성공·실패 모두 닫는다. CMD delayed expansion도 끈다.

실제 CMD/PowerShell로 한글·공백·`!`가 있는 경로에서 정상 byte 통과와 변조 byte의 exit2 거부를
검사했다. 잘못된 경로·literal/hash 거부를 합해2개 PASS(`679e81/exit0`)다.
이 검사는 C2 작업본의 Windows hash 경로 실적이며 C2 kit 전체·native CI·실물 PASS가 아니다.
native workflow는 RC tooling 변경도 추적하고 이 검사를 세 OS suite에 포함한다. Windows 실제
CMD 검사를 실행할 수 없는 POSIX의 조건부 skip은 skip으로 남긴다.

C1 prerequisite [42841115864](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42841115864)는
같은 C1 source의3OS 성공이다. C1 native package [42841116172](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42841116172)는
producer·smoke3OS·smoke 비교까지 성공했으나 전체 gate 미완료다. 교정 후보로 넘어가며 이 run과
build-only42841116200의 남은 실행을 취소했다(`aa5be6/exit0`). C1 부분 PASS·취소·파생 aggregate
거부와 software42841699604의 결과는 source별로 보존하고 C2 실적에 합치지 않는다.
이후 C1 software [42841699604](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42841699604)는
9/9 성공·skip0으로 종료했다(`c4b176/exit0`). native package는 성공5·취소25이며 전체 PASS가 아니다.

## Windows 입력 준비와 다음 순서

같은 고정 Windows toolchain1,013,457,231B와 NCS3,089,558,703B의 공식 원형 size/SHA-256을
통과했다(`2b27ec/exit0`). 별도 `D:/w06/host-w07/sdk`의 fresh 설치·등록·실제 도구 검증은
`bfbdfe/exit0`이다. NCS3.4.0·SDK Python3.12.4·bundle dcbdc366a1·nrfutil8.2.1을 유지했다.
`source_revision=null`은 로컬 입력의 정상 표시이며 CI 또는 C1 HIL 실적으로 바꾸지 않는다.
기존 SDK 입력은 수정하지 않았다.

C2를 새 source로 고정해 fresh native/package/software CI와 새 kit START를 검증한다.
이어서 lifecycle·설치본 대표 build·Windows Blink/Serial/debug/NUS 회귀를 수행한다.
그 후 사용자 OS7행의 전체 build·IDE·실물 USB·수명주기 gate와 HOST-W08을 인계한다.
현재 새 HIL0·사용자 물리 gate NOT_RUN이다. 공개·tag·Release·main 승격은 수행하지 않았다.

원래 M33-W06 S19 actual46PASS·명시 수락29/40/44·FAIL·soak·private11831/public3·완료 TODO6과
H12의 HOST-W06 마감을 보존한다. #29 분석 유예, 단일 writer, w06 PAUSED 요청 유지·예약 생성/재활성화 없음.
