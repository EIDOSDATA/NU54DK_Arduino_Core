#!/usr/bin/env python3
"""! @brief MCP/MCS·CCP/TBS 2-board HIL runner와 증거 계약을 검사합니다. """

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_media_call import (  # noqa: E402
    MediaCallFailure,
    parse_transcript,
    validate_evidence_envelope,
)


def media_transcript() -> bytes:
    """! @brief 100 normal·40 negative·20 reconnect media transcript를 만듭니다. """
    labels = (
        "MEDIA_PLAY", "MEDIA_PAUSE", "MEDIA_SEEK", "MEDIA_NEXT", "MEDIA_PREVIOUS",
        "MEDIA_SELECT", "MEDIA_REFRESH",
    )
    lines = []
    for index in range(100):
        label = labels[index % len(labels)]
        lines.append(f"client: {label} submitted=1")
        lines.append(f"client: {label} complete=1 normal_ops={index + 1}")
    for case in ("OPCODE", "STALE_OBJECT"):
        for _attempt in range(20):
            lines.append(f"client: MEDIA_NEG_{case} submitted=1")
            lines.append(f"client: MEDIA_NEG_{case} rejected=1 result=9 native=-95")
            lines.append("client: MEDIA_RECOVERY result=0 native=0")
    lines.append("client: player=Player0 track=Track id=256 position=0 duration=100 state=1 updates=300 notifications=25")
    lines.extend(f"host: HIL|1|RECONNECT_OK|attempt={index}" for index in range(1, 21))
    return ("\n".join(lines) + "\n").encode("ascii")


def call_transcript() -> bytes:
    """! @brief 여섯 normal 동작·두 negative·20 reconnect call transcript를 만듭니다. """
    lines = []
    for counted in [1] * 12 + [0] * 20:
        lines.append(f"host: HIL|1|CALL_INCOMING|counted={counted}")
        lines.append("server: CALL_INCOMING result=0 native=0")
    sequence = []
    counts = {
        "CALL_ORIGINATE": 10,
        "CALL_ACCEPT": 12,
        "CALL_HOLD": 22,
        "CALL_RETRIEVE": 22,
        "CALL_TERMINATE": 22,
    }
    for label, count in counts.items():
        sequence.extend([label] * count)
    for index, label in enumerate(sequence, start=1):
        lines.append(f"client: {label} submitted=1")
        lines.append(f"client: {label} complete=1 normal_ops={index}")
    for case in ("STALE_INDEX", "INVALID_TRANSITION"):
        for _attempt in range(20):
            lines.append(f"client: CALL_NEG_{case} submitted=1")
            lines.append(f"client: CALL_NEG_{case} rejected=1 result=6 native=4")
            lines.append("client: CALL_RECOVERY result=0 native=0")
    lines.append("client: call index=1 state=3 result=0 updates=300 notifications=120")
    lines.extend(f"host: HIL|1|RECONNECT_OK|attempt={index}" for index in range(1, 21))
    return ("\n".join(lines) + "\n").encode("ascii")


