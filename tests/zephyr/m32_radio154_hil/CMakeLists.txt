# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_radio154_hil)

zephyr_get(M32_RADIO154_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

execute_process(
    COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
    RESULT_VARIABLE revision_result
    OUTPUT_VARIABLE M32_RADIO154_CORE_REVISION
    ERROR_VARIABLE revision_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_RADIO154_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_RADIO154_CORE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32 W09 IEEE 802.15.4 Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE
    src/main.cpp
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_IEEE802154/src/NUCODE_Radio_IEEE802154.cpp"
)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_IEEE802154/src"
)
target_compile_definitions(app PRIVATE
    M32_RADIO154_CORE_REVISION="${M32_RADIO154_CORE_REVISION}"
)

if("${M32_RADIO154_ROLE}" STREQUAL "transmitter")
    target_compile_definitions(app PRIVATE NUCODE_M32_RADIO154_TRANSMITTER=1)
elseif(NOT "${M32_RADIO154_ROLE}" STREQUAL "receiver")
    message(FATAL_ERROR "M32_RADIO154_ROLE must be transmitter or receiver")
endif()
