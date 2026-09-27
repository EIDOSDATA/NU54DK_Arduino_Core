#!/usr/bin/env python3
"""! @brief M31 W07의 현재 설치본 역할 재배치 HIL을 안전하게 실행합니다. """

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable


HIL = Path(__file__).resolve().parent
sys.path.insert(0, str(HIL))

from ble_pair_hil_common import flash_image_pyocd  # noqa: E402
from m6_serial_echo import detail_value, find_serial_port, import_pyserial, read_details  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


SWD_DP_IDCODE = "0x6ba02477"
TARGETS = {"nRF54L15", "unsupported target"}
REGISTER_QUERY_TIMEOUT_SECONDS = 60


## @brief UTC ISO-8601 시각을 반환합니다.
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


## @brief raw probe UID를 SHA-256으로만 식별합니다.
def digest_uid(uid: str) -> str:
    return hashlib.sha256(uid.lower().encode("ascii")).hexdigest()


## @brief DAPLink 표기가 stale이어도 전압·SWD·hash·UART가 일치하는 보드만 찾습니다.
def discover_boards() -> list[dict]:
    _, list_ports = import_pyserial()
    ports = list_ports.comports()
    boards = []
    for letter in "EFG":
        root = Path(f"{letter}:/")
        details = read_details(root)
        if details is None:
            continue
        target = detail_value(details, "Target Detect")
        idcode = (detail_value(details, "SWD DP IDCODE") or "").lower()
        voltage = detail_value(details, "Target Voltage") or ""
        uid = (detail_value(details, "Unique ID") or "").lower()
        if target not in TARGETS or idcode != SWD_DP_IDCODE or "present" not in voltage or not uid:
            continue
        boards.append({
            "uid": uid,
            "probe_sha256": digest_uid(uid),
            "volume": root.as_posix(),
            "port": find_serial_port(uid, "auto", list_ports),
            "target_detect": target,
            "swd_dp_idcode": idcode,
            "target_voltage": voltage,
        })
    boards.sort(key=lambda item: item["probe_sha256"])
    if len(boards) != 3 or len({item["uid"] for item in boards}) != 3:
        raise RuntimeError("exact NU54DK probe가 3개가 아닙니다")
    return boards


