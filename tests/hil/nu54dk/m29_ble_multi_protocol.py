#!/usr/bin/env python3
"""! @brief M29-W07-D 3보드 protocol을 fail-closed로 해석합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re


PROTOCOL = "M29W07D|1"
ROLES = ("peripheral", "mixed", "central")
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


class MultiProtocolFailure(RuntimeError):
    """! @brief transcript가 고정 순서·identity·수치를 위반한 경우입니다. """


@dataclass(frozen=True)
class MultiRoleResult:
    """! @brief 한 role에서 검증한 두 transport의 정량 결과입니다. """

    role: str
    connections: int
    gatt_tx: int
    gatt_rx: int
    coc_tx: int
    coc_rx: int
    cross_link_events: int
    payload_errors: int
    dropped_events: int
    callback_context: str


def _identity(nonce: str, revision: str) -> tuple[str, str]:
    """! @brief 외부 입력 nonce와 revision을 canonical lowercase로 고정합니다. """

    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise MultiProtocolFailure("nonce는 32자리 lowercase hex여야 합니다.")
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise MultiProtocolFailure("Core revision은 40자리 lowercase hex여야 합니다.")
    return nonce, revision


def _lines(transcript: bytes) -> list[str]:
    """! @brief 모든 non-empty UART line이 ASCII protocol record인지 확인합니다. """

    if not isinstance(transcript, bytes) or len(transcript) == 0:
        raise MultiProtocolFailure("transcript가 비어 있습니다.")
    try:
        text = transcript.decode("ascii")
    except UnicodeDecodeError as error:
        raise MultiProtocolFailure("non-ASCII UART noise를 거부했습니다.") from error
    lines = [line.removesuffix("\r") for line in text.split("\n") if line != ""]
    if not lines:
        raise MultiProtocolFailure("protocol line이 없습니다.")
    for line in lines:
        if not line.startswith(PROTOCOL + "|"):
            raise MultiProtocolFailure(f"UART noise를 거부했습니다: {line!r}")
    return lines


def expected_lines(role: str, nonce: str, revision: str) -> list[str]:
    """! @brief role별 허용 record를 정확한 순서와 수치로 만듭니다. """

    nonce, revision = _identity(nonce, revision)
    if role not in ROLES:
        raise MultiProtocolFailure(f"알 수 없는 role입니다: {role}")
    suffix = f"|nonce={nonce}|core={revision}"
    lines = [
        f"{PROTOCOL}|READY|role={role}|core={revision}",
        f"{PROTOCOL}|BEGIN|role={role}|test=M29-MULTI-01{suffix}",
    ]
    if role == "peripheral":
        lines.append(
            f"{PROTOCOL}|ADVERTISE|role=peripheral|marker=161|psm=129|status=pass{suffix}"
        )
        connections, gatt_tx, gatt_rx, coc_tx, coc_rx = 1, 0, 1000, 1000, 1000
    elif role == "mixed":
        lines.extend(
            (
                f"{PROTOCOL}|SCAN|role=mixed|status=pass{suffix}",
                f"{PROTOCOL}|UPSTREAM|role=mixed|gatt=ready|coc=ready{suffix}",
                f"{PROTOCOL}|ADVERTISE|role=mixed|marker=178|psm=129|status=pass{suffix}",
            )
        )
        connections, gatt_tx, gatt_rx, coc_tx, coc_rx = 2, 1000, 1000, 2000, 2000
    else:
        lines.append(f"{PROTOCOL}|SCAN|role=central|status=pass{suffix}")
        connections, gatt_tx, gatt_rx, coc_tx, coc_rx = 1, 1000, 0, 1000, 1000
    lines.extend(
        (
            f"{PROTOCOL}|LINK|role={role}|connections={connections}|gatt=ready|coc=ready{suffix}",
            f"{PROTOCOL}|RESULT|role={role}|connections={connections}|gatt_tx={gatt_tx}"
            f"|gatt_rx={gatt_rx}|coc_tx={coc_tx}|coc_rx={coc_rx}|cross_link=0"
            f"|payload_errors=0|dropped_events=0|callback_context=pass{suffix}",
            f"{PROTOCOL}|END|role={role}|status=pass{suffix}",
        )
    )
    return lines


def parse_role_transcript(
    transcript: bytes, role: str, nonce: str, revision: str
) -> MultiRoleResult:
    """! @brief 한 role의 누락·중복·재배치·noise·잘못된 수치를 거부합니다. """

    expected = expected_lines(role, nonce, revision)
    actual = _lines(transcript)
    if actual != expected:
        difference = next(
            (
                index
                for index, pair in enumerate(zip(actual, expected, strict=False))
                if pair[0] != pair[1]
            ),
            min(len(actual), len(expected)),
        )
        actual_line = actual[difference] if difference < len(actual) else "<누락>"
        expected_line = expected[difference] if difference < len(expected) else "<없음>"
        raise MultiProtocolFailure(
            f"protocol 불일치 index={difference}: actual={actual_line!r}, "
            f"expected={expected_line!r}"
        )
    if role == "peripheral":
        values = (1, 0, 1000, 1000, 1000)
    elif role == "mixed":
        values = (2, 1000, 1000, 2000, 2000)
    else:
        values = (1, 1000, 0, 1000, 1000)
    return MultiRoleResult(
        role=role,
        connections=values[0],
        gatt_tx=values[1],
        gatt_rx=values[2],
        coc_tx=values[3],
        coc_rx=values[4],
        cross_link_events=0,
        payload_errors=0,
        dropped_events=0,
        callback_context="pass",
    )


def validate_three_role_session(results: dict[str, MultiRoleResult]) -> None:
    """! @brief 세 role이 정확히 한 번씩 존재하고 mixed의 두 link 분모가 일치하는지 확인합니다. """

    if set(results) != set(ROLES) or len(results) != len(ROLES):
        raise MultiProtocolFailure("세 고정 role 결과가 정확히 한 개씩 필요합니다.")
    mixed = results["mixed"]
    if (
        mixed.connections != 2
        or mixed.gatt_tx != 1000
        or mixed.gatt_rx != 1000
        or mixed.coc_tx != 2000
        or mixed.coc_rx != 2000
    ):
        raise MultiProtocolFailure("mixed 두 link 정량 분모가 일치하지 않습니다.")
    if any(
        result.cross_link_events != 0
        or result.payload_errors != 0
        or result.dropped_events != 0
        or result.callback_context != "pass"
        for result in results.values()
    ):
        raise MultiProtocolFailure("교차 event·payload·queue·callback 오류가 0이 아닙니다.")
