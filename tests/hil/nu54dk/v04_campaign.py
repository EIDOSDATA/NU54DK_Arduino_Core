"""v0.4.0 반복·soak 실행을 한 연속 세션으로 제한하는 공통 도우미입니다."""
from __future__ import annotations

import time

from v04_protocol import ProtocolError


def validate_options(repetitions, duration_seconds, progress_interval_seconds):
    """실수나 무제한 실행을 막는 campaign 경계를 검사합니다."""
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ProtocolError("campaign repetitions out of range")
    if (type(duration_seconds) not in (int, float) or duration_seconds < 0 or
            duration_seconds > 7200):
        raise ProtocolError("campaign duration out of range")
    if (type(progress_interval_seconds) not in (int, float) or
            not 1 <= progress_interval_seconds <= 60):
        raise ProtocolError("campaign progress interval out of range")


def run_cycles(run_once, append, repetitions=1, duration_seconds=0,
               progress_interval_seconds=5, monotonic=time.monotonic):
    """이 호출 안에서 연속 수행한 시간만 인정하고 중단 전 시간을 합산하지 않습니다."""
    validate_options(repetitions, duration_seconds, progress_interval_seconds)
    started = monotonic()
    next_progress = started + progress_interval_seconds
    completed = 0
    while completed < repetitions or duration_seconds:
        if duration_seconds and completed and monotonic() - started >= duration_seconds:
            break
        run_once(completed + 1)
        completed += 1
        now = monotonic()
        if now >= next_progress:
            append(
                "V04-CAMPAIGN-PROGRESS",
                {"status": "progress", "cleanup_only": True,
                 "completed_cycles": completed,
                 "continuous_elapsed_seconds": round(now - started, 3)})
            next_progress = now + progress_interval_seconds
        if not duration_seconds and completed >= repetitions:
            break
    elapsed = monotonic() - started
    summary = {
        "completed_cycles": completed,
        "continuous_elapsed_seconds": round(elapsed, 3),
        "requested_duration_seconds": duration_seconds,
        "requested_repetitions": repetitions,
        "interrupted_duration_reused": False,
    }
    append("V04-CAMPAIGN-COMPLETE", {"scope": "continuous-session", **summary})
    return summary
