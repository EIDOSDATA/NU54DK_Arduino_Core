"""! @brief PASS·조건부 SKIP·미실기를 실제 log에서 구분해 고정합니다. """
from pathlib import Path
import datetime
import hashlib
import json
import re

WORK = Path(__file__).resolve().parent
source = (WORK / "source.txt").read_text().strip()
host = (WORK / "gate-host-final.log").read_text(encoding="utf-8-sig")
counts = list(map(int, re.findall(r'^Ran (\d+) tests? in ', host, re.M)))
assert len(counts) == 81 and sum(counts) == 656
skips = re.findall(r"\.\.\. skipped (.+)", host)
assert len(skips) == 1 and "NUCODE_M13_CLI_DISCOVERY" in skips[0]
assert "M12_GATE_PASS=host" in host and "FAILED (" not in host
checks = {"gate-contract-final.log": "Ran 45 tests", "gate-package-final.log": "Ran 20 tests",
          "gate-inventory-final.log": "M27_RELEASE_CONTRACT_PASS=gates:16;blockers:8",
          "style-check.log": "CPP_STYLE_FILES=358; FAILED=0; WRITE=0",
          "gate-docs-prebuild.log": "PASS: 189 files", "gate-examples-final.log": "M12_GATE_PASS=examples",
          "build.log": "M12_ZEPHYR_BUILD_PASS=8", "inspect-prepared.log": "PREPARED_IMAGE_IDENTITY_PASS=2",
          "usb-only.log": "USB_PAIR_INVENTORY_PASS=2"}
for name, marker in checks.items():
    assert marker in (WORK / name).read_text(encoding="utf-8-sig"), (name, marker)
build = json.loads((WORK / "target-build-evidence.json").read_text(encoding="utf-8"))
assert build["status"] == "passed" and len(build["scenarios"]) == 8
comparison = json.loads((WORK / "build-input-comparison.json").read_text(encoding="utf-8"))
assert len(comparison["pair_builds"]) == 2 and len(comparison["ble_object_comparisons"]) == 6
payload = {"source": source, "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "host": {"total": 656, "passed": 655, "conditional_skipped": 1, "groups": 81, "skip_reason": skips[0], "required_native_compiler_skips": 0},
           "focused_host": {"total": 113, "passed": 113}, "compiler_selection_tests_added": 6,
           "contract_passed": 45, "package_passed": 20, "style_files_passed": 358,
           "markdown_pre_evidence_files_passed": 189, "examples_discovery": "passed; current-source isolated staging, not example compilation",
           "inventory": [75, 23, 16], "readiness_blockers": 8,
           "target": {"total_built": 8, "pair": 2, "ble": 6, "physical_executed": False},
           "pair_translation_units_unchanged_from_prepared407": True, "ble_gap_instructions_relocations_unchanged": True,
           "security_policy_modified": False, "gcc_executable_still_blocked": True,
           "host_route": "Explicit installed LLVM Clang/LLD 22.1.8 with WinLibs UCRT libraries; no GCC invocation or renamed executable",
           "physical_fixture407_status_at_record": "NOT RUN",
           "hashes": {name: hashlib.sha256((WORK / name).read_bytes()).hexdigest() for name in ["gate-host-final.log", *checks]}}
with (WORK / "software-validation.json").open("x", encoding="utf-8", newline="\n") as output:
    json.dump(payload, output, ensure_ascii=False, indent=2)
    output.write("\n")
print("SOFTWARE_VALIDATION_PASS;HOST=655_PASS_1_CONDITIONAL_SKIP;TARGET_BUILD=8;PHYSICAL_NOT_RUN")
