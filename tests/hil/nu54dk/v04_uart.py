"""Onboard UART vectors; SWD is control, DAP VCOM carries independent data."""
from contextlib import ExitStack
import hashlib
import itertools
import secrets
import time

from v04_protocol import ProtocolError


def payload(seed: int, count: int) -> bytes:
    if type(seed) is not int or not 0 <= seed <= 0xffffffff or not 1 <= count <= 2048:
        raise ProtocolError("invalid UART oracle input")
    return bytes(((seed + 37 * index + index // 8) ^ (index // 2)) % 256 for index in range(count))


def vectors():
    return itertools.product((115200, 1000000), (0, 1), (0, 1), (1, 32, 256, 1024), (1, 2))


def check_status(reply, buffers):
    expected = [buffers, 1, 0, (1 << buffers) - 1, 3, 3 if buffers == 2 else 0]
    if reply != expected:
        raise ProtocolError(f"UART DMA/event/ownership oracle failed: {reply}; expected={expected}")


def quiet(streams, append, case_id):
    """Record and discard only pre-command bytes; never discard active-test data."""
    discarded = {name: bytearray() for name in streams}
    start = last = time.monotonic()
    while time.monotonic() - start < 1:
        for name, stream in streams.items():
            data = stream.read(stream.in_waiting)
            if data:
                discarded[name].extend(data)
                last = time.monotonic()
                if len(discarded[name]) > 4096:
                    raise ProtocolError("excessive pre-arm UART noise")
        if time.monotonic() - last >= .1:
            if any(discarded.values()):
                append(case_id + "/pre-arm-drain", {"pre_arm_only": True,
                    "discarded": {name: data.hex() for name, data in discarded.items()}})
            return
        time.sleep(.005)
    raise ProtocolError("DAP VCOM did not become quiet before arm")


def collect(streams, expected, timeout=3):
    received = {name: bytearray() for name in streams}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, stream in streams.items():
            received[name].extend(stream.read(stream.in_waiting))
        if any(len(data) >= len(expected) for data in received.values()):
            break
        time.sleep(.005)
    time.sleep(.025)
    for name, stream in streams.items():
        received[name].extend(stream.read(stream.in_waiting))
    matches = [name for name, data in received.items() if data == expected]
    if len(matches) != 1 or any(data for name, data in received.items() if name not in matches):
        raise ProtocolError(f"UART exact response/noise failure: { {name: data[:2200].hex() for name,data in received.items()} }")
    return matches[0]


def discover(device, streams, instance, append):
    seed = secrets.randbits(32)
    for stream in streams.values():
        stream.apply_settings({"baudrate": 115200, "parity": "N", "rtscts": False})
        stream.rts = True
    quiet(streams, append, f"V04-UART-DISCOVER/{instance}")
    if device.command(9, (instance, seed)) != [0]:
        raise ProtocolError("UART discovery arm failed")
    selected = collect(streams, payload(seed ^ 0xc3, 32))
    status = device.command(11)
    if status[:4] != [0, 1, 0, 0]:
        raise ProtocolError(f"UART discovery lifecycle failed: {status}")
    if device.command(12) != [0, 1]:
        raise ProtocolError("UART discovery cancel/guard failed")
    append(f"V04-UART-DISCOVER/{instance}", {"seed": seed, "port": selected, "status_words": status})
    return selected


def send_payload(stream, outgoing, rate, parity, producer):
    if producer not in ("burst", "paced-64"):
        raise ProtocolError("unknown UART producer profile")
    chunk_size = len(outgoing) if producer == "burst" else 64
    for offset in range(0, len(outgoing), chunk_size):
        chunk = outgoing[offset:offset + chunk_size]
        if stream.write(chunk) != len(chunk):
            raise ProtocolError("partial Host UART write")
        if producer == "paced-64" and offset + chunk_size < len(outgoing):
            # Explicit diagnostic producer: one chunk's wire time + 2 ms.
            # Passing this is NOT a sustained line-rate/burst guarantee.
            time.sleep(len(chunk) * (11 if parity else 10) / rate + .002)


def exchange(device, streams, selected, instance, vector, append, suffix="", producer="burst"):
    rate, parity, flow, size, buffers = vector
    stream = streams[selected]
    stream.apply_settings({"baudrate": rate, "parity": "E" if parity else "N", "rtscts": bool(flow)})
    if not flow:
        stream.rts = True
    case_id = f"V04-UART-DATA/{instance}/{rate}/{parity}/{flow}/{size}/{buffers}" + suffix
    quiet(streams, append, case_id)
    seed = secrets.randbits(32)
    outgoing, incoming = payload(seed, size * buffers), payload(seed ^ 0x5a, size * buffers)
    if device.command(10, (instance, rate, size, buffers, seed, parity, flow)) != [0]:
        raise ProtocolError("UART arm failed")
    send_payload(stream, outgoing, rate, parity, producer)
    try:
        port = collect(streams, incoming)
    except ProtocolError as error:
        # A data-plane failure must retain the control-plane DMA state too.
        status = device.command(11)
        raise ProtocolError(f"{case_id}: {error}; DMA status={status}; seed={seed}; producer={producer}") from error
    if port != selected:
        raise ProtocolError("UART VCOM identity changed after discovery")
    status = device.command(11)
    check_status(status, buffers)
    if device.command(12) != [0, 1]:
        raise ProtocolError("UART STOP/guard failed")
    append(case_id, {"seed": seed, "baud_rate": rate, "parity": parity, "hardware_flow_control": bool(flow),
        "buffer_bytes": size, "buffers": buffers, "producer": producer,
        "continuous_receive": buffers == 2 and size >= 32, "status_words": status,
        "tx_sha256": hashlib.sha256(outgoing).hexdigest(), "rx_sha256": hashlib.sha256(incoming).hexdigest()})


def run_uart_onboard(device, ports, rounds, append, producer="burst"):
    import serial
    with ExitStack() as stack:
        streams = {port: stack.enter_context(serial.Serial(port, baudrate=115200, timeout=0,
                   write_timeout=3, rtscts=False, dsrdtr=False, xonxoff=False)) for port in ports}
        for instance in (20, 21, 22, 30):
            selected = discover(device, streams, instance, append)
            for vector in vectors():
                exchange(device, streams, selected, instance, vector, append, producer=producer)
            for index in range(rounds):
                # Exact STOP releases both the block and initial RX DMA workspace.
                quiet(streams, append, f"V04-UART-CANCEL/{instance}/{index}")
                if device.command(10, (instance, 115200, 32, 2, index, 0, 0)) != [0] or device.command(12) != [0, 1]:
                    raise ProtocolError("UART armed RX cancellation failed")
                append(f"V04-UART-CANCEL/{instance}/{index}", {"no_payload_sent": True})
                if instance != 30:
                    result = device.command(2, (instance, 1, 400000))
                    if result != [1, 0x41, 0, 0]:
                        raise ProtocolError("UART to read-only TWIM handover failed")
                exchange(device, streams, selected, instance, (115200, 0, 0, 32, 2), append, f"/handover-{index}", producer)
            print(f"V04_UART_ONBOARD_INSTANCE_PASS={instance};ROLE={device.image['role']}", flush=True)