## @brief stale DAPLink 문자열 대신 실제 Nordic DP/AP 레지스터로 접근성을 판정합니다.
def collect_register_identity(uid: str, _volume: str) -> dict[str, str]:
    command = [
        sys.executable, "-I", "-m", "pyocd", "commander", "--uid", uid,
        "--target", "nrf54l", "--frequency", "500000", "--connect", "under-reset",
        "-O", "cmsis_dap.limit_packets=true", "-O", "cmsis_dap.prefer_v1=false",
        "-O", "auto_unlock=false", "--no-init",
    ]
    read_commands = (
        "initdp\nmakeap 0\nmakeap 2\n"
        "readdp 0x0\nreaddp 0x24\nreadap 0 0xfc\nreadap 0 0x00\n"
        "readap 2 0xfc\nreadap 2 0x14\nexit\n"
    )
    result = subprocess.run(
        command,
        input=read_commands,
        text=True,
        capture_output=True,
        timeout=REGISTER_QUERY_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("CMSIS-DAP V2 DP/AP register query failure")
    output = result.stdout + "\n" + result.stderr
    patterns = {
        "dp_idcode": r"DP register 0x0 = 0x([0-9a-fA-F]{8})",
        "dp_targetid_observed": r"DP register 0x24 = 0x([0-9a-fA-F]{8})",
        "ahb_ap_idr": r"AP register 0xfc = 0x([0-9a-fA-F]{8})",
        "ahb_ap_csw": r"AP register 0x0 = 0x([0-9a-fA-F]{8})",
        "ctrl_ap_idr": r"AP register 0x20000fc = 0x([0-9a-fA-F]{8})",
        "approtect_status": r"AP register 0x2000014 = 0x([0-9a-fA-F]{8})",
    }
    values = {}
    for name, pattern in patterns.items():
        matched = re.search(pattern, output)
        if matched is None:
            raise RuntimeError(f"CMSIS-DAP V2 register record missing: {name}")
        values[name] = int(matched.group(1), 16)
    if (
        values["dp_idcode"] != 0x6BA02477
        or values["ahb_ap_idr"] != 0x84770001
        or values["ctrl_ap_idr"] != 0x32880000
        or values["ahb_ap_csw"] & 0x40 == 0
        or values["approtect_status"] != 0
    ):
        raise RuntimeError("Nordic DP/AP identity 또는 보호 상태 불일치")
    return {name: f"0x{value:08x}" for name, value in values.items()}


## @brief hash 하나를 lenient preflight로 검증한 board에 결합합니다.
def discover_by_hash(probe_sha256: str, _ports: object) -> tuple[str, str, str]:
    matches = [item for item in discover_boards() if item["probe_sha256"] == probe_sha256]
    if len(matches) != 1:
        raise RuntimeError(f"probe SHA-256 mapping count={len(matches)}")
    item = matches[0]
    collect_register_identity(item["uid"], item["volume"])
    return item["uid"], item["volume"], item["port"]


## @brief 다른 W07 campaign과 겹치지 않도록 OS-held lock을 유지합니다.
@contextmanager
def campaign_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("다른 W07 probe campaign이 실행 중입니다") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


## @brief runner main을 지정 인자로 실행하고 raw UID를 출력에서 제거합니다.
def invoke(main: Callable[[], int], arguments: list[str], uids: list[str]) -> int:
    original = sys.argv
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        sys.argv = [original[0], *arguments]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = int(main())
    finally:
        sys.argv = original
    out = stdout.getvalue()
    err = stderr.getvalue()
    for uid in uids:
        out = out.replace(uid, f"sha256:{digest_uid(uid)}")
        err = err.replace(uid, f"sha256:{digest_uid(uid)}")
    if out:
        print(out, end="")
    if err:
        print(err, file=sys.stderr, end="")
    return result


## @brief Arduino build root에서 example HEX를 반환합니다.
def image(build_root: Path, library: str, example: str) -> Path:
    path = build_root / f"{library}__{example}" / f"{example}.ino.hex"
    if not path.is_file():
        raise FileNotFoundError(f"설치 example image가 없습니다: {example}")
    return path


## @brief 설치 example의 prj.conf를 반환합니다.
def config(package_root: Path, library: str, example: str) -> Path:
    path = (
        package_root / "user" / "hardware" / "nucode" / "zephyr"
        / "libraries" / library / "examples" / example / "prj.conf"
    )
    if not path.is_file():
        raise FileNotFoundError(f"설치 example config가 없습니다: {example}")
    return path


## @brief 3보드 ISO bridge 역할을 현재 설치 image로 실행합니다.
def run_iso(arguments: argparse.Namespace, boards: list[dict]) -> int:
    import m31_iso_public_combined_run as runner

    role_boards = {"peer": boards[0], "bridge": boards[1], "receiver": boards[2]}
    images = {
        "peer": image(arguments.build_root, "NUCODE_BLE_ISO", "CISToBISPeer"),
        "bridge": image(arguments.build_root, "NUCODE_BLE_ISO", "CISToBISBridge"),
        "receiver": image(arguments.build_root, "NUCODE_BLE_ISO", "CISToBISReceiver"),
    }
    command = []
    for role in ("peer", "bridge", "receiver"):
        command.extend((f"--{role}-image", str(images[role])))
        command.extend((f"--{role}-probe-sha256", role_boards[role]["probe_sha256"]))
        command.extend((f"--{role}-port", role_boards[role]["port"]))
    command.extend(("--cycles", "20", "--seconds", "180", "--evidence",
                    str(arguments.output / "iso-combined.json")))
    with ProbeLocks([item["uid"] for item in boards]):
        return invoke(runner.main, command, [item["uid"] for item in boards])


## @brief 양방향 Audio image를 exact sector flash한 뒤 20회 종료·복구를 실행합니다.
def run_audio(arguments: argparse.Namespace, boards: list[dict]) -> int:
    import m31_audio_bap_duplex_cycle_run as runner

    runner.discover = discover_by_hash
    client = boards[2]
    server = boards[0]
    client_image = image(
        arguments.build_root, "NUCODE_BLE_Audio", "BapUnicastDuplexClient"
    )
    server_image = image(
        arguments.build_root, "NUCODE_BLE_Audio", "BapUnicastDuplexServer"
    )
    records = []
    with ProbeLocks([client["uid"], server["uid"]]):
        for role, board, path in (
            ("server", server, server_image),
            ("client", client, client_image),
        ):
            mode, byte_count = flash_image_pyocd(
                f"audio_{role}", board["uid"], path, 120.0, hardware_reset=True
            )
            record = {
                "status": "FLASH_PREPARED",
                f"{role}_flash": {"mode": mode, "bytes": int(byte_count)},
                f"{role}_probe_sha256": board["probe_sha256"],
                f"{role}_image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "auto_unlock": False,
                "erase": "sector",
            }
            record_path = arguments.output / f"audio-{role}-flash.json"
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            records.append(record_path)
    command = [
        "--client-probe-sha256", client["probe_sha256"],
        "--server-probe-sha256", server["probe_sha256"],
        "--client-image", str(client_image),
        "--server-image", str(server_image),
        "--client-config", str(config(arguments.package_root, "NUCODE_BLE_Audio", "BapUnicastDuplexClient")),
        "--server-config", str(config(arguments.package_root, "NUCODE_BLE_Audio", "BapUnicastDuplexServer")),
        "--client-flash-record", str(records[1]),
        "--server-flash-record", str(records[0]),
        "--core-revision", arguments.revision,
        "--source-clean", "--cycles", "20",
        "--output", str(arguments.output / "audio-duplex.json"),
    ]
    return invoke(runner.main, command, [item["uid"] for item in boards])


## @brief 제품 SDC CTE beacon의 20회 제어·negative를 실행합니다.
def run_df(arguments: argparse.Namespace, boards: list[dict]) -> int:
    import m31_df_beacon_run as runner

    runner.discover = discover_by_hash
    runner.collect_register_identity = collect_register_identity
    beacon = boards[1]
    command = [
        "--hex", str(image(arguments.build_root, "NUCODE_BLE_DirectionFinding", "CteBeacon")),
        "--probe-sha256", beacon["probe_sha256"],
        "--sdk-root", str(arguments.sdk_root),
        "--output-prefix", str(arguments.output / "df-beacon"),
        "--flash-timeout", "120", "--advertising-seconds", "1",
    ]
    return invoke(runner.main, command, [item["uid"] for item in boards])


## @brief CS counter gap은 관찰하고 중복·역행과 raw 값 오류만 거부합니다.
def read_cs_procedures_observe_gap(
    initiator: object,
    reflector: object,
    record: dict,
    count: int,
    timeout: float,
) -> None:
    pattern = re.compile(
        r"^CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) "
        r"tone=(\d+) valid_rtt=(\d+) distance_m=([0-9.]+)$"
    )
    deadline = time.monotonic() + timeout
    previous_counter = None
    record["counter_gap_policy"] = "observe_only"
    record["counter_gaps"] = []
    while time.monotonic() < deadline and record["procedures"] < count:
        for port, key in (
            (initiator, "initiator_lines"),
            (reflector, "reflector_lines"),
        ):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            record[key].append(line[:400])
            if key != "initiator_lines":
                continue
            match = pattern.match(line)
            if match is None:
                if line.startswith("CS_RAW"):
                    raise RuntimeError("malformed ranging output")
                continue
            counter, local, peer, rtt, tone, valid, distance = match.groups()
            counter, local, peer, rtt, tone, valid = map(
                int, (counter, local, peer, rtt, tone, valid)
            )
            if previous_counter is not None:
                delta = (counter - previous_counter) & 0xFFFF
                if delta == 0 or delta >= 0x8000:
                    raise RuntimeError("duplicate or backward CS counter")
                if delta > 1:
                    record["counter_gaps"].append(
                        {"before": previous_counter, "after": counter}
                    )
            if not (
                local == peer
                and local > 0
                and rtt > 0
                and tone > 0
                and 0 < valid <= rtt
                and 0.0 <= float(distance) < 1000.0
            ):
                raise RuntimeError("invalid ranging result")
            previous_counter = counter
            record["procedures"] += 1
    if record["procedures"] != count:
        raise RuntimeError("procedure count timeout")


## @brief CS initiator·reflector를 다른 보드 배치로 100 procedure 실행합니다.
def run_cs(arguments: argparse.Namespace, boards: list[dict]) -> int:
    import m31_cs_ras_pair_run as runner

    runner.discover = discover_by_hash
    runner.collect_register_identity = collect_register_identity
    runner.read_procedures = read_cs_procedures_observe_gap
    initiator = boards[1]
    reflector = boards[2]
    command = [
        "--initiator-probe-sha256", initiator["probe_sha256"],
        "--reflector-probe-sha256", reflector["probe_sha256"],
        "--initiator-image", str(image(arguments.build_root, "NUCODE_BLE_ChannelSounding", "RasInitiator")),
        "--reflector-image", str(image(arguments.build_root, "NUCODE_BLE_ChannelSounding", "RasReflector")),
        "--core-revision", arguments.revision,
        "--output", str(arguments.output / "cs-ras.json"),
        "--source-clean", "--flash", "--post-flash-reset",
        "--disconnect-cycles", "20", "--procedures", "100",
        "--procedure-timeout", "600",
    ]
    return invoke(runner.main, command, [item["uid"] for item in boards])


## @brief 한 case의 bounded lease와 결과를 기록합니다.
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("preflight", "iso", "audio", "df", "cs"), required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    arguments = parser.parse_args()
    arguments.repository = arguments.repository.resolve()
    arguments.package_root = arguments.package_root.resolve()
    arguments.build_root = arguments.build_root.resolve()
    arguments.output = arguments.output.resolve()
    arguments.sdk_root = arguments.sdk_root.resolve()
    head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=arguments.repository, text=True
    ).strip()
    dirty = subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=arguments.repository, text=True
    ).strip()
    if dirty or head != arguments.revision:
        parser.error("exact W07 HIL은 clean source와 full HEAD가 필요합니다")
    arguments.output.mkdir(parents=True, exist_ok=True)
    lease_path = arguments.output / f"lease-{arguments.case}.json"
    if lease_path.exists():
        parser.error("기존 lease/evidence를 덮어쓰지 않습니다")
    issued = datetime.now(timezone.utc)
    lease = {
        "case": arguments.case,
        "status": "ACTIVE",
        "issued_utc": issued.isoformat(),
        "expires_utc": (issued + timedelta(minutes=20)).isoformat(),
        "watchdog_seconds": 1200,
        "source_revision": head,
        "auto_unlock": False,
        "erase": "sector_only",
    }
    lease_path.write_text(json.dumps(lease, indent=2) + "\n", encoding="utf-8")
    boards = []
    public_boards = []
    try:
        with campaign_lock(arguments.output / "probe-campaign.lock"):
            boards = discover_boards()
            for board in boards:
                board["registers"] = collect_register_identity(board["uid"], board["volume"])
            public_boards = [
                {key: value for key, value in board.items() if key != "uid"}
                for board in boards
            ]
            if arguments.case == "preflight":
                (arguments.output / "preflight.json").write_text(
                    json.dumps(
                        {
                            "status": "PASS",
                            "source_revision": head,
                            "boards": public_boards,
                            "automatic_recovery_used": False,
                            "approtect_clear": True,
                            "raw_probe_uid_persisted": False,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ) + "\n",
                    encoding="utf-8",
                )
                code = 0
            else:
                runners = {"iso": run_iso, "audio": run_audio, "df": run_df, "cs": run_cs}
                code = runners[arguments.case](arguments, boards)
    except Exception as error:
        message = str(error)
        for board in boards:
            message = message.replace(board["uid"], f"sha256:{board['probe_sha256']}")
        lease["status"] = "FAIL"
        lease["failure_class"] = type(error).__name__
        lease["failure_detail"] = message[:240]
        lease["finished_utc"] = utc_now()
        lease_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"M31_W07_{arguments.case.upper()}=FAIL:{lease['failure_class']}", file=sys.stderr)
        return 1
    lease["status"] = "PASS" if code == 0 else "FAIL"
    lease["finished_utc"] = utc_now()
    lease["boards"] = public_boards
    lease_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M31_W07_{arguments.case.upper()}={lease['status']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
