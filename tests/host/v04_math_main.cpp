// SPDX-License-Identifier: MIT
#include "internal/timer_clock.h"
#include "protocol.h"
#include <cassert>
#include <iostream>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
int main() {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
#endif
    using nucode::arduino::internal::timerPrescalerFor;
    std::uint32_t p = 0;
    assert(timerPrescalerFor(128000000, 1000000, 9, p) && p == 7);
    assert(timerPrescalerFor(32000000, 1000000, 9, p) && p == 5);
    assert(timerPrescalerFor(16000000, 1000000, 9, p) && p == 4);
    for (auto base : {16000000U, 32000000U, 128000000U}) {
        for (unsigned shift = 0; shift <= 9; ++shift)
            assert(timerPrescalerFor(base, base >> shift, 9, p) && p == shift);
        assert(!timerPrescalerFor(base, 0, 9, p));
        assert(!timerPrescalerFor(base, base * 2U, 9, p));
        assert(!timerPrescalerFor(base, 3000000, 9, p));
        assert(!timerPrescalerFor(base, base >> 10, 9, p));
    }
    std::uint32_t frame[v04::words]{};
    std::cin.read(reinterpret_cast<char *>(frame), sizeof(frame));
    if (std::cin.gcount() != sizeof(frame) || !v04::valid(frame, 1)) return 2;
    std::cout << v04::checksum(frame) << '\n';
}
