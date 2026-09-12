# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m28_ble_capability)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
get_filename_component(NCS_ROOT "${ZEPHYR_BASE}/.." ABSOLUTE)

# @brief capability image에 결합할 exact Git revision을 읽습니다.
function(m28_git_revision repository output_name)
  execute_process(
    COMMAND git -C "${repository}" rev-parse HEAD
    RESULT_VARIABLE command_result
    OUTPUT_VARIABLE revision
    ERROR_VARIABLE command_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  string(LENGTH "${revision}" revision_length)
  if(NOT command_result EQUAL 0 OR
     NOT revision_length EQUAL 40 OR
     NOT revision MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M28 revision query failed for ${repository}: ${command_error}")
  endif()
  set(${output_name} "${revision}" PARENT_SCOPE)
endfunction()

m28_git_revision("${NUCODE_ROOT}" M28_CORE_REVISION)
m28_git_revision("${NUCODE_ROOT}/board_package/NU54DK_Zephyr_DTS" M28_BOARD_REVISION)
m28_git_revision("${NCS_ROOT}/nrf" M28_NCS_REVISION)
m28_git_revision("${NCS_ROOT}/zephyr" M28_ZEPHYR_REVISION)

target_sources(app PRIVATE src/main.cpp)
target_compile_definitions(app PRIVATE
  M28_CORE_REVISION=\"${M28_CORE_REVISION}\"
  M28_BOARD_REVISION=\"${M28_BOARD_REVISION}\"
  M28_NCS_REVISION=\"${M28_NCS_REVISION}\"
  M28_ZEPHYR_REVISION=\"${M28_ZEPHYR_REVISION}\"
)
