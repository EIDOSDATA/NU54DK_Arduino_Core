# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_dtm)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
execute_process(COMMAND git -C "${NUCODE_ROOT}" rev-parse HEAD
    OUTPUT_VARIABLE NUCODE_DIAGNOSTIC_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
set(identity_input "")
foreach(identity_file CMakeLists.txt Kconfig prj.conf hci.conf app.overlay src/main.c src/protocol.h)
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/${identity_file}" identity_hash)
    string(APPEND identity_input "${identity_file}:${identity_hash}\n")
endforeach()
string(SHA256 NUCODE_DIAGNOSTIC_SOURCE_HASH "${identity_input}")
target_sources(app PRIVATE src/main.c)
target_include_directories(app PRIVATE src)
target_compile_definitions(app PRIVATE
    NUCODE_DIAGNOSTIC_REVISION="${NUCODE_DIAGNOSTIC_REVISION}"
    NUCODE_DIAGNOSTIC_SOURCE_HASH="${NUCODE_DIAGNOSTIC_SOURCE_HASH}")
