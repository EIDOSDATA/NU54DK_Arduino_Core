"""! @brief GATT Ranging Service가 없는 UUID advertiser를 반복 거부합니다. """

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ble_pair_hil_common import flash_image_pyocd
from m6_serial_echo import import_pyserial
from m31_ble_capability_run import collect_register_identity, discover
from m31_cs_negative_attestation import (
    build_missing_service_records,
    complete_program_phase,
    make_attestation,
    phase_contract,
    prepare_program_phase,
)
from m31_cs_ras_pair_run import collect_until, hardware_reset
from v04_protocol import ProbeLocks


REPOSITORY = Path(__file__).resolve().parents[3]
APPLICATION_ROOTS = {
    "initiator": (
        REPOSITORY
        / "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator"
    ),
    "missing_service_peer": (
        Path(__file__).resolve().parent / "fixtures/RasMissingService"
    ),
}


def _disconnect_pair(
    initiator: Any,
    peer: Any,
    record: dict[str, Any],
    timeout: float = 10.0,
) -> bool:
    """! @brief 성공·실패 경로에서 ACL disconnect를 bounded하게 요청합니다. """

    try:
        initiator.write(b"d")
        initiator.flush()
        record["disconnect_commands"] += 1
        confirmed = collect_until(
            initiator,
            peer,
            record,
            [
                ("i", "CS initiator disconnected"),
                ("r", "CS missing service disconnected"),
            ],
            timeout,
        )
    except Exception as error:
        record["cleanup_error"] = type(error).__name__
        confirmed = False
    record["final_disconnect_confirmed"] = confirmed
    return confirmed


class _DisconnectingPair:
    """! @brief 부분 open을 포함해 항상 disconnect 시도와 serial close를 수행합니다. """

    def __init__(
        self,
        serial_module: Any,
        initiator_port: str,
        peer_port: str,
        record: dict[str, Any],
    ) -> None:
        self.serial_module = serial_module
        self.initiator_port = initiator_port
        self.peer_port = peer_port
        self.record = record
        self.initiator: Any = None
        self.peer: Any = None

    def __enter__(self) -> tuple[Any, Any]:
        """! @brief 두 serial을 열고 partial-open 실패를 즉시 정리합니다. """

        try:
            self.initiator = self.serial_module.Serial(
                self.initiator_port, 115200, timeout=0.05, write_timeout=2.0
            )
            self.peer = self.serial_module.Serial(
                self.peer_port, 115200, timeout=0.05, write_timeout=2.0
            )
        except Exception:
            if self.initiator is not None:
                self.initiator.close()
            raise
        return self.initiator, self.peer

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        """! @brief 완료되지 않은 ACL을 끊고 두 serial을 역순으로 닫습니다. """

        if (
            self.initiator is not None
            and self.peer is not None
            and not self.record.get("final_disconnect_confirmed", False)
        ):
            _disconnect_pair(self.initiator, self.peer, self.record)
        for port in (self.peer, self.initiator):
            if port is not None:
                port.close()


