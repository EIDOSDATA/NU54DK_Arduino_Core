/** @file @brief M32-W04 광고·identity·list·EAD 자원 경계를 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>

#include <array>
#include <cstring>
#include <iostream>

using namespace nucode::ble;

/** @brief 독립 SID의 세 advertising set과 초과·stale 경계를 검증합니다. */
void testMultipleSets()
{
    std::array<BLEAdvertisingSetHandle, 3> sets{};
    for (std::size_t index = 0U; index < sets.size(); ++index)
    {
        BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = static_cast<std::uint8_t>(index);
        assert(BLEExtendedAdvertising.create(parameters, sets[index]));
        assert(BLEExtendedAdvertising.start(sets[index]));
    }
    BLEExtendedAdvertisingParameters overflow_parameters{};
    BLEAdvertisingSetHandle overflow;
    assert(!BLEExtendedAdvertising.create(overflow_parameters, overflow));
    assert(BLEDevice.lastError() == BLEError::schema_full);

    bt_le_ext_adv_sent_info sent{};
    mock_ext_advertising_callbacks->sent(&mock_ext_advertisers[1], &sent);
    assert(BLEExtendedAdvertising.running(sets[0]));
    assert(!BLEExtendedAdvertising.running(sets[1]));
    assert(BLEExtendedAdvertising.running(sets[2]));
    assert(BLEExtendedAdvertising.remove(sets[1]));

    BLEAdvertisingSetHandle replacement;
    assert(BLEExtendedAdvertising.create(overflow_parameters, replacement));
    assert(replacement != sets[1]);
    mock_ext_advertising_callbacks->sent(&mock_ext_advertisers[1], &sent);
    assert(BLEExtendedAdvertising.exists(replacement));
}

/** @brief directed·coding·identity 조합을 controller 호출 전에 거부합니다. */
void testParameterGuards()
{
    BLEAdvertisingSetHandle handle;
    BLEExtendedAdvertisingParameters invalid{};
    invalid.identity = 3U;
    assert(!BLEExtendedAdvertising.create(invalid, handle));

    invalid = {};
    invalid.sid = 16U;
    assert(!BLEExtendedAdvertising.create(invalid, handle));

    invalid = {};
    invalid.coded = true;
    invalid.secondary_1m = true;
    assert(!BLEExtendedAdvertising.create(invalid, handle));

    invalid = {};
    invalid.coding = BLEAdvertisingCoding::s2;
    assert(!BLEExtendedAdvertising.create(invalid, handle));

    invalid = {};
    invalid.directed_peer = BLEAddress(
        "C0:DE:00:00:00:01", BLEAddress::Type::random_address);
    invalid.connectable = true;
    assert(!BLEExtendedAdvertising.create(invalid, handle));

    BLEExtendedAdvertisingParameters coded{};
    coded.coded = true;
    coded.coding = BLEAdvertisingCoding::s8;
    assert(BLEExtendedAdvertising.create(coded, handle));
    assert((mock_ext_advertising_options &
            BT_LE_ADV_OPT_REQUIRE_S8_CODING) != 0U);
}

/** @brief identity 사용 중 삭제와 controller list lifecycle을 검증합니다. */
void testIdentitiesAndLists()
{
    std::uint8_t identity_one = 0xffU;
    std::uint8_t identity_two = 0xffU;
    BLEAddress address_one;
    BLEAddress address_two;
    assert(BLEIdentity.count() == 1U);
    assert(BLEIdentity.create(identity_one, address_one));
    assert(BLEIdentity.create(identity_two, address_two));
    assert(identity_one == 1U && identity_two == 2U);
    assert(BLEIdentity.count() == 3U);
    assert(!BLEIdentity.create(identity_two, address_two));
    assert(BLEDevice.lastError() == BLEError::schema_full);

    BLEExtendedAdvertisingParameters parameters{};
    parameters.identity = identity_one;
    BLEAdvertisingSetHandle set;
    assert(BLEExtendedAdvertising.create(parameters, set));
    assert(!BLEIdentity.remove(identity_one));
    assert(BLEDevice.lastError() == BLEError::busy);
    assert(BLEExtendedAdvertising.remove(set));
    assert(BLEIdentity.remove(identity_one));
    assert(BLEIdentity.reset(identity_one, address_one));

    const BLEAddress peer(
        "C0:DE:00:00:00:03", BLEAddress::Type::random_address);
    assert(BLEAdvertisingLists.clearFilterAccept());
    assert(BLEAdvertisingLists.addFilterAccept(peer));
    assert(mock_filter_accept_count == 1U);
    assert(BLEAdvertisingLists.removeFilterAccept(peer));
    assert(mock_filter_accept_count == 0U);
    assert(BLEAdvertisingLists.addPeriodicAdvertiser(peer, 4U));
    assert(mock_periodic_advertiser_count == 1U);
    assert(!BLEAdvertisingLists.addPeriodicAdvertiser(peer, 16U));
    assert(BLEAdvertisingLists.clearPeriodicAdvertisers());
}

