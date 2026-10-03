# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_esb_hil)

zephyr_get(M32_ESB_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

execute_process(
    COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
    RESULT_VARIABLE revision_result
    OUTPUT_VARIABLE M32_ESB_CORE_REVISION
    ERROR_VARIABLE revision_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_ESB_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_ESB_CORE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32 W09 ESB Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE
    src/main.cpp
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_ESB/src/NUCODE_Radio_ESB.cpp"
)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_ESB/src"
)
target_compile_definitions(app PRIVATE
    M32_ESB_CORE_REVISION="${M32_ESB_CORE_REVISION}"
)

if("${M32_ESB_ROLE}" STREQUAL "ptx")
    target_compile_definitions(app PRIVATE NUCODE_M32_ESB_PTX=1)
elseif(NOT "${M32_ESB_ROLE}" STREQUAL "prx")
    message(FATAL_ERROR "M32_ESB_ROLE must be ptx or prx")
endif()
