"""! @brief M29-W07 Signed Write·EATT Host parser의 fail-closed 동작을 검증합니다. """

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m29_ble_signed_eatt import parse_role_transcript  # noqa: E402


NONCE = "0123456789abcdef0123456789abcdef"
REVISION = "1234567890abcdef1234567890abcdef12345678"
PROTOCOL = "M29W07|1"


def _suffix(iteration: int, nonce: str = NONCE, revision: str = REVISION) -> str:
    """! @brief fixture record의 고정 identity suffix를 만듭니다. """

    return f"|iteration={iteration}|nonce={nonce}|core={revision}"


def build_transcript(role: str) -> bytes:
    """! @brief 한 role의 완전한 20-reboot/replay/EATT fixture를 만듭니다. """

    lines = [
        f"{PROTOCOL}|READY|role={role}|bond_count=0|core={REVISION}",
        f"{PROTOCOL}|CLEAR|role={role}|bond_count=0|nonce={NONCE}|core={REVISION}",
        f"{PROTOCOL}|REBOOTING|role={role}|nonce={NONCE}|core={REVISION}",
        f"{PROTOCOL}|READY|role={role}|bond_count=0|core={REVISION}",
        f"{PROTOCOL}|BEGIN|role={role}|mode=pair{_suffix(0)}",
    ]
    if role == "peripheral":
        lines.append(
            f"{PROTOCOL}|ADVERTISE|role=peripheral|mode=pair|status=pass{_suffix(0)}"
        )
    else:
        lines.append(f"{PROTOCOL}|SCAN|role=central|mode=pair|status=pass{_suffix(0)}")
    lines.extend(
        (
            f"{PROTOCOL}|PAIR|role={role}|bond_count=1|local_counter=0|"
            f"remote_counter=0{_suffix(0)}",
            f"{PROTOCOL}|END|role={role}|mode=pair|status=pass|"
            f"callback_context=pass{_suffix(0)}",
        )
    )
    local_counter = 0
    remote_counter = 0
    for iteration in range(1, 21):
        if role == "central":
            local_counter += 1
        else:
            remote_counter += 1
        lines.extend(
            (
                f"{PROTOCOL}|REBOOTING|role={role}|nonce={NONCE}|core={REVISION}",
                f"{PROTOCOL}|READY|role={role}|bond_count=1|core={REVISION}",
                f"{PROTOCOL}|BEGIN|role={role}|mode=sign{_suffix(iteration)}",
            )
        )
        if role == "peripheral":
            lines.append(
                f"{PROTOCOL}|ADVERTISE|role=peripheral|mode=sign|status=pass"
                f"{_suffix(iteration)}"
            )
        else:
            lines.append(
                f"{PROTOCOL}|SCAN|role=central|mode=sign|status=pass"
                f"{_suffix(iteration)}"
            )
        lines.extend(
            (
                f"{PROTOCOL}|SIGN|role={role}|writes=1|local_counter={local_counter}|"
                f"remote_counter={remote_counter}{_suffix(iteration)}",
                f"{PROTOCOL}|END|role={role}|mode=sign|status=pass|"
                f"callback_context=pass{_suffix(iteration)}",
            )
        )
    if role == "central":
        local_counter += 1
        replay = (
            f"{PROTOCOL}|REPLAY|role=central|sent=2|signed_originals=1|replays=1|"
            f"local_counter={local_counter}|remote_counter={remote_counter}{_suffix(21)}"
        )
    else:
        remote_counter += 1
        replay = (
            f"{PROTOCOL}|REPLAY|role=peripheral|writes=1|replay_accepts=0|"
            f"local_counter={local_counter}|remote_counter={remote_counter}{_suffix(21)}"
        )
    lines.extend(
        (
            f"{PROTOCOL}|REBOOTING|role={role}|nonce={NONCE}|core={REVISION}",
            f"{PROTOCOL}|READY|role={role}|bond_count=1|core={REVISION}",
            f"{PROTOCOL}|BEGIN|role={role}|mode=replay{_suffix(21)}",
        )
    )
    if role == "peripheral":
        lines.append(
            f"{PROTOCOL}|ADVERTISE|role=peripheral|mode=replay|status=pass{_suffix(21)}"
        )
    else:
        lines.append(
            f"{PROTOCOL}|SCAN|role=central|mode=replay|status=pass{_suffix(21)}"
        )
    lines.extend(
        (
            replay,
            f"{PROTOCOL}|END|role={role}|mode=replay|status=pass|"
            f"callback_context=pass{_suffix(21)}",
            f"{PROTOCOL}|REBOOTING|role={role}|nonce={NONCE}|core={REVISION}",
            f"{PROTOCOL}|READY|role={role}|bond_count=1|core={REVISION}",
            f"{PROTOCOL}|BEGIN|role={role}|mode=eatt{_suffix(22)}",
        )
    )
    if role == "peripheral":
        lines.extend(
            (
                f"{PROTOCOL}|ADVERTISE|role=peripheral|mode=eatt|status=pass{_suffix(22)}",
                f"{PROTOCOL}|EATT|role=peripheral|bearers=2|ops_bearer0=1000|"
                "ops_bearer1=1000|production_writes=1|payload_errors=0|"
                f"deadlocks=0|starvation=0{_suffix(22)}",
            )
        )
    else:
        lines.extend(
            (
                f"{PROTOCOL}|SCAN|role=central|mode=eatt|status=pass{_suffix(22)}",
                f"{PROTOCOL}|EATT|role=central|bearers=2|ops_bearer0=1000|"
                "ops_bearer1=1000|unencrypted_rejected=1|over_limit_rejected=1|"
                "production_read=1|production_write=1|deadlocks=0|"
                f"starvation=0{_suffix(22)}",
            )
        )
    lines.append(
        f"{PROTOCOL}|END|role={role}|mode=eatt|status=pass|"
        f"callback_context=pass{_suffix(22)}"
    )
    return ("\n".join(lines) + "\n").encode("ascii")


