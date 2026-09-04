#!/usr/bin/env python3
"""Validate the v0.4 preparation inventory; never execute HIL or promote a gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "tests/hil/nu54dk/v04_test_plan.json"
DOCUMENT = ROOT / "00_Docs/01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md"
REQUIRED = {
    "V04-UART-DATA": {"uarte"}, "V04-UART-FLOW": {"uarte"},
    "V04-SPI-DATA": {"spim", "spis"}, "V04-TWI-DATA": {"twim", "twis"},
    "V04-PMIC-READ": {"twim"}, "V04-ADC": {"saadc"},
    "V04-ADC-INTERNAL": {"saadc"}, "V04-PWM": {"pwm"},
    "V04-GPIO": {"gpio", "gpiote"},
    "V04-EVENT": {"timer", "egu", "dppic", "ppib", "grtc"},
    "V04-PDM": {"pdm"}, "V04-I2S": {"i2s"}, "V04-QDEC": {"qdec"},
    "V04-DMA-LIFETIME": {"uarte", "spim", "spis", "twim", "twis", "saadc", "pwm", "pdm", "i2s"},
    "V04-BUS-RECOVERY": {"uarte", "spim", "spis", "twim", "twis"},
    "V04-SERIAL-CONCURRENCY": {"uarte", "spim", "spis", "twim", "twis"},
    "V04-ANALOG-CONCURRENCY": {"saadc", "pwm", "pdm", "i2s", "qdec", "timer", "gpiote", "egu", "dppic", "ppib", "grtc", "gpio"},
    "V04-SOAK": {"uarte", "spim", "spis", "twim", "twis", "saadc", "pwm", "pdm", "i2s", "qdec"},
    "V04-SYSTEM-BOUNDARY": {"system"},
}


class PlanFailure(ValueError):
    """Preparation coverage or schema drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanFailure(message)


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def validate(plan: dict, root: Path = ROOT) -> list[dict]:
    require(set(plan) == {"schema_version", "plan_id", "status", "scope_record", "baseline_source", "board_revision", "limits", "groups", "cases"}, "plan fields drifted")
    require(plan["schema_version"] == 1 and plan["status"] == "preparation", "not a preparation plan")
    require(plan["plan_id"] == "nu54dk-v04-functional-v1", "plan identity drifted")
    for key in ("baseline_source", "board_revision"):
        require(isinstance(plan[key], str) and re.fullmatch(r"[0-9a-f]{40}", plan[key]) is not None, f"invalid {key}")
    require(plan["scope_record"] == "00_Docs/04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md", "scope changed")
    require((root / plan["scope_record"]).is_file(), "missing scope record")
    inventory = read_json(root / "variants/nu54dk/peripheral-manifest.json")["instances"]
    serial = read_json(root / "variants/nu54dk/serial-fabric-contract.json")
    require(plan["board_revision"] == serial["identity"]["board_revision"], "board identity drifted")
    expected_groups: dict[str, list[str]] = {}
    for item in inventory:
        expected_groups.setdefault("system" if item["milestone"] == "M26" else item["kind"], []).append(item["id"])
    require(plan["groups"] == expected_groups, "inventory group/identity omission or drift")
    limits = plan["limits"]
    require(set(limits) == {"command_timeout_seconds", "stop_timeout_us", "recovery_repetitions", "handover_repetitions", "standalone_soak_seconds", "concurrent_soak_seconds", "unexpected_loss_allowed", "unexpected_reset_allowed", "guard_bytes"}, "limit fields drifted")
    for key, value in limits.items():
        require(type(value) is int and 0 <= value <= 86400000, f"invalid limit {key}")
        if not key.startswith("unexpected_"):
            require(value > 0, f"zero limit {key}")
    require(limits["unexpected_loss_allowed"] == limits["unexpected_reset_allowed"] == 0, "loss/reset allowance changed")
    require(isinstance(plan["cases"], list), "cases must be an array")
    seen = set()
    errata = set()
    for case in plan["cases"]:
        require(set(case) == {"id", "groups", "fixture", "modes", "parameters", "oracle", "needs", "reuse", "errata"}, "case fields drifted")
        name = case["id"]
        require(name in REQUIRED and name not in seen, f"unknown/duplicate case: {name}")
        seen.add(name)
        require(set(case["groups"]) == REQUIRED[name] and len(case["groups"]) == len(set(case["groups"])), f"case group coverage: {name}")
        require(case["fixture"] in {"onboard", "peer", "primary-route", "mixed", "contract"}, f"invalid fixture: {name}")
        require(isinstance(case["modes"], list) and case["modes"] and all(isinstance(mode, str) and mode for mode in case["modes"]) and len(set(case["modes"])) == len(case["modes"]), f"invalid modes: {name}")
        require(isinstance(case["parameters"], dict) and case["parameters"], f"missing parameters: {name}")
        for key in ("oracle", "needs"):
            require(isinstance(case[key], str) and case[key].strip(), f"missing {key}: {name}")
        require(isinstance(case["reuse"], list) and isinstance(case["errata"], list), f"invalid evidence/errata: {name}")
        for path in case["reuse"]:
            candidate = (root / path).resolve()
            require(candidate.is_relative_to(root.resolve()) and candidate.is_file(), f"invalid reuse path: {path}")
        require(all(type(number) is int for number in case["errata"]), f"invalid errata: {name}")
        errata.update(case["errata"])
    require(seen == set(REQUIRED), f"missing case: {sorted(set(REQUIRED) - seen)}")
    require(errata == {item["id"] for item in serial["errata"]}, "errata coverage drifted")
    dma_ids = {name for case in plan["cases"] if case["id"] == "V04-DMA-LIFETIME" for group in case["groups"] for name in plan["groups"][group]}
    expected_dma = {item["id"] for item in inventory if item["milestone"] in {"M24", "M25"} and item["dma"]["hardware"]}
    require(dma_ids == expected_dma, "DMA applicability mismatch")
    return inventory


