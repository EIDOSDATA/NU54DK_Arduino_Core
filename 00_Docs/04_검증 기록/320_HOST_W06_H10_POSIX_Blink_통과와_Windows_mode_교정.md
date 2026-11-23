# HOST-W06 H10 POSIX Blink 통과와 Windows mode 교정

기록일: 2026-11-10. Host 완료5/8, HOST-W06 진행 중이다.
Exact H10은 `26da68230a9b0a2ad19dc0b5697bb5d46c89e5c3`이다.
[319번](319_HOST_W06_H9_Kconfig_경로_원인과_native_교정.md)의 POSIX 공백 경로 교정을 fresh native CI에서 확인했다.

## H10 실제 결과

[Package CI42787963999](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42787963999)는
producer·Ubuntu smoke·macOS smoke 성공, Windows smoke 실패로 종료했다. 같은 H10 source의 실제
ELF·HEX·manifest·원형 compile log를 다시 대조했다(`72b75d/exit0`). 세 OS 전체 gate는 아직 FAIL이다.

| 실제 Host | 설치·발견 | Blink compile·artifact 검증 | FLASH | RAM |
| --- | --- | --- | --- | --- |
| Ubuntu AMD64 | PASS | PASS | 81,572 B | 29,439 B |
| macOS Apple Silicon | PASS | PASS | 81,572 B | 29,439 B |
| Windows x86-64 | PASS | SDK clean 검사 FAIL | 미측정 | 미측정 |

Ubuntu/macOS의 실제 ARM load SHA-256은 둘 다
`6eca127e7863bfc3bd7cfa073594be970d2efb2d9fab9a745e89b25bb3a30e71`이다.
할당 section·정규화 HEX·memory region/budget·금지 symbol도 같았다. 원형 ELF/HEX hash는 별도로 보존했다.
Windows 결과를 이 두 PASS로 채우지 않으며 전체204예제/OS·profile 거부9개/OS·세 OS 비교는 `NOT_RUN`이다.

| 원형 artifact | ID | ZIP SHA-256 |
| --- | --- | --- |
| Ubuntu PASS | 13749992600 | `8dda9353e305c4febe9f3618bd69d3e4c945bb55492af09790c30f60cee930a1` |
| macOS PASS | 13751242204 | `062da848396549618a3b6189e87e4e3f8761629b7aee813f03b382b28c1378c0` |
| Windows FAIL | 13751131412 | `7c6b2032a7e11cfe4ea901c1e4e3c9b997b00c754c59e679769dfd314aacef07` |

원형 ZIP 전체의 size·digest·source binding을 검증했다. PASS 두 개의 실제 ELF/HEX도 ZIP에서 읽어
manifest hash·size와 parser 결과를 재검증했다. 정본은 `D:/w06/control/host-w06-h10-smoke-audit-20261110.json`이다.
Producer는 native unit35개와 독립 재생성을 통과했으며 실제 package SHA-256은
`fecf6320cd1a082d34035e92995a752f6f29445921b3da733ae97cfb75504bf3`이다.
SDK prerequisite CI42787964007도 별도3OS 성공으로 종료했다. Software/build-only는 별도 관찰한다.

## Windows 원인과 교정

Windows 진단에는 변경으로1155개 경로가 잡혔고 `100755 => 100644` 실행 비트 차이가 확인됐다.
원형 Git metadata의 POSIX mode와 Windows filesystem의 표현 차이다. 파일 내용이 바뀌었다고 확정한
오류와 구분한다. 남은 실제 content·추가·누락 변경이 없는지는 fresh 실행의 같은 guard로 확인한다.

교정은 Windows에서 SDK Git 명령에만 `-c core.filemode=false`를 전달하는 것이다. Linux/macOS의
mode 검사는 유지하며 SDK 파일·Git index·repo/global config·OS 권한·SDK version을 바꾸지 않는다.
tracked content 변경·삭제·untracked 추가 검사는 그대로 수행한다. 강제 reset/clean 또는 미확인 경로 무시는 하지 않는다.

독립 실제 Git fixture의 repo config를 `core.filemode=true`로 유지한 채 Windows 표현 차이 처리,
실제 byte 변경·삭제·추가 검출, 정상·예외 시 patch 복원을 확인했다. SDK Git focused4개가
`dfaa92/exit0`으로 통과했다. 이는 제품 SDK를 수정한 시험이 아니며 fresh source의3OS native CI가 필요하다.
이전 H10 source의 Ubuntu/macOS 성공을 교정 source에 재분류하지 않는다.

기존 W06 S19 actual PASS46·명시 수락 #29·40·44·원형 FAIL·soak·private11831개·public3개와
완료 TODO6개를 보존한다. #29 분석 유예·새 HIL0·자동점검 w06 PAUSED 요청 유지·예약 생성/재활성화 없음.
Ubuntu/macOS 물리 USB·Serial·debug·lifecycle은 RC1 최종 사용자 gate `NOT_RUN`이다.