/** @brief EAD 인증·key/IV·replay·변조 경계를 검증합니다. */
void testEncryptedAdvertising()
{
    std::array<std::uint8_t, EncryptedAdvertisingData::session_key_length> key{};
    std::array<std::uint8_t,
               EncryptedAdvertisingData::initialization_vector_length> iv{};
    for (std::size_t index = 0U; index < key.size(); ++index)
    {
        key[index] = static_cast<std::uint8_t>(index + 1U);
    }
    for (std::size_t index = 0U; index < iv.size(); ++index)
    {
        iv[index] = static_cast<std::uint8_t>(0xa0U + index);
    }
    const std::array<std::uint8_t, 4> plaintext = {3U, 0xffU, 0x54U, 0x32U};
    std::array<std::uint8_t, 32> encrypted{};
    std::array<std::uint8_t, 32> decrypted{};
    std::size_t encrypted_length = 0U;
    std::size_t plaintext_length = 0U;
    EncryptedAdvertisingData ead;
    assert(ead.configure(key.data(), iv.data()));
    assert(ead.encrypt(plaintext.data(), plaintext.size(), encrypted.data(),
                       encrypted.size(), encrypted_length));
    assert(ead.decrypt(encrypted.data(), encrypted_length, decrypted.data(),
                       decrypted.size(), plaintext_length));
    assert(plaintext_length == plaintext.size());
    assert(std::memcmp(plaintext.data(), decrypted.data(), plaintext.size()) == 0);
    assert(!ead.decrypt(encrypted.data(), encrypted_length, decrypted.data(),
                        decrypted.size(), plaintext_length));
    assert(BLEDevice.lastError() == BLEError::duplicate);

    assert(ead.encrypt(plaintext.data(), plaintext.size(), encrypted.data(),
                       encrypted.size(), encrypted_length));
    encrypted[encrypted_length - 1U] ^= 0x01U;
    assert(!ead.decrypt(encrypted.data(), encrypted_length, decrypted.data(),
                        decrypted.size(), plaintext_length));
    assert(BLEDevice.lastError() == BLEError::driver_error);

    EncryptedAdvertisingData wrong_key;
    key[0] ^= 0x01U;
    assert(wrong_key.configure(key.data(), iv.data()));
    encrypted[encrypted_length - 1U] ^= 0x01U;
    assert(!wrong_key.decrypt(encrypted.data(), encrypted_length, decrypted.data(),
                              decrypted.size(), plaintext_length));

    EncryptedAdvertisingData wrong_iv;
    key[0] ^= 0x01U;
    iv[0] ^= 0x01U;
    assert(wrong_iv.configure(key.data(), iv.data()));
    assert(!wrong_iv.decrypt(encrypted.data(), encrypted_length, decrypted.data(),
                             decrypted.size(), plaintext_length));
}

/** @brief 두 periodic sync의 독립 generation과 초과 자원을 검증합니다. */
void testMultipleSyncs()
{
    const std::array<BLEAddress, 3> addresses = {
        BLEAddress("C0:DE:00:00:00:11", BLEAddress::Type::random_address),
        BLEAddress("C0:DE:00:00:00:12", BLEAddress::Type::random_address),
        BLEAddress("C0:DE:00:00:00:13", BLEAddress::Type::random_address),
    };
    BLEPeriodicSyncHandle first;
    BLEPeriodicSyncHandle second;
    BLEPeriodicSyncHandle overflow;
    assert(BLEPeriodicAdvertising.createSync(addresses[0], 1U, first));
    assert(BLEPeriodicAdvertising.createSync(addresses[1], 2U, second));
    assert(first != second);
    assert(!BLEPeriodicAdvertising.createSync(addresses[2], 3U, overflow));
    assert(BLEDevice.lastError() == BLEError::schema_full);

    const bt_addr_le_t first_address{
        BT_ADDR_LE_RANDOM, {{0x11U, 0U, 0U, 0U, 0xdeU, 0xc0U}}};
    const bt_addr_le_t second_address{
        BT_ADDR_LE_RANDOM, {{0x12U, 0U, 0U, 0U, 0xdeU, 0xc0U}}};
    bt_le_per_adv_sync_synced_info first_info{
        &first_address, 1U, 80U, BT_GAP_LE_PHY_1M, true, 0U, nullptr};
    bt_le_per_adv_sync_synced_info second_info{
        &second_address, 2U, 80U, BT_GAP_LE_PHY_1M, true, 0U, nullptr};
    mock_periodic_sync_callbacks->synced(&mock_periodic_syncs[0], &first_info);
    mock_periodic_sync_callbacks->synced(&mock_periodic_syncs[1], &second_info);
    assert(BLEPeriodicAdvertising.synchronized(first));
    assert(BLEPeriodicAdvertising.synchronized(second));
    assert(BLEPeriodicAdvertising.deleteSync(first));
    assert(!BLEPeriodicAdvertising.exists(first));
    assert(BLEPeriodicAdvertising.exists(second));
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    assert(BLEDevice.begin("m32-w04"));
    const char *const scenario = argv[1];
    if (std::strcmp(scenario, "multiple_sets") == 0)
    {
        testMultipleSets();
    }
    else if (std::strcmp(scenario, "parameter_guards") == 0)
    {
        testParameterGuards();
    }
    else if (std::strcmp(scenario, "identities_lists") == 0)
    {
        testIdentitiesAndLists();
    }
    else if (std::strcmp(scenario, "ead_negative") == 0)
    {
        testEncryptedAdvertising();
    }
    else if (std::strcmp(scenario, "multiple_syncs") == 0)
    {
        testMultipleSyncs();
    }
    else
    {
        assert(false);
    }
    BLEDevice.end();
    std::cout << "M32_W04_HOST_PASS=" << scenario << '\n';
}
