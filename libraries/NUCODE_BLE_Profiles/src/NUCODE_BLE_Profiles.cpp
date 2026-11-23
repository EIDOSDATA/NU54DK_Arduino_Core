/**
 * @file NUCODE_BLE_Profiles.cpp
 * @brief 표준 sensor, ANS, BMS를 기존 generation GATT API에 결합합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "NUCODE_BLE_Profiles.h"
#include <NUCODE_BLE_Security.h>

namespace nucode::ble::profiles
{
    namespace
    {
        BLEProperty properties(Kind kind) noexcept
        {
            if (kind == Kind::current_time)
            {
                return BLEProperty::read | BLEProperty::notify;
            }
            if (kind == Kind::elapsed_time)
            {
                return BLEProperty::read | BLEProperty::indicate;
            }
            return Codec::usesIndications(kind) ? BLEProperty::indicate : BLEProperty::notify;
        }
    } // namespace
    SensorService::SensorService(Kind kind) noexcept
        : kind_(kind), service_(BLEUuid(static_cast<std::uint16_t>(kind))),
          measurement_(BLEUuid(Codec::measurementUuid(kind)), properties(kind),
                       kind == Kind::current_time || kind == Kind::elapsed_time
                           ? BLEPermission::read
                           : BLEPermission::none,
                       Packet::capacity),
          feature_(BLEUuid(kind == Kind::cycling ? 0x2a5cU : 0x2a54U), BLEProperty::read,
                   BLEPermission::read, 2U)
    {
    }
    bool SensorService::begin() noexcept
    {
        if (ready_ ||
            (kind_ != Kind::current_time && kind_ != Kind::thermometer && kind_ != Kind::cycling &&
             kind_ != Kind::running && kind_ != Kind::elapsed_time))
        {
            return false;
        }
        Packet initial;
        switch (kind_)
        {
        case Kind::current_time:
            static_cast<void>(Codec::encode(CurrentTime{}, initial));
            break;
        case Kind::thermometer:
            static_cast<void>(Codec::encode(Temperature{}, initial));
            break;
        case Kind::cycling:
        {
            CyclingMeasurement value;
            value.has_wheel = false;
            static_cast<void>(Codec::encode(value, initial));
            break;
        }
        case Kind::running:
            static_cast<void>(Codec::encode(RunningMeasurement{}, initial));
            break;
        case Kind::elapsed_time:
            static_cast<void>(Codec::encode(ElapsedTime{}, initial));
            break;
        default:
            return false;
        }
        if (!measurement_.setValue(initial.data, initial.length) ||
            !service_.addCharacteristic(measurement_))
        {
            return false;
        }
        if (kind_ == Kind::cycling || kind_ == Kind::running)
        {
            const std::uint8_t feature[] = {
                static_cast<std::uint8_t>(kind_ == Kind::cycling ? 2U : 5U), 0U};
            if (!feature_.setValue(feature, sizeof(feature)) ||
                !service_.addCharacteristic(feature_))
            {
                return false;
            }
        }
        ready_ = BLEDevice.addService(service_);
        return ready_;
    }
    bool SensorService::setValue(const Packet &packet) noexcept
    {
        if (!ready_ || packet.length > Packet::capacity ||
            !Codec::valid(kind_, packet.data, packet.length))
        {
            return false;
        }
        if ((kind_ == Kind::cycling && (packet.data[0] & 1U) != 0U) ||
            (kind_ == Kind::running && (packet.data[0] & 2U) != 0U))
        {
            return false;
        }
        return measurement_.setValue(packet.data, packet.length);
    }
    bool SensorService::send(BLEConnectionHandle peer) noexcept
    {
        return ready_ && BLEConnection.connected(peer) &&
               (Codec::usesIndications(kind_) ? measurement_.indicate(peer)
                                              : measurement_.notify(peer));
    }
    Kind SensorService::kind() const noexcept
    {
        return kind_;
    }
    BLECharacteristic &SensorService::measurement() noexcept
    {
        return measurement_;
    }

    AlertService::AlertService() noexcept
        : service_(BLEUuid(0x1811U)),
          supported_new_(BLEUuid(0x2a47U), BLEProperty::read, BLEPermission::read, 2U),
          new_alert_(BLEUuid(0x2a46U), BLEProperty::notify, BLEPermission::none, 20U),
          supported_unread_(BLEUuid(0x2a48U), BLEProperty::read, BLEPermission::read, 2U),
          unread_(BLEUuid(0x2a45U), BLEProperty::notify, BLEPermission::none, 2U),
          control_(BLEUuid(0x2a44U), BLEProperty::write, BLEPermission::write, 2U)
    {
    }
    bool AlertService::begin() noexcept
    {
        if (ready_)
        {
            return false;
        }
        const std::uint8_t supported[] = {0xffU, 0x03U};
        control_.onAuthorize(authorize, this);
        control_.onEvent(event, this);
        ready_ =
            supported_new_.setValue(supported, sizeof(supported)) &&
            supported_unread_.setValue(supported, sizeof(supported)) &&
            service_.addCharacteristic(supported_new_) && service_.addCharacteristic(new_alert_) &&
            service_.addCharacteristic(supported_unread_) && service_.addCharacteristic(unread_) &&
            service_.addCharacteristic(control_) && BLEDevice.addService(service_);
        return ready_;
    }
    AlertService::Link *AlertService::link(BLEConnectionHandle peer, bool create) noexcept
    {
        if (!peer.valid() || !BLEConnection.connected(peer))
        {
            return nullptr;
        }
        for (Link &entry : links_)
        {
            if (entry.handle == peer)
            {
                return &entry;
            }
        }
        if (create)
        {
            for (Link &entry : links_)
            {
                if (!entry.handle.valid() || !BLEConnection.connected(entry.handle))
                {
                    entry = Link{};
                    entry.handle = peer;
                    return &entry;
                }
            }
        }
        return nullptr;
    }
    bool AlertService::authorize(const BLEGattAuthorizationRequest &request, void *context) noexcept
    {
        static_cast<void>(context);
        AlertControl check;
        return request.operation == BLEGattAuthorizationOperation::write && request.offset == 0U &&
               !request.prepare && !request.without_response && request.connection.valid() &&
               check.apply(request.data, request.length);
    }
    void AlertService::event(BLECharacteristic &value, const BLECharacteristicEventInfo &event,
                             void *context) noexcept
    {
        static_cast<void>(value);
        if (event.event != BLECharacteristicEvent::written)
        {
            return;
        }
        auto &self = *static_cast<AlertService *>(context);
        Link *entry = self.link(event.connection, true);
        if (entry != nullptr)
        {
            static_cast<void>(entry->control.apply(event.data, event.length));
        }
    }
    bool AlertService::send(BLEConnectionHandle peer, const Alert &value) noexcept
    {
        Packet packet;
        if (!ready_ || !Codec::encode(value, packet))
        {
            return false;
        }
        latest_[value.category] = value;
        have_alert_[value.category] = true;
        Link *entry = link(peer, false);
        return entry != nullptr && entry->control.newEnabled(value.category) &&
               new_alert_.setValue(packet.data, packet.length) && new_alert_.notify(peer);
    }
    bool AlertService::unread(BLEConnectionHandle peer, std::uint8_t category,
                              std::uint8_t count) noexcept
    {
        if (!ready_ || category > 9U)
        {
            return false;
        }
        unread_count_[category] = count;
        Link *entry = link(peer, false);
        const std::uint8_t packet[] = {category, count};
        return entry != nullptr && entry->control.unreadEnabled(category) &&
               unread_.setValue(packet, sizeof(packet)) && unread_.notify(peer);
    }
    void AlertService::poll() noexcept
    {
        for (Link &entry : links_)
        {
            if (!BLEConnection.connected(entry.handle))
            {
                entry = Link{};
                continue;
            }
            const auto new_mask = entry.control.takeImmediateNew();
            const auto unread_mask = entry.control.takeImmediateUnread();
            for (std::uint8_t category = 0U; category < 10U; ++category)
            {
                if ((new_mask & (1U << category)) != 0U && have_alert_[category])
                {
                    static_cast<void>(send(entry.handle, latest_[category]));
                }
                if ((unread_mask & (1U << category)) != 0U)
                {
                    static_cast<void>(unread(entry.handle, category, unread_count_[category]));
                }
            }
        }
    }

    BondManagementService::BondManagementService() noexcept
        : service_(BLEUuid(0x181eU)),
          feature_(BLEUuid(0x2aa5U), BLEProperty::read, BLEPermission::read, 3U),
          control_(BLEUuid(0x2aa4U), BLEProperty::write, BLEPermission::write, 32U)
    {
    }
    bool BondManagementService::begin(BondDeleteAuthorization callback, void *context) noexcept
    {
        if (ready_ || callback == nullptr)
        {
            return false;
        }
        authorize_ = callback;
        context_ = context;
        /** @brief LE requesting-device 삭제와 authorization bit만 광고합니다. */
        const std::uint8_t feature[] = {0x20U, 0U, 0U};
        control_.onAuthorize(authorize, this);
        control_.onEvent(event, this);
        ready_ = feature_.setValue(feature, sizeof(feature)) &&
                 service_.addCharacteristic(feature_) && service_.addCharacteristic(control_) &&
                 BLEDevice.addService(service_);
        return ready_;
    }
    bool BondManagementService::authorize(const BLEGattAuthorizationRequest &request,
                                          void *context) noexcept
    {
        auto &self = *static_cast<BondManagementService *>(context);
        if (request.operation != BLEGattAuthorizationOperation::write || request.offset != 0U ||
            request.prepare || request.without_response || request.data == nullptr ||
            request.length < 2U || request.length > 32U || request.data[0] != 3U ||
            BLESecurity.currentLevel(request.connection) < SecurityLevel::encrypted ||
            (BLESecurity.bondState(request.connection) != BondState::persistence_pending &&
             BLESecurity.bondState(request.connection) != BondState::verified))
        {
            return false;
        }
        if (!self.armed() || self.authorize_ == nullptr ||
            !self.authorize_({request.connection, request.data + 1U, request.length - 1U},
                             self.context_))
        {
            return false;
        }
        bool expected = true;
        return __atomic_compare_exchange_n(&self.armed_, &expected, false, false, __ATOMIC_ACQ_REL,
                                           __ATOMIC_ACQUIRE);
    }
    void BondManagementService::event(BLECharacteristic &value,
                                      const BLECharacteristicEventInfo &event,
                                      void *context) noexcept
    {
        static_cast<void>(value);
        if (event.event != BLECharacteristicEvent::written)
        {
            return;
        }
        auto &self = *static_cast<BondManagementService *>(context);
        if (!BLEConnection.connected(event.connection) ||
            BLESecurity.currentLevel(event.connection) < SecurityLevel::encrypted ||
            !BLEConnection.identityResolved(event.connection))
        {
            ++self.failed_;
            return;
        }
        const BLEAddress address = BLEConnection.peerAddress(event.connection);
        PeerAddress peer;
        peer.type = static_cast<std::uint8_t>(address.type());
        const std::uint8_t *bytes = address.data();
        for (std::size_t i = 0U; i < 6U; ++i)
        {
            peer.value[i] = bytes[i];
        }
        if (BLESecurity.eraseBond(peer))
        {
            ++self.accepted_;
        }
        else
        {
            ++self.failed_;
        }
    }
    std::uint32_t BondManagementService::acceptedCount() const noexcept
    {
        return accepted_;
    }
    void BondManagementService::setArmed(bool armed) noexcept
    {
        __atomic_store_n(&armed_, armed, __ATOMIC_RELEASE);
    }
    bool BondManagementService::armed() const noexcept
    {
        return __atomic_load_n(&armed_, __ATOMIC_ACQUIRE);
    }
    std::uint32_t BondManagementService::failureCount() const noexcept
    {
        return failed_;
    }
} // namespace nucode::ble::profiles
#endif
