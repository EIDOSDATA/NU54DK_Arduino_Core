/**
 * @file peripheral_inventory.cpp
 * @brief generated manifest table의 공개 조회와 진단 포맷을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "nucode/PeripheralInventory.h"

#include <stdio.h>
#include <string.h>

namespace nucode::arduino
{
    namespace
    {
        const PeripheralDescriptor inventory[] = {
#include "generated/PeripheralInventory.inc"
        };
    } // namespace

    std::size_t peripheralInventorySize() noexcept
    {
        return sizeof(inventory) / sizeof(inventory[0]);
    }

    const PeripheralDescriptor *peripheralInventoryAt(std::size_t index) noexcept
    {
        return index < peripheralInventorySize() ? &inventory[index] : nullptr;
    }

    const PeripheralDescriptor *findPeripheral(PeripheralKind kind, std::uint8_t instance) noexcept
    {
        for (const auto &descriptor : inventory)
        {
            if ((descriptor.kind == kind) && (descriptor.instance == instance))
            {
                return &descriptor;
            }
        }
        return nullptr;
    }

    const PeripheralDescriptor *findPeripheralByObject(const char *public_object) noexcept
    {
        if ((public_object == nullptr) || (public_object[0] == '\0'))
        {
            return nullptr;
        }
        for (const auto &descriptor : inventory)
        {
            if ((descriptor.public_object[0] != '\0') &&
                (::strcmp(descriptor.public_object, public_object) == 0))
            {
                return &descriptor;
            }
        }
        return nullptr;
    }

    const char *peripheralKindToken(PeripheralKind kind) noexcept
    {
        switch (kind)
        {
        case PeripheralKind::uarte:
            return "uarte";
        case PeripheralKind::spim:
            return "spim";
        case PeripheralKind::spis:
            return "spis";
        case PeripheralKind::twim:
            return "twim";
        case PeripheralKind::twis:
            return "twis";
        case PeripheralKind::gpio:
            return "gpio";
        case PeripheralKind::gpiote:
            return "gpiote";
        case PeripheralKind::egu:
            return "egu";
        case PeripheralKind::dppic:
            return "dppic";
        case PeripheralKind::ppib:
            return "ppib";
        case PeripheralKind::timer:
            return "timer";
        case PeripheralKind::grtc:
            return "grtc";
        case PeripheralKind::saadc:
            return "saadc";
        case PeripheralKind::pwm:
            return "pwm";
        case PeripheralKind::pdm:
            return "pdm";
        case PeripheralKind::i2s:
            return "i2s";
        case PeripheralKind::qdec:
            return "qdec";
        case PeripheralKind::comp:
            return "comp";
        case PeripheralKind::lpcomp:
            return "lpcomp";
        case PeripheralKind::temp:
            return "temp";
        case PeripheralKind::wdt:
            return "wdt";
        case PeripheralKind::nfct:
            return "nfct";
        case PeripheralKind::radio:
            return "radio";
        case PeripheralKind::cracen:
            return "cracen";
        case PeripheralKind::kmu:
            return "kmu";
        case PeripheralKind::rng:
            return "rng";
        case PeripheralKind::tampc:
            return "tampc";
        case PeripheralKind::power:
            return "power";
        case PeripheralKind::clock:
            return "clock";
        case PeripheralKind::cache:
            return "cache";
        case PeripheralKind::vpr:
            return "vpr";
        case PeripheralKind::sqspi:
            return "sqspi";
        default:
            return "unknown";
        }
    }

    const char *peripheralRouteStateToken(PeripheralRouteState state) noexcept
    {
        switch (state)
        {
        case PeripheralRouteState::not_required:
            return "not-required";
        case PeripheralRouteState::candidate:
            return "candidate";
        case PeripheralRouteState::partial:
            return "partial";
        case PeripheralRouteState::verified:
            return "verified";
        case PeripheralRouteState::unroutable:
            return "unroutable";
        default:
            return "unknown";
        }
    }

    const char *peripheralSourceStateToken(PeripheralSourceState state) noexcept
    {
        switch (state)
        {
        case PeripheralSourceState::absent:
            return "absent";
        case PeripheralSourceState::internal:
            return "internal";
        case PeripheralSourceState::partial:
            return "partial";
        case PeripheralSourceState::implemented:
            return "implemented";
        default:
            return "unknown";
        }
    }

    const char *peripheralExposureStateToken(PeripheralExposureState state) noexcept
    {
        switch (state)
        {
        case PeripheralExposureState::none:
            return "none";
        case PeripheralExposureState::internal:
            return "internal";
        case PeripheralExposureState::public_api:
            return "public";
        default:
            return "unknown";
        }
    }

    const char *peripheralVerificationStateToken(PeripheralVerificationState state) noexcept
    {
        switch (state)
        {
        case PeripheralVerificationState::not_applicable:
            return "not-applicable";
        case PeripheralVerificationState::not_run:
            return "not-run";
        case PeripheralVerificationState::partial:
            return "partial";
        case PeripheralVerificationState::pass:
            return "pass";
        default:
            return "unknown";
        }
    }

    std::size_t formatPeripheralIdentity(const PeripheralDescriptor &descriptor, char *buffer,
                                         std::size_t capacity) noexcept
    {
        if (buffer == nullptr)
        {
            capacity = 0U;
        }
        const int required =
            ::snprintf(buffer, capacity,
                       "NU54:PERIPHERAL:%s:kind=%s:instance=%u:block=%s:dts=%s:object=%s:"
                       "route=%s:source=%s:exposure=%s:build=%s:semantic=%s:hil=%s:"
                       "concurrent=%s:dma=0x%02x",
                       descriptor.id, peripheralKindToken(descriptor.kind),
                       static_cast<unsigned>(descriptor.instance), descriptor.sharing_group,
                       descriptor.devicetree_node, descriptor.public_object,
                       peripheralRouteStateToken(descriptor.route_state),
                       peripheralSourceStateToken(descriptor.source_state),
                       peripheralExposureStateToken(descriptor.exposure_state),
                       peripheralVerificationStateToken(descriptor.build_state),
                       peripheralVerificationStateToken(descriptor.semantic_state),
                       peripheralVerificationStateToken(descriptor.hil_state),
                       peripheralVerificationStateToken(descriptor.concurrent_hil_state),
                       static_cast<unsigned>(descriptor.dma_capabilities));
        return required < 0 ? 0U : static_cast<std::size_t>(required);
    }

} // namespace nucode::arduino
