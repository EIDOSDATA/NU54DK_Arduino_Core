"""QDEC signal/oracle preparation only: AB transition semantics, no pin driving.

Nordic nRF54L15 'Sampling and decoding' table is the reference:
https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/qdec.html-concept_gfd_jzd_4r
"""
from v04_protocol import ProtocolError

POSITIVE = (0, 1, 3, 2)


def states(cycles, reverse=False):
    if type(cycles) is not int or not 1 <= cycles <= 1000 or type(reverse) is not bool:
        raise ProtocolError("invalid quadrature cycles/direction")
    cycle = (2, 3, 1, 0) if reverse else (1, 3, 2, 0)
    return [0] + list(cycle) * cycles


def decode_samples(samples):
    if not samples or any(type(sample) is not int or sample not in range(4) for sample in samples):
        raise ProtocolError("AB samples must be two-bit states")
    movement = doubles = 0
    for previous, current in zip(samples, samples[1:]):
        if previous == current:
            continue
        if previous ^ current == 3:
            doubles += 1
        elif POSITIVE[(POSITIVE.index(previous) + 1) % 4] == current:
            movement += 1
        else:
            movement -= 1
    return movement, doubles


def verify_timing(state_interval_us, sample_period_us, debounce=False):
    if (type(state_interval_us) is not int or state_interval_us not in (2000, 10000) or
            type(sample_period_us) is not int or sample_period_us not in (128, 256, 512)):
        raise ProtocolError("unqualified quadrature generator/sampling profile")
    # Two samples for debounce plus margin; a slow default cannot silently alias.
    if state_interval_us < sample_period_us * (4 if debounce else 2):
        raise ProtocolError("insufficient samples per quadrature state")
    return True
