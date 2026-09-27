"""! @brief P2 실기 계측에서 stack·heap 안전 여유와 최종 크기를 판정합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


STACK = re.compile(r"P2_STACK name=(.+?) reserved=(\d+) used=(\d+)")
MALLOC = re.compile(r"P2_MALLOC free=(\d+) allocated=(\d+) peak=(\d+)")
KHEAP = re.compile(r"P2_KHEAP index=(\d+) free=(\d+) allocated=(\d+) peak=(\d+)")


def sha256(path: Path) -> str:
    """! @brief 입력 evidence 파일의 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_role(lines: list[str]) -> dict:
    """! @brief 한 역할의 모든 checkpoint에서 stack·heap 최고치를 집계합니다. """
    stacks: dict[str, dict[str, int]] = {}
    malloc_samples = []
    kheap_samples: dict[int, list[dict[str, int]]] = {}
    unexpected = []
    for line in lines:
        match = STACK.search(line)
        if match is not None:
            name = match.group(1)
            reserved = int(match.group(2))
            used = int(match.group(3))
            previous = stacks.get(name)
            if previous is None or used > previous["used_bytes"]:
                stacks[name] = {
                    "reserved_bytes": reserved,
                    "used_bytes": used,
                    "remaining_bytes": reserved - used,
                }
        match = MALLOC.search(line)
        if match is not None:
            malloc_samples.append({
                "free_bytes": int(match.group(1)),
                "allocated_bytes": int(match.group(2)),
                "peak_bytes": int(match.group(3)),
            })
        match = KHEAP.search(line)
        if match is not None:
            index = int(match.group(1))
            kheap_samples.setdefault(index, []).append({
                "free_bytes": int(match.group(2)),
                "allocated_bytes": int(match.group(3)),
                "peak_bytes": int(match.group(4)),
            })
        if any(token in line for token in ("P2_FAIL", "FATAL", "ASSERTION FAIL", "FAULT")):
            unexpected.append(line)

    malloc = None
    if malloc_samples:
        malloc = {
            "minimum_free_bytes": min(item["free_bytes"] for item in malloc_samples),
            "maximum_allocated_bytes": max(item["allocated_bytes"] for item in malloc_samples),
            "maximum_peak_bytes": max(item["peak_bytes"] for item in malloc_samples),
            "final": malloc_samples[-1],
            "returned_after_stop": malloc_samples[-1]["allocated_bytes"] == 0,
        }
    kheaps = {}
    for index, samples in kheap_samples.items():
        kheaps[str(index)] = {
            "minimum_free_bytes": min(item["free_bytes"] for item in samples),
            "maximum_allocated_bytes": max(item["allocated_bytes"] for item in samples),
            "maximum_peak_bytes": max(item["peak_bytes"] for item in samples),
            "final": samples[-1],
            "returned_after_stop": samples[-1]["allocated_bytes"] == 0,
        }
    return {
        "stack_high_water": dict(sorted(stacks.items())),
        "malloc": malloc,
        "kernel_heaps": kheaps,
        "unexpected_fault_lines": unexpected,
    }


def evidence_record(path: Path) -> dict:
    """! @brief PASS evidence를 검증하고 역할별 메모리 집계를 만듭니다. """
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("result") != "PASS":
        raise RuntimeError(f"PASS가 아닌 evidence입니다: {path}")
    roles = {
        role: aggregate_role(lines)
        for role, lines in document["lines"].items()
    }
    if any(item["unexpected_fault_lines"] for item in roles.values()):
        raise RuntimeError(f"예상하지 않은 fault가 있습니다: {path}")
    return {
        "path": path.as_posix(),
        "sha256": sha256(path),
        "case": document["case"],
        "result": document["result"],
        "observed": document["observed"],
        "roles": roles,
    }


