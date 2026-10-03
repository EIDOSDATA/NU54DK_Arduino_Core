/**
 * @file main.cpp
 * @brief M32 advertising·identity·list·EAD 공개 API의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#include <cstdint>

static_assert(CONFIG_BT_EXT_ADV_MAX_ADV_SET == 3);
static_assert(CONFIG_BT_ID_MAX == 3);
static_assert(CONFIG_BT_EXT_ADV_CODING_SELECTION == 1);
static_assert(CONFIG_BT_EAD == 1);
static_assert(nucode::ble::ExtendedAdvertising::product_maximum_sets == 3U);
static_assert(nucode::ble::Identity::product_maximum_identities == 3U);
static_assert(nucode::ble::EncryptedAdvertisingData::maximum_plaintext_length == 246U);

int main()
{
    nucode::ble::BLEExtendedAdvertisingParameters parameters;
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    nucode::ble::BLEAddress address;
    nucode::ble::EncryptedAdvertisingData ead;
    std::uint8_t identity = 0U;
    std::uint8_t key[nucode::ble::EncryptedAdvertisingData::session_key_length] = {};
    std::uint8_t iv[nucode::ble::EncryptedAdvertisingData::initialization_vector_length] = {};
    std::uint8_t plaintext[4] = {2U, 0xffU, 1U, 0U};
    std::uint8_t encrypted[32] = {};
    std::uint8_t decrypted[sizeof(plaintext)] = {};
    std::size_t encrypted_length = 0U;
    std::size_t decrypted_length = 0U;

    parameters.identity = 1U;
    parameters.sid = 1U;
    parameters.coded = true;
    parameters.coding = nucode::ble::BLEAdvertisingCoding::s8;
    parameters.filter_scan_requests = true;
    static_cast<void>(BLEExtendedAdvertising.create(parameters, advertising_set));
    static_cast<void>(BLEIdentity.count());
    static_cast<void>(BLEIdentity.address(identity, address));
    static_cast<void>(BLEIdentity.create(identity, address));
    static_cast<void>(BLEIdentity.reset(identity, address));
    static_cast<void>(BLEIdentity.remove(identity));
    static_cast<void>(BLEAdvertisingLists.filterAcceptCapacity());
    static_cast<void>(BLEAdvertisingLists.resolvingCapacity());
    static_cast<void>(BLEAdvertisingLists.periodicAdvertiserCapacity());
    static_cast<void>(BLEAdvertisingLists.addFilterAccept(address));
    static_cast<void>(BLEAdvertisingLists.removeFilterAccept(address));
    static_cast<void>(BLEAdvertisingLists.clearFilterAccept());
    static_cast<void>(BLEAdvertisingLists.addPeriodicAdvertiser(address, 1U));
    static_cast<void>(BLEAdvertisingLists.removePeriodicAdvertiser(address, 1U));
    static_cast<void>(BLEAdvertisingLists.clearPeriodicAdvertisers());
    static_cast<void>(ead.configure(key, iv));
    static_cast<void>(ead.encrypt(plaintext, sizeof(plaintext), encrypted,
                                  sizeof(encrypted), encrypted_length));
    static_cast<void>(ead.decrypt(encrypted, encrypted_length, decrypted,
                                  sizeof(decrypted), decrypted_length));
    ead.clear();
    return 0;
}
