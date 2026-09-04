# C/C++ 정렬 기준

프로젝트가 직접 관리하는 C/C++와 Arduino `.ino` 예제를 정렬합니다.
SDK, `third_party`, board submodule, 기존 공개 ZIP·asset은 대상이 아닙니다.

- BSD/Allman: 여는 중괄호는 다음 줄, 들여쓰기·탭 폭 4칸, 실제 들여쓰기는 공백.
- 한 줄 `if`/`else`/`for`/`while` 본문도 중괄호 생략 금지.
- 주석은 한국어 Doxygen. 이름·API identifier·SPDX·원저작권 표시는 유지.
- 동작·소유권·오류·제한을 정확하게 설명하고 구현과 다른 보증을 추가하지 않음.

기준 도구는 clang-format **22.1.8**입니다. 다른 도구 버전으로 전 파일을 재정렬하지 않습니다.
사용자 요청에 따라 현재 T01~T09 준비를 끝낸 뒤, 최종 커밋·푸시 전에 전체 정렬과 회귀 검사를
수행합니다. [.clang-format](../../.clang-format)은 반복 실행 기준입니다.

```powershell
$Format = 'C:\NU54DEV\tools\LLVM-22.1.8\bin\clang-format.exe'
python tools/format/run_cpp_style.py --list
python tools/format/run_cpp_style.py --clang-format $Format --write
python tools/format/run_cpp_style.py --clang-format $Format
```

마지막 명령은 변경 없는 검사입니다. 대상 목록은 Git의 tracked/untracked first-party 파일을
합쳐 수집하므로 아직 커밋하지 않은 새 파일도 누락하지 않습니다.

`InsertBraces`는 보통의 제어문을 보완하지만, 전처리기·매크로 내부까지 완전한 AST 검증을
대신하지 않습니다. 한국어 Doxygen 내용도 자동 번역하지 않습니다. 최종 리뷰에서 해당 부분과
주석을 직접 대조하고, token/제어 흐름 변경·정렬 멱등성·Host·영향 target build를 확인해야 합니다.
정렬로 실행 코드가 달라졌다면 필요한 실기도 다시 수행합니다. 정렬 PASS는 HIL PASS가 아닙니다.
