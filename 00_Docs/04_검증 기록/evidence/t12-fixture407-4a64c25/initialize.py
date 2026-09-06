"""! @brief 새 사용자 결선 확인을 clean source와 실행 checkpoint에 고정합니다. """
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
WORK = Path(__file__).resolve().parent
PREVIOUS = WORK.parent / "t12-fixture407-resume"
SOURCE = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
BASELINE = "393e419f4c855037d4e6221c315f9be808a7d274"
assert SOURCE == "4a64c2562fdd5e9169faecf56b43043a0afec67c"
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
assert not (WORK / "source.txt").exists()
changes = subprocess.check_output(["git", "diff", "--name-only", "-z", BASELINE, SOURCE], cwd=ROOT).decode("utf-8").rstrip('\0').split('\0')
assert all(path.startswith("00_Docs/") or path in ("README.md", "tests/hil/nu54dk/README.md") for path in changes)
for name in ("runtime.py", "prepare.py", "run.py", "postflight.py", "audit_results.py"):
    text = (PREVIOUS / name).read_text(encoding="utf-8").replace("Path(r'C:\\u3o')", "Path(r'C:\\u3p')")
    (WORK / name).write_text(text, encoding="utf-8", newline="\n")
(WORK / "source.txt").write_text(SOURCE + "\n", encoding="ascii", newline="\n")
checkpoint = {"fixture_id": 407, "source": SOURCE, "user_confirmation_recorded_at_utc": "2026-09-06T14:55:35+00:00",
              "confirmation_text": "ㅇㅇ 그대로야.",
              "question_answered": "A P1.13 to B P1.14 and common GND, DAP UART disconnected, SWD connected, buttons unpressed; unchanged?",
              "prior_usb_off_rewiring_confirmed_at_utc": "2026-09-06T13:47:49+00:00",
              "wiring": "A P1.13/AIN6 P4-11 <-> B P1.14 P4-12; common GND P2-30; old A P1.12 disconnected; existing SB/PMIC unchanged",
              "signal_profile": "B INPUT pulldown/pullup/pulldown, 25 ms settling; buttons unpressed; no output driver",
              "swd_frequency_hz": 10000000, "scope": "T10/T12 Fixture 407 first physical execution, evidence/docs/commit/push; no Fixture 408 until separately confirmed"}
(WORK / "checkpoint.json").write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
software = PREVIOUS / "software-validation.json"
payload = {"current_source": SOURCE, "validated_software_source": BASELINE,
           "changed_paths": changes, "all_changes_documentation_or_historical_evidence": True,
           "production_build_runner_host_test_fixture_changes": [],
           "prior_software_result": str(software), "prior_software_result_sha256": hashlib.sha256(software.read_bytes()).hexdigest(),
           "prior_result": json.loads(software.read_text(encoding="utf-8")),
           "decision": "Preserve prior full Host/package/contract/style results under their original source; rebuild current exact pair images and inspect source/config/input hashes before physical execution. No firmware provenance strings are edited."}
(WORK / "software-input-comparison.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("407_CONFIRMATION_RECORDED=2026-09-06T14:55:35Z;CODE_AND_TEST_DELTA=0;SOURCE=" + SOURCE)
