"""! @brief reset 뒤 DAP UART 유휴 입력과 VCOM buffer를 준비하고 exact image를 시작합니다. """
from __future__ import annotations

import time
from typing import Any, Callable


## @brief 고정 nRF54L15의 DAP target TX P0.00·P1.04 PIN_CNF 주소입니다.
DAP_UART_TX_PIN_CNF = (("P0.00", 0x5010A080), ("P1.04", 0x500D8290))


## @brief CPU가 정지한 reset 입력의 PULL만 바꾸고 readback으로 유휴 HIGH bias를 확인합니다.
def prepare_dap_uart_idle_inputs(target: Any) -> list[dict[str, Any]]:
    pins = [(name, address, target.read32(address))
            for name, address in DAP_UART_TX_PIN_CNF]
    if any(value & 1 for _, _, value in pins):
        raise RuntimeError("DAP UART TX pins must be reset inputs before idle bias")
    for _, address, value in pins:
        target.write32(address, (value & ~0xC) | 0xC)
    target.flush()
    records = []
    for name, address, value in pins:
        observed = target.read32(address)
        expected = (value & ~0xC) | 0xC
        if observed != expected:
            raise RuntimeError(f"DAP UART idle bias readback failed: {name}")
        records.append({"pin": name, "pin_cnf_address": f"0x{address:08x}",
                        "before": f"0x{value:08x}", "after": f"0x{observed:08x}",
                        "mode": "input-pullup"})
    return records


## @brief exact CPU를 halt한 동안만 유휴 bias와 초기 수신 buffer를 준비합니다.
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
        idle_bias = prepare_dap_uart_idle_inputs(target)
        ## @brief 앱이 READY를 보낼 수 없는 halt 구간에서만 reset transient를 비웁니다.
        time.sleep(0.05)
        for stream in streams.values():
            stream.reset_input_buffer()
            stream.reset_output_buffer()
        target.resume()
    return {"method": "reset-halt-drain-resume", "cpuid": f"0x{cpuid:08x}",
            "frequency_hz": swd_frequency_hz,
            "dap_uart_idle_bias": idle_bias,
            "auto_unlock": False, "mass_erase_requested": False}