def main() -> int:
    """! @brief 두 보드에서 missing-service 거부 20회와 정리를 검증합니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--initiator-probe-sha256", required=True)
    parser.add_argument(
        "--missing-service-peer-probe-sha256",
        "--spoof-probe-sha256",
        dest="missing_service_peer_probe_sha256",
        required=True,
    )
    parser.add_argument("--initiator-image", type=Path, required=True)
    parser.add_argument(
        "--missing-service-peer-image",
        "--spoof-image",
        dest="missing_service_peer_image",
        type=Path,
        required=True,
    )
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.cycles != 20:
        parser.error("release campaign requires exactly 20 cycles")
    if args.reset_only:
        parser.error("release campaign requires exact sector programming")
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    if args.source_clean:
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
        ).strip()
        changed = subprocess.check_output(
            ("git", "status", "--porcelain"), cwd=REPOSITORY, text=True
        ).strip()
        if changed or args.core_revision != revision:
            parser.error("exact HIL requires clean source and full HEAD revision")

    serial, ports = import_pyserial()
    init_uid, init_volume, init_port = discover(args.initiator_probe_sha256, ports)
    spoof_uid, spoof_volume, spoof_port = discover(
        args.missing_service_peer_probe_sha256, ports
    )
    if init_uid == spoof_uid or init_port == spoof_port:
        raise RuntimeError("role mapping overlap")
    images = {
        "initiator": args.initiator_image,
        "missing_service_peer": args.missing_service_peer_image,
    }
    phase = prepare_program_phase(
        args.output,
        "missing_service",
        args.core_revision,
        images,
        APPLICATION_ROOTS,
    )
    record = {
        "status": "FAIL",
        "test": "advertised_ranging_uuid_without_gatt_service",
        "core_revision": args.core_revision,
        "source_clean": True,
        "board_revision": phase.board_revision,
        "negative_phase": phase_contract(phase),
        "initiator_probe_sha256": args.initiator_probe_sha256,
        "missing_service_peer_probe_sha256": (
            args.missing_service_peer_probe_sha256
        ),
        "initiator_port": init_port,
        "missing_service_peer_port": spoof_port,
        "initiator_image_sha256": hashlib.sha256(args.initiator_image.read_bytes()).hexdigest(),
        "missing_service_peer_image_sha256": hashlib.sha256(
            args.missing_service_peer_image.read_bytes()
        ).hexdigest(),
        "cycles_expected": args.cycles,
        "cycles_rejected": 0,
        "disconnect_commands": 0,
        "final_disconnect_confirmed": False,
        "mode": "sector_flash_pair_reset",
        "initiator_lines": [],
        "reflector_lines": [],
    }
    opened_ports = {}
    flash_results = {}
    cleanup = {}
    try:
        with ProbeLocks([init_uid, spoof_uid]):
            record["initiator_registers"] = collect_register_identity(init_uid, init_volume)
            record["spoof_registers"] = collect_register_identity(spoof_uid, spoof_volume)
            with _DisconnectingPair(
                serial, init_port, spoof_port, record
            ) as (initiator, spoof):
                opened_ports = {
                    "initiator": initiator,
                    "missing_service_peer": spoof,
                }
                initiator.reset_input_buffer()
                spoof.reset_input_buffer()
                record["missing_service_peer_flash"] = flash_image_pyocd(
                    "cs_missing_ras",
                    spoof_uid,
                    args.missing_service_peer_image,
                    120.0,
                    hardware_reset=True,
                )
                record["initiator_flash"] = flash_image_pyocd(
                    "cs_initiator",
                    init_uid,
                    args.initiator_image,
                    120.0,
                    hardware_reset=True,
                )
                flash_results = {
                    "initiator": record["initiator_flash"],
                    "missing_service_peer": record[
                        "missing_service_peer_flash"
                    ],
                }
                initiator.reset_input_buffer()
                spoof.reset_input_buffer()
                hardware_reset(args.missing_service_peer_probe_sha256)
                hardware_reset(args.initiator_probe_sha256)
                started = time.monotonic()
                for cycle in range(args.cycles):
                    if cycle > 0:
                        initiator.write(b"d")
                        initiator.flush()
                        record["disconnect_commands"] += 1
                    if not collect_until(
                        initiator, spoof, record,
                        [("i", "CS initiator connected; securing"),
                         ("i", "CS initiator failed: -2")], 30.0
                    ):
                        raise RuntimeError("missing GATT service not rejected")
                    if any("CS_RAW counter=" in line or "CS procedures requested" in line
                           for line in record["initiator_lines"]):
                        raise RuntimeError("spoof produced ranging output")
                    record["cycles_rejected"] = cycle + 1
                if not _disconnect_pair(initiator, spoof, record):
                    raise RuntimeError("final missing-service disconnect incomplete")
                record["initiator_disconnects"] = sum(
                    "CS initiator disconnected" in line
                    for line in record["initiator_lines"]
                )
                record["peer_disconnects"] = sum(
                    "CS missing service disconnected" in line
                    for line in record["reflector_lines"]
                )
                initiator_failures = sum(
                    "CS initiator failed: -2" in line
                    for line in record["initiator_lines"]
                )
                spoof_connections = sum(
                    "CS missing service connected" in line
                    for line in record["reflector_lines"]
                )
                record["initiator_failures"] = initiator_failures
                record["peer_connections"] = spoof_connections
                if (initiator_failures != args.cycles or
                        spoof_connections < args.cycles or
                        record["initiator_disconnects"] < args.cycles or
                        record["peer_disconnects"] < args.cycles):
                    raise RuntimeError("reject or connection count mismatch")
                record["elapsed_s"] = round(time.monotonic() - started, 3)
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(init_uid, "<probe>").replace(spoof_uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    finally:
        disconnected = record.get("final_disconnect_confirmed") is True
        cleanup = {
            "initiator": {
                "stop": "PASS" if disconnected else "FAIL",
                "disconnect": "PASS" if disconnected else "FAIL",
                "serial_close": (
                    "PASS"
                    if getattr(opened_ports.get("initiator"), "is_open", None)
                    is False
                    else "FAIL"
                ),
            },
            "missing_service_peer": {
                "stop": "NOT_APPLICABLE",
                "disconnect": "PASS" if disconnected else "FAIL",
                "serial_close": (
                    "PASS"
                    if getattr(
                        opened_ports.get("missing_service_peer"),
                        "is_open",
                        None,
                    )
                    is False
                    else "FAIL"
                ),
            },
        }
        record["cleanup"] = cleanup
        record["missing_service_peer_lines"] = record["reflector_lines"]

    if "failure_class" not in record:
        try:
            exact_program = complete_program_phase(
                phase,
                args.core_revision,
                {"initiator": init_uid, "missing_service_peer": spoof_uid},
                {
                    "initiator": args.initiator_probe_sha256,
                    "missing_service_peer": (
                        args.missing_service_peer_probe_sha256
                    ),
                },
                flash_results,
            )
            cycle_records = build_missing_service_records(record, cleanup)
            record["dispatch_cycle_records"] = cycle_records
            record["program_phase"] = exact_program
            record["m33_dispatch_attestation"] = make_attestation(
                phase, args.core_revision, exact_program, cycle_records
            )
            record["status"] = "PASS"
        except Exception as error:
            record["failure_class"] = type(error).__name__
            record["failure_detail"] = str(error)[:120]
    for key in (
        "initiator_lines",
        "reflector_lines",
        "missing_service_peer_lines",
    ):
        record[key] = [
            re.sub(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                   "<bt-address>", line)
            for line in record[key]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_CS_MISSING_SERVICE=" + record["status"] +
          ";REJECTED=" + str(record["cycles_rejected"]))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
