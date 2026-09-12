# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m28_ble_3board_hil)

# @brief Twister의 시험·역할 cache 변수를 한 image의 compile 정의로 고정합니다.
zephyr_get(M28_B3_TEST)
zephyr_get(M28_B3_ROLE)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
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
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattDatabase.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
)

if("${M28_B3_ROLE}" STREQUAL "peripheral")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_PERIPHERAL=1)
elseif("${M28_B3_ROLE}" STREQUAL "mixed")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_MIXED=1)
elseif("${M28_B3_ROLE}" STREQUAL "central")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_CENTRAL=1)
else()
  message(FATAL_ERROR "M28_B3_ROLE must be peripheral, mixed, or central")
endif()

if("${M28_B3_TEST}" STREQUAL "link")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_TEST_LINK=1)
elseif("${M28_B3_TEST}" STREQUAL "periodic")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_TEST_PERIODIC=1)
elseif("${M28_B3_TEST}" STREQUAL "control")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_TEST_CONTROL=1)
elseif("${M28_B3_TEST}" STREQUAL "soak")
  target_compile_definitions(app PRIVATE NUCODE_M28_B3_TEST_SOAK=1)
else()
  message(FATAL_ERROR "M28_B3_TEST must be link, periodic, control, or soak")
endif()
