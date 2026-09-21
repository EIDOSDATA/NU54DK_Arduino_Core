# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
list(APPEND EXTRA_CONF_FILE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/zephyr/ble-security.conf"
)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m30_ble_pair_hil)

# @brief role과 IO capability를 현재 image의 고정 compile 계약으로 반영합니다.
zephyr_get(M30_PAIR_ROLE)
zephyr_get(M30_PAIR_CASE)
zephyr_get(M30_PAIR_IO)

target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityPairing.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityOob.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityBond.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityHid.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityBattery.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityDeviceInformation.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src"
)

if("${M30_PAIR_ROLE}" STREQUAL "central")
  target_compile_definitions(app PRIVATE NUCODE_M30_PAIR_CENTRAL=1)
elseif(NOT "${M30_PAIR_ROLE}" STREQUAL "peripheral")
  message(FATAL_ERROR "M30_PAIR_ROLE must be peripheral or central")
endif()

if("${M30_PAIR_CASE}" STREQUAL "0")
  set(M30_PAIR_CASE_NAME no_input_output)
  set(M30_PAIR_METHOD just_works)
elseif("${M30_PAIR_CASE}" STREQUAL "1")
  set(M30_PAIR_CASE_NAME display_keyboard)
  set(M30_PAIR_METHOD passkey_entry)
elseif("${M30_PAIR_CASE}" STREQUAL "2")
  set(M30_PAIR_CASE_NAME keyboard_display)
  set(M30_PAIR_METHOD passkey_entry)
elseif("${M30_PAIR_CASE}" STREQUAL "3")
  set(M30_PAIR_CASE_NAME display_yes_no)
  set(M30_PAIR_METHOD numeric_comparison)
elseif("${M30_PAIR_CASE}" STREQUAL "4")
  set(M30_PAIR_CASE_NAME keyboard_display_full)
  set(M30_PAIR_METHOD numeric_comparison)
else()
  message(FATAL_ERROR "M30_PAIR_CASE must be 0..4")
endif()

target_compile_definitions(app PRIVATE
  NUCODE_M30_PAIR_CASE=${M30_PAIR_CASE}
  NUCODE_M30_PAIR_IO=${M30_PAIR_IO}
  NUCODE_M30_PAIR_CASE_NAME="${M30_PAIR_CASE_NAME}"
  NUCODE_M30_PAIR_METHOD="${M30_PAIR_METHOD}"
)
