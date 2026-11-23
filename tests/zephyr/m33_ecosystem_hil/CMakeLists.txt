# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.20.0)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
list(APPEND EXTRA_CONF_FILE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/zephyr/ble-security.conf")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_companion_hil)
zephyr_get(COMPANION_ROLE)
execute_process(COMMAND git -C "${NUCODE_ROOT}" rev-parse HEAD OUTPUT_VARIABLE CORE_REVISION
                OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
target_compile_definitions(app PRIVATE COMPANION_CORE_REVISION="${CORE_REVISION}")
file(GLOB_RECURSE IDENTITY_FILES RELATIVE "${NUCODE_ROOT}"
    "${CMAKE_CURRENT_LIST_DIR}/*.cpp" "${CMAKE_CURRENT_LIST_DIR}/*.conf" "${CMAKE_CURRENT_LIST_DIR}/*.overlay"
    "${CMAKE_CURRENT_LIST_DIR}/CMakeLists.txt"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/*.cpp" "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/*.h"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Companion/src/*.cpp" "${NUCODE_ROOT}/libraries/NUCODE_BLE_Companion/src/*.h"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/*.c"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/*.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/*.h")
list(SORT IDENTITY_FILES)
set(IDENTITY_SOURCE "")
foreach(IDENTITY_FILE IN LISTS IDENTITY_FILES)
    file(SHA256 "${NUCODE_ROOT}/${IDENTITY_FILE}" IDENTITY_SHA)
    string(APPEND IDENTITY_SOURCE "${IDENTITY_FILE}:${IDENTITY_SHA}\n")
endforeach()
string(SHA256 SOURCE_SHA "${IDENTITY_SOURCE}")
target_compile_definitions(app PRIVATE COMPANION_FIRMWARE_IDENTITY="${CORE_REVISION}${SOURCE_SHA}")
if(COMPANION_ROLE STREQUAL "peer")
    target_compile_definitions(app PRIVATE COMPANION_PEER=1)
elseif(NOT COMPANION_ROLE STREQUAL "client")
    message(FATAL_ERROR "COMPANION_ROLE must be client or peer")
endif()
set(BLE "${NUCODE_ROOT}/libraries/NUCODE_BLE/src")
set(COMPANION "${NUCODE_ROOT}/libraries/NUCODE_BLE_Companion/src")
set(SECURITY "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src")
file(GLOB SECURITY_SOURCES CONFIGURE_DEPENDS "${SECURITY}/internal/security/*.cpp")
target_include_directories(app PRIVATE "${BLE}" "${COMPANION}" "${SECURITY}")
target_sources(app PRIVATE src/main.cpp "${COMPANION}/NUCODE_BLE_Companion.cpp"
    "${COMPANION}/NUCODE_BLE_CompanionCodec.cpp"
    "${SECURITY}/NUCODE_BLE_Security.cpp" ${SECURITY_SOURCES}
    "${SECURITY}/internal/NUCODE_BLE_HidsBackend.c"
    "${SECURITY}/internal/NUCODE_BLE_ProfilesBackend.c"
    "${BLE}/NUCODE_BLE_GAP.cpp" "${BLE}/NUCODE_BLE_GATT.cpp"
    "${BLE}/internal/NUCODE_BLE_Stack.cpp"
    "${BLE}/internal/gap/GapValues.cpp" "${BLE}/internal/gap/GapAdvertising.cpp"
    "${BLE}/internal/gap/GapExtendedAdvertising.cpp" "${BLE}/internal/gap/GapPeriodicAdvertising.cpp"
    "${BLE}/internal/gap/GapPawr.cpp" "${BLE}/internal/gap/GapScanning.cpp"
    "${BLE}/internal/gap/GapConnection.cpp" "${BLE}/internal/gatt/GattDatabase.cpp"
    "${BLE}/internal/gatt/GattCache.cpp" "${BLE}/internal/gatt/GattServer.cpp"
    "${BLE}/internal/gatt/GattClient.cpp")
