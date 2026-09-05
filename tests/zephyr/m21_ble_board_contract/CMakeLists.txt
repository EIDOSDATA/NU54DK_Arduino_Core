# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
list(APPEND EXTRA_CONF_FILE
  "${NUCODE_ROOT}/libraries/NUCODE_NU54DK/zephyr/board-system.conf"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/zephyr/ble-security.conf"
)
list(APPEND DTC_OVERLAY_FILE
  "${NUCODE_ROOT}/variants/nu54dk/profiles/ble/app.overlay"
  "${NUCODE_ROOT}/libraries/NUCODE_NU54DK/zephyr/board-system.overlay"
)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m21_ble_board_contract)

target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_ROOT}/libraries/NUCODE_NU54DK/src/NUCODE_NU54DK.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityPairing.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityBond.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityHid.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityBattery.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityDeviceInformation.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_NU54DK/src"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src"
)
