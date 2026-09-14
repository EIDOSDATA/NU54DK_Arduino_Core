# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m30_ble_dfu_hil)

# @brief 일반 빌드와 sysbuild에서 전달된 역할 변수를 동일하게 읽습니다.
zephyr_get(M30_DFU_ROLE)
zephyr_get(M30_DFU_AUTO_CONFIRM)
zephyr_get(M30_DFU_POWER_HIL)

if(NOT "${M30_DFU_ROLE}" STREQUAL "peripheral" AND
   NOT "${M30_DFU_ROLE}" STREQUAL "central")
  message(FATAL_ERROR "M30_DFU_ROLE must be peripheral or central")
endif()

# @brief HIL protocol을 exact source revision에 결합합니다.
execute_process(
  COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
  RESULT_VARIABLE revision_result
  OUTPUT_VARIABLE M30_DFU_CORE_REVISION
  ERROR_VARIABLE revision_error
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M30_DFU_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M30_DFU_CORE_REVISION MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "M30 DFU Core revision query failed: ${revision_error}")
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
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src"
)
target_compile_definitions(app PRIVATE
  M30_DFU_CORE_REVISION="${M30_DFU_CORE_REVISION}"
)

if("${M30_DFU_ROLE}" STREQUAL "peripheral")
  target_sources(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_DFU/src/NUCODE_BLE_DFU.cpp"
  )
  target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_DFU/src"
  )
  target_compile_definitions(app PRIVATE NUCODE_M30_DFU_PERIPHERAL=1)
  if("${M30_DFU_AUTO_CONFIRM}" STREQUAL "0")
    target_compile_definitions(app PRIVATE NUCODE_M30_DFU_AUTO_CONFIRM=0)
  else()
    target_compile_definitions(app PRIVATE NUCODE_M30_DFU_AUTO_CONFIRM=1)
  endif()
  if("${M30_DFU_POWER_HIL}" STREQUAL "1")
    target_compile_definitions(app PRIVATE NUCODE_M30_DFU_POWER_HIL=1)
  endif()
endif()
