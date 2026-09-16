"""Measure upstream BAP unicast ISO traffic and optional LC3 decoding."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ble_pair_hil_common import flash_image_pyocd
from m6_serial_echo import import_pyserial
from m31_ble_capability_run import collect_register_identity, discover
from m31_cs_ras_pair_run import hardware_reset
from v04_protocol import ProbeLocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--server-probe-sha256", required=True)
    parser.add_argument("--client-image", type=Path, required=True)
    parser.add_argument("--server-image", type=Path, required=True)
    parser.add_argument("--client-config", type=Path)
    parser.add_argument("--server-config", type=Path)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--flash-client-only", action="store_true")
    parser.add_argument("--flash-server-only", action="store_true")
    parser.add_argument("--flash-only", action="store_true")
    parser.add_argument("--source-clean", action="store_true")
    parser.add_argument("--client-flash-record", type=Path)
    parser.add_argument("--server-flash-record", type=Path)
    parser.add_argument("--require-lc3", action="store_true")
    parser.add_argument("--arduino-sink", action="store_true")
    parser.add_argument("--arduino-source", action="store_true")
    parser.add_argument("--arduino-duplex-server", action="store_true")
    parser.add_argument("--arduino-duplex-pair", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()
    if args.timeout_seconds < 10.0 or args.timeout_seconds > 180.0:
        parser.error("timeout must be between 10 and 180 seconds")
    if args.reset_only and args.flash_client_only:
        parser.error("reset-only cannot also flash the client")
    if args.reset_only and args.flash_server_only:
        parser.error("reset-only cannot also flash the server")
    if args.reset_only and args.flash_only:
        parser.error("flash-only cannot also request reset-only")
    if args.flash_client_only and args.flash_server_only:
        parser.error("choose at most one flash-only role")
    if args.arduino_source and not args.arduino_sink:
        parser.error("Arduino source measurement requires Arduino sink")
    if args.arduino_duplex_server and (not args.arduino_sink or args.arduino_source):
        parser.error("Arduino duplex server requires sink without Arduino source")
    if args.arduino_duplex_pair and (not args.arduino_sink or args.arduino_source or
                                     args.arduino_duplex_server):
        parser.error("Arduino duplex pair requires sink and excludes other source modes")
    if (args.client_flash_record or args.server_flash_record) and not args.reset_only:
        parser.error("flash records are only accepted for reset-only measurements")
    client_config = args.client_config or (args.client_image.parent / ".config")
    server_config = args.server_config or (args.server_image.parent / ".config")
    if args.require_lc3:
        for config_path in (client_config, server_config):
            config = config_path.read_text(encoding="utf-8")
            if "CONFIG_LIBLC3=y\n" not in config or "CONFIG_FPU=y\n" not in config:
                parser.error("LC3/FPU must be enabled in both image build configs")
    if args.source_clean:
        root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=root, text=True
        ).strip()
        changed = subprocess.check_output(
            ("git", "status", "--porcelain"), cwd=root, text=True
        ).strip()
        if changed or args.core_revision != revision:
            parser.error("exact HIL requires clean source and full HEAD revision")

    for role, record_path, image, probe in (
        ("client", args.client_flash_record, args.client_image,
         args.client_probe_sha256),
        ("server", args.server_flash_record, args.server_image,
         args.server_probe_sha256),
    ):
        if record_path is None:
            continue
        flashed = json.loads(record_path.read_text(encoding="utf-8-sig"))
        if (flashed.get("status") != "FLASH_PREPARED" or
                not flashed.get(f"{role}_flash") or
                flashed.get(f"{role}_probe_sha256") != probe or
                flashed.get(f"{role}_image_sha256") !=
                hashlib.sha256(image.read_bytes()).hexdigest()):
            parser.error(f"{role} flash record does not match the selected image/probe")

    serial, ports = import_pyserial()
    client_uid, client_volume, client_port = discover(args.client_probe_sha256, ports)
    server_uid, server_volume, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "test": "arduino_bap_unicast_lc3_duplex_pair" if args.arduino_duplex_pair else
                "arduino_bap_unicast_lc3_duplex_server" if args.arduino_duplex_server else
                "arduino_bap_unicast_lc3_pair" if args.arduino_source else
                "arduino_bap_unicast_lc3_sink" if args.arduino_sink else
                "upstream_bap_unicast_bidirectional_sdu",
        "source_clean": args.source_clean,
        "core_revision": args.core_revision,
        "mode": "hardware_reset_only" if args.reset_only else
                "sector_flash_client_reset" if args.flash_client_only else
                "sector_flash_server_reset" if args.flash_server_only else
                "sector_flash_pair_reset",
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port,
        "server_port": server_port,
        "client_image_sha256": hashlib.sha256(args.client_image.read_bytes()).hexdigest(),
        "server_image_sha256": hashlib.sha256(args.server_image.read_bytes()).hexdigest(),
        "client_config_sha256": hashlib.sha256(
            client_config.read_bytes()
        ).hexdigest(),
        "server_config_sha256": hashlib.sha256(
            server_config.read_bytes()
        ).hexdigest(),
        "client_lines": [],
        "server_lines": [],
        "client_tx_streams": {},
        "server_tx_streams": {},
        "client_rx_sdus": 0,
        "server_rx_sdus": 0,
        "server_plc_count": 0,
        "server_pcm_energy": 0,
        "server_queue_drops": 0,
        "client_pcm_energy": 0,
        "client_queue_drops": 0,
        "require_lc3": args.require_lc3,
        "client_flash_record_sha256": (
            hashlib.sha256(args.client_flash_record.read_bytes()).hexdigest() if
            args.client_flash_record else None
        ),
        "server_flash_record_sha256": (
            hashlib.sha256(args.server_flash_record.read_bytes()).hexdigest() if
            args.server_flash_record else None
        ),
    }
    tx_pattern = re.compile(
        r"Stream (0x[0-9a-fA-F]+): Sent (\d+) total SDUs of size (\d+)"
    )
    client_rx_pattern = re.compile(
        r"LE Audio duplex received=(\d+) energy=(\d+) dropped=(\d+)" if
        args.arduino_duplex_pair else
        r"Incoming audio on stream .* len 40 \((\d+)\)"
    )
    server_rx_pattern = re.compile(
        r"LE Audio duplex received=(\d+) energy=(\d+) dropped=(\d+)" if
        (args.arduino_duplex_server or args.arduino_duplex_pair) else
        r"LE Audio decoded frames=(\d+) energy=(\d+) dropped=(\d+)" if
        args.arduino_sink else
        r"Incoming audio on stream .* len 40 \((\d+)\)"
    )
    try:
        with ProbeLocks([client_uid, server_uid]):
            record["client_registers"] = collect_register_identity(
                client_uid, client_volume
            )
            record["server_registers"] = collect_register_identity(
                server_uid, server_volume
            )
            with serial.Serial(client_port, 115200, timeout=0.05) as client, \
                    serial.Serial(server_port, 115200, timeout=0.05) as server:
                client.reset_input_buffer()
                server.reset_input_buffer()
                if not args.reset_only:
                    if not args.flash_client_only:
                        record["server_flash"] = flash_image_pyocd(
                            "bap_unicast_server", server_uid, args.server_image,
                            120.0, hardware_reset=True
                        )
                    if not args.flash_server_only:
                        record["client_flash"] = flash_image_pyocd(
                            "bap_unicast_client", client_uid, args.client_image,
                            120.0, hardware_reset=True
                        )
                    if args.flash_only:
                        record["status"] = "FLASH_PREPARED"
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        args.output.write_text(
                            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8"
                        )
                        print("M31_BAP_NATIVE=FLASH_PREPARED")
                        return 0
                client.reset_input_buffer()
                server.reset_input_buffer()
                hardware_reset(server_uid)
                hardware_reset(client_uid)
                started = time.monotonic()
                deadline = started + args.timeout_seconds
                while time.monotonic() < deadline:
                    for port, key, tx_key in (
                        (client, "client_lines", "client_tx_streams"),
                        (server, "server_lines", "server_tx_streams"),
                    ):
                        line = port.readline().decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        line = re.sub(
                            r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                            "<bt-address>", line[:400]
                        )
                        record[key].append(line)
                        match = tx_pattern.search(line)
                        if match is not None:
                            stream, count, length = match.groups()
                            if int(length) != 40:
                                raise RuntimeError("unexpected BAP SDU length")
                            record[tx_key][stream] = max(
                                int(count), record[tx_key].get(stream, 0)
                            )
                        if key == "client_lines":
                            if args.arduino_duplex_pair:
                                match = re.search(r"LE Audio duplex sent frames=(\d+)", line)
                                if match is not None:
                                    record["client_tx_streams"]["arduino"] = max(
                                        int(match.group(1)),
                                        record["client_tx_streams"].get("arduino", 0)
                                    )
                            if args.arduino_source:
                                match = re.search(r"LE Audio sent frames=(\d+)", line)
                                if match is not None:
                                    record["client_tx_streams"]["arduino"] = max(
                                        int(match.group(1)),
                                        record["client_tx_streams"].get("arduino", 0)
                                    )
                            match = client_rx_pattern.search(line)
                            if match is not None:
                                record["client_rx_sdus"] = max(
                                    int(match.group(1)), record["client_rx_sdus"]
                                )
                                if args.arduino_duplex_pair:
                                    record["client_pcm_energy"] = max(
                                        int(match.group(2)), record["client_pcm_energy"]
                                    )
                                    record["client_queue_drops"] = max(
                                        int(match.group(3)), record["client_queue_drops"]
                                    )
                        elif key == "server_lines":
                            if args.arduino_duplex_server or args.arduino_duplex_pair:
                                match = re.search(r"LE Audio duplex sent=(\d+)", line)
                                if match is not None:
                                    record["server_tx_streams"]["arduino"] = max(
                                        int(match.group(1)),
                                        record["server_tx_streams"].get("arduino", 0)
                                    )
                            match = server_rx_pattern.search(line)
                            if match is not None:
                                record["server_rx_sdus"] = max(
                                    int(match.group(1)), record["server_rx_sdus"]
                                )
                                if args.arduino_sink:
                                    record["server_pcm_energy"] = max(
                                        int(match.group(2)), record["server_pcm_energy"]
                                    )
                                    record["server_queue_drops"] = max(
                                        int(match.group(3)), record["server_queue_drops"]
                                    )
                            if "Decoder performed PLC" in line:
                                record["server_plc_count"] += 1
                    if (args.arduino_sink and
                            len([count for count in record["client_tx_streams"].values()
                                 if count >= 1000]) >= 1 and
                            record["server_rx_sdus"] >= 1000 and
                            (not (args.arduino_duplex_server or args.arduino_duplex_pair) or
                             (record["server_tx_streams"].get("arduino", 0) >= 1000 and
                              record["client_rx_sdus"] >= 1000))):
                        break
                    if (not args.arduino_sink and
                            len([count for count in record["client_tx_streams"].values()
                                 if count >= 1000]) >= 2 and
                            len([count for count in record["server_tx_streams"].values()
                                 if count >= 1000]) >= 1 and
                            record["client_rx_sdus"] >= 1000):
                        break
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                if not any(("LE Audio duplex client streaming" if args.arduino_duplex_pair
                            else "LE Audio source streaming" if args.arduino_source
                            else "Streams started") in line
                           for line in record["client_lines"]):
                    raise RuntimeError("BAP client streams did not start")
                required_client_streams = 1 if args.arduino_sink else 2
                if len([count for count in record["client_tx_streams"].values()
                        if count >= 1000]) < required_client_streams:
                    raise RuntimeError("client TX streams did not reach 1000 SDUs")
                if args.arduino_sink:
                    if record["server_rx_sdus"] < 1000:
                        raise RuntimeError("Arduino sink did not decode 1000 LC3 frames")
                    if record["server_pcm_energy"] == 0:
                        raise RuntimeError("Arduino sink decoded zero-energy PCM")
                    if record["server_queue_drops"] != 0 or any(
                        "failed" in line.lower() for line in record["server_lines"]
                    ):
                        raise RuntimeError("Arduino sink error or queue drop observed")
                    if args.arduino_source and any(
                        "failed" in line.lower() for line in record["client_lines"]
                    ):
                        raise RuntimeError("Arduino source error observed")
                    if args.arduino_duplex_server or args.arduino_duplex_pair:
                        if record["server_tx_streams"].get("arduino", 0) < 1000:
                            raise RuntimeError("Arduino server TX did not reach 1000 SDUs")
                        if record["client_rx_sdus"] < 1000:
                            raise RuntimeError("client RX did not reach 1000 SDUs")
                    if args.arduino_duplex_pair:
                        if record["client_pcm_energy"] == 0:
                            raise RuntimeError("Arduino client decoded zero-energy PCM")
                        if record["client_queue_drops"] != 0 or any(
                            "failed" in line.lower() for line in record["client_lines"]
                        ):
                            raise RuntimeError("Arduino client error or queue drop observed")
                    record["status"] = (
                        "ARDUINO_BAP_DUPLEX_PAIR_1000_FRAME_PASS" if args.arduino_duplex_pair
                        else
                        "ARDUINO_BAP_DUPLEX_SERVER_1000_FRAME_PASS" if
                        args.arduino_duplex_server else
                        "ARDUINO_BAP_LC3_PAIR_1000_FRAME_PASS" if args.arduino_source
                        else "ARDUINO_BAP_LC3_1000_FRAME_PASS"
                    )
                else:
                    if len([count for count in record["server_tx_streams"].values()
                            if count >= 1000]) < 1:
                        raise RuntimeError("server TX stream did not reach 1000 SDUs")
                    if record["client_rx_sdus"] < 1000:
                        raise RuntimeError("client RX stream did not reach 1000 SDUs")
                    if not any("Audio Stream" in line and "started" in line
                               for line in record["server_lines"]):
                        raise RuntimeError("BAP server stream did not start")
                if args.require_lc3:
                    if record["server_rx_sdus"] < 1000:
                        raise RuntimeError("LC3 server RX did not reach 1000 valid SDUs")
                    keys = () if (args.arduino_source or args.arduino_duplex_pair) else (
                        ("client_lines",) if args.arduino_sink else (
                        "client_lines", "server_lines"
                        )
                    )
                    for key in keys:
                        if not any("Setting up LC3 encoder" in line
                                   for line in record[key]):
                            raise RuntimeError("LC3 encoder setup was not observed")
                        if any("encoder failed" in line.lower() or
                               "decoder failed" in line.lower() or
                               "decoder not setup" in line.lower()
                               for line in record[key]):
                            raise RuntimeError("LC3 encode/decode error observed")
                    if not args.arduino_sink:
                        record["status"] = "NATIVE_BAP_LC3_1000_SDU_PASS"
                elif not args.arduino_sink:
                    record["status"] = "NATIVE_BAP_1000_SDU_PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(client_uid, "<probe>")
        detail = detail.replace(server_uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_BAP_NATIVE=" + record["status"])
    return 0 if record["status"] in (
        "NATIVE_BAP_1000_SDU_PASS", "NATIVE_BAP_LC3_1000_SDU_PASS",
        "ARDUINO_BAP_LC3_1000_FRAME_PASS",
        "ARDUINO_BAP_LC3_PAIR_1000_FRAME_PASS",
        "ARDUINO_BAP_DUPLEX_SERVER_1000_FRAME_PASS",
        "ARDUINO_BAP_DUPLEX_PAIR_1000_FRAME_PASS"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