class M29BleSignedEattParserTests(unittest.TestCase):
    """! @brief W07 parser의 성공과 identity·순서·수치 오류 거부를 검증합니다. """

    def test_accepts_exact_peripheral(self):
        result = parse_role_transcript(build_transcript("peripheral"), NONCE, REVISION, "peripheral")
        self.assertEqual(result.final_remote_counter, 21)
        self.assertEqual(result.replay_accepts, 0)

    def test_accepts_exact_central(self):
        result = parse_role_transcript(build_transcript("central"), NONCE, REVISION, "central")
        self.assertEqual(result.final_local_counter, 21)
        self.assertEqual(result.operations_per_bearer, 1000)

    def test_rejects_noise(self):
        transcript = b"noise\n" + build_transcript("central")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_non_ascii(self):
        transcript = build_transcript("central").replace(b"M29W07", b"\xffM29W07", 1)
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_missing_record(self):
        lines = build_transcript("central").splitlines()
        del lines[15]
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(b"\n".join(lines) + b"\n", NONCE, REVISION, "central")

    def test_rejects_duplicate_record(self):
        lines = build_transcript("central").splitlines()
        lines.insert(15, lines[15])
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(b"\n".join(lines) + b"\n", NONCE, REVISION, "central")

    def test_rejects_reordered_record(self):
        lines = build_transcript("peripheral").splitlines()
        lines[4], lines[5] = lines[5], lines[4]
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(b"\n".join(lines) + b"\n", NONCE, REVISION, "peripheral")

    def test_rejects_wrong_revision(self):
        transcript = build_transcript("central").replace(REVISION.encode(), b"0" * 40, 1)
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_stale_nonce(self):
        transcript = build_transcript("central").replace(NONCE.encode(), b"f" * 32, 1)
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_counter_rollback(self):
        transcript = build_transcript("central").replace(
            b"local_counter=10|remote_counter=0|iteration=10",
            b"local_counter=9|remote_counter=0|iteration=10",
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_replay_accept(self):
        transcript = build_transcript("peripheral").replace(
            b"replay_accepts=0", b"replay_accepts=1"
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "peripheral")

    def test_rejects_eatt_shortfall(self):
        transcript = build_transcript("central").replace(
            b"ops_bearer1=1000", b"ops_bearer1=999"
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")

    def test_rejects_target_fail(self):
        lines = build_transcript("central").splitlines()
        lines[8] = (
            f"{PROTOCOL}|FAIL|role=central|mode=sign|stage=gatt|code=-5{_suffix(1)}"
        ).encode("ascii")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(b"\n".join(lines) + b"\n", NONCE, REVISION, "central")

    def test_rejects_end_trailing_record(self):
        transcript = build_transcript("central") + b"M29W07|1|EXTRA\n"
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript, NONCE, REVISION, "central")


if __name__ == "__main__":
    unittest.main(verbosity=2)
