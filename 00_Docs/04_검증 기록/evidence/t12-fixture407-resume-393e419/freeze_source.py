"""! @brief 범위와 미완료 gate를 기록한 clean source를 로컬에 고정합니다. """
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
WORK = Path(__file__).resolve().parent
todo = ROOT / "00_Docs/TODO_v0.4.0.md"
text = todo.read_text(encoding="utf-8").replace("TODO-V04-001 / 3.8", "TODO-V04-001 / 3.9")
rows = {
    "이번 요청의 실행 범위": "사용자 재개 지시로 LLVM 22.1.8 Host 선택 지원을 추가했다. T09/T12·R13 도구 유지보수: CC/CXX·JSON 인자 선택 23개 시험군, 명시적 환경 6개 회귀, 자기 복사 대입·Arduino entrypoint 분리, BLE scan enum→uint8_t 명시 변환 1줄. 관련 Host 113 PASS. 전체 Host·계약·Inventory·정렬 및 pair/BLE target을 검증한 뒤 407만 실행. SDK·board·보안 정책 변경 없음",
    "이번에 끝낸 일": "기존 g++는 재개 후에도 Windows 차단. 설치된 Clang/LLD는 실제 compile/link/run 가능하며 관련 Host 113개 PASS. 407 준비·이전 차단은 80번 보존. 401~406 누계 기능 216·samples 46,656 유지",
    "진행 중인 T 항목": "T09/T12: LLVM 전체 Host 및 current-source pair/BLE target 회귀 진행. 407 실기 미실행. 408도 필수 후속",
    "다음 착수 항목": "**LLVM 전체 회귀·새 exact pair image 확인 후 Fixture 407 실기; 408도 필수**",
    "다음 구체적 행동": "새 clean source에서 canonical Host·계약·Inventory·docs·style와 pair 2개/BLE 6개 target을 검사한다. 407 결선 확인 30분이 경과했으므로 실제 flash 직전 같은 결선·버튼 미누름을 재확인한다. SWD 10 MHz 고정",
    "다음 작업에 필요한 사용자 행동": "별도 Host 환경 경로는 필요 없다. 설치된 LLVM이 정상 동작한다. 모든 software·image 준비 후 407 결선 A P1.13↔B P1.14·공통 GND, DAP UART 분리/SWD 연결·버튼 미누름이 유지되는지만 재확인한다",
    "이 TODO 작성 작업의 실행 중 시험": "관련 Host 113개 종료·PASS. 후속 canonical 전체 Host 및 target 회귀 예정. 407 flash/reset/HIL 미실행. 마지막 업로드 source는 406 exact 96f38e9; 재연결 후 runtime identity 미검사",
    "문서 작업 검증": "초기 Clang 실행에서 자기 대입·weak main·enum narrowing·CMake target 선택 문제를 발견해 기록했다. 수정 뒤 관련 Host 113/113 PASS. 전체 Host 656개와 새 target·문서 결과는 아직 미확정",
}
for key, value in rows.items():
    text, count = re.subn(r'^\| ' + re.escape(key) + r' \|.*$', '| ' + key + ' | ' + value + ' |', text, flags=re.M)
    assert count == 1, key
todo.write_text(text, encoding="utf-8")
changes = subprocess.check_output(["git", "status", "--porcelain", "-z"], cwd=ROOT).decode().split('\0')
paths = [line[3:] for line in changes if line]
for path in paths:
    assert (path.startswith("tests/host/") or path in ("00_Docs/TODO_v0.4.0.md", "00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md", "libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp")), path
subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
subprocess.run(["git", "add", "--", *paths], cwd=ROOT, check=True)
subprocess.run(["git", "commit", "-m", "test(host): support explicit Clang compiler selection"], cwd=ROOT, check=True)
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
(WORK / "source.txt").write_text(source + "\n", encoding="ascii")
(WORK / "source-files.json").write_text(json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("RESUME_SOURCE=" + source)
