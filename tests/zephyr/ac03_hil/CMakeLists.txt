# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_ac03_hil)

get_filename_component(NUCODE_CORE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_CORE_ROOT}/libraries/EEPROM/src/EEPROM.cpp"
  "${NUCODE_CORE_ROOT}/libraries/EEPROM/src/internal/EEPROMRecord.cpp"
  "${NUCODE_CORE_ROOT}/libraries/EEPROM/src/internal/EEPROMSettings.cpp"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src/FS.cpp"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src/internal/FilePaths.cpp"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src/internal/FileSlots.cpp"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src/internal/File.cpp"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src/LittleFS.cpp"
)

target_include_directories(app PRIVATE
  "${NUCODE_CORE_ROOT}/libraries/EEPROM/src"
  "${NUCODE_CORE_ROOT}/libraries/LittleFS/src"
)
