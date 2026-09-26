# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
list(APPEND EXTRA_CONF_FILE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/zephyr/ble-security.conf"
)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m30_ble_profile_hil)

zephyr_get(M30_PROFILE_ROLE)

# @brief HIL protocol을 exact source revision에 결합합니다.
execute_process(
  COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
  RESULT_VARIABLE revision_result
  OUTPUT_VARIABLE M30_PROFILE_CORE_REVISION
  ERROR_VARIABLE revision_error
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M30_PROFILE_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M30_PROFILE_CORE_REVISION MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "M30 profile Core revision query failed: ${revision_error}")
endif()

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
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/SecurityProfiles.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_ProfilesBackend.c"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src"
)
target_compile_definitions(app PRIVATE
  M30_PROFILE_CORE_REVISION="${M30_PROFILE_CORE_REVISION}"
)

if("${M30_PROFILE_ROLE}" STREQUAL "central")
  target_compile_definitions(app PRIVATE NUCODE_M30_PROFILE_CENTRAL=1)
elseif(NOT "${M30_PROFILE_ROLE}" STREQUAL "peripheral")
  message(FATAL_ERROR "M30_PROFILE_ROLE must be peripheral or central")
endif()
