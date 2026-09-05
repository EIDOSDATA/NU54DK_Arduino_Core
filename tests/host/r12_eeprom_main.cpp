/** @file @brief 실제 EEPROM의 record·실패·명시적 복구와 process 재시작을 검증합니다. */
#include <EEPROM.h>
#include <zephyr/settings/settings.h>
#include <zephyr/kernel.h>
#include <cassert>
#include <cstring>
#include <iostream>
int main(int argc, char **argv)
{
    assert(argc == 3);
    const char *scenario = argv[1];
    mock_settings_file = argv[2];
    if (std::strcmp(scenario, "corrupt") == 0)
    {
        const auto before = mock_read_record();
        assert(!EEPROM.begin(8) && EEPROM.lastError() == EEPROMError::corrupt);
        assert(mock_read_record() == before && mock_settings_saves == 0);
        assert(EEPROM.reset(8) && mock_settings_saves == 1);
        for (unsigned i = 0; i < 8; ++i)
        {
            assert(EEPROM.read(i) == 0xFF);
        }
        return 0;
    }
    if (std::strcmp(scenario, "init_failure") == 0)
    {
        mock_settings_init_error = -EIO;
        assert(!EEPROM.begin(8) && EEPROM.lastDriverError() == -EIO);
        mock_settings_init_error = 0;
    }
    if (std::strcmp(scenario, "load_failure") == 0)
    {
        mock_settings_load_error = -EIO;
        assert(!EEPROM.begin(8) && EEPROM.lastDriverError() == -EIO);
        mock_settings_load_error = 0;
    }
    if (std::strcmp(scenario, "short_load") == 0)
    {
        mock_short_load = true;
        assert(!EEPROM.begin(8) && EEPROM.lastError() == EEPROMError::corrupt);
        mock_short_load = false;
    }
    assert(EEPROM.begin(8));
    if (std::strcmp(scenario, "write") == 0)
    {
        for (unsigned i = 0; i < 8; ++i)
        {
            assert(EEPROM.read(i) == 0xFF);
            EEPROM.write(i, static_cast<std::uint8_t>(0xA0 + i));
        }
        assert(mock_settings_saves == 0);
        assert(EEPROM.commit() && mock_settings_saves == 1);
        EEPROM.update(0, 0xA0);
        assert(EEPROM.commit() && mock_settings_saves == 1);
    }
    else if (std::strcmp(scenario, "read") == 0 || std::strcmp(scenario, "resize") == 0)
    {
        for (unsigned i = 0; i < 8; ++i)
        {
            assert(EEPROM.read(i) == 0xA0 + i);
        }
        if (std::strcmp(scenario, "resize") == 0)
        {
            assert(EEPROM.begin(16) && EEPROM.length() == 16);
            for (unsigned i = 8; i < 16; ++i)
            {
                assert(EEPROM.read(i) == 0xFF);
            }
            assert(EEPROM.commit());
        }
    }
    else if (std::strcmp(scenario, "save_failure") == 0)
    {
        const auto before = mock_read_record();
        EEPROM.write(0, 0x55);
        mock_settings_save_error = -ENOSPC;
        assert(!EEPROM.commit() && EEPROM.lastError() == EEPROMError::no_space);
        assert(mock_read_record() == before && EEPROM.read(0) == 0x55);
        mock_settings_save_error = 0;
        assert(EEPROM.commit() && mock_settings_saves == 1);
    }
    else if (std::strcmp(scenario, "bounds") == 0)
    {
        EEPROM.write(-1, 1);
        assert(EEPROM.lastError() == EEPROMError::out_of_bounds);
        EEPROM.write(8, 1);
        assert(EEPROM.lastError() == EEPROMError::out_of_bounds);
        assert(!EEPROM.begin(0) && !EEPROM.begin(1025));
        mock_in_isr = true;
        assert(!EEPROM.commit() && EEPROM.lastError() == EEPROMError::invalid_context);
        mock_in_isr = false;
    }
    else
    {
        assert(std::strcmp(scenario, "init_failure") == 0 ||
               std::strcmp(scenario, "load_failure") == 0 ||
               std::strcmp(scenario, "short_load") == 0);
    }
    std::cout << "R12_EEPROM_PASS=" << scenario << '\n';
}
