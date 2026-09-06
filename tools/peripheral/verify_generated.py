#!/usr/bin/env python3
"""! @brief 기존 정책 원본의 생성물을 독립 Python process 두 번으로 재현하고 drift를 검사합니다. """
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GENERATORS = (
    "verify_m23_inventory", "verify_m24_serial_contract",
    "verify_m26_system_contract", "verify_v04_test_plan",
)


class GenerationFailure(RuntimeError):
    """! @brief 원본·생성 결정성 또는 저장된 생성물 계약의 실패입니다. """


def load_generator(name: str) -> Any:
    """! @brief 같은 tools 디렉터리의 기존 생성기만 읽습니다. """
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("r13_" + name, path)
    if spec is None or spec.loader is None:
        raise GenerationFailure(f"생성기를 읽지 못했습니다: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_all() -> dict[str, str]:
    """! @brief 각 기존 schema·부정 계약을 통과한 데이터만 메모리에 생성합니다. """
    m23, m24, m26, plan = map(load_generator, GENERATORS)
    manifest = m23.strict_json_object(m23.MANIFEST_PATH)
    m23.validate_schema_contract(m23.strict_json_object(m23.SCHEMA_PATH))
    instances = m23.validate_inventory(manifest)
    m23.validate_repository_sources(instances)
    serial = m24.strict_json_object(m24.CONTRACT_PATH)
    m24.validate_schema_contract(m24.strict_json_object(m24.SCHEMA_PATH))
    m24.validate_contract(serial)
    system = m26.strict_json(m26.CONTRACT_PATH)
    capabilities = m26.validate_contract(system)
    test_plan = plan.read_json(plan.PLAN)
    inventory = plan.validate(test_plan)
    outputs = {
        m23.CPP_PATH: m23.render_cpp(instances),
        m23.MATRIX_PATH: m23.render_matrix(manifest, instances),
        m24.DOCUMENT_PATH: m24.render_document(serial),
        m26.DOCUMENT_PATH: m26.render_document(system, capabilities),
        plan.DOCUMENT: plan.render(test_plan, inventory),
    }
    return {path.relative_to(ROOT).as_posix(): text for path, text in outputs.items()}


def verify_outputs(first: dict[str, str], second: dict[str, str], root: Path) -> dict[str, dict[str, Any]]:
    """! @brief 서로 다른 process 결과와 저장된 UTF-8/LF 의미의 생성물을 대조합니다. """
    if not first or first != second:
        raise GenerationFailure("Python hash seed/process 간 생성 결과가 다릅니다.")
    records = {}
    for relative, expected in sorted(first.items()):
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise GenerationFailure(f"생성물 경로가 저장소 밖입니다: {relative}")
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise GenerationFailure(f"생성물을 읽지 못했습니다: {relative}") from error
        if actual != expected:
            raise GenerationFailure(f"저장된 생성물이 원본에서 drift했습니다: {relative}")
        data = expected.encode("utf-8")
        records[relative] = {"sha256_utf8_lf": hashlib.sha256(data).hexdigest(), "bytes_utf8_lf": len(data)}
    return records


def main() -> int:
    """! @brief 원본 파일을 쓰지 않고 두 독립 생성과 저장소 drift를 검사합니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.render_json:
        print(json.dumps(render_all(), ensure_ascii=True, sort_keys=True))
        return 0
    results = []
    for seed in (17, 101):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--render-json"],
            cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONUTF8": "1"},
            capture_output=True, encoding="utf-8", timeout=120,
        )
        if result.returncode != 0:
            raise GenerationFailure(f"정책 생성 실패: {result.stderr.strip()}")
        results.append(json.loads(result.stdout))
    records = verify_outputs(results[0], results[1], ROOT)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps({
            "schema_version": 1, "physical_executed": False,
            "generators": list(GENERATORS), "python_hash_seeds": [17, 101],
            "normalization": "UTF-8 with LF; existing Git checkout EOL contract",
            "outputs": records,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"GENERATED_CONTRACTS_PASS={len(records)};GENERATORS={len(GENERATORS)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GenerationFailure, subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as error:
        print(f"GENERATED_CONTRACTS_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
