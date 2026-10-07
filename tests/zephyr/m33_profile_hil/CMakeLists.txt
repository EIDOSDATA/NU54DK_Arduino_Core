# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.20.0)
# sysbuild 상위 cache의 역할을 Kconfig 병합 전에 읽습니다.
find_package(Zephyr REQUIRED COMPONENTS extensions basic_settings HINTS $ENV{ZEPHYR_BASE})
zephyr_get(M33_PROFILE_ROLE)
zephyr_get(M33_PROFILE_FAMILY)
zephyr_get(USE_CCACHE)
if(NOT M33_PROFILE_FAMILY)
    set(M33_PROFILE_FAMILY standard)
endif()
if(NOT M33_PROFILE_FAMILY MATCHES "^(standard|native)$")
    message(FATAL_ERROR "M33_PROFILE_FAMILY must be standard or native")
endif()
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
list(APPEND EXTRA_CONF_FILE "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/zephyr/ble-security.conf")
list(APPEND EXTRA_DTC_OVERLAY_FILE "${CMAKE_CURRENT_LIST_DIR}/app.overlay")
if(M33_PROFILE_FAMILY STREQUAL "native")
    list(APPEND EXTRA_CONF_FILE "${CMAKE_CURRENT_LIST_DIR}/native.conf")
    if(M33_PROFILE_ROLE MATCHES "^(client|watcher)$")
        list(APPEND EXTRA_CONF_FILE "${CMAKE_CURRENT_LIST_DIR}/native-client.conf")
    endif()
endif()
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m33_profile_hil)
if(NOT M33_PROFILE_ROLE MATCHES "^(server|client|watcher)$")
    message(FATAL_ERROR "M33_PROFILE_ROLE must be server, client or watcher")
endif()
execute_process(COMMAND git -C "${NUCODE_ROOT}" rev-parse HEAD
    OUTPUT_VARIABLE revision OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
file(GLOB gap_sources CONFIGURE_DEPENDS "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/*.cpp")
file(GLOB gatt_sources CONFIGURE_DEPENDS "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/*.cpp")
file(GLOB security_sources CONFIGURE_DEPENDS "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/security/*.cpp")
file(GLOB profile_sources CONFIGURE_DEPENDS "${NUCODE_ROOT}/libraries/NUCODE_BLE_Profiles/src/*.cpp")
target_sources(app PRIVATE src/main.cpp ${gap_sources} ${gatt_sources} ${security_sources} ${profile_sources}
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_ProfilesBackend.c")
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Security/src"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Profiles/src")
target_compile_definitions(app PRIVATE M33_PROFILE_CORE_REVISION="${revision}" M33_PROFILE_ROLE="${M33_PROFILE_ROLE}")
if(M33_PROFILE_ROLE STREQUAL "server")
    target_compile_definitions(app PRIVATE M33_PROFILE_SERVER=1)
elseif(M33_PROFILE_ROLE STREQUAL "watcher")
    if(M33_PROFILE_FAMILY STREQUAL "native")
        target_compile_definitions(app PRIVATE M33_PROFILE_SECOND_PEER=1)
    else()
        target_compile_definitions(app PRIVATE M33_PROFILE_WATCHER=1)
    endif()
endif()
if(M33_PROFILE_FAMILY STREQUAL "native")
    target_compile_definitions(app PRIVATE M33_PROFILE_NATIVE=1)
endif()