class MediaCallHilContractTests(unittest.TestCase):
    """! @brief 장치 없이 parser와 runner fail-closed 경계를 고정합니다. """

    def test_media_transcript_closes_all_denominators(self) -> None:
        """! @brief media 100/20+20/20/180 분모를 승인합니다. """
        result = parse_transcript("media", media_transcript(), 180.0)
        self.assertEqual(result.normal_operations, 100)
        self.assertEqual(result.negative_by_case, {"OPCODE": 20, "STALE_OBJECT": 20})
        self.assertEqual(result.recoveries, 40)
        self.assertEqual(result.reconnects, 20)
        self.assertGreaterEqual(result.state_notifications, 20)

    def test_call_transcript_closes_all_denominators(self) -> None:
        """! @brief call 여섯 동작 100/20+20/20/180 분모를 승인합니다. """
        result = parse_transcript("call", call_transcript(), 180.0)
        self.assertEqual(result.normal_operations, 100)
        self.assertEqual(result.normal_by_operation["CALL_INCOMING"], 12)
        self.assertEqual(result.normal_by_operation["CALL_ORIGINATE"], 10)
        self.assertEqual(
            result.negative_by_case, {"STALE_INDEX": 20, "INVALID_TRANSITION": 20}
        )

    def test_parser_rejects_missing_negative_raw_uid_and_short_soak(self) -> None:
        """! @brief 부분 성공·identity 유출·179초 실행을 완료로 승격하지 않습니다. """
        with self.assertRaises(MediaCallFailure):
            parse_transcript("media", media_transcript().replace(
                b"client: MEDIA_NEG_OPCODE rejected=1 result=9 native=-95\n", b"", 1
            ), 180.0)
        with self.assertRaises(MediaCallFailure):
            parse_transcript("media", media_transcript() + b"client: uid=raw-secret\n", 180.0)
        with self.assertRaises(MediaCallFailure):
            parse_transcript(
                "media", media_transcript() + b"client: 0123456789abcdef0123456789abcdef\n",
                180.0
            )
        with self.assertRaises(MediaCallFailure):
            parse_transcript("call", call_transcript(), 179.999)

    def test_evidence_binds_hashes_registers_and_full_revisions(self) -> None:
        """! @brief artifact SHA-256과 DP/AP register를 clean full revision에 결합합니다. """
        transcript = media_transcript()
        identity = ExpectedIdentity("a" * 40, "b" * 40, "c" * 40, "d" * 40)
        registers = {
            "dp_idcode": "0x6ba02477",
            "dp_targetid_observed": "0x01000000",
            "ahb_ap_idr": "0x84770001",
            "ahb_ap_csw": "0x23000052",
            "ctrl_ap_idr": "0x32880000",
            "approtect_status": "0x00000000",
        }
        images = {"player": "1" * 64, "client": "2" * 64}
        evidence = {
            "status": "PASS",
            "source_clean": True,
            "identity": vars(identity),
            "profile": "media",
            "soak_seconds": 180.0,
            "transcript": transcript,
            "transcript_sha256": hashlib.sha256(transcript).hexdigest(),
            "boards": {
                role: {
                    "probe_sha256": str(index) * 64,
                    "image_sha256": image,
                    "config_sha256": str(index + 2) * 64,
                    "probe_registers": registers,
                }
                for index, (role, image) in enumerate(images.items(), start=1)
            },
        }
        result = validate_evidence_envelope(evidence, images, identity)
        self.assertEqual(result.normal_operations, 100)
        evidence["boards"]["client"]["probe_registers"] = {}
        with self.assertRaises(MediaCallFailure):
            validate_evidence_envelope(evidence, images, identity)
        evidence["boards"]["client"]["probe_registers"] = registers
        evidence["boards"]["client"]["uid"] = "private-probe-identity"
        with self.assertRaises(MediaCallFailure):
            validate_evidence_envelope(evidence, images, identity)

    def test_runner_reuses_common_probe_flash_and_register_helpers(self) -> None:
        """! @brief runner가 raw UID 인자가 아닌 SHA-256 identity만 공개하는지 검사합니다. """
        text = (HIL / "m31_media_call_run.py").read_text(encoding="utf-8")
        for token in (
            "discover(probe_hash, list_ports)",
            "collect_register_identity(",
            "flash_image_pyocd(",
            "ProbeLocks(",
            '"image_sha256": _hash(image)',
            '"config_sha256": _hash(config)',
            '"source_clean": not bool(dirty)',
            '"identity": vars(identity)',
            "MEDIA_OPERATIONS",
            '_wait_state(session, "player=" if args.profile == "media" else "call index=")',
            '"CALL_REMOTE_ANSWER", state=4',
            "_reconnect_campaign(",
            "args.soak_seconds",
        ):
            self.assertIn(token, text)
        self.assertNotIn('parser.add_argument("--uid"', text)
        self.assertNotIn('"uid": board["uid"]', text)

    def test_public_examples_expose_negative_and_notification_oracles(self) -> None:
        """! @brief HIL이 Zephyr가 아닌 공개 Serial/API 흐름만 사용함을 고정합니다. """
        examples = ROOT / "libraries/NUCODE_BLE_Audio/examples"
        media = (examples / "MediaControlClient/MediaControlClient.ino").read_text(
            encoding="utf-8"
        )
        call = (examples / "CallControlClient/CallControlClient.ino").read_text(
            encoding="utf-8"
        )
        server = (examples / "CallControlServer/CallControlServer.ino").read_text(
            encoding="utf-8"
        )
        for token in ("MEDIA_NEG_OPCODE", "MEDIA_NEG_STALE_OBJECT", "notifications="):
            self.assertIn(token, media)
        for token in ("CALL_NEG_STALE_INDEX", "CALL_NEG_INVALID_TRANSITION", "notifications="):
            self.assertIn(token, call)
        for token in ("CALL_INCOMING", "Call controller connected", "Call controller disconnected"):
            self.assertIn(token, server)
        for sketch in (media, call, server):
            self.assertNotIn("#include <zephyr/", sketch)


if __name__ == "__main__":
    unittest.main()