def render(plan: dict, inventory: list[dict], root: Path = ROOT) -> str:
    profiles = read_json(root / "variants/nu54dk/serial-fabric-contract.json")["approved_profiles"]
    lines = ["# v0.4.0 기능 시험 목록", "", "이 문서는 `v04_test_plan.json`에서 생성한다. 손으로 수정하지 않는다.", "",
             "**준비 기준선이며 실기 결과·최종 지원 선언이 아니다.** 수치는 코어 기능 검증을 위한 초기 engineering 기준이며 최대 성능 보증이나 사용자와 합의한 실측값이 아니다.", "",
             "T02에서 API/핀/clock 성립을 대조하고 T04~T08에서 실행 vector·fixture를 고정한다. 불가능한 필수 조합은 HOLD로 남긴다. 실제 실행 전 계획 개정·image·배선표 hash를 함께 고정한다.", "",
             "- 범위: [42번 합의](<../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>), 진행: [TODO](../TODO_v0.4.0.md).",
             "- 원본: [시험 JSON](../../tests/hil/nu54dk/v04_test_plan.json), 검사: [verify_v04_test_plan.py](../../tools/peripheral/verify_v04_test_plan.py).",
             "- 각 family/instance/mode는 별도 결과 ID를 가진다. 적용 불가 mode는 이유를 기록하며 암묵적으로 PASS하지 않는다.",
             "- 기능 sweep는 각 rate·buffer·mode를 기준 설정에서 하나씩 변경하고, protocol mode×bit order는 전 조합을 검사한다. soak는 단독 통과한 기준 설정으로 별도 실행한다.",
             "- 동일 block 방향 있는 충돌 조합은 86개다. 두 board의 같은 roundtrip 오류를 가리지 않도록 독립 pattern과 count를 검사한다.",
             "- errata 조건·workaround는 고정 SDK와 silicon revision으로 T02/T07에서 구체화한다. 번호가 있다는 사실만으로 회귀 시험이 준비된 것은 아니다.",
             "- QDEC·GPIO·event는 DMA로 세지 않는다. M26 16개는 기존 지원 경계 전수 판정이며 raw 보안/RADIO 실행 대상이 아니다.", "", "## 1. 공통 기준", "", "| 기준 | 값 |", "| --- | --- |"]
    lines += [f"| {key} | {value} |" for key, value in plan["limits"].items()]
    lines += ["", "모든 외부 시험은 T10 배선 확인 뒤 실행한다. PMIC에는 승인된 read-only 요청만 보내며 bus 오류 주입·1MHz 부하는 공유 PMIC 경로에서 금지한다.", "", "## 2. 시험 family", ""]
    for case in plan["cases"]:
        identities = [name for group in case["groups"] for name in plan["groups"][group]]
        lines += [f"### {case['id']}", "", f"- 대상: {', '.join(identities)}", f"- 실행 자원: `{case['fixture']}`", f"- 모드: {', '.join(case['modes'])}", f"- 수치: `{json.dumps(case['parameters'], ensure_ascii=False, sort_keys=True)}`", f"- 합격 기준: {case['oracle']}", f"- 준비 의존성: {case['needs']}", f"- 기존 runner 참고: {', '.join(case['reuse']) or '신규 필요'}; errata: {', '.join(map(str, case['errata'])) or '해당 목록 없음'}", ""]
    lines += ["## 3. M24 primary route 추적", "", "이 표의 온보드 분류는 primary 기본 경로만 뜻한다. UART flow/error·I2C peer·1MHz·복구는 추가 결선이 필요할 수 있다.", "", "| Identity | 계약 profile | Primary 자원 | 분류 |", "| --- | --- | --- | --- |"]
    lines += [f"| {p['identity']} | {p['id']} | {p['test_resource']} | {p['execution_class']} |" for p in profiles]
    lines += ["", "## 4. Inventory 추적", "", "아래는 현재 manifest의 상태 축을 그대로 표시한 것으로 이 계획의 실행 결과가 아니다. 최신 onboard 증거는 41번 기록과 개별 source를 별도 대조한다.", "", "| Identity | 단계 | source / exposure | build / semantic | HIL / concurrent HIL | 요구 family |", "| --- | --- | --- | --- | --- | --- |"]
    for item in inventory:
        state = item["states"]
        families = [case["id"] for case in plan["cases"] if any(item["id"] in plan["groups"][group] for group in case["groups"])]
        lines += [f"| {item['id']} | {item['milestone']} | {state['source']} / {state['exposure']} | {state['build']} / {state['semantic']} | {state['hil']} / {state['concurrent_hil']} | {', '.join(families)} |"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the tracked Markdown only")
    args = parser.parse_args()
    plan = read_json(PLAN)
    inventory = validate(plan)
    output = render(plan, inventory)
    if args.write:
        DOCUMENT.write_text(output, encoding="utf-8", newline="\n")
    require(DOCUMENT.read_text(encoding="utf-8") == output, "generated document drift; run --write")
    print(f"V04_TEST_PLAN_PASS=identities:{len(inventory)};families:{len(plan['cases'])};physical_executed:0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PlanFailure, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(f"V04_TEST_PLAN_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
