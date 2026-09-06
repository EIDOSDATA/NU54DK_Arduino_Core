"""! @brief 새 exact image와 변경 범위·BLE 기계어 불변성을 독립적으로 대조합니다. """
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

WORK = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
BUILD = Path(r"C:\u3o")
SOURCE = (WORK / "source.txt").read_text().strip()
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == SOURCE
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
for before, after in ((WORK.parent / "r13/u3o-artifact-index.json", WORK / "target-artifact-index.json"),
                      (BUILD / "m12-build-evidence.json", WORK / "target-build-evidence.json")):
    assert not after.exists()
    shutil.copyfile(before, after)
index = json.loads((WORK / "target-artifact-index.json").read_text(encoding="utf-8"))
old_pair = json.loads((WORK.parent / "t12-fixture407/target-artifact-index.json").read_text(encoding="utf-8"))
pairs = [target for target in index["targets"] if target["scenario"].startswith("nucode.v04.pair_")]
assert len(pairs) == 2
rows = []
for after in pairs:
    before = next(target for target in old_pair["targets"] if target["scenario"] == after["scenario"])
    assert before["repository_compiled_sources_sha256"] == after["repository_compiled_sources_sha256"]
    rows.append({"scenario": after["scenario"], "compiled_inputs_unchanged_from_076685a": True,
                 "translation_units": len(after["repository_compiled_sources_sha256"]),
                 "configuration_unchanged": before["normalized_config_sha256"] == after["normalized_config_sha256"]})
product_delta = subprocess.check_output(["git", "diff", "--name-only", "076685a", SOURCE, "--", "cores", "variants", "libraries", "tools", "zephyr", "board_package", "platform.txt", "boards.txt"], cwd=ROOT, text=True).splitlines()
assert product_delta == ["libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp"]
objdump = Path(r"C:\ncs\toolchains\dcbdc366a1\opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin\arm-zephyr-eabi-objdump.exe")
ble = []
for target in index["targets"]:
    scenario = target["scenario"]
    if scenario.startswith("nucode.v04."):
        continue
    outputs = []
    objects = []
    for tree in (Path(r"C:\u2a"), BUILD):
        objects_found = list((tree / "nrf54l15dk_nrf54l15_cpuapp_nu54dk/zephyr_gnu" / scenario).rglob("GapScanning.cpp.obj"))
        assert len(objects_found) == 1, (scenario, tree)
        obj = objects_found[0]
        result = subprocess.run([str(objdump), "-dr", str(obj)], capture_output=True, check=True)
        normalized = re.sub(rb'^.*: +file format .*\r?\n', b'<OBJECT>: file format elf32-littlearm\n', result.stdout, flags=re.M)
        outputs.append(normalized)
        objects.append({"path": str(obj), "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest(), "disassembly_relocations_sha256": hashlib.sha256(normalized).hexdigest()})
    assert outputs[0] == outputs[1], scenario
    ble.append({"scenario": scenario, "gap_scanning_instructions_and_relocations_unchanged": True, "objects": objects})
assert len(ble) == 6
payload = {"source": SOURCE, "pair_comparison_source": "076685aa78247ec18e4fd95be50b2123a1f043fa",
           "ble_comparison_source": "18a7cbe", "product_delta": product_delta, "pair_builds": rows, "ble_object_comparisons": ble,
           "scope": "BLE explicit uint8_t cast preserves GCC target instructions and relocations. Historical BLE HIL retains its original source; no new BLE physical PASS is claimed."}
(WORK / "build-input-comparison.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for role, target in enumerate(pairs, 1):
    shutil.copyfile(target["build_log"]["path"], WORK / f"role{role}-build.log")
    record = target["identity_records"][0]["file"]["path"]
    shutil.copyfile(record, WORK / f"role{role}-build-record.yml")
print("PAIR_INPUT_AUDIT_PASS=2;BLE_INSTRUCTION_RELOCATION_EQUIVALENCE_PASS=6")
