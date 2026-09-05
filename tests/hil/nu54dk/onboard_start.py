"""Start an exact flashed image only after resetting and clearing VCOM buffers."""
from __future__ import annotations

import time
from typing import Any, Callable


def reset_halted_start(
    streams: dict[str, Any],
    probe_id: str,
    *,
    session_factory: Callable | None = None,
    swd_frequency_hz: int = 1_000_000,
) -> dict[str, Any]:
    if len(streams) != 2 or not probe_id.strip() or swd_frequency_hz <= 0:
        raise RuntimeError("controlled onboard start requires an exact probe and two VCOMs")
    if session_factory is None:
        from pyocd.core.helpers import ConnectHelper
        session_factory = ConnectHelper.session_with_chosen_probe
    session = session_factory(
        unique_id=probe_id, target_override="nrf54l", frequency=swd_frequency_hz,
        blocking=False, no_config=True,
        options={"auto_unlock": False, "connect_mode": "attach", "resume_on_disconnect": False},
    )
    if session is None:
        raise RuntimeError("selected onboard probe was not found")
    with session:
        target = session.target
        target.reset_and_halt()
        if target.get_state().name != "HALTED":
            raise RuntimeError("target did not halt before VCOM synchronization")
        cpuid = target.read32(0xE000ED00)
        if cpuid != 0x411FD210:
            raise RuntimeError(f"unexpected onboard CPUID: 0x{cpuid:08x}")
        # Drain reset transients while the application cannot emit READY yet.
        time.sleep(0.05)
        for stream in streams.values():
            stream.reset_input_buffer()
            stream.reset_output_buffer()
        target.resume()
    return {"method": "reset-halt-drain-resume", "cpuid": f"0x{cpuid:08x}",
            "frequency_hz": swd_frequency_hz,
            "auto_unlock": False, "mass_erase_requested": False}
