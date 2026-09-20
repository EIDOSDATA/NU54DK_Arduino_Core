#!/usr/bin/env python3
"""! @brief TMAP/GMAP 공개 Arduino 예제의 2-board LE Audio HIL을 실행합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    file_sha256,
    flash_image_pyocd,
    git_revision,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
)
from m31_ble_capability_run import (  # noqa: E402
    collect_register_identity,
    discover,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


MAX_TRANSCRIPT_BYTES = 512 * 1024
PROBE_HASH = re.compile(r"^[0-9a-f]{64}$")
BLE_ADDRESS = re.compile(rb"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")


class HilFailure(RuntimeError):
    """! @brief fail-closed TMAP/GMAP HIL 오류입니다. """


@dataclass(frozen=True)
class Scenario:
    """! @brief 한 번에 flash할 source/sink 공개 예제 계약입니다. """

    name: str
    profile: str
    transport: str
    source_example: str
    sink_example: str
    source_role: int
    sink_role: int
    service: str
    source_ready: str
    sink_ready: str
    source_streaming: str
    source_count: re.Pattern[str]
    sink_count: re.Pattern[str]
    source_stop: str
    sink_stop: str
    source_negative_role: str
    sink_negative_role: str
    quality_negative: str
    feature_negative: str | None
    required_source_config: tuple[str, ...]
    required_sink_config: tuple[str, ...]

    @property
    def source_root(self) -> Path:
        return REPOSITORY / "libraries/NUCODE_BLE_Audio/examples" / self.source_example

    @property
    def sink_root(self) -> Path:
        return REPOSITORY / "libraries/NUCODE_BLE_Audio/examples" / self.sink_example


SCENARIOS = {
    "tmap-unicast": Scenario(
        "tmap-unicast", "TMAP", "unicast", "TelephonyMediaGateway",
        "TelephonyMediaTerminal", 0x05, 0x0A, "TMAS",
        "TMAP local roles=0x5 service=TMAS",
        "TMAP local roles=0xA service=TMAS",
        "TMAP unicast streaming", re.compile(r"^TMAP sent frames=(\d+)$"),
        re.compile(r"^TMAP decoded frames=(\d+) dropped=(\d+)$"),
        "TMAP stream stop result=0", "TMAP unicast server stop result=0",
        "Invalid TMAP peer rejected", "Unsupported TMAP role rejected",
        "TMAP quality mismatch rejected", None,
        ("CONFIG_BT_TMAP=y", "CONFIG_BT_BAP_UNICAST_CLIENT=y", "CONFIG_LIBLC3=y"),
        ("CONFIG_BT_TMAP=y", "CONFIG_BT_BAP_UNICAST_SERVER=y", "CONFIG_LIBLC3=y"),
    ),
    "tmap-broadcast": Scenario(
        "tmap-broadcast", "TMAP", "broadcast", "TelephonyMediaBroadcaster",
        "TelephonyMediaReceiver", 0x10, 0x20, "TMAS",
        "TMAP local roles=0x10 service=TMAS",
        "TMAP local roles=0x20 service=TMAS",
        "TMAP broadcast streaming", re.compile(r"^TMAP broadcast sent=(\d+)$"),
        re.compile(r"^TMAP broadcast received=(\d+) dropped=(\d+)$"),
        "TMAP broadcast stop result=0", "TMAP broadcast sink stop result=0",
        "Unsupported TMAP role rejected", "Unsupported TMAP role rejected",
        "TMAP quality mismatch rejected", None,
        ("CONFIG_BT_TMAP=y", "CONFIG_BT_BAP_BROADCAST_SOURCE=y", "CONFIG_LIBLC3=y"),
        ("CONFIG_BT_TMAP=y", "CONFIG_BT_BAP_BROADCAST_SINK=y", "CONFIG_LIBLC3=y"),
    ),
    "gmap-unicast": Scenario(
        "gmap-unicast", "GMAP", "unicast", "GamingAudioGateway",
        "GamingAudioTerminal", 0x01, 0x02, "GMAS",
        "GMAP local roles=0x1 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0",
        "GMAP local roles=0x2 service=GMAS features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0",
        "Gaming unicast streaming", re.compile(r"^Gaming sent frames=(\d+)$"),
        re.compile(r"^Gaming decoded frames=(\d+) dropped=(\d+)$"),
        "Gaming stream stop result=0", "Gaming unicast server stop result=0",
        "Invalid GMAP peer rejected", "Unsupported GMAP role rejected",
        "Gaming quality mismatch rejected", "Invalid GMAP feature rejected",
        ("CONFIG_BT_GMAP=y", "CONFIG_BT_BAP_UNICAST_CLIENT=y", "CONFIG_LIBLC3=y"),
        ("CONFIG_BT_GMAP=y", "CONFIG_BT_BAP_UNICAST_SERVER=y", "CONFIG_LIBLC3=y"),
    ),
    "gmap-broadcast": Scenario(
        "gmap-broadcast", "GMAP", "broadcast", "GamingAudioBroadcaster",
        "GamingAudioReceiver", 0x04, 0x08, "GMAS",
        "GMAP local roles=0x4 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0",
        "GMAP local roles=0x8 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0",
        "Gaming broadcast streaming", re.compile(r"^Gaming broadcast sent=(\d+)$"),
        re.compile(r"^Gaming broadcast received=(\d+) dropped=(\d+)$"),
        "Gaming broadcast stop result=0", "Gaming broadcast sink stop result=0",
        "Unsupported GMAP role rejected", "Unsupported GMAP role rejected",
        "Gaming quality mismatch rejected", "Invalid GMAP feature rejected",
        ("CONFIG_BT_GMAP=y", "CONFIG_BT_BAP_BROADCAST_SOURCE=y", "CONFIG_LIBLC3=y"),
        ("CONFIG_BT_GMAP=y", "CONFIG_BT_BAP_BROADCAST_SINK=y", "CONFIG_LIBLC3=y"),
    ),
}


@dataclass
class Counter:
    """! @brief restart 때 0으로 돌아가는 target counter를 누적값으로 바꿉니다. """

    last: int = 0
    offset: int = 0
    total: int = 0

    def update(self, value: int) -> None:
        if value < self.last:
            self.offset += self.last
        self.last = value
        self.total = self.offset + value


@dataclass
class Observation:
    """! @brief 두 공개 Serial transcript에서 누적한 판정 상태입니다. """

    scenario: Scenario
    local_ready: set[str] = field(default_factory=set)
    peer_role_seen: bool = False
    peer_features_seen: bool = False
    source_frames: Counter = field(default_factory=Counter)
    sink_frames: Counter = field(default_factory=Counter)
    streaming_count: int = 0
    sink_start_count: int = 0
    source_stop_count: int = 0
    sink_stop_count: int = 0
    role_negative: set[str] = field(default_factory=set)
    quality_negative: set[str] = field(default_factory=set)
    feature_negative: set[str] = field(default_factory=set)

    def ingest(self, role: str, line: str) -> None:
        """! @brief 공개 메시지만 strict 상태로 반영하고 실패 token은 즉시 거부합니다. """
        folded = line.casefold()
        fatal = ("unexpectedly accepted", " start failed", " send failed", " decode failed",
                 " sync failed", "security request failed", "fatal", "assert")
        if any(marker in folded for marker in fatal):
            raise HilFailure(f"{role} 공개 Serial 실패: {line}")
        expected_ready = self.scenario.source_ready if role == "source" else self.scenario.sink_ready
        if line == expected_ready:
            self.local_ready.add(role)
        if role == "source" and line == self.scenario.source_streaming:
            self.streaming_count += 1
        if role == "sink" and ("ready for unicast audio" in line or "receiver scanning" in line):
            self.sink_start_count += 1
        if role == "source" and line.startswith(f"{self.scenario.profile} peer roles=0x"):
            try:
                roles = int(line.rsplit("0x", 1)[1], 16)
            except ValueError as error:
                raise HilFailure(f"peer role 형식 오류: {line}") from error
            if roles != self.scenario.sink_role:
                raise HilFailure(f"peer role 불일치: 0x{roles:x}")
            self.peer_role_seen = True
        if role == "source" and line.startswith("GMAP peer features="):
            expected = "GMAP peer features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0"
            if line != expected:
                raise HilFailure(f"GMAP peer feature 불일치: {line}")
            self.peer_features_seen = True
        source_match = self.scenario.source_count.fullmatch(line)
        if role == "source" and source_match is not None:
            self.source_frames.update(int(source_match.group(1)))
        sink_match = self.scenario.sink_count.fullmatch(line)
        if role == "sink" and sink_match is not None:
            if int(sink_match.group(2)) != 0:
                raise HilFailure(f"{role} frame drop이 0이 아닙니다: {line}")
            self.sink_frames.update(int(sink_match.group(1)))
        if role == "source" and line == self.scenario.source_stop:
            self.source_stop_count += 1
        if role == "sink" and line == self.scenario.sink_stop:
            self.sink_stop_count += 1
        if line == (self.scenario.source_negative_role if role == "source" else self.scenario.sink_negative_role):
            self.role_negative.add(role)
        if line == self.scenario.quality_negative:
            self.quality_negative.add(role)
        if self.scenario.feature_negative is not None and line == self.scenario.feature_negative:
            self.feature_negative.add(role)

    def ready(self) -> bool:
        profile_discovery = self.scenario.transport == "broadcast" or self.peer_role_seen
        feature_discovery = self.scenario.profile == "TMAP" or self.scenario.transport == "broadcast" or self.peer_features_seen
        return self.local_ready == {"source", "sink"} and profile_discovery and feature_discovery and self.streaming_count > 0

    def negatives_complete(self) -> bool:
        features = self.scenario.feature_negative is None or self.feature_negative == {"source", "sink"}
        return (self.role_negative == {"source", "sink"} and
                self.quality_negative == {"source", "sink"} and features)


def validate_config(path: Path, required: tuple[str, ...]) -> dict[str, Any]:
    """! @brief 실제 build 설정에서 역할별 필수 feature를 exact line으로 확인합니다. """
    resolved = path.resolve()
    if not resolved.is_file():
        raise HilFailure(f"config 파일이 없습니다: {resolved}")
    text = resolved.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines()}
    missing = [token for token in required if token not in lines]
    if missing:
        raise HilFailure(f"config 필수 항목 누락: {', '.join(missing)}")
    return {"name": resolved.name, "size": resolved.stat().st_size,
            "sha256": file_sha256(resolved), "required": list(required)}


def validate_revisions(sdk_root: Path, expected_core: str) -> dict[str, str]:
    """! @brief core·board·NCS·Zephyr의 full revision을 lock과 결합합니다. """
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    revisions = {
        "core": git_revision(REPOSITORY, expected_core),
        "board": git_revision(BOARD_ROOT),
        "ncs": git_revision(sdk_root / "nrf"),
        "zephyr": git_revision(sdk_root / "zephyr"),
    }
    validate_board_revision(revisions["board"])
    expected = {
        "board": lock["board"]["revision"],
        "ncs": lock["ncs"]["revision"],
        "zephyr": lock["zephyr"]["revision"],
    }
    for name, revision in expected.items():
        if revisions[name] != revision:
            raise HilFailure(f"{name} full revision이 SDK lock과 다릅니다")
    return revisions


def validate_clean_source() -> None:
    """! @brief core와 board submodule 전체의 untracked 포함 clean 상태를 확인합니다. """
    for name, root in (("core", REPOSITORY), ("board", BOARD_ROOT)):
        result = subprocess.run(
            ("git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"),
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0 or result.stdout.strip():
            raise HilFailure(f"{name} source가 clean하지 않습니다")


def sanitize_transcript(raw: bytes, forbidden: tuple[str, ...]) -> bytes:
    """! @brief BLE 주소와 raw probe UID가 증적에 남지 않도록 제거합니다. """
    sanitized = BLE_ADDRESS.sub(b"<redacted-ble-address>", raw)
    for identity in forbidden:
        if identity:
            sanitized = re.sub(re.escape(identity).encode("ascii"), b"<redacted-probe>",
                               sanitized, flags=re.IGNORECASE)
    return sanitized


class SerialHarness:
    """! @brief 두 COM의 공개 줄을 bounded transcript와 oracle에 전달합니다. """

    def __init__(self, source: Any, sink: Any, observation: Observation) -> None:
        self.ports = {"source": source, "sink": sink}
        self.observation = observation
        self.pending = {"source": bytearray(), "sink": bytearray()}
        self.captures = {"source": bytearray(), "sink": bytearray()}

    def command(self, role: str, command: str) -> None:
        payload = command.encode("ascii")
        if self.ports[role].write(payload) != len(payload):
            raise HilFailure(f"{role} command 일부만 기록됐습니다")
        self.ports[role].flush()

    def poll(self) -> None:
        progressed = False
        for role, port in self.ports.items():
            waiting = getattr(port, "in_waiting", 0)
            chunk = port.read(waiting if waiting > 0 else 1)
            if not chunk:
                continue
            progressed = True
            self.pending[role].extend(chunk)
            self.captures[role].extend(chunk)
            if len(self.captures[role]) > MAX_TRANSCRIPT_BYTES:
                raise HilFailure(f"{role} transcript 크기 제한 초과")
            while b"\n" in self.pending[role]:
                raw_line, _, remainder = self.pending[role].partition(b"\n")
                self.pending[role] = bytearray(remainder)
                line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
                if line:
                    self.observation.ingest(role, line)
        if not progressed:
            time.sleep(0.01)

    def wait(self, predicate: Callable[[], bool], timeout_seconds: float, label: str) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.poll()
            if predicate():
                return
        raise HilFailure(f"{label} timeout")


def run_protocol(harness: SerialHarness, scenario: Scenario, soak_seconds: float,
                 minimum_soak_frames: int, cycles: int, step_timeout: float) -> dict[str, Any]:
    """! @brief role/service/stream/negative/recovery 계약을 공개 Serial로 수행합니다. """
    harness.wait(harness.observation.ready, step_timeout, "role/service/stream discovery")
    source_base = harness.observation.source_frames.total
    sink_base = harness.observation.sink_frames.total
    soak_started = time.monotonic()
    harness.wait(
        lambda: (time.monotonic() - soak_started >= soak_seconds and
                 harness.observation.source_frames.total - source_base >= minimum_soak_frames and
                 harness.observation.sink_frames.total - sink_base >= minimum_soak_frames),
        soak_seconds + max(step_timeout, 60.0), "180-second frame/decode soak",
    )

    for role in ("source", "sink"):
        harness.command(role, "x")
        harness.command(role, "q")
        if scenario.feature_negative is not None:
            harness.command(role, "f")
    harness.wait(harness.observation.negatives_complete, step_timeout,
                 "unsupported role/quality/feature negative")

    for cycle in range(1, cycles + 1):
        source_stop = harness.observation.source_stop_count
        sink_stop = harness.observation.sink_stop_count
        harness.command("source", "s")
        if scenario.transport == "broadcast":
            harness.command("sink", "s")
        harness.wait(
            lambda: (harness.observation.source_stop_count > source_stop and
                     (scenario.transport == "unicast" or
                      harness.observation.sink_stop_count > sink_stop)),
            step_timeout, f"cycle {cycle} stop",
        )
        source_frames = harness.observation.source_frames.total
        sink_frames = harness.observation.sink_frames.total
        if scenario.transport == "unicast":
            starts = harness.observation.streaming_count
            harness.command("source", "r")
            harness.wait(
                lambda: (harness.observation.streaming_count > starts and
                         harness.observation.source_frames.total >= source_frames + 100 and
                         harness.observation.sink_frames.total >= sink_frames + 100),
                step_timeout, f"cycle {cycle} disconnect/reconnect",
            )
        else:
            starts = harness.observation.streaming_count
            harness.command("sink", "r")
            harness.command("source", "r")
            harness.wait(
                lambda: (harness.observation.streaming_count > starts and
                         harness.observation.source_frames.total >= source_frames + 100 and
                         harness.observation.sink_frames.total >= sink_frames + 100),
                step_timeout, f"cycle {cycle} stop/restart",
            )

    final_source_stop = harness.observation.source_stop_count
    harness.command("source", "s")
    harness.wait(lambda: harness.observation.source_stop_count > final_source_stop,
                 step_timeout, "final stop")
    return {
        "advertised_discovered_role_feature_service": "PASS",
        "stream_start_send_read_stop": "PASS",
        "soak_seconds": soak_seconds,
        "minimum_soak_frames": minimum_soak_frames,
        "source_frames": harness.observation.source_frames.total,
        "decoded_frames": harness.observation.sink_frames.total,
        "dropped_frames": 0,
        "recovery_cycles": cycles,
        "stop_restart_pass": f"{cycles}/{cycles}",
        "disconnect_reconnect_pass": (f"{cycles}/{cycles}" if scenario.transport == "unicast"
                                      else "not-applicable-broadcast"),
        "negative_role": "PASS",
        "negative_quality": "PASS",
        "negative_feature": "PASS" if scenario.feature_negative is not None else "not-applicable",
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief source/sink identity, image, config와 HIL 결과를 한 증적에 묶습니다. """
    scenario = SCENARIOS[args.scenario]
    if args.cycles != 20:
        raise HilFailure("완료 HIL은 --cycles 20만 허용합니다")
    if (not math.isfinite(args.soak_seconds) or args.soak_seconds < 180.0 or
            args.minimum_soak_frames < 17500):
        raise HilFailure("완료 HIL은 역할별 180초와 17500 frame 이상이 필요합니다")
    if (not math.isfinite(args.step_timeout) or not 15.0 <= args.step_timeout <= 300.0 or
            not math.isfinite(args.flash_timeout) or not 30.0 <= args.flash_timeout <= 300.0):
        raise HilFailure("step timeout은 15..300초, flash timeout은 30..300초여야 합니다")
    if args.source_probe_sha256 == args.sink_probe_sha256:
        raise HilFailure("source와 sink probe SHA-256이 같습니다")
    if not PROBE_HASH.fullmatch(args.source_probe_sha256) or not PROBE_HASH.fullmatch(args.sink_probe_sha256):
        raise HilFailure("probe identity는 소문자 SHA-256이어야 합니다")
    evidence_path = args.evidence.resolve()
    if evidence_path.suffix.lower() != ".json":
        raise HilFailure("--evidence는 .json이어야 합니다")
    transcript_paths = {
        role: evidence_path.with_name(f"{evidence_path.stem}.{role}.transcript.log")
        for role in ("source", "sink")
    }
    if any(path.exists() for path in (evidence_path, *transcript_paths.values())):
        raise HilFailure("기존 evidence/transcript를 덮어쓰지 않습니다")

    validate_clean_source()
    sdk_root = args.sdk_root.resolve()
    revisions = validate_revisions(sdk_root, args.expected_core_revision)
    image_core_revision = revisions["core"]
    if args.image_core_revision:
        resolved_image_revision = subprocess.run(
            ("git", "-C", str(REPOSITORY), "rev-parse", "--verify",
             f"{args.image_core_revision}^{{commit}}"),
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        image_core_revision = resolved_image_revision.stdout.strip()
        if resolved_image_revision.returncode != 0 or not re.fullmatch(
                r"[0-9a-f]{40}", image_core_revision):
            raise HilFailure("image core revision을 commit으로 해석할 수 없습니다")
    source_image = validate_hex_image(str(args.source_image.resolve()))
    sink_image = validate_hex_image(str(args.sink_image.resolve()))
    image_state = {
        "source": (source_image.stat().st_size, file_sha256(source_image)),
        "sink": (sink_image.stat().st_size, file_sha256(sink_image)),
    }
    build_records = {
        "source": validate_build_record(source_image, image_core_revision, revisions["board"],
                                         scenario.source_root),
        "sink": validate_build_record(sink_image, image_core_revision, revisions["board"],
                                       scenario.sink_root),
    }
    configs = {
        "source": validate_config(args.source_config, scenario.required_source_config),
        "sink": validate_config(args.sink_config, scenario.required_sink_config),
    }

    serial_module, list_ports = import_pyserial()
    source_uid, source_volume, source_port = discover(args.source_probe_sha256, list_ports)
    sink_uid, sink_volume, sink_port = discover(args.sink_probe_sha256, list_ports)
    if source_uid == sink_uid or source_port.casefold() == sink_port.casefold():
        raise HilFailure("source/sink physical endpoint가 중복됩니다")
    captures: dict[str, bytes] = {"source": b"", "sink": b""}
    with ProbeLocks((source_uid, sink_uid)):
        registers = {
            "source": collect_register_identity(source_uid, source_volume),
            "sink": collect_register_identity(sink_uid, sink_volume),
        }
        with serial_module.Serial(source_port, 115200, timeout=0.02) as source_serial, \
             serial_module.Serial(sink_port, 115200, timeout=0.02) as sink_serial:
            source_serial.reset_input_buffer()
            sink_serial.reset_input_buffer()
            sink_flash = flash_image_pyocd("sink", sink_uid, sink_image, args.flash_timeout,
                                          hardware_reset=True)
            source_flash = flash_image_pyocd("source", source_uid, source_image, args.flash_timeout,
                                            hardware_reset=True)
            observation = Observation(scenario)
            harness = SerialHarness(source_serial, sink_serial, observation)
            try:
                result = run_protocol(harness, scenario, args.soak_seconds,
                                      args.minimum_soak_frames, args.cycles, args.step_timeout)
            except Exception:
                captures = {role: bytes(raw) for role, raw in harness.captures.items()}
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                for role, path in transcript_paths.items():
                    path.write_bytes(sanitize_transcript(captures[role],
                                                         (source_uid, sink_uid)))
                raise
            captures = {role: bytes(raw) for role, raw in harness.captures.items()}

    for role, image in (("source", source_image), ("sink", sink_image)):
        validate_image_unchanged(image, *image_state[role])
    if file_sha256(args.source_config.resolve()) != configs["source"]["sha256"]:
        raise HilFailure("시험 중 source config byte가 변경됐습니다")
    if file_sha256(args.sink_config.resolve()) != configs["sink"]["sha256"]:
        raise HilFailure("시험 중 sink config byte가 변경됐습니다")
    validate_clean_source()
    if validate_revisions(sdk_root, args.expected_core_revision) != revisions:
        raise HilFailure("시험 중 source/SDK revision이 변경됐습니다")
    sanitized = {
        role: sanitize_transcript(raw, (source_uid, sink_uid)) for role, raw in captures.items()
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    for role, path in transcript_paths.items():
        path.write_bytes(sanitized[role])
    evidence = {
        "test_id": "M31-W03-10-TMAP-GMAP-HIL",
        "status": "PASS",
        "scenario": scenario.name,
        "source_clean": True,
        "identity": revisions,
        "image_core_revision": image_core_revision,
        "sdk_lock_sha256": file_sha256(REPOSITORY / "tools/ci/ncs-3.4.0.lock.json"),
        "roles": {
            "source": {"role_bits": f"0x{scenario.source_role:02x}", "service": scenario.service,
                       "probe_sha256": args.source_probe_sha256,
                       "probe_registers": registers["source"], "vcom": source_port},
            "sink": {"role_bits": f"0x{scenario.sink_role:02x}", "service": scenario.service,
                     "probe_sha256": args.sink_probe_sha256,
                     "probe_registers": registers["sink"], "vcom": sink_port},
        },
        "artifacts": {
            "source": {"image_name": source_image.name, "image_size": image_state["source"][0],
                       "image_sha256": image_state["source"][1], "config": configs["source"],
                       "build_record": build_records["source"], "flash_mode": source_flash[0],
                       "flash_bytes": source_flash[1]},
            "sink": {"image_name": sink_image.name, "image_size": image_state["sink"][0],
                     "image_sha256": image_state["sink"][1], "config": configs["sink"],
                     "build_record": build_records["sink"], "flash_mode": sink_flash[0],
                     "flash_bytes": sink_flash[1]},
        },
        "transcripts": {
            role: {"name": transcript_paths[role].name, "size": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest()}
            for role, raw in sanitized.items()
        },
        "result": result,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return evidence


def build_parser() -> argparse.ArgumentParser:
    """! @brief raw UID를 받지 않는 완료 HIL 명령행을 정의합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), required=True)
    parser.add_argument("--source-probe-sha256", required=True)
    parser.add_argument("--sink-probe-sha256", required=True)
    parser.add_argument("--source-image", type=Path, required=True)
    parser.add_argument("--sink-image", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--sink-config", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, default=Path("C:/ncs/v3.4.0"))
    parser.add_argument("--expected-core-revision", required=True)
    parser.add_argument("--image-core-revision")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--soak-seconds", type=float, default=180.0)
    parser.add_argument("--minimum-soak-frames", type=int, default=17500)
    parser.add_argument("--step-timeout", type=float, default=45.0)
    parser.add_argument("--flash-timeout", type=float, default=300.0)
    return parser


def main() -> int:
    """! @brief 오류에서 raw identity를 제거하고 PASS 한 줄만 출력합니다. """
    try:
        evidence = execute(build_parser().parse_args())
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        message = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", message)
        print(f"M31_TMAP_GMAP_HIL_FAIL: {type(error).__name__}: {message[:500]}", file=sys.stderr)
        return 1
    print(f"M31_TMAP_GMAP_HIL_PASS=1;SCENARIO={evidence['scenario']};CYCLES=20")
    return 0


if __name__ == "__main__":
    sys.exit(main())
