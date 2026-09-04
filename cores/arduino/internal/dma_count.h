// SPDX-License-Identifier: MIT
#ifndef NUCODE_INTERNAL_DMA_COUNT_H_
#define NUCODE_INTERNAL_DMA_COUNT_H_
#include <cstddef>
namespace nucode::arduino::internal {
// MAXCNT counts bytes, samples or words depending on the peripheral. Divide
// first so even an adversarial size_t cannot overflow during validation.
[[nodiscard]] constexpr bool dmaCountFits(std::size_t count,
                                          std::size_t register_max,
                                          std::size_t register_units_per_element) noexcept {
    return count != 0 && register_units_per_element != 0 &&
           count <= register_max / register_units_per_element;
}
}
#endif
