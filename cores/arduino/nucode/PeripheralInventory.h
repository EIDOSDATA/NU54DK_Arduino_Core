/**
 * @file PeripheralInventory.h
 * @brief nRF54L15/NU54DK 주변장치 identity와 검증 축의 공개 조회 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_PERIPHERAL_INVENTORY_H_
#define NUCODE_ARDUINO_CORE_NUCODE_PERIPHERAL_INVENTORY_H_

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{
    /** @brief manifest가 구분하는 실제 hardware personality 종류입니다. */
    enum class PeripheralKind : std::uint8_t
    {
        uarte = 0U,
        spim,
        spis,
        twim,
        twis,
        gpio,
        gpiote,
        egu,
        dppic,
        ppib,
        timer,
        grtc,
        saadc,
        pwm,
        pdm,
        i2s,
        qdec,
        comp,
        lpcomp,
        temp,
        wdt,
        nfct,
        radio,
        cracen,
        kmu,
        rng,
        tampc,
        power,
        clock,
        cache,
        vpr,
        sqspi,
    };

    /** @brief 보드에서 해당 personality의 신호를 꺼낼 수 있는지 나타냅니다. */
    enum class PeripheralRouteState : std::uint8_t
    {
        not_required = 0U,
        candidate,
        partial,
        verified,
        unroutable,
    };

    /** @brief NU54DK Core source가 해당 identity를 구현한 수준입니다. */
    enum class PeripheralSourceState : std::uint8_t
    {
        absent = 0U,
        internal,
        partial,
        implemented,
    };

    /** @brief Arduino 사용자가 해당 identity를 선택할 수 있는 노출 수준입니다. */
    enum class PeripheralExposureState : std::uint8_t
    {
        none = 0U,
        internal,
        public_api,
    };

    /** @brief 독립 검증 축의 결과입니다. */
    enum class PeripheralVerificationState : std::uint8_t
    {
        not_applicable = 0U,
        not_run,
        partial,
        pass,
    };

    /** @brief 해당 hardware와 공개 API가 제공하는 DMA 수준입니다. */
    enum class PeripheralDmaCapability : std::uint8_t
    {
        none = 0U,
        hardware = 1U << 0U,
        driver_managed = 1U << 1U,
        synchronous_api = 1U << 2U,
        asynchronous_api = 1U << 3U,
        continuous_api = 1U << 4U,
        double_buffered_api = 1U << 5U,
    };

    /** @brief 두 DMA capability를 결합합니다. */
    [[nodiscard]] constexpr PeripheralDmaCapability operator|(PeripheralDmaCapability lhs,
                                                              PeripheralDmaCapability rhs) noexcept
    {
        return static_cast<PeripheralDmaCapability>(static_cast<std::uint8_t>(lhs) |
                                                    static_cast<std::uint8_t>(rhs));
    }

    /** @brief DMA capability mask가 요청 비트를 포함하는지 확인합니다. */
    [[nodiscard]] constexpr bool
    hasPeripheralDmaCapability(PeripheralDmaCapability capabilities,
                               PeripheralDmaCapability requested) noexcept
    {
        return (static_cast<std::uint8_t>(capabilities) & static_cast<std::uint8_t>(requested)) !=
               0U;
    }

    /**
	 * @brief manifest 한 행을 allocation 없이 조회하는 고정 descriptor입니다.
	 *
	 * 같은 `sharing_group`을 가진 personality는 하나의 물리 register/IRQ block을
	 * 공유하므로 동시에 소유할 수 없습니다. 빈 문자열은 해당 항목이 없음을 뜻합니다.
	 */
    struct PeripheralDescriptor
    {
        const char *id;
        PeripheralKind kind;
        std::uint8_t instance;
        const char *sharing_group;
        const char *devicetree_node;
        const char *board_route;
        const char *driver;
        const char *public_object;
        const char *public_api;
        const char *milestone;
        PeripheralRouteState route_state;
        PeripheralSourceState source_state;
        PeripheralExposureState exposure_state;
        PeripheralVerificationState silicon_state;
        PeripheralVerificationState build_state;
        PeripheralVerificationState semantic_state;
        PeripheralVerificationState hil_state;
        PeripheralVerificationState concurrent_hil_state;
        PeripheralDmaCapability dma_capabilities;
        std::uint8_t dma_max_count_bits;
    };

    /** @brief manifest에 등록된 descriptor 수를 반환합니다. */
    [[nodiscard]] std::size_t peripheralInventorySize() noexcept;

    /** @brief index의 descriptor를 반환하며 범위를 벗어나면 nullptr입니다. */
    [[nodiscard]] const PeripheralDescriptor *peripheralInventoryAt(std::size_t index) noexcept;

    /** @brief kind와 instance가 모두 일치하는 실제 identity를 찾습니다. */
    [[nodiscard]] const PeripheralDescriptor *findPeripheral(PeripheralKind kind,
                                                             std::uint8_t instance) noexcept;

    /**
	 * @brief Arduino 공개 객체 이름이 소유한 실제 identity를 찾습니다.
	 *
	 * 독립 객체를 가장하는 alias를 허용하지 않으므로 한 이름은 최대 한 행과 일치합니다.
	 */
    [[nodiscard]] const PeripheralDescriptor *
    findPeripheralByObject(const char *public_object) noexcept;

    /** @brief enum 값의 안정된 영문 token을 반환합니다. */
    [[nodiscard]] const char *peripheralKindToken(PeripheralKind kind) noexcept;
    [[nodiscard]] const char *peripheralRouteStateToken(PeripheralRouteState state) noexcept;
    [[nodiscard]] const char *peripheralSourceStateToken(PeripheralSourceState state) noexcept;
    [[nodiscard]] const char *peripheralExposureStateToken(PeripheralExposureState state) noexcept;
    [[nodiscard]] const char *
    peripheralVerificationStateToken(PeripheralVerificationState state) noexcept;

    /**
	 * @brief descriptor를 한 줄 ASCII 진단 형식으로 포맷합니다.
	 *
	 * 형식은 `NU54:PERIPHERAL:<id>:kind=<kind>:instance=<n>:block=<group>:`로
	 * 시작하며 route/source/build/semantic/HIL/concurrent/DMA 상태를 이어 붙입니다.
	 * buffer가 nullptr이거나 capacity가 0이면 필요한 길이만 계산합니다.
	 */
    [[nodiscard]] std::size_t formatPeripheralIdentity(const PeripheralDescriptor &descriptor,
                                                       char *buffer, std::size_t capacity) noexcept;

} // namespace nucode::arduino

#endif
