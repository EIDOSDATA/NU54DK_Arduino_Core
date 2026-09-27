#!/usr/bin/env python3
"""! @brief M30-W07 3보드 보안 연산 protocol을 fail-closed로 해석합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re


PROTOCOL = "M30W07|1"
ROLES = ("peripheral", "mixed", "central")
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


class MultiSecurityProtocolFailure(RuntimeError):
    """! @brief transcript가 고정 순서·identity·수치를 위반한 경우입니다. """


@dataclass(frozen=True)
class MultiSecurityRoleResult:
    """! @brief 한 role의 동시 link 보안 연산 결과입니다. """

    role: str
    connections: int
    client_operations: int
    server_operations: int
    cross_link_events: int
    security_errors: int
    key_size_errors: int
    callback_context: str


def _identity(nonce: str, revision: str) -> tuple[str, str]:
    """! @brief nonce와 revision을 canonical lowercase identity로 고정합니다. """

    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise MultiSecurityProtocolFailure("nonce는 32자리 lowercase hex여야 합니다.")
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise MultiSecurityProtocolFailure("Core revision은 40자리 lowercase hex여야 합니다.")
    return nonce, revision


def _lines(transcript: bytes) -> list[str]:
    """! @brief 빈 줄 외의 모든 UART byte가 ASCII protocol record인지 확인합니다. """

    if not isinstance(transcript, bytes) or len(transcript) == 0:
        raise MultiSecurityProtocolFailure("transcript가 비어 있습니다.")
    try:
        text = transcript.decode("ascii")
    except UnicodeDecodeError as error:
        raise MultiSecurityProtocolFailure("non-ASCII UART noise를 거부했습니다.") from error
    lines = [line.removesuffix("\r") for line in text.split("\n") if line != ""]
    if not lines:
        raise MultiSecurityProtocolFailure("protocol line이 없습니다.")
    if any(not line.startswith(PROTOCOL + "|") for line in lines):
        raise MultiSecurityProtocolFailure("protocol 밖 UART noise를 거부했습니다.")
    return lines


def expected_lines(role: str, nonce: str, revision: str) -> list[str]:
    """! @brief role별 허용 record를 정확한 순서와 정량값으로 만듭니다. """

    nonce, revision = _identity(nonce, revision)
    if role not in ROLES:
        raise MultiSecurityProtocolFailure(f"알 수 없는 role입니다: {role}")
    suffix = f"|nonce={nonce}|core={revision}"
    lines = [
        f"{PROTOCOL}|READY|role={role}|core={revision}",
        f"{PROTOCOL}|BEGIN|role={role}|test=M30-MULTI-01{suffix}",
    ]
    if role == "peripheral":
        lines.append(
            f"{PROTOCOL}|ADVERTISE|role=peripheral|marker=161|status=pass{suffix}"
        )
        connections, client_operations, server_operations = 1, 0, 100
    elif role == "mixed":
        lines.extend(
            (
                f"{PROTOCOL}|SCAN|role=mixed|status=pass{suffix}",
                f"{PROTOCOL}|UPSTREAM|role=mixed|security=ready|key_size=16{suffix}",
                f"{PROTOCOL}|ADVERTISE|role=mixed|marker=178|status=pass{suffix}",
            )
        )
        connections, client_operations, server_operations = 2, 100, 100
    else:
        lines.append(f"{PROTOCOL}|SCAN|role=central|status=pass{suffix}")
        connections, client_operations, server_operations = 1, 100, 0
    lines.extend(
        (
            f"{PROTOCOL}|LINK|role={role}|connections={connections}"
            f"|level=2|key_size=16{suffix}",
            f"{PROTOCOL}|RUNNING|role={role}|operations_per_link=100{suffix}",
        )
    )
    lines.extend(
        f"{PROTOCOL}|PROGRESS|role={role}|operations_per_link={operations}{suffix}"
        for operations in range(10, 101, 10)
    )
    lines.extend(
        (
            f"{PROTOCOL}|RESULT|role={role}|connections={connections}"
            f"|client_ops={client_operations}|server_ops={server_operations}"
            f"|cross_link=0|security_errors=0|key_size_errors=0"
            f"|callback_context=pass{suffix}",
            f"{PROTOCOL}|END|role={role}|status=pass{suffix}",
        )
    )
    return lines


def parse_role_transcript(
    transcript: bytes, role: str, nonce: str, revision: str
) -> MultiSecurityRoleResult:
    """! @brief 누락·중복·재배치·noise·잘못된 link 수치를 거부합니다. """

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
        raise MultiSecurityProtocolFailure(
            f"protocol 불일치 index={difference}: actual={actual_line!r}, "
            f"expected={expected_line!r}"
        )
    if role == "peripheral":
        values = (1, 0, 100)
    elif role == "mixed":
        values = (2, 100, 100)
    else:
        values = (1, 100, 0)
    return MultiSecurityRoleResult(
        role=role,
        connections=values[0],
        client_operations=values[1],
        server_operations=values[2],
        cross_link_events=0,
        security_errors=0,
        key_size_errors=0,
        callback_context="pass",
    )


def validate_three_role_session(
    results: dict[str, MultiSecurityRoleResult],
) -> None:
    """! @brief 세 role과 mixed 두 link의 100회 분모·오류 0을 확인합니다. """

    if set(results) != set(ROLES) or len(results) != len(ROLES):
        raise MultiSecurityProtocolFailure("세 고정 role 결과가 정확히 한 개씩 필요합니다.")
    mixed = results["mixed"]
    if (
        mixed.connections != 2
        or mixed.client_operations != 100
        or mixed.server_operations != 100
    ):
        raise MultiSecurityProtocolFailure("mixed 두 link 보안 연산 분모가 일치하지 않습니다.")
    if any(
        result.cross_link_events != 0
        or result.security_errors != 0
        or result.key_size_errors != 0
        or result.callback_context != "pass"
        for result in results.values()
    ):
        raise MultiSecurityProtocolFailure("교차 event·보안·key·callback 오류가 0이 아닙니다.")