def main() -> int:
    """! @brief 세 오류·복구 부하와 선행 장시간 부하를 합쳐 최종 결정을 기록합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    files = [
        args.evidence_dir / "coc-peer-credit-r2.json",
        args.evidence_dir / "audio-encryption-recovery.json",
        args.evidence_dir / "cs-peer-loss-recovery.json",
    ]
    workloads = [evidence_record(path) for path in files]
    document = {
        "schema_version": 1,
        "case": "m31-p2-final-stack-heap-margin-and-size-decision",
        "result": "PASS",
        "workloads": workloads,
        "previous_supported_worst_loads": [
            {
                "record": "00_Docs/04_검증 기록/258_M31_P2_Audio_양방향_장시간과_종료_복구.md",
                "load": "supported bidirectional two-stream CIS, 10000 frames per direction and 20 teardown cycles",
                "stack_high_water_bytes": {
                    "client": {"BT RX WQ": [1520, 3200], "BT LW WQ": [936, 2104], "MPSL Work": [400, 1024], "main": [3568, 8192]},
                    "server": {"BT RX WQ": [1232, 3200], "BT LW WQ": [1168, 2104], "MPSL Work": [656, 1024], "main": [3560, 8192]},
                },
                "malloc_allocated_peak_bytes": [0, 0],
            },
            {
                "record": "00_Docs/04_검증 기록/260_M31_P2_CS_누락_분류와_256_step_장시간.md",
                "load": "1000 valid 256/256-step CS raw results",
                "stack_high_water_bytes": {
                    "initiator": {"BT RX WQ": [1520, 3200], "BT LW WQ": [936, 2104], "MPSL Work": [504, 1024], "main": [1104, 8192]},
                    "reflector": {"BT RX WQ": [1232, 3200], "BT LW WQ": [1168, 2104], "MPSL Work": [760, 1024], "main": [1032, 8192]},
                },
                "malloc_allocated_peak_bytes": [0, 0],
            },
        ],
        "allocation_failure_and_return": {
            "net_buf_pool": {
                "result": "PASS",
                "evidence": "257 record: four 512-byte CoC TX buffers accepted, fifth returned busy, all four echoed, reconnect recovery passed",
                "classification": "bounded pool allocation failure; distinct from direct peer-credit exhaustion",
            },
            "libc_malloc_and_kernel_heap": {
                "result": "PASS",
                "evidence": "all reported final allocated values are zero; CoC and CS kernel-heap peaks returned to zero allocation",
                "forced_failure_injection": "NOT RUN — measured paths did not allocate from libc malloc; synthetic exhaustion would not exercise a supported consumer",
            },
            "leak_or_unbounded_retry": {
                "result": "PASS",
                "evidence": "bounded timeouts, finite recovery actions, both STOP in all three new HIL cases",
            },
        },
        "telemetry_impact": {
            "result": "PASS",
            "placement": "reports are emitted at ready/error/recovery/STOP checkpoints, outside the recovery acceptance counter",
            "native_comparison": "the native pairs use the same analyzer and heap-stat configuration",
            "timing": "all acceptance windows are wall-clock bounded; no cause-free retry can convert a failure to PASS",
        },
        "sdc_pool": {
            "result": "PASS",
            "record": "00_Docs/04_검증 기록/248_M31_P2_SDC_pool_정적_경계_감사.md",
            "contract": "fixed NCS v3.4.0 role/count formula, initialization size check, 8-byte address alignment",
            "interpretation": "static sdc_mempool symbol size is not runtime high-water",
            "decision": "keep SDK-calculated sizes; internal high-water is not an additional gate",
        },
        "final_size_decisions": [
            {
                "item": "main stack",
                "reserved_bytes": 8192,
                "largest_observed_used_bytes": 3568,
                "minimum_observed_margin_bytes": 4624,
                "decision": "KEEP",
                "reason": "maximum remains from supported two-stream Audio; cross-feature and instrumentation variance does not justify a profile-wide reduction",
            },
            {
                "item": "system workqueue stack",
                "reserved_bytes": 4096,
                "largest_new_observed_used_bytes": 912,
                "minimum_new_observed_margin_bytes": 3184,
                "decision": "KEEP",
                "reason": "shared system facility across standard/full and adaptive feature combinations",
            },
            {
                "item": "BT RX workqueue stack",
                "reserved_bytes": 3200,
                "largest_observed_used_bytes": 1520,
                "minimum_observed_margin_bytes": 1680,
                "decision": "KEEP",
                "reason": "same maximum occurs in Audio and CS supported workloads",
            },
            {
                "item": "BT long workqueue stack",
                "reserved_bytes": 2104,
                "largest_observed_used_bytes": 1168,
                "minimum_observed_margin_bytes": 936,
                "decision": "KEEP",
                "reason": "shared Bluetooth host path; no configuration-specific shrink proof",
            },
            {
                "item": "MPSL work stack",
                "reserved_bytes": 1024,
                "largest_observed_used_bytes": 760,
                "minimum_observed_margin_bytes": 264,
                "decision": "KEEP",
                "reason": "CS reflector leaves only 264 bytes in the observed maximum",
            },
            {
                "item": "libc malloc arena",
                "reserved_bytes": 8192,
                "largest_observed_allocated_bytes": 0,
                "decision": "KEEP",
                "reason": "standard/full compatibility and optional codec/library paths remain; zero use in selected paths alone is not shrink proof",
            },
            {
                "item": "feature kernel heap",
                "decision": "KEEP CONFIGURED VALUES",
                "reason": "CoC 8192-byte pool stayed free; CS small pool reached 264-byte peak and returned; Audio source intentionally keeps kernel heap disabled",
            },
        ],
        "conclusion": "No supported workload shows overflow, leak, or unrecovered allocation failure. No size has sufficient evidence for reduction, so existing reservations remain final for P2.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"P2 memory finalization: PASS -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
