# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_mesh_dfu_hil)

zephyr_get(M32_MDFU_ROLE)
zephyr_get(M32_MDFU_CANDIDATE_SHA256)
zephyr_get(M32_MDFU_CANDIDATE_SIZE)

set(m32_mdfu_roles distributor target_a target_b candidate)
if(NOT M32_MDFU_ROLE IN_LIST m32_mdfu_roles)
  message(FATAL_ERROR
    "M32_MDFU_ROLE must be distributor, target_a, target_b, or candidate")
endif()

execute_process(
  COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
  RESULT_VARIABLE revision_result
  OUTPUT_VARIABLE M32_MDFU_CORE_REVISION
  ERROR_VARIABLE revision_error
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_MDFU_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_MDFU_CORE_REVISION MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "M32 MDFU Core revision query failed: ${revision_error}")
endif()

if(NOT "${M32_MDFU_ROLE}" STREQUAL "candidate")
  string(LENGTH "${M32_MDFU_CANDIDATE_SHA256}" candidate_digest_length)
  if(NOT candidate_digest_length EQUAL 64 OR
     NOT M32_MDFU_CANDIDATE_SHA256 MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32_MDFU_CANDIDATE_SHA256 must be 64 lowercase hex digits")
  endif()
  if(NOT M32_MDFU_CANDIDATE_SIZE MATCHES "^[1-9][0-9]*$")
    message(FATAL_ERROR "M32_MDFU_CANDIDATE_SIZE must be a positive integer")
  endif()
endif()

if("${M32_MDFU_ROLE}" STREQUAL "candidate")
  target_sources(app PRIVATE src/candidate.cpp)
else()
  target_sources(app PRIVATE
    src/main.cpp
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh_Composition.c"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh_Update/src/NUCODE_BLE_Mesh_Update.cpp"
  )
  target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh_Update/src"
  )
endif()
target_compile_definitions(app PRIVATE
  M32_MDFU_CORE_REVISION="${M32_MDFU_CORE_REVISION}"
  M32_MDFU_ROLE_NAME="${M32_MDFU_ROLE}"
)

if("${M32_MDFU_ROLE}" STREQUAL "distributor")
  target_compile_definitions(app PRIVATE NUCODE_M32_MDFU_DISTRIBUTOR=1)
elseif("${M32_MDFU_ROLE}" STREQUAL "target_a")
  target_compile_definitions(app PRIVATE NUCODE_M32_MDFU_TARGET_A=1)
elseif("${M32_MDFU_ROLE}" STREQUAL "target_b")
  target_compile_definitions(app PRIVATE NUCODE_M32_MDFU_TARGET_B=1)
else()
  target_compile_definitions(app PRIVATE NUCODE_M32_MDFU_CANDIDATE=1)
endif()

if(NOT "${M32_MDFU_ROLE}" STREQUAL "candidate")
  target_compile_definitions(app PRIVATE
    M32_MDFU_CANDIDATE_SHA256="${M32_MDFU_CANDIDATE_SHA256}"
    M32_MDFU_CANDIDATE_SIZE=${M32_MDFU_CANDIDATE_SIZE}
  )
endif()
