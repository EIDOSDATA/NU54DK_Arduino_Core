# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(m31_iso_bis_hil)

zephyr_get(M31_BIS_ROLE)
if(NOT "${M31_BIS_ROLE}" STREQUAL "source" AND
   NOT "${M31_BIS_ROLE}" STREQUAL "receiver")
    message(FATAL_ERROR "M31_BIS_ROLE must be source or receiver")
endif()

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
get_filename_component(NCS_ROOT "${ZEPHYR_BASE}/.." ABSOLUTE)

# @brief 실행 image의 고정 checkout 네 개를 직접 보고합니다.
function(m31_bis_revision repository output_name)
    execute_process(
        COMMAND git -c "safe.directory=${repository}" -C "${repository}" rev-parse HEAD
        RESULT_VARIABLE command_result
        OUTPUT_VARIABLE revision
        ERROR_VARIABLE command_error
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    string(LENGTH "${revision}" revision_length)
    if(NOT command_result EQUAL 0 OR
       NOT revision_length EQUAL 40 OR
       NOT revision MATCHES "^[0-9a-f]+$")
        message(FATAL_ERROR "M31 BIS revision query failed: ${command_error}")
    endif()
    set(${output_name} "${revision}" PARENT_SCOPE)
endfunction()

m31_bis_revision("${NUCODE_ROOT}" M31_CORE_REVISION)
m31_bis_revision("${NUCODE_ROOT}/board_package/NU54DK_Zephyr_DTS" M31_BOARD_REVISION)
m31_bis_revision("${NCS_ROOT}/nrf" M31_NCS_REVISION)
m31_bis_revision("${NCS_ROOT}/zephyr" M31_ZEPHYR_REVISION)

target_compile_definitions(app PRIVATE
    M31_BIS_ROLE="${M31_BIS_ROLE}"
    M31_CORE_REVISION="${M31_CORE_REVISION}"
    M31_BOARD_REVISION="${M31_BOARD_REVISION}"
    M31_NCS_REVISION="${M31_NCS_REVISION}"
    M31_ZEPHYR_REVISION="${M31_ZEPHYR_REVISION}"
)
target_sources(app PRIVATE src/main.cpp)
